"""Framework-free values for the accepted Vellis RTG domain."""

from __future__ import annotations

import json
import math
import re
import uuid as uuid_module
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from enum import StrEnum

SAFE_INTEGER_MINIMUM = -9_007_199_254_740_991
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
PUBLIC_ITEM_LIMIT = 1_000

_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_TIMESTAMP_PATTERN = re.compile(
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})T"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?"
    r"(?P<offset>Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_JSON_NUMBER_PATTERN = re.compile(
    r"(?P<sign>-?)(?P<integer>0|[1-9][0-9]*)"
    r"(?:\.(?P<fraction>[0-9]+))?(?:[eE](?P<exponent>[+-]?[0-9]+))?\Z"
)


class _JsonNumber(str):
    pass


class ValueKind(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    TEXT = "text"
    DATE = "date"
    TIMESTAMP = "timestamp"


class ObjectKind(StrEnum):
    ANCHOR = "anchor"
    ASSOCIATED_DATA = "associatedData"
    LINK = "link"


class DefinitionKind(StrEnum):
    ANCHOR = "anchor"
    ASSOCIATED_DATA = "associatedData"
    LINK = "link"


class StateKind(StrEnum):
    CURRENT = "current"
    DRAFT = "draft"
    REVISION = "revision"
    TIME = "time"


class TransitionKind(StrEnum):
    INITIALIZATION = "initialization"
    GRAPH_CHANGE = "graphChange"
    DRAFT_ACTIVATION = "draftActivation"
    RESTORE = "restore"


class FindingCode(StrEnum):
    DUPLICATE = "duplicate"
    MISSING = "missing"
    UNKNOWN = "unknown"
    KIND_MISMATCH = "kindMismatch"
    INVALID_VALUE = "invalidValue"
    CONSTRAINT_VIOLATION = "constraintViolation"
    CARDINALITY_VIOLATION = "cardinalityViolation"
    CONFLICT = "conflict"
    STALE_REVISION = "staleRevision"
    EXPIRED_CURSOR = "expiredCursor"
    RESULT_LIMIT_EXCEEDED = "resultLimitExceeded"
    INTEGRITY_FAILURE = "integrityFailure"


class OperationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Finding:
    code: FindingCode
    summary: str
    path: str | None = None
    type_keys: tuple[str, ...] = ()
    uuids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, FindingCode) or not isinstance(self.summary, str):
            raise ValueError("finding code and summary have invalid types")
        if self.summary == "":
            raise ValueError("finding summary must be nonempty")
        _require_optional_text(self.path, "finding path")
        _require_text_tuple(self.type_keys, "finding type keys")
        _require_text_tuple(self.uuids, "finding UUIDs")
        object.__setattr__(self, "type_keys", tuple(sorted(set(self.type_keys))))
        object.__setattr__(
            self,
            "uuids",
            tuple(sorted({canonical_uuid(value) for value in self.uuids})),
        )


