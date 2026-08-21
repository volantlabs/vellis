"""Framework-free public JSON projection for validated successor-domain results."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, cast

from vellis.change_domain import (
    DraftChangeResult,
    DraftInspectionPayload,
    DraftInspectionResult,
    ValidationResult,
)
from vellis.domain import (
    AssociatedData,
    Finding,
    OperationOutcome,
    PropertyDefinition,
    ScalarValue,
    TimestampValue,
)
from vellis.history_domain import HistoryResult
from vellis.query_domain import (
    HydratedObject,
    IdentityQueryPayload,
    PatternMatch,
    PatternQueryPayload,
    QueryResult,
)

_REQUIRED_NULL_FIELDS = frozenset(
    {
        "vellis.change_domain.DraftInspectionEntry.current",
        "vellis.change_domain.DraftInspectionEntry.proposed",
    }
)

_OMITTED_NULL_FIELDS = frozenset(
    {
        "vellis.change_domain.DraftChangeResult.payload",
        "vellis.change_domain.DraftInspectionPayload.cursor",
        "vellis.change_domain.DraftInspectionResult.payload",
        "vellis.change_domain.ValidationPayload.cursor",
        "vellis.change_domain.ValidationPayload.effective_draft_change_count",
        "vellis.change_domain.ValidationPayload.raw_draft_entry_count",
        "vellis.change_domain.ValidationResult.payload",
        "vellis.domain.Anchor.system",
        "vellis.domain.AnchorTypeDefinition.system",
        "vellis.domain.AssociatedData.system",
        "vellis.domain.AssociatedDataTypeDefinition.system",
        "vellis.domain.Cardinality.maximum",
        "vellis.domain.Finding.path",
        "vellis.domain.Link.system",
        "vellis.domain.LinkTypeDefinition.system",
        "vellis.domain.OperationOutcome.evaluated_revision",
        "vellis.domain.OperationOutcome.resulting_revision",
        "vellis.domain.PropertyDefinition.maximum",
        "vellis.domain.PropertyDefinition.maximum_length",
        "vellis.domain.PropertyDefinition.minimum",
        "vellis.domain.PropertyDefinition.minimum_length",
        "vellis.domain.PropertyDefinition.pattern",
        "vellis.domain.SystemEnvelope.legacy_v1",
        "vellis.history_domain.ActivityHistoryEntry.evaluated_revision",
        "vellis.history_domain.ActivityHistoryEntry.resulting_revision",
        "vellis.history_domain.ActivityHistoryEntry.source",
        "vellis.history_domain.ActivityHistoryEntry.verbose_payload",
        "vellis.history_domain.CanonicalHistoryEntry.source",
        "vellis.history_domain.HistoryResult.evaluated_revision",
        "vellis.history_domain.HistoryResult.payload",
        "vellis.query_domain.HydratedObject.display_name",
        "vellis.query_domain.HydratedObject.properties",
        "vellis.query_domain.HydratedObject.source_uuid",
        "vellis.query_domain.HydratedObject.system",
        "vellis.query_domain.HydratedObject.target_uuid",
        "vellis.query_domain.QueryResult.evaluated_revision",
        "vellis.query_domain.QueryResult.payload",
        "vellis.query_domain.TypeInspectionResult.evaluated_revision",
        "vellis.query_domain.TypeInspectionResult.neighborhoods",
        "vellis.query_domain.TypeSummaryResult.anchor_types",
        "vellis.query_domain.TypeSummaryResult.evaluated_revision",
    }
)


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(value.capitalize() for value in tail)


def public_result(value: object) -> dict[str, object]:
    if isinstance(value, QueryResult):
        result = _header(value)
        if value.payload is not None:
            result.update(_query_payload(value.payload))
        else:
            _project_none(result, value, "payload")
        return result
    if isinstance(value, HistoryResult):
        result = _header(value)
        if value.payload is not None:
            result.update(_object(value.payload))
        else:
            _project_none(result, value, "payload")
        return result
    if isinstance(value, DraftChangeResult | DraftInspectionResult | ValidationResult):
        result = _object(value.outcome)
        if value.payload is not None:
            if isinstance(value.payload, DraftInspectionPayload):
                result.update(_object(value.payload.counts))
                detail = _object(value.payload)
                detail.pop("counts", None)
                result.update(detail)
            else:
                result.update(_object(value.payload))
        else:
            _project_none(result, value, "payload")
        return result
    if isinstance(value, OperationOutcome):
        return _object(value)
    if is_dataclass(value):
        return _object(value)
    raise TypeError(f"no public result projection for {type(value).__name__}")


def _header(value: object) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in ("status", "summary", "findings", "evaluated_revision"):
        member = getattr(value, name)
        if member is None:
            _project_none(result, value, name)
        elif name != "findings" or member:
            result[_camel(name)] = _value(member)
    return result


def _query_payload(value: IdentityQueryPayload | PatternQueryPayload) -> dict[str, object]:
    if isinstance(value, IdentityQueryPayload):
        return {
            "foundUuids": _value(value.found_uuids),
            "missingUuids": _value(value.missing_uuids),
            "objects": _object_map(value.objects),
        }
    return {
        "matches": _value(value.matches),
        "objects": _object_map(value.objects),
    }


def _object_map(values: tuple[HydratedObject, ...]) -> dict[str, object]:
    return {value.uuid: _value(value) for value in values}


def _object(value: object) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in fields(cast(Any, value)):
        if item.name.startswith("_"):
            continue
        if (
            isinstance(value, PropertyDefinition)
            and item.name == "allowed_values"
            and not value.allowed_values_present
        ):
            continue
        member = getattr(value, item.name)
        if member is None:
            _project_none(result, value, item.name)
            continue
        if isinstance(value, Finding) and item.name in {"type_keys", "uuids"} and not member:
            continue
        result[_camel(item.name)] = _value(member)
    return result


def _project_none(result: dict[str, object], owner: object, name: str) -> None:
    key = f"{type(owner).__module__}.{type(owner).__qualname__}.{name}"
    if key in _REQUIRED_NULL_FIELDS:
        result[_camel(name)] = None
        return
    if key not in _OMITTED_NULL_FIELDS:
        raise TypeError(f"unclassified public None field: {key}")


def _value(value: object) -> object:
    if isinstance(value, ScalarValue):
        return value.wire_value()
    if isinstance(value, TimestampValue):
        return value.canonical
    if isinstance(value, PatternMatch):
        return {"bindings": dict(value.bindings)}
    if isinstance(value, AssociatedData):
        result = _object(value)
        result["properties"] = {name: _value(member) for name, member in value.properties}
        return result
    if isinstance(value, HydratedObject):
        result = _object(value)
        if value.properties is not None:
            result["properties"] = {name: _value(member) for name, member in value.properties}
        return result
    return _container_or_plain_value(value)


def _container_or_plain_value(value: object) -> object:
    if isinstance(value, tuple | list):
        return [_value(member) for member in value]
    if isinstance(value, dict):
        return {str(key): _value(member) for key, member in value.items()}
    if is_dataclass(value):
        return _object(value)
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return value
