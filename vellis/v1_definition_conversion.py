"""Streamed v1 definition, property, and local-cardinality conversion."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import cast

import re2

from vellis.domain import (
    SAFE_INTEGER_MAXIMUM,
    SAFE_INTEGER_MINIMUM,
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    Cardinality,
    LinkTypeDefinition,
    PropertyDefinition,
    ScalarValue,
    TypeDefinition,
    ValueKind,
)
from vellis.domain_validation import property_definition_findings
from vellis.v1_candidate import stage_definition
from vellis.v1_conversion_common import (
    is_live,
    legacy_system,
    omit_nonlive,
    required_text,
)
from vellis.v1_identity import identity_conflicted, source_entry_live
from vellis.v1_import_domain import V1Disposition, V1ImportError
from vellis.v1_pointer import append_pointer
from vellis.v1_population import permitted_anchor_keys, permitted_link_keys
from vellis.v1_report import add_disposition
from vellis.v1_stage import STAGE_RELATION, iter_category, put_payload

_REFINEMENT_FIELDS = {
    "allowed_values",
    "minimum",
    "maximum",
    "minimum_length",
    "maximum_length",
    "pattern",
}
_PROPERTY_FIELDS = _REFINEMENT_FIELDS | {
    "required",
    "value_kinds",
    "description",
}


def convert_definitions(connection) -> None:
    _report_nonlive_definitions(connection)
    _convert_bounds(connection)
    for _key, pointer, raw in _live_definition_rows(connection):
        assert isinstance(raw, dict)
        type_key = raw.get("type_key")
        if isinstance(type_key, str) and identity_conflicted(connection, "type", type_key):
            continue
        try:
            definition = _definition(connection, raw, pointer)
            stage_definition(connection, definition, pointer)
            add_disposition(
                connection,
                V1Disposition.PRESERVED,
                "definition-preserved",
                pointer,
                f"live {definition.kind.value} definition {definition.type_key} is preserved",
                target_type_key=definition.type_key,
            )
        except (TypeError, ValueError, V1ImportError) as error:
            add_disposition(
                connection,
                V1Disposition.BLOCKING,
                "definition-invalid",
                pointer,
                str(error),
                target_type_key=_optional_text(raw.get("type_key")),
            )


def _live_definition_rows(connection):
    for key, pointer, raw in iter_category(connection, "sourceDefinition"):
        if not isinstance(raw, dict):
            raise V1ImportError(f"{pointer} is not an object")
        if source_entry_live(connection, raw, pointer):
            yield key, pointer, raw


def _report_nonlive_definitions(connection) -> None:
    for key, pointer, raw in iter_category(connection, "sourceDefinition"):
        if not isinstance(raw, dict):
            continue
        live = source_entry_live(connection, raw, pointer)
        if live is False:
            omit_nonlive(connection, "definition", pointer, raw.get("type_key", key))


def _definition(connection, raw, pointer) -> TypeDefinition:
    type_key = required_text(raw, "type_key", pointer)
    description = required_text(raw, "description", pointer)
    system = legacy_system(raw, pointer)
    kind = raw.get("kind")
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise V1ImportError(f"{pointer}/payload is not an object")
    if kind == "anchor":
        payload_pointer = append_pointer(pointer, "payload")
        _optional_text_collection(payload, "required_data_types", payload_pointer)
        _optional_text_collection(payload, "optional_data_types", payload_pointer)
        return AnchorTypeDefinition(type_key, description, system)
    if kind == "data_object":
        permitted = permitted_anchor_keys(connection, type_key)
        if not permitted:
            raise V1ImportError(f"data type {type_key} has no permitted live anchor type")
        properties = _properties(connection, type_key, payload, pointer)
        return AssociatedDataTypeDefinition(
            type_key,
            description,
            permitted,
            properties,
            _bound(connection, type_key, "anchorsPerObject", Cardinality(1)),
            _bound(connection, type_key, "objectsPerAnchor", Cardinality(0)),
            system,
        )
    if kind == "link":
        declared_sources = _text_set(payload.get("allowed_source_types"), f"{pointer}/payload")
        declared_targets = _text_set(payload.get("allowed_target_types"), f"{pointer}/payload")
        sources = permitted_link_keys(connection, type_key, "source", list(declared_sources))
        targets = permitted_link_keys(connection, type_key, "target", list(declared_targets))
        return LinkTypeDefinition(
            type_key,
            description,
            sources,
            targets,
            _bound(connection, type_key, "linksPerSource", Cardinality(0)),
            _bound(connection, type_key, "linksPerTarget", Cardinality(0)),
            system,
        )
    raise V1ImportError(f"{pointer}/kind is not anchor, data_object, or link")


def _properties(connection, type_key, payload, pointer):
    raw_properties = payload.get("properties", {})
    if not isinstance(raw_properties, dict):
        raise V1ImportError(f"{pointer}/payload/properties is not an object")
    properties = []
    for name in sorted(raw_properties):
        raw = raw_properties[name]
        prop_pointer = append_pointer(pointer, "payload", "properties", name)
        if not isinstance(name, str) or not isinstance(raw, dict):
            raise V1ImportError(f"{prop_pointer} is not a property definition")
        properties.append(_property(connection, type_key, name, raw, prop_pointer))
    return tuple(properties)


def _property(connection, type_key, name, raw, pointer):
    description = required_text(raw, "description", pointer)
    declared_kinds = _optional_text_collection(raw, "value_kinds", pointer)
    kind, nullable, converted = _infer_property(
        declared_kinds, _property_occurrences(connection, type_key, name)
    )
    required = raw.get("required", False)
    if type(required) is not bool:
        raise V1ImportError(f"{pointer}/required is not Boolean")
    if converted:
        add_disposition(
            connection,
            V1Disposition.CONVERTED,
            "property-json-text",
            pointer,
            f"{type_key}.{name} becomes canonical JSON text for every occurrence",
            target_type_key=type_key,
            target_property=name,
        )
    base = PropertyDefinition(
        name,
        description,
        kind,
        required,
        nullable,
    )
    if converted:
        _report_converted_refinements(connection, type_key, name, raw, pointer)
        return base
    return _compatible_constraints(connection, type_key, raw, pointer, base)


def _property_occurrences(connection, type_key, name):
    for _key, _pointer, raw in iter_category(connection, "sourceData"):
        if not isinstance(raw, dict) or raw.get("type") != type_key:
            continue
        if not source_entry_live(connection, raw, _pointer):
            continue
        properties = raw.get("properties", {})
        if isinstance(properties, dict) and name in properties:
            yield properties[name]


def _infer_property(declared, values):
    declared_kinds = declared if isinstance(declared, list) else []
    observed = set()
    has_unsafe_integer = False
    has_nonfinite_number = False
    for value in values:
        observed.add(_source_kind(value))
        if type(value) is int and not _safe_integer(value):
            has_unsafe_integer = True
        if isinstance(value, Decimal) and not _finite_number(value):
            has_nonfinite_number = True
    declared_nonnull = {_declared_kind(value) for value in declared_kinds if value != "null"}
    nullable = "null" in declared_kinds or "null" in observed
    observed_nonnull = observed - {"null"}
    if declared_nonnull == {"number"} and observed_nonnull <= {"integer", "number"}:
        nonnull = {"number"}
    else:
        nonnull = (declared_nonnull | observed_nonnull) - {None}
    if None in declared_nonnull or len(nonnull) != 1:
        return ValueKind.TEXT, False, True
    selected = next(iter(nonnull), None)
    if selected == "integer" and has_unsafe_integer:
        return ValueKind.TEXT, False, True
    if selected == "number" and (has_unsafe_integer or has_nonfinite_number):
        return ValueKind.TEXT, False, True
    mapping = {
        "boolean": ValueKind.BOOLEAN,
        "integer": ValueKind.INTEGER,
        "number": ValueKind.NUMBER,
        "text": ValueKind.TEXT,
    }
    if selected not in mapping:
        return ValueKind.TEXT, False, True
    return mapping[selected], nullable, False


def _compatible_constraints(connection, type_key, raw, pointer, base):
    allowed, allowed_valid = _allowed_refinement(raw, base.value_kind)
    minimum, minimum_valid = _scalar_refinement(raw, "minimum", base.value_kind)
    maximum, maximum_valid = _scalar_refinement(raw, "maximum", base.value_kind)
    min_length, min_length_valid = _natural_refinement(raw, "minimum_length")
    max_length, max_length_valid = _natural_refinement(raw, "maximum_length")
    pattern, pattern_valid = _pattern_refinement(raw)
    candidate = PropertyDefinition(
        base.name,
        base.description,
        base.value_kind,
        base.required,
        base.nullable,
        allowed,
        minimum,
        maximum,
        min_length,
        max_length,
        pattern,
    )
    conversions_valid = all(
        (
            allowed_valid,
            minimum_valid,
            maximum_valid,
            min_length_valid,
            max_length_valid,
            pattern_valid,
        )
    )
    if not conversions_valid or property_definition_findings(candidate):
        add_disposition(
            connection,
            V1Disposition.OMITTED,
            "property-constraints-omitted",
            pointer,
            f"incompatible v1 refinements on {type_key}.{base.name} were omitted",
            target_type_key=type_key,
            target_property=base.name,
        )
        return base
    _report_unsupported_refinements(connection, type_key, base.name, raw, pointer)
    return candidate


def _report_converted_refinements(connection, type_key, name, raw, pointer):
    if set(raw) & _REFINEMENT_FIELDS:
        add_disposition(
            connection,
            V1Disposition.OMITTED,
            "property-constraints-omitted",
            pointer,
            f"v1 refinements on JSON-text-converted {type_key}.{name} were omitted",
            target_type_key=type_key,
            target_property=name,
        )
    _report_unsupported_refinements(connection, type_key, name, raw, pointer)


def _report_unsupported_refinements(connection, type_key, name, raw, pointer):
    if not set(raw) - _PROPERTY_FIELDS:
        return
    add_disposition(
        connection,
        V1Disposition.OMITTED,
        "property-refinement-omitted",
        pointer,
        f"unsupported v1 refinements on {type_key}.{name} were omitted",
        target_type_key=type_key,
        target_property=name,
    )


def _allowed_refinement(raw, kind):
    if "allowed_values" not in raw:
        return (), True
    value = raw["allowed_values"]
    if not isinstance(value, list) or not value:
        return (), False
    converted = tuple(_scalar(item, kind) for item in value)
    if any(item is None for item in converted):
        return (), False
    return cast(tuple[ScalarValue, ...], converted), True


def _scalar_refinement(raw, name, kind):
    if name not in raw:
        return None, True
    value = _scalar(raw[name], kind)
    return value, value is not None


def _natural_refinement(raw, name):
    if name not in raw:
        return None, True
    value = _optional_natural(raw[name])
    return value, value is not None


def _pattern_refinement(raw):
    if "pattern" not in raw:
        return None, True
    value = raw["pattern"]
    if not isinstance(value, str):
        return None, False
    try:
        re2.compile(value)
    except re2.error:
        return None, False
    return value, True


def _convert_bounds(connection):
    ordinal = 0
    for _key, pointer, raw in iter_category(connection, "sourceConstraint"):
        if not isinstance(raw, dict):
            continue
        try:
            live = is_live(raw, pointer)
        except (TypeError, ValueError, V1ImportError) as error:
            add_disposition(
                connection,
                V1Disposition.BLOCKING,
                "constraint-invalid",
                append_pointer(pointer, "system", "live"),
                str(error),
            )
            continue
        if not live:
            omit_nonlive(connection, "constraint", pointer, raw.get("uuid"))
            continue
        mapped = _local_bound(connection, raw)
        if mapped is None:
            for target in _bound_targets(raw):
                put_payload(
                    connection,
                    "boundConflict",
                    f"{target[0]}\x00{target[1]}",
                    pointer,
                    {"typeKey": target[0], "role": target[1]},
                    ordinal=ordinal,
                )
                ordinal += 1
            add_disposition(
                connection,
                V1Disposition.OMITTED,
                "relationship-rule-omitted",
                pointer,
                "v1 relationship rule is not exactly one complete local type bound",
            )
            continue
        target, role, bound = mapped
        put_payload(
            connection,
            "boundCandidate",
            f"{target}\x00{role}",
            pointer,
            {"typeKey": target, "role": role, "minimum": bound.minimum, "maximum": bound.maximum},
            ordinal=ordinal,
        )
        ordinal += 1
    groups = connection.execute(
        f"""SELECT natural_key,count(*) FROM {STAGE_RELATION}
            WHERE category='boundCandidate' GROUP BY natural_key ORDER BY natural_key"""
    )
    for key, count in groups:
        conflicts = int(
            connection.execute(
                f"SELECT count(*) FROM {STAGE_RELATION} "
                "WHERE category='boundConflict' AND natural_key=?",
                (key,),
            ).fetchone()[0]
        )
        if int(count) != 1 or conflicts:
            rows = connection.execute(
                f"SELECT source_pointer,payload FROM {STAGE_RELATION} "
                "WHERE category='boundCandidate' AND natural_key=? ORDER BY ordinal",
                (key,),
            )
            for pointer, payload_text in rows:
                payload = _decoded(payload_text)
                add_disposition(
                    connection,
                    V1Disposition.OMITTED,
                    "overlapping-relationship-rule",
                    pointer,
                    f"overlapping v1 rules for {payload['typeKey']} {payload['role']} were omitted",
                    target_type_key=str(payload["typeKey"]),
                )
            continue
        row = connection.execute(
            f"SELECT source_pointer,payload FROM {STAGE_RELATION} "
            "WHERE category='boundCandidate' AND natural_key=?",
            (key,),
        ).fetchone()
        assert row is not None
        pointer, payload_text = row
        payload = _decoded(payload_text)
        put_payload(
            connection,
            "mappedBound",
            str(key),
            str(pointer),
            payload,
        )
        add_disposition(
            connection,
            V1Disposition.CONVERTED,
            "local-bound-mapped",
            pointer,
            f"v1 rule maps exactly to {payload['typeKey']} {payload['role']}",
            target_type_key=str(payload["typeKey"]),
        )


def _local_bound(connection, raw):
    if raw.get("kind") != "cardinality" or not isinstance(raw.get("payload"), dict):
        return None
    payload = cast(dict[str, object], raw["payload"])
    if set(payload) - {
        "query_spec",
        "counted_binding",
        "group_by_bindings",
        "minimum",
        "maximum",
    }:
        return None
    query = payload.get("query_spec")
    if not isinstance(query, dict):
        return None
    bound = _source_bound(payload)
    if bound is None:
        return None
    data = query.get("data_requirements", [])
    links = query.get("link_requirements", [])
    anchors = query.get("anchor_buckets", [])
    if not all(isinstance(value, list) for value in (data, links, anchors)):
        return None
    if not _exact_query_fields(query, data, links, anchors):
        return None
    counted, groups = payload.get("counted_binding"), payload.get("group_by_bindings")
    if not isinstance(counted, str) or not isinstance(groups, list) or len(groups) != 1:
        return None
    if len(data) == 1 and len(links) == 0 and len(anchors) == 1:
        return _data_bound(connection, data[0], anchors[0], counted, groups[0], bound)
    if len(links) == 1 and len(data) == 0 and len(anchors) == 2:
        return _link_bound(connection, links[0], anchors, counted, groups[0], bound)
    return None


def _source_bound(payload):
    minimum, maximum = payload.get("minimum", 0), payload.get("maximum")
    if type(minimum) is not int or minimum < 0:
        return None
    if maximum is not None and (type(maximum) is not int or maximum < minimum):
        return None
    return Cardinality(minimum, cast(int | None, maximum))


def _exact_query_fields(query, data, links, anchors):
    if set(query) - {"anchor_buckets", "data_requirements", "link_requirements"}:
        return False
    selectors = (*anchors, *data, *links)
    if any(
        not isinstance(item, dict) or not _nonempty_text(item.get("name")) for item in selectors
    ):
        return False
    selector_names = [item["name"] for item in selectors]
    if len(selector_names) != len(set(selector_names)):
        return False
    if any(
        not isinstance(item, dict)
        or set(item) != {"name", "anchor_type_keys"}
        or not _unique_texts(item.get("anchor_type_keys"))
        for item in anchors
    ):
        return False
    anchor_names = [item["name"] for item in anchors]
    if any(
        not isinstance(item, dict)
        or set(item) != {"name", "anchor_bucket", "data_type_key", "required"}
        or item.get("required") is not False
        or item.get("anchor_bucket") not in anchor_names
        or not _nonempty_text(item.get("data_type_key"))
        for item in data
    ):
        return False
    return all(
        isinstance(item, dict)
        and set(item) == {"name", "source_bucket", "target_bucket", "link_type_keys", "required"}
        and item.get("required") is False
        and _unique_texts(item.get("link_type_keys"))
        and item.get("source_bucket") in anchor_names
        and item.get("target_bucket") in anchor_names
        and item.get("source_bucket") != item.get("target_bucket")
        for item in links
    )


def _unique_texts(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) for item in value)
        and len(value) == len(set(value))
    )


def _nonempty_text(value):
    return isinstance(value, str) and bool(value)


def _bound_targets(raw):
    if raw.get("kind") != "cardinality" or not isinstance(raw.get("payload"), dict):
        return ()
    payload = cast(dict[str, object], raw["payload"])
    query = payload.get("query_spec")
    if not isinstance(query, dict):
        return ()
    counted = payload.get("counted_binding")
    groups = payload.get("group_by_bindings")
    if not isinstance(counted, str) or not isinstance(groups, list):
        return ()
    data = query.get("data_requirements", [])
    links = query.get("link_requirements", [])
    targets = set()
    if isinstance(data, list):
        for requirement in data:
            if isinstance(requirement, dict):
                targets.update(_data_bound_targets(requirement, counted, groups))
    if isinstance(links, list):
        for requirement in links:
            if isinstance(requirement, dict):
                targets.update(_link_bound_targets(requirement, counted, groups))
    return tuple(sorted(targets))


def _data_bound_targets(requirement, counted, groups):
    target = requirement.get("data_type_key")
    name = requirement.get("name")
    anchor = requirement.get("anchor_bucket")
    if not isinstance(target, str) or not isinstance(name, str) or not isinstance(anchor, str):
        return ()
    result = []
    if counted == name and anchor in groups:
        result.append((target, "objectsPerAnchor"))
    if counted == anchor and name in groups:
        result.append((target, "anchorsPerObject"))
    return tuple(result)


def _link_bound_targets(requirement, counted, groups):
    type_keys = requirement.get("link_type_keys")
    name = requirement.get("name")
    source = requirement.get("source_bucket")
    target = requirement.get("target_bucket")
    if (
        not isinstance(type_keys, list)
        or not isinstance(name, str)
        or not isinstance(source, str)
        or not isinstance(target, str)
        or counted != name
    ):
        return ()
    recognizable = sorted({value for value in type_keys if isinstance(value, str) and value})
    result: list[tuple[str, str]] = []
    if source in groups:
        result.extend((type_key, "linksPerSource") for type_key in recognizable)
    if target in groups:
        result.extend((type_key, "linksPerTarget") for type_key in recognizable)
    return tuple(result)


def _data_bound(connection, data, anchor, counted, group, bound):
    if not isinstance(data, dict) or not isinstance(anchor, dict):
        return None
    type_key, anchor_name = data.get("data_type_key"), anchor.get("name")
    definition = _source_definition(connection, type_key)
    if not isinstance(definition, dict) or definition.get("kind") != "data_object":
        return None
    permitted = set(permitted_anchor_keys(connection, str(type_key)))
    actual = set(anchor.get("anchor_type_keys", []))
    if actual != permitted or data.get("anchor_bucket") != anchor_name:
        return None
    if counted == data.get("name") and group == anchor_name:
        return str(type_key), "objectsPerAnchor", bound
    if counted == anchor_name and group == data.get("name"):
        return str(type_key), "anchorsPerObject", bound
    return None


def _link_bound(connection, link, anchors, counted, group, bound):
    if not isinstance(link, dict) or any(not isinstance(item, dict) for item in anchors):
        return None
    type_keys = link.get("link_type_keys")
    if not isinstance(type_keys, list) or len(type_keys) != 1:
        return None
    type_key = type_keys[0]
    definition = _source_definition(connection, type_key)
    if not isinstance(definition, dict) or definition.get("kind") != "link":
        return None
    payload = definition.get("payload", {})
    if not isinstance(payload, dict):
        return None
    expected_source = permitted_link_keys(
        connection, str(type_key), "source", payload.get("allowed_source_types")
    )
    expected_target = permitted_link_keys(
        connection, str(type_key), "target", payload.get("allowed_target_types")
    )
    endpoints = _exact_link_endpoints(link, anchors, expected_source, expected_target)
    if endpoints is None:
        return None
    source, target = endpoints
    if counted != link.get("name"):
        return None
    if group == source.get("name"):
        return str(type_key), "linksPerSource", bound
    if group == target.get("name"):
        return str(type_key), "linksPerTarget", bound
    return None


def _exact_link_endpoints(link, anchors, expected_source, expected_target):
    by_name = {item.get("name"): item for item in anchors}
    source = by_name.get(link.get("source_bucket"))
    target = by_name.get(link.get("target_bucket"))
    if not isinstance(source, dict) or not isinstance(target, dict):
        return None
    if set(source.get("anchor_type_keys", [])) != set(expected_source):
        return None
    if set(target.get("anchor_type_keys", [])) != set(expected_target):
        return None
    return source, target


def _source_definition(connection, type_key):
    for _key, _pointer, raw in _live_definition_rows(connection):
        if raw.get("type_key") == type_key:
            return raw
    return None


def _bound(connection, type_key, role, default):
    row = connection.execute(
        f"SELECT payload FROM {STAGE_RELATION} WHERE category='mappedBound' AND natural_key=?",
        (f"{type_key}\x00{role}",),
    ).fetchone()
    if row is None:
        return default
    payload = _decoded(row[0])
    return Cardinality(int(payload["minimum"]), cast(int | None, payload["maximum"]))


def _decoded(value):
    from vellis.v1_json import decode_legacy_json

    payload = decode_legacy_json(str(value))
    assert isinstance(payload, dict)
    return payload


def _declared_kind(value):
    return {
        "string": "text",
        "uuid": "text",
        "boolean": "boolean",
        "integer": "integer",
        "number": "number",
    }.get(value)


def _source_kind(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if isinstance(value, Decimal):
        return "number"
    if isinstance(value, str):
        return "text"
    return "nested"


def _safe_integer(value):
    return type(value) is int and SAFE_INTEGER_MINIMUM <= value <= SAFE_INTEGER_MAXIMUM


def _finite_number(value):
    if type(value) is int:
        return SAFE_INTEGER_MINIMUM <= value <= SAFE_INTEGER_MAXIMUM
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError, ValueError:
        return False


def _scalar(value, kind):
    if value is None:
        return None
    try:
        if kind is ValueKind.BOOLEAN and type(value) is bool:
            return ScalarValue.boolean(value)
        if kind is ValueKind.INTEGER and _safe_integer(value):
            return ScalarValue.integer(value)
        if kind is ValueKind.NUMBER and _finite_number(value):
            return ScalarValue.number(float(value))
        if kind is ValueKind.TEXT and isinstance(value, str):
            return ScalarValue.text(value)
    except ValueError, OverflowError:
        return None
    return None


def _optional_natural(value):
    return value if type(value) is int and value >= 0 else None


def _text_set(value, pointer):
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise V1ImportError(f"{pointer} has no nonempty permitted type set")
    if len(set(value)) != len(value):
        raise V1ImportError(f"{pointer} has duplicate permitted type keys")
    return tuple(sorted(value))


def _optional_text_collection(raw, name, pointer):
    if name not in raw:
        return []
    value = raw[name]
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(set(value))
    ):
        raise V1ImportError(
            f"{append_pointer(pointer, name)} must be a text array without duplicates"
        )
    return value


def _optional_text(value):
    return value if isinstance(value, str) else None