@dataclass(frozen=True, slots=True)
class OperationOutcome:
    status: OperationStatus
    summary: str
    findings: tuple[Finding, ...] = ()
    evaluated_revision: int | None = None
    resulting_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperationStatus) or not isinstance(self.summary, str):
            raise ValueError("operation status and summary have invalid types")
        if self.summary == "":
            raise ValueError("operation summary must be nonempty")
        _require_instance_tuple(self.findings, Finding, "operation findings")
        _require_optional_revision(self.evaluated_revision)
        _require_optional_revision(self.resulting_revision)
        object.__setattr__(
            self,
            "findings",
            tuple(
                sorted(
                    self.findings,
                    key=lambda value: (
                        value.code.value,
                        value.path or "",
                        value.type_keys,
                        value.uuids,
                        value.summary,
                    ),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class TimestampValue:
    epoch_seconds: int
    nanosecond: int
    canonical: str

    def __post_init__(self) -> None:
        if type(self.epoch_seconds) is not int or type(self.nanosecond) is not int:
            raise ValueError("timestamp numeric fields must be integers")
        if not 0 <= self.nanosecond <= 999_999_999:
            raise ValueError("timestamp nanosecond is outside its valid range")
        epoch_seconds, nanosecond, canonical = _timestamp_parts(self.canonical)
        if (self.epoch_seconds, self.nanosecond, self.canonical) != (
            epoch_seconds,
            nanosecond,
            canonical,
        ):
            raise ValueError("timestamp fields do not describe one canonical instant")


ScalarContent = bool | int | float | str | TimestampValue


@dataclass(frozen=True, slots=True)
class ScalarValue:
    kind: ValueKind
    value: ScalarContent

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ValueKind):
            raise ValueError("scalar kind must be a ValueKind")
        if self.kind is ValueKind.NUMBER and isinstance(self.value, float) and self.value == 0.0:
            object.__setattr__(self, "value", 0.0)
        _validate_scalar_content(self.kind, self.value)

    @classmethod
    def boolean(cls, value: bool) -> ScalarValue:
        if not isinstance(value, bool):
            raise ValueError("boolean value must be a Boolean")
        return cls(ValueKind.BOOLEAN, value)

    @classmethod
    def integer(cls, value: int) -> ScalarValue:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("integer value must be an integer, not a Boolean")
        if not SAFE_INTEGER_MINIMUM <= value <= SAFE_INTEGER_MAXIMUM:
            raise ValueError("integer value is outside the safe-integer range")
        return cls(ValueKind.INTEGER, value)

    @classmethod
    def number(cls, value: int | float) -> ScalarValue:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("number value must be an integer or float, not a Boolean")
        try:
            converted = float(value)
        except OverflowError as error:
            raise ValueError("number value must be finite binary64") from error
        if not math.isfinite(converted):
            raise ValueError("number value must be finite binary64")
        if converted == 0.0:
            converted = 0.0
        return cls(ValueKind.NUMBER, converted)

    @classmethod
    def text(cls, value: str) -> ScalarValue:
        if not isinstance(value, str):
            raise ValueError("text value must be a string")
        return cls(ValueKind.TEXT, value)

    @classmethod
    def date(cls, value: str) -> ScalarValue:
        return cls(ValueKind.DATE, canonical_date(value))

    @classmethod
    def timestamp(cls, value: str) -> ScalarValue:
        return cls(ValueKind.TIMESTAMP, parse_timestamp(value))

    def wire_value(self) -> bool | int | float | str:
        if isinstance(self.value, TimestampValue):
            return self.value.canonical
        return self.value


@dataclass(frozen=True, slots=True)
class Cardinality:
    minimum: int
    maximum: int | None = None

    def __post_init__(self) -> None:
        if type(self.minimum) is not int or (
            self.maximum is not None and type(self.maximum) is not int
        ):
            raise ValueError("cardinality bounds must be integers")
        if self.minimum < 0 or (self.maximum is not None and self.maximum < self.minimum):
            raise ValueError("cardinality bounds are invalid")


@dataclass(frozen=True, slots=True)
class PropertyDefinition:
    name: str
    description: str
    value_kind: ValueKind
    required: bool = False
    nullable: bool = False
    allowed_values: tuple[ScalarValue, ...] = ()
    minimum: ScalarValue | None = None
    maximum: ScalarValue | None = None
    minimum_length: int | None = None
    maximum_length: int | None = None
    pattern: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not isinstance(self.description, str):
            raise ValueError("property name and description must be text")
        if not isinstance(self.value_kind, ValueKind):
            raise ValueError("property value kind must be a ValueKind")
        if type(self.required) is not bool or type(self.nullable) is not bool:
            raise ValueError("property required and nullable flags must be Boolean")
        _require_instance_tuple(self.allowed_values, ScalarValue, "allowed values")
        _require_optional_instance(self.minimum, ScalarValue, "minimum")
        _require_optional_instance(self.maximum, ScalarValue, "maximum")
        _require_optional_int(self.minimum_length, "minimum length")
        _require_optional_int(self.maximum_length, "maximum length")
        _require_optional_text(self.pattern, "property pattern")


@dataclass(frozen=True, slots=True)
class SystemEnvelope:
    created_revision: int
    last_changed_revision: int
    legacy_v1: str | None = None

    def __post_init__(self) -> None:
        if type(self.created_revision) is not int or type(self.last_changed_revision) is not int:
            raise ValueError("system revisions must be integers")
        if self.created_revision < 0 or self.last_changed_revision < self.created_revision:
            raise ValueError("system revision order is invalid")
        if self.legacy_v1 is not None:
            _require_canonical_json_text(self.legacy_v1)


@dataclass(frozen=True, slots=True)
class AnchorTypeDefinition:
    type_key: str
    description: str
    system: SystemEnvelope | None = None
    kind: DefinitionKind = field(default=DefinitionKind.ANCHOR, init=False)

    def __post_init__(self) -> None:
        _validate_definition_header(self.type_key, self.description, self.system)


@dataclass(frozen=True, slots=True)
class AssociatedDataTypeDefinition:
    type_key: str
    description: str
    permitted_anchor_type_keys: tuple[str, ...]
    properties: tuple[PropertyDefinition, ...]
    anchors_per_object: Cardinality
    objects_per_anchor: Cardinality
    system: SystemEnvelope | None = None
    kind: DefinitionKind = field(default=DefinitionKind.ASSOCIATED_DATA, init=False)

    def __post_init__(self) -> None:
        _validate_definition_header(self.type_key, self.description, self.system)
        _require_text_tuple(self.permitted_anchor_type_keys, "permitted anchor type keys")
        _require_instance_tuple(self.properties, PropertyDefinition, "property definitions")
        _require_instance(self.anchors_per_object, Cardinality, "anchors per object")
        _require_instance(self.objects_per_anchor, Cardinality, "objects per anchor")


@dataclass(frozen=True, slots=True)
class LinkTypeDefinition:
    type_key: str
    description: str
    permitted_source_type_keys: tuple[str, ...]
    permitted_target_type_keys: tuple[str, ...]
    links_per_source: Cardinality
    links_per_target: Cardinality
    system: SystemEnvelope | None = None
    kind: DefinitionKind = field(default=DefinitionKind.LINK, init=False)

    def __post_init__(self) -> None:
        _validate_definition_header(self.type_key, self.description, self.system)
        _require_text_tuple(self.permitted_source_type_keys, "permitted source type keys")
        _require_text_tuple(self.permitted_target_type_keys, "permitted target type keys")
        _require_instance(self.links_per_source, Cardinality, "links per source")
        _require_instance(self.links_per_target, Cardinality, "links per target")


TypeDefinition = AnchorTypeDefinition | AssociatedDataTypeDefinition | LinkTypeDefinition


@dataclass(frozen=True, slots=True)
class Anchor:
    uuid: str
    type_key: str
    display_name: str
    system: SystemEnvelope | None = None
    kind: ObjectKind = field(default=ObjectKind.ANCHOR, init=False)

    def __post_init__(self) -> None:
        _validate_object_header_types(self.type_key, self.system)
        if not isinstance(self.display_name, str):
            raise ValueError("anchor display name must be text")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))


