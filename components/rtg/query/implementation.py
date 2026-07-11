from __future__ import annotations

import itertools
from uuid import UUID

import re2

from components.rtg.diagnostics import rtg_diagnostic
from components.rtg.graph.protocol import (
    JsonObject,
    JsonValue,
    RtgAnchor,
    RtgDataObject,
    RtgGraph,
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
        graph: RtgGraph,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        options = query_options or RtgQueryOptions()
        _validate_options(options)
        _validate_spec(query_spec)
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
        bindings: list[RtgQueryBindingRow] = []
        for anchor_values in itertools.product(*(bucket_candidates[name] for name in bucket_names)):
            anchor_binding = dict(
                zip(bucket_names, (anchor.uuid for anchor in anchor_values), strict=True)
            )
            if any(value is None for value in anchor_binding.values()):
                continue
            partial_rows = [RtgQueryBindingRow(row_index=0, anchors=anchor_binding)]  # type: ignore[arg-type]
            for link_requirement in query_spec.link_requirements:
                partial_rows = _expand_link_requirement(
                    graph, options, partial_rows, link_requirement
                )
                if not partial_rows:
                    break
            if not partial_rows:
                continue
            for data_requirement in query_spec.data_requirements:
                partial_rows = _expand_data_requirement(
                    graph, options, partial_rows, data_requirement
                )
                if not partial_rows:
                    break
            bindings.extend(partial_rows)

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
        return RtgQueryResult(bindings=indexed, returns=returns, diagnostics=tuple(diagnostics))


def _expand_link_requirement(
    graph: RtgGraph,
    options: RtgQueryOptions,
    rows: list[RtgQueryBindingRow],
    requirement: RtgQueryLinkRequirement,
) -> list[RtgQueryBindingRow]:
    expanded: list[RtgQueryBindingRow] = []
    for row in rows:
        source_uuid = row.anchors[requirement.source_bucket]
        target_uuid = row.anchors[requirement.target_bucket]
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
    return expanded


def _expand_data_requirement(
    graph: RtgGraph,
    options: RtgQueryOptions,
    rows: list[RtgQueryBindingRow],
    requirement: RtgQueryDataRequirement,
) -> list[RtgQueryBindingRow]:
    expanded: list[RtgQueryBindingRow] = []
    for row in rows:
        anchor_uuid = row.anchors[requirement.anchor_bucket]
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
    graph: RtgGraph,
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
            if isinstance(returned_properties, dict) and _resolve_path(
                returned_properties, path
            )[0]:
                resolved_count += 1
        path_label = ".".join(path)
        if bound_count == 0:
            diagnostics.append(
                RtgQueryDiagnostic(
                    severity="informational",
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
                    severity="informational",
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
        raise RtgQuerySpecInvalid(f"unsupported predicate operator: {predicate.operator}")
    found, actual = _resolve_path(properties, predicate.path)
    if predicate.operator == "exists":
        return found
    if not found:
        return False
    if predicate.operator == "equals":
        return _json_equal(actual, predicate.value)
    if predicate.operator == "not_equals":
        return not _json_equal(actual, predicate.value)
    if predicate.operator in {"lt", "lte", "gt", "gte"}:
        expected = predicate.value
        if isinstance(actual, bool) or isinstance(expected, bool):
            return False
        if isinstance(actual, str) and isinstance(expected, str):
            return _compare_strings(actual, expected, predicate.operator)
        if isinstance(actual, int | float) and isinstance(expected, int | float):
            return _compare_numbers(actual, expected, predicate.operator)
        return False
    if predicate.operator == "contains":
        return isinstance(actual, list) and any(
            _json_equal(item, predicate.value) for item in actual
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
    """Compare JSON values without Python's Boolean/number equivalence."""
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, int | float) or isinstance(right, int | float):
        return (
            isinstance(left, int | float)
            and not isinstance(left, bool)
            and isinstance(right, int | float)
            and not isinstance(right, bool)
            and left == right
        )
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_equal(a, b) for a, b in zip(left, right, strict=True))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_json_equal(left[key], right[key]) for key in left)
        )
    return False


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
            raise RtgQuerySpecInvalid(f"unsupported regex flag: {flag}")
    pattern = (
        f"(?{''.join(option_letters)}){predicate.value}"
        if option_letters
        else predicate.value
    )
    try:
        return re2.search(pattern, actual) is not None
    except re2.error as error:
        raise RtgQuerySpecInvalid(f"unsupported regex pattern: {error}") from error


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
        keys.append(str(row.anchors[bucket.name]))
    for requirement in query_spec.link_requirements:
        keys.append(str(row.links[requirement.name]))
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
        return (0, "number", float(value))
    if isinstance(value, str):
        return (0, "string", value)
    return (1, "", "")


def _validate_options(options: RtgQueryOptions) -> None:
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
            raise RtgQuerySpecInvalid("order_by data_requirement must be non-empty")
        if not order.path:
            raise RtgQuerySpecInvalid("order_by path must be non-empty")


def _validate_spec(query_spec: RtgQuerySpec) -> None:
    bucket_names = _names(
        "anchor bucket", tuple(bucket.name for bucket in query_spec.anchor_buckets)
    )
    if not bucket_names:
        raise RtgQuerySpecInvalid("at least one anchor bucket is required")
    for bucket in query_spec.anchor_buckets:
        if not bucket.anchor_type_keys:
            raise RtgQuerySpecInvalid(f"anchor bucket {bucket.name!r} has no type keys")
    _names("link requirement", tuple(item.name for item in query_spec.link_requirements))
    _names("data requirement", tuple(item.name for item in query_spec.data_requirements))
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
                        "Define both endpoint names in query_spec.anchor_buckets before using "
                        "them."
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
            raise RtgQuerySpecInvalid(f"link requirement {link.name!r} has no link type keys")
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
            raise RtgQuerySpecInvalid(f"data requirement {data.name!r} has no data type")
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
                        "query_spec": {
                            "return_spec": {"properties": [["facts", ["due"]]]}
                        },
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
        raise RtgQuerySpecInvalid(f"{label} names must be non-empty")
    if len(set(names)) != len(names):
        raise RtgQuerySpecInvalid(f"{label} names must be unique")
    return set(names)


def _discovery_suggestion(query_spec: RtgQuerySpec) -> str | None:
    if query_spec.diagnostic_options.unknown_term_guidance == "none":
        return None
    return "Use controller discovery or a schema pack to confirm valid type keys."
