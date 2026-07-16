from __future__ import annotations

import itertools
from typing import Any, cast
from uuid import UUID

import re2

from components.rtg.diagnostics import rtg_diagnostic
from components.rtg.graph.protocol import (
    JsonObject,
    JsonValue,
    RtgAnchor,
    RtgDataObject,
    RtgGraphReadView,
)
from components.rtg.query.json_values import (
    canonical_json_key,
    json_number_decimal,
    json_value_equal,
)
from components.rtg.query.protocol import (
    RtgQueryBindingRow,
    RtgQueryDataRequirement,
    RtgQueryDiagnostic,
    RtgQueryEngine,
    RtgQueryLinkRequirement,
    RtgQueryOptions,
    RtgQueryOrderBy,
    RtgQueryPropertyPredicate,
    RtgQueryResult,
    RtgQueryReturnRow,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    RtgQueryUnsupported,
)

_LIVE_FILTERS = {"all", "live", "non_live"}
_OPERATORS = {
    "exists",
    "equals",
    "not_equals",
    "lt",
    "lte",
    "gt",
    "gte",
    "contains",
    "in",
    "substring",
    "regex",
}


class SimpleRtgQueryEngine(RtgQueryEngine):
    """Stateless query engine over public RTG graph read contracts."""

    def execute(
        self,
        graph: RtgGraphReadView,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        options = query_options or RtgQueryOptions()
        _validate_options(options)
        _validate_spec(query_spec)
        if query_spec.return_spec.aggregations and options.distinct_rows:
            raise _invalid(
                "query_options.distinct_rows cannot be combined with aggregation",
                path="query_options.distinct_rows",
                remedy="Disable distinct_rows when return_spec.aggregations is present.",
            )
        _validate_order_by_against_spec(query_spec, options)

        diagnostics: list[RtgQueryDiagnostic] = []
        bucket_candidates = {
            bucket.name: tuple(
                anchor
                for type_key in bucket.anchor_type_keys
                for anchor in graph.list_by_type(type_key).objects
                if isinstance(anchor, RtgAnchor) and _matches_live(anchor, options)
            )
            for bucket in query_spec.anchor_buckets
        }
        if query_spec.diagnostic_options.include_non_fatal:
            for bucket_name, candidates in bucket_candidates.items():
                if not candidates:
                    diagnostics.append(
                        RtgQueryDiagnostic(
                            severity="warning",
                            code="query.no_bucket_matches",
                            message=f"Anchor bucket {bucket_name!r} matched no anchors.",
                            suggestion=_discovery_suggestion(query_spec),
                            affected_terms=(bucket_name,),
                        )
                    )

        bucket_names = tuple(bucket.name for bucket in query_spec.anchor_buckets)
        optional_target_buckets = {
            requirement.target_bucket
            for requirement in query_spec.link_requirements
            if not requirement.required
        }
        bindings: list[RtgQueryBindingRow] = []
        product_candidates = tuple(
            bucket_candidates[name]
            if bucket_candidates[name] or name not in optional_target_buckets
            else (None,)
            for name in bucket_names
        )
        for anchor_values in itertools.product(*product_candidates):
            anchor_binding = {
                name: anchor.uuid
                for name, anchor in zip(bucket_names, anchor_values, strict=True)
                if anchor is not None and anchor.uuid is not None
            }
            if not anchor_binding:
                continue
            bindings.append(RtgQueryBindingRow(row_index=0, anchors=anchor_binding))
        for link_requirement in query_spec.link_requirements:
            bindings = _expand_link_requirement(graph, options, bindings, link_requirement)
            if not bindings:
                break
        for data_requirement in query_spec.data_requirements:
            bindings = _expand_data_requirement(graph, options, bindings, data_requirement)
            if not bindings:
                break

        ordered = sorted(bindings, key=lambda row: _row_sort_key(row, query_spec))
        indexed = tuple(
            RtgQueryBindingRow(
                row_index=index,
                anchors=row.anchors,
                links=row.links,
                data_objects=row.data_objects,
            )
            for index, row in enumerate(ordered)
        )
        returns = tuple(_shape_return_row(graph, query_spec, row) for row in indexed)
        if options.order_by:
            indexed, returns = _apply_return_ordering(indexed, returns, options.order_by)
        diagnostics.extend(_return_property_diagnostics(query_spec, indexed, returns))
        if query_spec.return_spec.aggregations:
            aggregation_rows = _aggregate_rows(indexed, returns, query_spec)
            total = len(aggregation_rows)
            sliced_aggregations, next_offset = _slice_rows(aggregation_rows, options)
            indexed_aggregations = [
                {"row_index": index, **row} for index, row in enumerate(sliced_aggregations)
            ]
            return RtgQueryResult(
                bindings=(),
                returns=(),
                diagnostics=tuple(diagnostics),
                aggregations=tuple(indexed_aggregations),
                total_row_count=total,
                returned_row_count=len(indexed_aggregations),
                next_offset=next_offset,
            )
        pairs = list(zip(indexed, returns, strict=True))
        if options.distinct_rows:
            pairs = _distinct_return_pairs(pairs)
        total = len(pairs)
        sliced_pairs, next_offset = _slice_rows(pairs, options)
        final_bindings, final_returns = _reindex_pairs(sliced_pairs)
        return RtgQueryResult(
            bindings=final_bindings,
            returns=final_returns,
            diagnostics=tuple(diagnostics),
            total_row_count=total,
            returned_row_count=len(final_returns),
            next_offset=next_offset,
        )


def _expand_link_requirement(
    graph: RtgGraphReadView,
    options: RtgQueryOptions,
    rows: list[RtgQueryBindingRow],
    requirement: RtgQueryLinkRequirement,
) -> list[RtgQueryBindingRow]:
    if not requirement.required:
        return _expand_optional_link_requirement(graph, options, rows, requirement)
    expanded: list[RtgQueryBindingRow] = []
    for row in rows:
        source_uuid = row.anchors.get(requirement.source_bucket)
        target_uuid = row.anchors.get(requirement.target_bucket)
        if source_uuid is None or target_uuid is None:
            continue
        matches = [
            link
            for link in graph.list_incident_links(source_uuid, "source").links
            if link.target_uuid == target_uuid
            and link.type in requirement.link_type_keys
            and _matches_live(link, options)
        ]
        for link in sorted(matches, key=lambda item: str(item.uuid)):
            if link.uuid is None:
                continue
            expanded.append(
                RtgQueryBindingRow(
                    row_index=0,
                    anchors=row.anchors,
                    links={**row.links, requirement.name: link.uuid},
                    data_objects=row.data_objects,
                )
            )
    return _dedupe_binding_rows(expanded)


def _expand_optional_link_requirement(
    graph: RtgGraphReadView,
    options: RtgQueryOptions,
    rows: list[RtgQueryBindingRow],
    requirement: RtgQueryLinkRequirement,
) -> list[RtgQueryBindingRow]:
    grouped: dict[
        tuple[tuple[tuple[str, UUID], ...], ...],
        tuple[RtgQueryBindingRow, list[RtgQueryBindingRow]],
    ] = {}
    for row in rows:
        source_uuid = row.anchors.get(requirement.source_bucket)
        unbound_anchors = dict(row.anchors)
        unbound_anchors.pop(requirement.target_bucket, None)
        unbound = RtgQueryBindingRow(
            row_index=0,
            anchors=unbound_anchors,
            links=row.links,
            data_objects=row.data_objects,
        )
        key = (
            tuple(sorted(unbound.anchors.items())),
            tuple(sorted(unbound.links.items())),
            tuple(sorted(unbound.data_objects.items())),
        )
        if key not in grouped:
            grouped[key] = (unbound, [])
        if source_uuid is None:
            continue
        target_uuid = row.anchors.get(requirement.target_bucket)
        if target_uuid is None:
            continue
        matches = [
            link
            for link in graph.list_incident_links(source_uuid, "source").links
            if link.target_uuid == target_uuid
            and link.type in requirement.link_type_keys
            and _matches_live(link, options)
        ]
        for link in sorted(matches, key=lambda item: str(item.uuid)):
            if link.uuid is not None:
                grouped[key][1].append(
                    RtgQueryBindingRow(
                        row_index=0,
                        anchors=row.anchors,
                        links={**row.links, requirement.name: link.uuid},
                        data_objects=row.data_objects,
                    )
                )
    expanded: list[RtgQueryBindingRow] = []
    for unbound, matches in grouped.values():
        expanded.extend(matches or [unbound])
    return _dedupe_binding_rows(expanded)


def _dedupe_binding_rows(rows: list[RtgQueryBindingRow]) -> list[RtgQueryBindingRow]:
    seen: set[tuple[tuple[tuple[str, UUID], ...], ...]] = set()
    result: list[RtgQueryBindingRow] = []
    for row in rows:
        key = (
            tuple(sorted(row.anchors.items())),
            tuple(sorted(row.links.items())),
            tuple(sorted(row.data_objects.items())),
        )
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _expand_data_requirement(
    graph: RtgGraphReadView,
    options: RtgQueryOptions,
    rows: list[RtgQueryBindingRow],
    requirement: RtgQueryDataRequirement,
) -> list[RtgQueryBindingRow]:
    expanded: list[RtgQueryBindingRow] = []
    for row in rows:
        anchor_uuid = row.anchors.get(requirement.anchor_bucket)
        if anchor_uuid is None:
            if not requirement.required:
                expanded.append(row)
            continue
        matches = [
            data
            for data in graph.list_anchor_data(anchor_uuid).data_objects
            if data.type == requirement.data_type_key
            and _matches_live(data, options)
            and all(
                _predicate_matches(data.properties, predicate)
                for predicate in requirement.predicates
            )
        ]
        if not matches and not requirement.required:
            expanded.append(row)
        for data in sorted(matches, key=lambda item: str(item.uuid)):
            if data.uuid is None:
                continue
            expanded.append(
                RtgQueryBindingRow(
                    row_index=0,
                    anchors=row.anchors,
                    links=row.links,
                    data_objects={**row.data_objects, requirement.name: data.uuid},
                )
            )
    return expanded


def _shape_return_row(
    graph: RtgGraphReadView,
    query_spec: RtgQuerySpec,
    row: RtgQueryBindingRow,
) -> RtgQueryReturnRow:
    return_spec = query_spec.return_spec
    properties: JsonObject = {}
    for requirement_name, path in return_spec.properties:
        data_uuid = row.data_objects.get(requirement_name)
        if data_uuid is None:
            continue
        data = graph.get_object(data_uuid)
        if not isinstance(data, RtgDataObject):
            continue
        found, value = _resolve_path(data.properties, path)
        if found:
            properties.setdefault(requirement_name, {})
            _assign_nested(properties[requirement_name], path, value)
    return RtgQueryReturnRow(
        row_index=row.row_index,
        anchors={
            name: row.anchors[name] for name in return_spec.anchor_buckets if name in row.anchors
        },
        links={
            name: row.links[name] for name in return_spec.link_requirements if name in row.links
        },
        data_objects={
            name: row.data_objects[name]
            for name in return_spec.data_requirements
            if name in row.data_objects
        },
        properties=properties,
    )


def _return_property_diagnostics(
    query_spec: RtgQuerySpec,
    bindings: tuple[RtgQueryBindingRow, ...],
    returns: tuple[RtgQueryReturnRow, ...],
) -> list[RtgQueryDiagnostic]:
    if not query_spec.diagnostic_options.include_non_fatal or not bindings:
        return []
    diagnostics: list[RtgQueryDiagnostic] = []
    for index, (requirement_name, path) in enumerate(query_spec.return_spec.properties):
        bound_count = sum(1 for row in bindings if requirement_name in row.data_objects)
        resolved_count = 0
        for row in returns:
            returned_properties = row.properties.get(requirement_name)
            if (
                isinstance(returned_properties, dict)
                and _resolve_path(returned_properties, path)[0]
            ):
                resolved_count += 1
        path_label = ".".join(path)
        if bound_count == 0:
            diagnostics.append(
                RtgQueryDiagnostic(
                    severity="info",
                    code="query.return_property_requirement_unbound",
                    message=(
                        f"Returned property {requirement_name}.{path_label} resolved no values "
                        "because the data requirement was not bound in any row."
                    ),
                    suggestion=(
                        "Check the data requirement name in return_spec.properties and make "
                        "sure it matches a query_spec.data_requirements entry that can bind rows."
                    ),
                    affected_terms=(requirement_name,),
                    diagnostic=rtg_diagnostic(
                        code="query.return_property_requirement_unbound",
                        category="query_contract",
                        path=f"query_spec.return_spec.properties[{index}]",
                        problem=(
                            "The returned property references a data requirement with no row "
                            "bindings."
                        ),
                        remedy=(
                            "Use the exact data requirement name from "
                            "query_spec.data_requirements, or add/repair the data requirement "
                            "before returning its properties."
                        ),
                        minimal_example={
                            "data_requirements": [{"name": "facts"}],
                            "return_spec": {"properties": [["facts", ["title"]]]},
                        },
                        guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
                    ),
                )
            )
        elif resolved_count == 0:
            diagnostics.append(
                RtgQueryDiagnostic(
                    severity="info",
                    code="query.return_property_path_unresolved",
                    message=(
                        f"Returned property {requirement_name}.{path_label} resolved no values "
                        f"across {bound_count} bound row(s)."
                    ),
                    suggestion=(
                        "Check the property path against the associated data object's properties. "
                        "Returned properties are omitted when the path is absent."
                    ),
                    affected_terms=(requirement_name, path_label),
                    diagnostic=rtg_diagnostic(
                        code="query.return_property_path_unresolved",
                        category="query_contract",
                        path=f"query_spec.return_spec.properties[{index}][1]",
                        problem=(
                            "The returned property path did not exist on any bound data object."
                        ),
                        remedy=(
                            "Inspect the schema pack or a representative object, then use an "
                            "existing property path in return_spec.properties."
                        ),
                        minimal_example={"return_spec": {"properties": [["facts", ["title"]]]}},
                        guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
                    ),
                )
            )
    return diagnostics


def _matches_live(obj: RtgAnchor | RtgDataObject | object, options: RtgQueryOptions) -> bool:
    uuid_value = getattr(obj, "uuid", None)
    system = getattr(obj, "system", {})
    overlay_live = (
        options.live_status_overlay.get(uuid_value) if isinstance(uuid_value, UUID) else None
    )
    live = overlay_live if overlay_live is not None else system.get("live", True)
    if options.live_filter == "all":
        return True
    if options.live_filter == "live":
        return live is True
    return live is False


def _predicate_matches(properties: JsonObject, predicate: RtgQueryPropertyPredicate) -> bool:
    if predicate.operator not in _OPERATORS:
        raise _invalid(
            f"unsupported predicate operator: {predicate.operator}",
            path="query_spec.data_requirements.predicates.operator",
            remedy="Use a supported query predicate operator.",
            code="query.predicate.unsupported_operator",
            accepted_fields=tuple(sorted(_OPERATORS)),
        )
    found, actual = _resolve_path(properties, predicate.path)
    if predicate.operator == "exists":
        return found
    if not found:
        return False
    expected_value = cast(JsonValue, predicate.value)
    if predicate.operator == "equals":
        return _json_equal(actual, expected_value)
    if predicate.operator == "not_equals":
        return not _json_equal(actual, expected_value)
    if predicate.operator in {"lt", "lte", "gt", "gte"}:
        expected = expected_value
        if isinstance(actual, bool) or isinstance(expected, bool):
            return False
        if isinstance(actual, str) and isinstance(expected, str):
            return _compare_strings(actual, expected, predicate.operator)
        if isinstance(actual, int | float) and isinstance(expected, int | float):
            return _compare_numbers(actual, expected, predicate.operator)
        return False
    if predicate.operator == "contains":
        return isinstance(actual, list) and any(
            _json_equal(item, expected_value) for item in actual
        )
    if predicate.operator == "in":
        return any(_json_equal(actual, item) for item in predicate.values)
    if predicate.operator == "substring":
        if not isinstance(actual, str) or not isinstance(predicate.value, str):
            return False
        if predicate.case_sensitive:
            return predicate.value in actual
        return predicate.value.lower() in actual.lower()
    if predicate.operator == "regex":
        return _regex_matches(actual, predicate)
    raise RtgQueryUnsupported(predicate.operator)


def _compare_strings(left: str, right: str, operator: str) -> bool:
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "gt":
        return left > right
    return left >= right


def _compare_numbers(left: int | float, right: int | float, operator: str) -> bool:
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "gt":
        return left > right
    return left >= right


def _json_equal(left: JsonValue, right: JsonValue) -> bool:
    return json_value_equal(left, right)


def _regex_matches(actual: JsonValue, predicate: RtgQueryPropertyPredicate) -> bool:
    if not isinstance(actual, str) or not isinstance(predicate.value, str):
        return False
    option_letters: list[str] = []
    for flag in predicate.regex_flags:
        if flag == "case_insensitive":
            option_letters.append("i")
        elif flag == "multiline":
            option_letters.append("m")
        else:
            raise _invalid(
                f"unsupported regex flag: {flag}",
                path="query_spec.data_requirements.predicates.regex_flags",
                remedy="Use only case_insensitive or multiline.",
                accepted_fields=("case_insensitive", "multiline"),
            )
    pattern = (
        f"(?{''.join(option_letters)}){predicate.value}" if option_letters else predicate.value
    )
    try:
        return re2.search(pattern, actual) is not None
    except re2.error as error:
        raise _invalid(
            f"unsupported regex pattern: {error}",
            path="query_spec.data_requirements.predicates.value",
            remedy="Use a valid RE2 pattern without unsupported constructs.",
        ) from error


def _resolve_path(properties: JsonObject, path: tuple[str, ...]) -> tuple[bool, JsonValue]:
    current: JsonValue = properties
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _assign_nested(target: JsonValue, path: tuple[str, ...], value: JsonValue) -> None:
    if not isinstance(target, dict) or not path:
        return
    current: JsonObject = target
    for segment in path[:-1]:
        child = current.setdefault(segment, {})
        if not isinstance(child, dict):
            return
        current = child
    current[path[-1]] = value


def _row_sort_key(row: RtgQueryBindingRow, query_spec: RtgQuerySpec) -> tuple[str, ...]:
    keys: list[str] = []
    for bucket in query_spec.anchor_buckets:
        keys.append(str(row.anchors.get(bucket.name, UUID(int=0))))
    for requirement in query_spec.link_requirements:
        keys.append(str(row.links.get(requirement.name, UUID(int=0))))
    for requirement in query_spec.data_requirements:
        keys.append(str(row.data_objects.get(requirement.name, UUID(int=0))))
    return tuple(keys)


def _apply_return_ordering(
    bindings: tuple[RtgQueryBindingRow, ...],
    returns: tuple[RtgQueryReturnRow, ...],
    order_by: tuple[RtgQueryOrderBy, ...],
) -> tuple[tuple[RtgQueryBindingRow, ...], tuple[RtgQueryReturnRow, ...]]:
    rows = list(zip(bindings, returns, strict=True))
    for order in reversed(order_by):
        reverse = order.direction == "descending"
        rows.sort(key=lambda pair, item=order: _return_sort_key(pair[1], item), reverse=reverse)
        if reverse:
            missing = [pair for pair in rows if _return_sort_key(pair[1], order)[0] == 1]
            present = [pair for pair in rows if _return_sort_key(pair[1], order)[0] == 0]
            rows = present + missing
    reindexed_bindings: list[RtgQueryBindingRow] = []
    reindexed_returns: list[RtgQueryReturnRow] = []
    for index, (binding, returned) in enumerate(rows):
        reindexed_bindings.append(
            RtgQueryBindingRow(
                row_index=index,
                anchors=binding.anchors,
                links=binding.links,
                data_objects=binding.data_objects,
            )
        )
        reindexed_returns.append(
            RtgQueryReturnRow(
                row_index=index,
                anchors=returned.anchors,
                links=returned.links,
                data_objects=returned.data_objects,
                properties=returned.properties,
            )
        )
    return tuple(reindexed_bindings), tuple(reindexed_returns)


def _return_sort_key(row: RtgQueryReturnRow, order: RtgQueryOrderBy) -> tuple[int, str, object]:
    data_properties = row.properties.get(order.data_requirement)
    if not isinstance(data_properties, dict):
        return (1, "", "")
    found, value = _resolve_path(data_properties, order.path)
    if not found or isinstance(value, bool):
        return (1, "", "")
    if isinstance(value, int | float):
        return (0, "number", json_number_decimal(value))
    if isinstance(value, str):
        return (0, "string", value)
    return (1, "", "")


def _distinct_return_pairs(
    pairs: list[tuple[RtgQueryBindingRow, RtgQueryReturnRow]],
) -> list[tuple[RtgQueryBindingRow, RtgQueryReturnRow]]:
    seen: set[str] = set()
    result: list[tuple[RtgQueryBindingRow, RtgQueryReturnRow]] = []
    for pair in pairs:
        returned = pair[1]
        projection = {
            "anchors": {key: str(value) for key, value in returned.anchors.items()},
            "links": {key: str(value) for key, value in returned.links.items()},
            "data_objects": {key: str(value) for key, value in returned.data_objects.items()},
            "properties": returned.properties,
        }
        key = canonical_json_key(projection)
        if key not in seen:
            seen.add(key)
            result.append(pair)
    return result


def _reindex_pairs(
    pairs: list[tuple[RtgQueryBindingRow, RtgQueryReturnRow]],
) -> tuple[tuple[RtgQueryBindingRow, ...], tuple[RtgQueryReturnRow, ...]]:
    bindings: list[RtgQueryBindingRow] = []
    returns: list[RtgQueryReturnRow] = []
    for index, (binding, returned) in enumerate(pairs):
        bindings.append(
            RtgQueryBindingRow(
                row_index=index,
                anchors=binding.anchors,
                links=binding.links,
                data_objects=binding.data_objects,
            )
        )
        returns.append(
            RtgQueryReturnRow(
                row_index=index,
                anchors=returned.anchors,
                links=returned.links,
                data_objects=returned.data_objects,
                properties=returned.properties,
            )
        )
    return tuple(bindings), tuple(returns)


def _slice_rows(rows: list[Any], options: RtgQueryOptions) -> tuple[list[Any], int | None]:
    start = options.offset
    stop = None if options.limit is None else start + options.limit
    sliced = rows[start:stop]
    next_offset = start + len(sliced)
    return sliced, next_offset if next_offset < len(rows) else None


def _aggregate_rows(
    bindings: tuple[RtgQueryBindingRow, ...],
    returns: tuple[RtgQueryReturnRow, ...],
    query_spec: RtgQuerySpec,
) -> list[JsonObject]:
    grouped: dict[str, tuple[list[JsonValue], list[set[UUID]]]] = {}
    aggregations = query_spec.return_spec.aggregations
    for binding, returned in zip(bindings, returns, strict=True):
        group_values: list[JsonValue] = []
        for requirement, path in query_spec.return_spec.group_by:
            properties = returned.properties.get(requirement)
            found, value = (
                _resolve_path(properties, path) if isinstance(properties, dict) else (False, None)
            )
            group_values.append(value if found else None)
        group_key = canonical_json_key(group_values)
        if group_key not in grouped:
            grouped[group_key] = (group_values, [set() for _ in aggregations])
        distinct_sets = grouped[group_key][1]
        for index, aggregation in enumerate(aggregations):
            uuid_value = _binding_uuid(binding, aggregation.binding)
            if uuid_value is not None:
                distinct_sets[index].add(uuid_value)
    if not grouped and not query_spec.return_spec.group_by:
        grouped["[]"] = ([], [set() for _ in aggregations])
    rows: list[JsonObject] = []
    for group_key in sorted(grouped):
        group_values, distinct_sets = grouped[group_key]
        group_payload: JsonObject = {}
        for (requirement, path), value in zip(
            query_spec.return_spec.group_by, group_values, strict=True
        ):
            group_payload.setdefault(requirement, {})
            _assign_nested(group_payload[requirement], path, value)
        row: JsonObject = {"group_by": group_payload}
        for aggregation, values in zip(aggregations, distinct_sets, strict=True):
            row[aggregation.name] = len(values)
        rows.append(row)
    return rows


def _binding_uuid(row: RtgQueryBindingRow, name: str) -> UUID | None:
    return row.anchors.get(name) or row.links.get(name) or row.data_objects.get(name)


def _validate_options(options: RtgQueryOptions) -> None:
    if options.limit is not None and (
        isinstance(options.limit, bool) or not isinstance(options.limit, int) or options.limit <= 0
    ):
        raise _invalid(
            "query_options.limit must be a positive integer",
            path="query_options.limit",
            remedy="Use a positive integer or omit limit.",
        )
    if (
        isinstance(options.offset, bool)
        or not isinstance(options.offset, int)
        or options.offset < 0
    ):
        raise _invalid(
            "query_options.offset must be a non-negative integer",
            path="query_options.offset",
            remedy="Use zero or a positive integer.",
        )
    if not isinstance(options.distinct_rows, bool):
        raise _invalid(
            "query_options.distinct_rows must be boolean",
            path="query_options.distinct_rows",
            remedy="Use true or false.",
        )
    if options.live_filter not in _LIVE_FILTERS:
        raise RtgQuerySpecInvalid(
            f"invalid live_filter: {options.live_filter}",
            diagnostic=rtg_diagnostic(
                code="query.options.invalid_live_filter",
                category="query_contract",
                path="query_options.live_filter",
                problem="live_filter must be one of the supported live-state filters.",
                remedy="Use live_filter 'all', 'live', or 'non_live'.",
                accepted_fields=tuple(sorted(_LIVE_FILTERS)),
                minimal_example={"query_options": {"live_filter": "live"}},
                guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
            ),
        )
    for order in options.order_by:
        if order.direction not in {"ascending", "descending"}:
            raise RtgQuerySpecInvalid(
                f"invalid order_by direction: {order.direction}",
                diagnostic=rtg_diagnostic(
                    code="query.options.invalid_order_direction",
                    category="query_contract",
                    path="query_options.order_by.direction",
                    problem="order_by direction must be ascending or descending.",
                    remedy="Set direction to 'ascending' or 'descending'.",
                    accepted_fields=("ascending", "descending"),
                    minimal_example={
                        "query_options": {
                            "order_by": [
                                {
                                    "data_requirement": "facts",
                                    "path": ["title"],
                                    "direction": "ascending",
                                }
                            ]
                        }
                    },
                    guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
                ),
            )
        if not order.data_requirement:
            raise _invalid(
                "order_by data_requirement must be non-empty",
                path="query_options.order_by.data_requirement",
                remedy="Name a returned data requirement.",
            )
        if not order.path:
            raise _invalid(
                "order_by path must be non-empty",
                path="query_options.order_by.path",
                remedy="Supply at least one property path segment.",
            )


def _validate_spec(query_spec: RtgQuerySpec) -> None:
    bucket_names = _names(
        "anchor bucket", tuple(bucket.name for bucket in query_spec.anchor_buckets)
    )
    if not bucket_names:
        raise _invalid(
            "at least one anchor bucket is required",
            path="query_spec.anchor_buckets",
            remedy="Define at least one named anchor bucket.",
        )
    for bucket in query_spec.anchor_buckets:
        if not bucket.anchor_type_keys:
            raise _invalid(
                f"anchor bucket {bucket.name!r} has no type keys",
                path="query_spec.anchor_buckets.anchor_type_keys",
                remedy="Supply at least one anchor type key.",
            )
    link_names = _names(
        "link requirement", tuple(item.name for item in query_spec.link_requirements)
    )
    data_names = _names(
        "data requirement", tuple(item.name for item in query_spec.data_requirements)
    )
    all_binding_names = (*bucket_names, *link_names, *data_names)
    if len(set(all_binding_names)) != len(all_binding_names):
        raise _invalid(
            "anchor bucket, link requirement, and data requirement names must be globally unique",
            path="query_spec",
            remedy=(
                "Give every anchor bucket, link requirement, and data requirement a unique name."
            ),
        )
    for link in query_spec.link_requirements:
        if link.source_bucket not in bucket_names or link.target_bucket not in bucket_names:
            raise RtgQuerySpecInvalid(
                f"link requirement {link.name!r} names unknown bucket",
                diagnostic=rtg_diagnostic(
                    code="query.spec.unknown_bucket",
                    category="query_contract",
                    path="query_spec.link_requirements",
                    problem=(
                        "A link requirement references an anchor bucket name that is not defined."
                    ),
                    remedy=(
                        "Define both endpoint names in query_spec.anchor_buckets before using them."
                    ),
                    minimal_example={
                        "anchor_buckets": [
                            {"name": "source", "anchor_type_keys": ["Item"]},
                            {"name": "target", "anchor_type_keys": ["Item"]},
                        ],
                        "link_requirements": [
                            {
                                "name": "related",
                                "source_bucket": "source",
                                "target_bucket": "target",
                                "link_type_keys": ["related_to"],
                            }
                        ],
                    },
                    guide_topics=("workflow_patterns", "query_examples"),
                ),
            )
        if not link.link_type_keys:
            raise _invalid(
                f"link requirement {link.name!r} has no link type keys",
                path="query_spec.link_requirements.link_type_keys",
                remedy="Supply at least one link type key.",
            )
    for data in query_spec.data_requirements:
        if data.anchor_bucket not in bucket_names:
            raise RtgQuerySpecInvalid(
                f"data requirement {data.name!r} names unknown bucket",
                diagnostic=rtg_diagnostic(
                    code="query.spec.unknown_bucket",
                    category="query_contract",
                    path="query_spec.data_requirements",
                    problem=(
                        "A data requirement references an anchor bucket name that is not defined."
                    ),
                    remedy=(
                        "Define the anchor bucket in query_spec.anchor_buckets before requiring "
                        "data."
                    ),
                    minimal_example={
                        "anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}],
                        "data_requirements": [
                            {
                                "name": "facts",
                                "anchor_bucket": "item",
                                "data_type_key": "ItemFacts",
                            }
                        ],
                    },
                    guide_topics=("workflow_patterns", "query_examples"),
                ),
            )
        if not data.data_type_key:
            raise _invalid(
                f"data requirement {data.name!r} has no data type",
                path="query_spec.data_requirements.data_type_key",
                remedy="Supply a non-empty data type key.",
            )
        for predicate in data.predicates:
            if predicate.operator not in _OPERATORS:
                raise RtgQuerySpecInvalid(
                    f"unsupported predicate operator: {predicate.operator}",
                    diagnostic=rtg_diagnostic(
                        code="query.predicate.unsupported_operator",
                        category="query_contract",
                        path="query_spec.data_requirements.predicates.operator",
                        problem="The predicate operator is not supported by the RTG query engine.",
                        remedy="Use one of the supported predicate operators.",
                        accepted_fields=tuple(sorted(_OPERATORS)),
                        minimal_example={
                            "predicates": [
                                {"path": ["title"], "operator": "equals", "value": "Item alpha"}
                            ]
                        },
                        guide_topics=("workflow_patterns", "query_examples"),
                    ),
                )
            if (
                predicate.operator not in {"exists", "in"}
                and getattr(predicate.value, "__vellis_codec_absent__", False) is True
            ):
                raise _invalid(
                    f"predicate operator {predicate.operator!r} requires value",
                    path="query_spec.data_requirements.predicates.value",
                    remedy="Provide value explicitly; use JSON null when null is intended.",
                )
    if query_spec.diagnostic_options.unknown_term_guidance not in {
        "none",
        "suggest_discovery",
    }:
        raise _invalid(
            "unknown_term_guidance must be none or suggest_discovery",
            path="query_spec.diagnostic_options.unknown_term_guidance",
            remedy="Use 'none' or 'suggest_discovery'.",
            accepted_fields=("none", "suggest_discovery"),
        )
    for label, selected, declared in (
        ("anchor_buckets", query_spec.return_spec.anchor_buckets, bucket_names),
        ("link_requirements", query_spec.return_spec.link_requirements, link_names),
        ("data_requirements", query_spec.return_spec.data_requirements, data_names),
    ):
        unknown = set(selected) - declared
        if unknown:
            raise _invalid(
                f"return_spec.{label} names unknown requirement {sorted(unknown)[0]!r}",
                path=f"query_spec.return_spec.{label}",
                remedy="Select only names declared by this query specification.",
            )
    for label, properties in (
        ("properties", query_spec.return_spec.properties),
        ("group_by", query_spec.return_spec.group_by),
    ):
        for data_requirement, path in properties:
            if data_requirement not in data_names:
                raise _invalid(
                    f"return_spec.{label} names unknown data requirement {data_requirement!r}",
                    path=f"query_spec.return_spec.{label}",
                    remedy=(
                        "Reference a declared data requirement, including an optional one when "
                        "appropriate."
                    ),
                )
            if not path:
                raise _invalid(
                    f"return_spec.{label} property path must be non-empty",
                    path=f"query_spec.return_spec.{label}",
                    remedy="Supply at least one property path segment.",
                )
    returned_properties = set(query_spec.return_spec.properties)
    for group_path in query_spec.return_spec.group_by:
        if group_path not in returned_properties:
            raise _invalid(
                "group_by paths must also be listed in return_spec.properties",
                path="query_spec.return_spec.group_by",
                remedy="Add every group_by pair to return_spec.properties.",
            )
    binding_names = bucket_names | link_names | data_names
    aggregation_names = _names(
        "aggregation",
        tuple(item.name for item in query_spec.return_spec.aggregations),
    )
    reserved_aggregation_names = aggregation_names & {"group_by", "row_index"}
    if reserved_aggregation_names:
        raise RtgQuerySpecInvalid(
            "aggregation names cannot use reserved result fields",
            diagnostic=rtg_diagnostic(
                code="query.aggregation.reserved_name",
                category="query_contract",
                path="query_spec.return_spec.aggregations.name",
                problem="Aggregation names would overwrite structural result fields.",
                remedy="Choose names other than row_index and group_by.",
                accepted_fields=("non-reserved unique aggregation name",),
                guide_topics=("query_examples", "tool_call_shapes"),
            ),
        )
    for aggregation in query_spec.return_spec.aggregations:
        if aggregation.function != "count":
            raise _invalid(
                "only count aggregation is supported",
                path="query_spec.return_spec.aggregations.function",
                remedy="Use the count aggregation function.",
                accepted_fields=("count",),
            )
        if aggregation.binding not in binding_names:
            raise _invalid(
                f"aggregation {aggregation.name!r} names unknown binding",
                path="query_spec.return_spec.aggregations.binding",
                remedy="Reference a declared anchor, link, or data binding name.",
            )
    if query_spec.return_spec.group_by and not aggregation_names:
        raise _invalid(
            "group_by requires at least one aggregation",
            path="query_spec.return_spec.group_by",
            remedy="Add at least one count aggregation or remove group_by.",
        )


def _validate_order_by_against_spec(
    query_spec: RtgQuerySpec,
    options: RtgQueryOptions,
) -> None:
    returned_properties = set(query_spec.return_spec.properties)
    for order in options.order_by:
        if (order.data_requirement, order.path) not in returned_properties:
            raise RtgQuerySpecInvalid(
                "order_by must reference a property path listed in return_spec.properties",
                diagnostic=rtg_diagnostic(
                    code="query.options.order_by_not_returned",
                    category="query_contract",
                    path="query_options.order_by",
                    problem="order_by can sort only property paths returned by the query.",
                    remedy=(
                        "Add the same data requirement and path to "
                        "query_spec.return_spec.properties before using it in order_by."
                    ),
                    minimal_example={
                        "query_spec": {"return_spec": {"properties": [["facts", ["due"]]]}},
                        "query_options": {
                            "order_by": [
                                {
                                    "data_requirement": "facts",
                                    "path": ["due"],
                                    "direction": "ascending",
                                }
                            ]
                        },
                    },
                    guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
                ),
            )


def _names(label: str, names: tuple[str, ...]) -> set[str]:
    if any(not name for name in names):
        raise _invalid(
            f"{label} names must be non-empty",
            path=f"query_spec.{label.replace(' ', '_')}s.name",
            remedy=f"Give every {label} a non-empty name.",
        )
    if len(set(names)) != len(names):
        raise _invalid(
            f"{label} names must be unique",
            path=f"query_spec.{label.replace(' ', '_')}s.name",
            remedy=f"Give every {label} a unique name.",
        )
    return set(names)


def _invalid(
    message: str,
    *,
    path: str,
    remedy: str,
    code: str = "query.spec.invalid",
    accepted_fields: tuple[str, ...] = (),
) -> RtgQuerySpecInvalid:
    return RtgQuerySpecInvalid(
        message,
        diagnostic=rtg_diagnostic(
            code=code,
            category="query_contract",
            path=path,
            problem=message,
            remedy=remedy,
            accepted_fields=accepted_fields,
            guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
        ),
    )


def _discovery_suggestion(query_spec: RtgQuerySpec) -> str | None:
    if query_spec.diagnostic_options.unknown_term_guidance == "none":
        return None
    return "Use controller discovery or a schema pack to confirm valid type keys."