@dataclass(frozen=True, slots=True)
class AssociatedData:
    uuid: str
    type_key: str
    anchor_uuids: tuple[str, ...]
    properties: tuple[tuple[str, ScalarValue | None], ...] = ()
    system: SystemEnvelope | None = None
    kind: ObjectKind = field(default=ObjectKind.ASSOCIATED_DATA, init=False)

    def __post_init__(self) -> None:
        _validate_object_header_types(self.type_key, self.system)
        _require_text_tuple(self.anchor_uuids, "associated anchor UUIDs")
        _require_property_tuple(self.properties, "associated data properties")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))
        object.__setattr__(
            self,
            "anchor_uuids",
            tuple(sorted(canonical_uuid(value) for value in self.anchor_uuids)),
        )


@dataclass(frozen=True, slots=True)
class Link:
    uuid: str
    type_key: str
    source_uuid: str
    target_uuid: str
    system: SystemEnvelope | None = None
    kind: ObjectKind = field(default=ObjectKind.LINK, init=False)

    def __post_init__(self) -> None:
        _validate_object_header_types(self.type_key, self.system)
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))
        object.__setattr__(self, "source_uuid", canonical_uuid(self.source_uuid))
        object.__setattr__(self, "target_uuid", canonical_uuid(self.target_uuid))


GraphObject = Anchor | AssociatedData | Link


