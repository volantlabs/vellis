"""Framework-free values for progressive discovery and one bounded graph query."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from vellis.domain import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    CurrentState,
    DraftState,
    Finding,
    LinkTypeDefinition,
    ObjectKind,
    OperationStatus,
    RevisionState,
    ScalarValue,
    StateSelection,
    SystemEnvelope,
    TimeState,
    TypeDefinition,
    canonical_uuid,
)


class PatternNodeKind(StrEnum):
    ANCHOR = "anchor"
    ASSOCIATED_DATA = "associatedData"


class PredicateOperator(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    IS_NULL = "isNull"
    IS_NOT_NULL = "isNotNull"
    EQUAL = "equal"
    NOT_EQUAL = "notEqual"
    LESS_THAN = "lessThan"
    LESS_THAN_OR_EQUAL = "lessThanOrEqual"
    GREATER_THAN = "greaterThan"
    GREATER_THAN_OR_EQUAL = "greaterThanOrEqual"
    ANY_OF = "anyOf"
    CONTAINS = "contains"
    PREFIX = "prefix"
    REGEX = "regex"
    ALL_TERMS = "allTerms"
    ANY_TERMS = "anyTerms"
    PHRASE = "phrase"


@dataclass(frozen=True, slots=True)
class PropertySelection:
    names: tuple[str, ...] = ()
    all: bool = False

    def __post_init__(self) -> None:
        _text_tuple(self.names, "property names")
        if type(self.all) is not bool:
            raise ValueError("property all flag must be Boolean")
        if self.all and self.names:
            raise ValueError("property selection cannot combine all with names")


@dataclass(frozen=True, slots=True)
class IdentityObjectSelection:
    uuid: str
    properties: PropertySelection | None = None
    include_legacy_system: bool = False

    def __post_init__(self) -> None:
        if self.properties is not None and not isinstance(self.properties, PropertySelection):
            raise ValueError("identity properties must be a property selection")
        if type(self.include_legacy_system) is not bool:
            raise ValueError("legacy-system selection must be Boolean")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))


@dataclass(frozen=True, slots=True)
class IdentitySelection:
    objects: tuple[IdentityObjectSelection, ...]
    kind: str = field(default="identities", init=False)

    def __post_init__(self) -> None:
        _instance_tuple(self.objects, IdentityObjectSelection, "identity objects")


@dataclass(frozen=True, slots=True)
class DisplayNameField:
    kind: str = field(default="displayName", init=False)


@dataclass(frozen=True, slots=True)
class PropertyField:
    name: str
    kind: str = field(default="property", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise ValueError("property field name must be text")


PredicateField = DisplayNameField | PropertyField


@dataclass(frozen=True, slots=True)
class Predicate:
    field: PredicateField
    operator: PredicateOperator
    value: ScalarValue | None = None
    values: tuple[ScalarValue | None, ...] = ()
    text: str | None = None
    terms: tuple[str, ...] = ()
    case_sensitive: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.field, DisplayNameField | PropertyField):
            raise ValueError("predicate field has an invalid type")
        if not isinstance(self.operator, PredicateOperator):
            raise ValueError("predicate operator has an invalid type")
        if self.value is not None and not isinstance(self.value, ScalarValue):
            raise ValueError("predicate value must be scalar")
        if not isinstance(self.values, tuple) or any(
            value is not None and not isinstance(value, ScalarValue) for value in self.values
        ):
            raise ValueError("predicate values must be a tuple of scalar or null values")
        if self.text is not None and not isinstance(self.text, str):
            raise ValueError("predicate text must be text")
        _text_tuple(self.terms, "predicate terms")
        if type(self.case_sensitive) is not bool:
            raise ValueError("predicate caseSensitive must be Boolean")


@dataclass(frozen=True, slots=True)
class PatternNode:
    name: str
    kind: PatternNodeKind
    type_keys: tuple[str, ...] = ()
    uuids: tuple[str, ...] = ()
    predicates: tuple[Predicate, ...] = ()
    properties: PropertySelection | None = None
    include_legacy_system: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not isinstance(self.kind, PatternNodeKind):
            raise ValueError("pattern node name or kind has an invalid type")
        _text_tuple(self.type_keys, "node type keys")
        _text_tuple(self.uuids, "node UUIDs")
        _instance_tuple(self.predicates, Predicate, "node predicates")
        if self.properties is not None and not isinstance(self.properties, PropertySelection):
            raise ValueError("node properties must be a property selection")
        if type(self.include_legacy_system) is not bool:
            raise ValueError("node legacy-system selection must be Boolean")
        object.__setattr__(self, "uuids", tuple(canonical_uuid(value) for value in self.uuids))


@dataclass(frozen=True, slots=True)
class DirectAssociation:
    anchor: str
    associated_data: str

    def __post_init__(self) -> None:
        if not isinstance(self.anchor, str) or not isinstance(self.associated_data, str):
            raise ValueError("direct-association names must be text")


@dataclass(frozen=True, slots=True)
class PatternLink:
    name: str
    source: str
    target: str
    type_keys: tuple[str, ...] = ()
    uuids: tuple[str, ...] = ()
    include_legacy_system: bool = False

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in (self.name, self.source, self.target)):
            raise ValueError("pattern-link names must be text")
        _text_tuple(self.type_keys, "link type keys")
        _text_tuple(self.uuids, "link UUIDs")
        if type(self.include_legacy_system) is not bool:
            raise ValueError("link legacy-system selection must be Boolean")
        object.__setattr__(self, "uuids", tuple(canonical_uuid(value) for value in self.uuids))


@dataclass(frozen=True, slots=True)
class PatternSelection:
    maximum_matches: int
    nodes: tuple[PatternNode, ...]
    direct_associations: tuple[DirectAssociation, ...] = ()
    links: tuple[PatternLink, ...] = ()
    kind: str = field(default="pattern", init=False)

    def __post_init__(self) -> None:
        if type(self.maximum_matches) is not int:
            raise ValueError("maximumMatches must be an integer")
        _instance_tuple(self.nodes, PatternNode, "pattern nodes")
        _instance_tuple(self.direct_associations, DirectAssociation, "direct associations")
        _instance_tuple(self.links, PatternLink, "pattern links")


QuerySelection = IdentitySelection | PatternSelection


@dataclass(frozen=True, slots=True)
class GraphQuery:
    selection: QuerySelection
    state: StateSelection | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.selection, IdentitySelection | PatternSelection):
            raise ValueError("query selection has an invalid type")
        if self.state is not None and not isinstance(
            self.state, CurrentState | DraftState | RevisionState | TimeState
        ):
            raise ValueError("query state has an invalid type")


@dataclass(frozen=True, slots=True)
class HydratedObject:
    uuid: str
    kind: ObjectKind
    type_key: str
    display_name: str | None
    anchor_uuids: tuple[str, ...]
    source_uuid: str | None
    target_uuid: str | None
    properties: tuple[tuple[str, ScalarValue | None], ...] | None
    system: SystemEnvelope | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObjectKind) or not isinstance(self.type_key, str):
            raise ValueError("hydrated object kind or type key is invalid")
        _text_tuple(self.anchor_uuids, "hydrated anchor UUIDs")
        if self.properties is not None:
            _property_tuple(self.properties)
        if self.system is not None and not isinstance(self.system, SystemEnvelope):
            raise ValueError("hydrated system value is invalid")
        object.__setattr__(self, "uuid", canonical_uuid(self.uuid))
        object.__setattr__(
            self, "anchor_uuids", tuple(canonical_uuid(value) for value in self.anchor_uuids)
        )
        if self.source_uuid is not None:
            object.__setattr__(self, "source_uuid", canonical_uuid(self.source_uuid))
        if self.target_uuid is not None:
            object.__setattr__(self, "target_uuid", canonical_uuid(self.target_uuid))
        _hydrated_shape(self)


@dataclass(frozen=True, slots=True)
class PatternMatch:
    bindings: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple) or any(
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], str)
            or not isinstance(value[1], str)
            for value in self.bindings
        ):
            raise ValueError("pattern bindings have invalid types")
        object.__setattr__(
            self,
            "bindings",
            tuple((name, canonical_uuid(uuid)) for name, uuid in self.bindings),
        )


@dataclass(frozen=True, slots=True)
class IdentityQueryPayload:
    found_uuids: tuple[str, ...]
    missing_uuids: tuple[str, ...]
    objects: tuple[HydratedObject, ...]

    def __post_init__(self) -> None:
        _text_tuple(self.found_uuids, "found UUIDs")
        _text_tuple(self.missing_uuids, "missing UUIDs")
        _instance_tuple(self.objects, HydratedObject, "hydrated objects")
        object.__setattr__(
            self, "found_uuids", tuple(canonical_uuid(value) for value in self.found_uuids)
        )
        object.__setattr__(
            self, "missing_uuids", tuple(canonical_uuid(value) for value in self.missing_uuids)
        )


@dataclass(frozen=True, slots=True)
class PatternQueryPayload:
    matches: tuple[PatternMatch, ...]
    objects: tuple[HydratedObject, ...]

    def __post_init__(self) -> None:
        _instance_tuple(self.matches, PatternMatch, "pattern matches")
        _instance_tuple(self.objects, HydratedObject, "hydrated objects")


QueryPayload = IdentityQueryPayload | PatternQueryPayload


@dataclass(frozen=True, slots=True)
class QueryResult:
    status: OperationStatus
    summary: str
    findings: tuple[Finding, ...]
    evaluated_revision: int | None
    payload: QueryPayload | None

    def __post_init__(self) -> None:
        _result_header(self.status, self.summary, self.findings, self.evaluated_revision)
        object.__setattr__(self, "findings", _ordered_findings(self.findings))
        if self.status is OperationStatus.ACCEPTED and not isinstance(
            self.payload, IdentityQueryPayload | PatternQueryPayload
        ):
            raise ValueError("accepted query result requires its payload")
        if self.status is OperationStatus.REJECTED and self.payload is not None:
            raise ValueError("rejected query result cannot carry a payload")


@dataclass(frozen=True, slots=True)
class TypeSummaryResult:
    status: OperationStatus
    summary: str
    findings: tuple[Finding, ...]
    evaluated_revision: int | None
    anchor_types: tuple[TypeDefinition, ...] | None

    def __post_init__(self) -> None:
        _result_header(self.status, self.summary, self.findings, self.evaluated_revision)
        object.__setattr__(self, "findings", _ordered_findings(self.findings))
        if self.status is OperationStatus.ACCEPTED:
            _instance_tuple(self.anchor_types, AnchorTypeDefinition, "anchor type summaries")
        elif self.anchor_types is not None:
            raise ValueError("rejected type summary cannot carry a payload")


@dataclass(frozen=True, slots=True)
class DefinitionNeighborhood:
    anchor_type: TypeDefinition
    associated_data_types: tuple[TypeDefinition, ...]
    link_types: tuple[TypeDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.anchor_type, AnchorTypeDefinition):
            raise ValueError("neighborhood anchor has another definition kind")
        _instance_tuple(
            self.associated_data_types,
            AssociatedDataTypeDefinition,
            "neighborhood associated-data definitions",
        )
        _instance_tuple(self.link_types, LinkTypeDefinition, "neighborhood link definitions")


@dataclass(frozen=True, slots=True)
class TypeInspectionResult:
    status: OperationStatus
    summary: str
    findings: tuple[Finding, ...]
    evaluated_revision: int | None
    neighborhoods: tuple[DefinitionNeighborhood, ...] | None

    def __post_init__(self) -> None:
        _result_header(self.status, self.summary, self.findings, self.evaluated_revision)
        object.__setattr__(self, "findings", _ordered_findings(self.findings))
        if self.status is OperationStatus.ACCEPTED:
            _instance_tuple(self.neighborhoods, DefinitionNeighborhood, "definition neighborhoods")
        elif self.neighborhoods is not None:
            raise ValueError("rejected type inspection cannot carry a payload")


def _text_tuple(values: object, label: str) -> None:
    if not isinstance(values, tuple) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{label} must be a tuple of text")


def _instance_tuple(values: object, expected: type | tuple[type, ...], label: str) -> None:
    if not isinstance(values, tuple) or any(not isinstance(value, expected) for value in values):
        raise ValueError(f"{label} have invalid types")


def _property_tuple(values: object) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, tuple)
        or len(value) != 2
        or not isinstance(value[0], str)
        or (value[1] is not None and not isinstance(value[1], ScalarValue))
        for value in values
    ):
        raise ValueError("hydrated properties have invalid types")


def _hydrated_shape(value: HydratedObject) -> None:
    if value.kind is ObjectKind.ANCHOR:
        valid = (
            isinstance(value.display_name, str)
            and not value.anchor_uuids
            and value.source_uuid is None
            and value.target_uuid is None
            and value.properties is None
        )
    elif value.kind is ObjectKind.ASSOCIATED_DATA:
        valid = (
            value.display_name is None
            and bool(value.anchor_uuids)
            and value.source_uuid is None
            and value.target_uuid is None
        )
    else:
        valid = (
            value.display_name is None
            and not value.anchor_uuids
            and value.source_uuid is not None
            and value.target_uuid is not None
            and value.properties is None
        )
    if not valid:
        raise ValueError("hydrated structural fields do not match object kind")


def _result_header(
    status: OperationStatus,
    summary: str,
    findings: tuple[Finding, ...],
    evaluated_revision: int | None,
) -> None:
    if not isinstance(status, OperationStatus) or not isinstance(summary, str) or summary == "":
        raise ValueError("result status or summary is invalid")
    _instance_tuple(findings, Finding, "result findings")
    if status is OperationStatus.ACCEPTED and findings:
        raise ValueError("accepted read result cannot carry findings")
    if status is OperationStatus.REJECTED and not findings:
        raise ValueError("rejected read result requires findings")
    if evaluated_revision is not None and (
        type(evaluated_revision) is not int or evaluated_revision < 0
    ):
        raise ValueError("evaluated revision is invalid")


def _ordered_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    return tuple(
        sorted(
            findings,
            key=lambda value: (
                value.code.value,
                value.path or "",
                value.type_keys,
                value.uuids,
                value.summary,
            ),
        )
    )