@dataclass(frozen=True, slots=True)
class CurrentState:
    kind: StateKind = field(default=StateKind.CURRENT, init=False)


@dataclass(frozen=True, slots=True)
class DraftState:
    kind: StateKind = field(default=StateKind.DRAFT, init=False)


@dataclass(frozen=True, slots=True)
class RevisionState:
    revision: int
    kind: StateKind = field(default=StateKind.REVISION, init=False)

    def __post_init__(self) -> None:
        _require_revision(self.revision)


@dataclass(frozen=True, slots=True)
class TimeState:
    timestamp: TimestampValue
    kind: StateKind = field(default=StateKind.TIME, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, TimestampValue):
            raise ValueError("time state requires a timestamp")


StateSelection = CurrentState | DraftState | RevisionState | TimeState


@dataclass(frozen=True, slots=True)
class AnchorUpsert:
    uuid: str
    type_key: str | None = None
    display_name: str | None = None
    kind: ObjectKind = field(default=ObjectKind.ANCHOR, init=False)

    def __post_init__(self) -> None:
        _require_optional_text(self.type_key, "anchor upsert type key")
        _require_optional_text(self.display_name, "anchor upsert display name")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))


@dataclass(frozen=True, slots=True)
class AssociatedDataUpsert:
    uuid: str
    type_key: str | None = None
    anchor_uuids: tuple[str, ...] | None = None
    add_anchor_uuids: tuple[str, ...] = ()
    remove_anchor_uuids: tuple[str, ...] = ()
    set_properties: tuple[tuple[str, ScalarValue | None], ...] = ()
    remove_properties: tuple[str, ...] = ()
    kind: ObjectKind = field(default=ObjectKind.ASSOCIATED_DATA, init=False)

    def __post_init__(self) -> None:
        _require_optional_text(self.type_key, "associated-data upsert type key")
        if self.anchor_uuids is not None:
            _require_text_tuple(self.anchor_uuids, "complete anchor UUIDs")
        _require_text_tuple(self.add_anchor_uuids, "added anchor UUIDs")
        _require_text_tuple(self.remove_anchor_uuids, "removed anchor UUIDs")
        _require_property_tuple(self.set_properties, "set properties")
        _require_text_tuple(self.remove_properties, "removed properties")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))
        if self.anchor_uuids is not None:
            object.__setattr__(self, "anchor_uuids", _canonical_uuid_tuple(self.anchor_uuids))
        object.__setattr__(self, "add_anchor_uuids", _canonical_uuid_tuple(self.add_anchor_uuids))
        object.__setattr__(
            self, "remove_anchor_uuids", _canonical_uuid_tuple(self.remove_anchor_uuids)
        )


@dataclass(frozen=True, slots=True)
class LinkUpsert:
    uuid: str
    type_key: str | None = None
    source_uuid: str | None = None
    target_uuid: str | None = None
    kind: ObjectKind = field(default=ObjectKind.LINK, init=False)

    def __post_init__(self) -> None:
        _require_optional_text(self.type_key, "link upsert type key")
        _require_optional_text(self.source_uuid, "link upsert source UUID")
        _require_optional_text(self.target_uuid, "link upsert target UUID")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))
        if self.source_uuid is not None:
            object.__setattr__(self, "source_uuid", canonical_uuid(self.source_uuid))
        if self.target_uuid is not None:
            object.__setattr__(self, "target_uuid", canonical_uuid(self.target_uuid))


ObjectUpsert = AnchorUpsert | AssociatedDataUpsert | LinkUpsert


@dataclass(frozen=True, slots=True)
class GraphChangeRequest:
    expected_revision: int
    upserts: tuple[ObjectUpsert, ...] = ()
    remove_uuids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_revision(self.expected_revision)
        _require_instance_tuple(
            self.upserts,
            (AnchorUpsert, AssociatedDataUpsert, LinkUpsert),
            "graph upserts",
        )
        _require_text_tuple(self.remove_uuids, "removed object UUIDs")
        object.__setattr__(self, "remove_uuids", _canonical_uuid_tuple(self.remove_uuids))


@dataclass(frozen=True, slots=True)
class ResolvedState:
    evaluated_revision: int
    includes_draft: bool = False

    def __post_init__(self) -> None:
        _require_revision(self.evaluated_revision)
        if type(self.includes_draft) is not bool:
            raise ValueError("draft inclusion must be Boolean")


def canonical_uuid(value: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("UUID must be a valid hyphenated UUID")
    if any(value[index] != "-" for index in (8, 13, 18, 23)):
        raise ValueError("UUID must be a valid hyphenated UUID")
    try:
        parsed = uuid_module.UUID(value)
    except (AttributeError, ValueError) as error:
        raise ValueError("UUID must be a valid hyphenated UUID") from error
    canonical = str(parsed)
    return canonical


def canonical_date(value: str) -> str:
    if not isinstance(value, str) or _DATE_PATTERN.fullmatch(value) is None:
        raise ValueError("date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("date must be a valid Gregorian date") from error
    if not 1 <= parsed.year <= 9999:
        raise ValueError("date year must be between 0001 and 9999")
    return parsed.isoformat()


def parse_timestamp(value: str) -> TimestampValue:
    epoch_seconds, nanosecond, canonical = _timestamp_parts(value)
    return TimestampValue(epoch_seconds, nanosecond, canonical)


def _timestamp_parts(value: str) -> tuple[int, int, str]:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    match = _TIMESTAMP_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("timestamp must be offset-aware RFC 3339 with seconds")
    second = int(match.group("second"))
    if second > 59:
        raise ValueError("timestamp leap seconds are unsupported")
    offset = _parse_offset(match.group("offset"))
    year, month, day = map(int, match.group("date").split("-"))
    try:
        local = datetime(
            year,
            month,
            day,
            int(match.group("hour")),
            int(match.group("minute")),
            second,
            tzinfo=offset,
        )
        normalized = local.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError("timestamp is outside the supported calendar range") from error
    fraction = match.group("fraction") or ""
    nanosecond = int(fraction.ljust(9, "0")) if fraction else 0
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    epoch_seconds = delta.days * 86_400 + delta.seconds
    base = normalized.strftime("%Y-%m-%dT%H:%M:%S")
    suffix = "" if nanosecond == 0 else f".{nanosecond:09d}".rstrip("0")
    return epoch_seconds, nanosecond, f"{base}{suffix}Z"


def _parse_offset(value: str) -> tzinfo:
    if value == "Z":
        return UTC
    if value == "-00:00":
        raise ValueError("timestamp offset must be known")
    sign = 1 if value[0] == "+" else -1
    hours, minutes = map(int, value[1:].split(":"))
    if hours > 23 or minutes > 59:
        raise ValueError("timestamp offset is invalid")
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def canonical_number_text(value: float) -> str:
    normalized = ScalarValue.number(value).value
    assert isinstance(normalized, float)
    text = repr(normalized)
    lower = text.lower()
    if "e" in lower:
        mantissa, exponent = lower.split("e", 1)
        if normalized.is_integer() and "." not in mantissa:
            mantissa = f"{mantissa}.0"
        return f"{mantissa}e{int(exponent)}"
    if normalized.is_integer() and "." not in lower:
        return f"{text}.0"
    return lower


def _require_revision(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("revision must be a nonnegative integer")


def _validate_scalar_content(kind: ValueKind, value: ScalarContent) -> None:
    if kind is ValueKind.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("Boolean scalar content is invalid")
        return
    if kind in {ValueKind.INTEGER, ValueKind.NUMBER}:
        _validate_numeric_content(kind, value)
        return
    if kind is ValueKind.TIMESTAMP:
        if not isinstance(value, TimestampValue):
            raise ValueError("timestamp scalar content is invalid")
        return
    if not isinstance(value, str):
        raise ValueError(f"{kind.value} scalar content is invalid")
    if kind is ValueKind.DATE and canonical_date(value) != value:
        raise ValueError("date scalar content is not canonical")


def _validate_numeric_content(kind: ValueKind, value: ScalarContent) -> None:
    if kind is ValueKind.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("integer scalar content is invalid")
        if not SAFE_INTEGER_MINIMUM <= value <= SAFE_INTEGER_MAXIMUM:
            raise ValueError("integer scalar content is outside the safe-integer range")
        return
    if not isinstance(value, float) or not math.isfinite(value):
        raise ValueError("number scalar content must be finite binary64")


def _canonical_uuid_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(canonical_uuid(value) for value in values))


def _validate_definition_header(
    type_key: str, description: str, system: SystemEnvelope | None
) -> None:
    if not isinstance(type_key, str) or not isinstance(description, str):
        raise ValueError("definition type key and description must be text")
    _require_optional_instance(system, SystemEnvelope, "definition system envelope")


def _validate_object_header_types(type_key: str, system: SystemEnvelope | None) -> None:
    if not isinstance(type_key, str):
        raise ValueError("object type key must be text")
    _require_optional_instance(system, SystemEnvelope, "object system envelope")


def _require_instance(value: object, expected: type[object], label: str) -> None:
    if not isinstance(value, expected):
        raise ValueError(f"{label} has an invalid type")


def _require_optional_instance(value: object, expected: type[object], label: str) -> None:
    if value is not None:
        _require_instance(value, expected, label)


def _require_instance_tuple(
    values: object,
    expected: type[object] | tuple[type[object], ...],
    label: str,
) -> None:
    if not isinstance(values, tuple) or any(not isinstance(value, expected) for value in values):
        raise ValueError(f"{label} must be an immutable typed tuple")


def _require_text_tuple(values: object, label: str) -> None:
    _require_instance_tuple(values, str, label)


def _require_property_tuple(values: object, label: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{label} must be an immutable typed tuple")
    for item in values:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or (item[1] is not None and not isinstance(item[1], ScalarValue))
        ):
            raise ValueError(f"{label} contains an invalid entry")


def _require_optional_text(value: object, label: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be text")


def _require_optional_int(value: object, label: str) -> None:
    if value is not None and type(value) is not int:
        raise ValueError(f"{label} must be an integer")


def _require_optional_revision(value: object) -> None:
    if value is not None:
        _require_revision(value)  # type: ignore[arg-type]


def _require_canonical_json_text(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("legacyV1 must be canonical JSON text")
    try:
        decoded = json.loads(
            value,
            parse_int=_JsonNumber,
            parse_float=_JsonNumber,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_json_object,
        )
        canonical = _encode_canonical_json(decoded)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("legacyV1 must be canonical JSON text") from error
    if canonical != value:
        raise ValueError("legacyV1 must be canonical JSON text")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _encode_canonical_json(value: object) -> str:
    if isinstance(value, _JsonNumber):
        return _canonical_json_number(value)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_encode_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        members = (
            f"{json.dumps(key, ensure_ascii=False)}:{_encode_canonical_json(value[key])}"
            for key in sorted(value)
        )
        return "{" + ",".join(members) + "}"
    raise ValueError("unsupported JSON value")


def _canonical_json_number(value: str) -> str:
    match = _JSON_NUMBER_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("invalid JSON number")
    sign = match.group("sign")
    fraction = match.group("fraction") or ""
    digits = (match.group("integer") + fraction).lstrip("0")
    if digits == "":
        return "0"
    exponent = int(match.group("exponent") or "0") - len(fraction)
    while digits.endswith("0"):
        digits = digits[:-1]
        exponent += 1
    plain_length = _plain_decimal_length(len(digits), exponent)
    scientific_exponent = len(digits) - 1 + exponent
    scientific = _scientific_decimal(digits, scientific_exponent)
    if plain_length <= len(scientific):
        body = _plain_decimal(digits, exponent)
    else:
        body = scientific
    return sign + body


def _plain_decimal_length(digit_count: int, exponent: int) -> int:
    point = digit_count + exponent
    if exponent >= 0:
        return point
    if point > 0:
        return digit_count + 1
    return 2 - point + digit_count


def _plain_decimal(digits: str, exponent: int) -> str:
    point = len(digits) + exponent
    if exponent >= 0:
        return digits + ("0" * exponent)
    if point > 0:
        return f"{digits[:point]}.{digits[point:]}"
    return "0." + ("0" * -point) + digits


def _scientific_decimal(digits: str, exponent: int) -> str:
    coefficient = digits[0] if len(digits) == 1 else f"{digits[0]}.{digits[1:]}"
    return coefficient if exponent == 0 else f"{coefficient}e{exponent}"
