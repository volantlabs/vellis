"""Strict wire-only models and one-way conversion into the successor domain."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from vellis.domain import (
    AnchorTypeDefinition,
    AnchorUpsert,
    AssociatedDataTypeDefinition,
    AssociatedDataUpsert,
    Cardinality,
    CurrentState,
    DraftState,
    LinkTypeDefinition,
    LinkUpsert,
    PropertyDefinition,
    RevisionState,
    ScalarValue,
    TimeState,
    TypeDefinition,
    ValueKind,
    canonical_date,
    canonical_uuid,
    parse_timestamp,
)
from vellis.history_domain import SequenceHistoryRange, TimeHistoryRange
from vellis.query_domain import (
    DirectAssociation,
    DisplayNameField,
    IdentityObjectSelection,
    IdentitySelection,
    PatternLink,
    PatternNode,
    PatternNodeKind,
    PatternSelection,
    Predicate,
    PredicateOperator,
    PropertyField,
    PropertySelection,
)


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(value.capitalize() for value in tail)


PUBLIC_ITEM_LIMIT = 1_000
NonemptyText = Annotated[str, Field(min_length=1)]
BoundedStrings = Annotated[list[NonemptyText], Field(max_length=PUBLIC_ITEM_LIMIT)]
NonemptyStrings = Annotated[list[NonemptyText], Field(min_length=1, max_length=PUBLIC_ITEM_LIMIT)]
CanonicalUuid = Annotated[str, AfterValidator(canonical_uuid)]
CanonicalUuids = Annotated[list[CanonicalUuid], Field(max_length=PUBLIC_ITEM_LIMIT)]
NonemptyCanonicalUuids = Annotated[
    list[CanonicalUuid], Field(min_length=1, max_length=PUBLIC_ITEM_LIMIT)
]
CanonicalDate = Annotated[str, AfterValidator(canonical_date)]
CanonicalTimestamp = Annotated[str, AfterValidator(lambda value: parse_timestamp(value).canonical)]
ValueKindInput = Literal["boolean", "integer", "number", "text", "date", "timestamp"]
DraftCategoryInput = Literal["definitions", "anchors", "associatedData", "links"]
DraftOperationInput = Literal["add", "patch", "replace", "remove"]
ValidationScopeInput = Literal["current", "draft"]


type OmissibleInput[T] = T | SkipJsonSchema[None]


def _omitted_none():
    return None


def _reject_explicit_null(value):
    if value is None:
        raise ValueError("optional member must be omitted rather than null")
    return value


type OmissibleArgument[T] = Annotated[OmissibleInput[T], BeforeValidator(_reject_explicit_null)]


class WireModel(BaseModel):
    _direct_null_fields: ClassVar[frozenset[str]] = frozenset()
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        alias_generator=_camel,
        validate_by_alias=True,
        validate_by_name=False,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_json_null(cls, value):
        if not isinstance(value, dict):
            return value
        for name, field in cls.model_fields.items():
            alias = field.alias or name
            if alias in value and value[alias] is None and name not in cls._direct_null_fields:
                raise ValueError(f"{alias} must be omitted rather than null")
        return value


class CurrentStateInput(WireModel):
    kind: Literal["current"]

    def domain(self):
        return CurrentState()


class DraftStateInput(WireModel):
    kind: Literal["draft"]

    def domain(self):
        return DraftState()


class RevisionStateInput(WireModel):
    kind: Literal["revision"]
    revision: int = Field(ge=0)

    def domain(self):
        return RevisionState(self.revision)


class TimeStateInput(WireModel):
    kind: Literal["time"]
    timestamp: CanonicalTimestamp

    def domain(self):
        return TimeState(parse_timestamp(self.timestamp))


StateInput = Annotated[
    CurrentStateInput | DraftStateInput | RevisionStateInput | TimeStateInput,
    Field(discriminator="kind"),
]


class BooleanScalarInput(WireModel):
    kind: Literal["boolean"]
    value: bool

    def domain(self) -> ScalarValue:
        return ScalarValue.boolean(self.value)


class IntegerScalarInput(WireModel):
    kind: Literal["integer"]
    value: int = Field(ge=-9_007_199_254_740_991, le=9_007_199_254_740_991)

    def domain(self) -> ScalarValue:
        return ScalarValue.integer(self.value)


class NumberScalarInput(WireModel):
    kind: Literal["number"]
    value: float = Field(allow_inf_nan=False)

    def domain(self) -> ScalarValue:
        return ScalarValue.number(self.value)


class TextScalarInput(WireModel):
    kind: Literal["text"]
    value: str

    def domain(self) -> ScalarValue:
        return ScalarValue.text(self.value)


class DateScalarInput(WireModel):
    kind: Literal["date"]
    value: CanonicalDate

    def domain(self) -> ScalarValue:
        return ScalarValue.date(self.value)


class TimestampScalarInput(WireModel):
    kind: Literal["timestamp"]
    value: CanonicalTimestamp

    def domain(self) -> ScalarValue:
        return ScalarValue.timestamp(self.value)


class NullScalarInput(WireModel):
    _direct_null_fields = frozenset({"value"})
    kind: Literal["null"]
    value: None

    def domain(self) -> None:
        return None


NonNullScalarInput = Annotated[
    BooleanScalarInput
    | IntegerScalarInput
    | NumberScalarInput
    | TextScalarInput
    | DateScalarInput
    | TimestampScalarInput,
    Field(discriminator="kind"),
]

ScalarInput = Annotated[
    BooleanScalarInput
    | IntegerScalarInput
    | NumberScalarInput
    | TextScalarInput
    | DateScalarInput
    | TimestampScalarInput
    | NullScalarInput,
    Field(discriminator="kind"),
]


class CardinalityInput(WireModel):
    minimum: int = Field(ge=0)
    maximum: OmissibleInput[int] = Field(default_factory=_omitted_none, ge=0)

    @model_validator(mode="after")
    def valid_range(self):
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("cardinality maximum must not be less than minimum")
        return self

    def domain(self) -> Cardinality:
        return Cardinality(self.minimum, self.maximum)


class PropertyDefinitionInput(WireModel):
    name: str
    description: str
    value_kind: ValueKindInput
    required: bool = False
    nullable: bool = False
    allowed_values: OmissibleInput[
        Annotated[list[NonNullScalarInput], Field(max_length=PUBLIC_ITEM_LIMIT)]
    ] = Field(default_factory=_omitted_none)
    minimum: OmissibleInput[NonNullScalarInput] = Field(default_factory=_omitted_none)
    maximum: OmissibleInput[NonNullScalarInput] = Field(default_factory=_omitted_none)
    minimum_length: OmissibleInput[int] = Field(default_factory=_omitted_none)
    maximum_length: OmissibleInput[int] = Field(default_factory=_omitted_none)
    pattern: OmissibleInput[str] = Field(default_factory=_omitted_none)

    @model_validator(mode="after")
    def unique_allowed_values(self):
        values = tuple(value.domain() for value in self.allowed_values or ())
        if len(set(values)) != len(values):
            raise ValueError("allowedValues must not contain duplicates")
        return self

    def domain(self) -> PropertyDefinition:
        return PropertyDefinition(
            self.name,
            self.description,
            ValueKind(self.value_kind),
            self.required,
            self.nullable,
            tuple(value.domain() for value in self.allowed_values or ()),
            None if self.minimum is None else self.minimum.domain(),
            None if self.maximum is None else self.maximum.domain(),
            self.minimum_length,
            self.maximum_length,
            self.pattern,
            self.allowed_values is not None,
        )


class AnchorDefinitionInput(WireModel):
    kind: Literal["anchor"]
    type_key: str
    description: str

    def domain(self) -> TypeDefinition:
        return AnchorTypeDefinition(self.type_key, self.description)


class AssociatedDataDefinitionInput(WireModel):
    kind: Literal["associatedData"]
    type_key: str
    description: str
    permitted_anchor_type_keys: Annotated[list[str], Field(max_length=PUBLIC_ITEM_LIMIT)]
    properties: Annotated[list[PropertyDefinitionInput], Field(max_length=PUBLIC_ITEM_LIMIT)]
    anchors_per_object: CardinalityInput
    objects_per_anchor: CardinalityInput

    @model_validator(mode="after")
    def unique_set_members(self):
        if len(set(self.permitted_anchor_type_keys)) != len(self.permitted_anchor_type_keys):
            raise ValueError("permittedAnchorTypeKeys must not contain duplicates")
        names = tuple(value.name for value in self.properties)
        if len(set(names)) != len(names):
            raise ValueError("properties must not contain duplicate names")
        return self

    def domain(self) -> TypeDefinition:
        return AssociatedDataTypeDefinition(
            self.type_key,
            self.description,
            tuple(self.permitted_anchor_type_keys),
            tuple(value.domain() for value in self.properties),
            self.anchors_per_object.domain(),
            self.objects_per_anchor.domain(),
        )


class LinkDefinitionInput(WireModel):
    kind: Literal["link"]
    type_key: str
    description: str
    permitted_source_type_keys: Annotated[list[str], Field(max_length=PUBLIC_ITEM_LIMIT)]
    permitted_target_type_keys: Annotated[list[str], Field(max_length=PUBLIC_ITEM_LIMIT)]
    links_per_source: CardinalityInput
    links_per_target: CardinalityInput

    @model_validator(mode="after")
    def unique_set_members(self):
        if len(set(self.permitted_source_type_keys)) != len(self.permitted_source_type_keys):
            raise ValueError("permittedSourceTypeKeys must not contain duplicates")
        if len(set(self.permitted_target_type_keys)) != len(self.permitted_target_type_keys):
            raise ValueError("permittedTargetTypeKeys must not contain duplicates")
        return self

    def domain(self) -> TypeDefinition:
        return LinkTypeDefinition(
            self.type_key,
            self.description,
            tuple(self.permitted_source_type_keys),
            tuple(self.permitted_target_type_keys),
            self.links_per_source.domain(),
            self.links_per_target.domain(),
        )


DefinitionInput = Annotated[
    AnchorDefinitionInput | AssociatedDataDefinitionInput | LinkDefinitionInput,
    Field(discriminator="kind"),
]


class AnchorUpsertInput(WireModel):
    kind: Literal["anchor"]
    uuid: CanonicalUuid
    type_key: OmissibleInput[str] = Field(default_factory=_omitted_none)
    display_name: OmissibleInput[str] = Field(default_factory=_omitted_none)

    def domain(self):
        return AnchorUpsert(self.uuid, self.type_key, self.display_name)


class AssociatedDataUpsertInput(WireModel):
    kind: Literal["associatedData"]
    uuid: CanonicalUuid
    type_key: OmissibleInput[str] = Field(default_factory=_omitted_none)
    anchor_uuids: OmissibleInput[NonemptyCanonicalUuids] = Field(default_factory=_omitted_none)
    add_anchor_uuids: CanonicalUuids = []
    remove_anchor_uuids: CanonicalUuids = []
    set_properties: Annotated[dict[str, ScalarInput], Field(max_length=PUBLIC_ITEM_LIMIT)] = {}
    remove_properties: BoundedStrings = []

    def domain(self):
        return AssociatedDataUpsert(
            self.uuid,
            self.type_key,
            None if self.anchor_uuids is None else tuple(self.anchor_uuids),
            tuple(self.add_anchor_uuids),
            tuple(self.remove_anchor_uuids),
            tuple((name, value.domain()) for name, value in self.set_properties.items()),
            tuple(self.remove_properties),
        )


class LinkUpsertInput(WireModel):
    kind: Literal["link"]
    uuid: CanonicalUuid
    type_key: OmissibleInput[str] = Field(default_factory=_omitted_none)
    source_uuid: OmissibleInput[CanonicalUuid] = Field(default_factory=_omitted_none)
    target_uuid: OmissibleInput[CanonicalUuid] = Field(default_factory=_omitted_none)

    def domain(self):
        return LinkUpsert(self.uuid, self.type_key, self.source_uuid, self.target_uuid)


ObjectUpsertInput = Annotated[
    AnchorUpsertInput | AssociatedDataUpsertInput | LinkUpsertInput,
    Field(discriminator="kind"),
]


PropertySelectionInput = BoundedStrings | Literal["*"]


def _property_selection(value: PropertySelectionInput | None):
    if value is None:
        return None
    if value == "*":
        return PropertySelection((), True)
    return PropertySelection(tuple(value), False)


class IdentityObjectInput(WireModel):
    uuid: CanonicalUuid
    properties: OmissibleInput[PropertySelectionInput] = Field(default_factory=_omitted_none)
    include_legacy_system: bool = False

    def domain(self):
        return IdentityObjectSelection(
            self.uuid, _property_selection(self.properties), self.include_legacy_system
        )


class IdentitySelectionInput(WireModel):
    kind: Literal["identities"]
    objects: Annotated[list[IdentityObjectInput], Field(min_length=1, max_length=PUBLIC_ITEM_LIMIT)]

    def domain(self):
        return IdentitySelection(tuple(value.domain() for value in self.objects))


class DisplayNameFieldInput(WireModel):
    kind: Literal["displayName"]

    def domain(self):
        return DisplayNameField()


class PropertyFieldInput(WireModel):
    kind: Literal["property"]
    name: str

    def domain(self):
        return PropertyField(self.name)


PredicateFieldInput = Annotated[
    DisplayNameFieldInput | PropertyFieldInput, Field(discriminator="kind")
]


class PresencePredicateInput(WireModel):
    field: PropertyFieldInput
    operator: Literal["present", "missing", "isNull", "isNotNull"]

    def domain(self):
        return Predicate(self.field.domain(), PredicateOperator(self.operator))


class EqualityPredicateInput(WireModel):
    field: PredicateFieldInput
    operator: Literal["equal", "notEqual"]
    value: NonNullScalarInput

    def domain(self):
        return Predicate(
            self.field.domain(), PredicateOperator(self.operator), value=self.value.domain()
        )


class OrderingPredicateInput(WireModel):
    field: PredicateFieldInput
    operator: Literal[
        "lessThan",
        "lessThanOrEqual",
        "greaterThan",
        "greaterThanOrEqual",
    ]
    value: NonNullScalarInput

    def domain(self):
        return Predicate(
            self.field.domain(), PredicateOperator(self.operator), value=self.value.domain()
        )


class AnyOfPredicateInput(WireModel):
    field: PredicateFieldInput
    operator: Literal["anyOf"]
    values: Annotated[list[ScalarInput], Field(min_length=1, max_length=PUBLIC_ITEM_LIMIT)]

    def domain(self):
        return Predicate(
            self.field.domain(),
            PredicateOperator.ANY_OF,
            values=tuple(value.domain() for value in self.values),
        )


class TextPredicateInput(WireModel):
    field: PredicateFieldInput
    operator: Literal["contains", "prefix", "regex"]
    value: str
    case_sensitive: bool = False

    def domain(self):
        return Predicate(
            self.field.domain(),
            PredicateOperator(self.operator),
            text=self.value,
            case_sensitive=self.case_sensitive,
        )


class TermsPredicateInput(WireModel):
    field: PredicateFieldInput
    operator: Literal["allTerms", "anyTerms"]
    terms: NonemptyStrings

    def domain(self):
        return Predicate(
            self.field.domain(),
            PredicateOperator(self.operator),
            terms=tuple(self.terms),
        )


class PhrasePredicateInput(WireModel):
    field: PredicateFieldInput
    operator: Literal["phrase"]
    phrase: Annotated[str, Field(min_length=1)]

    def domain(self):
        return Predicate(self.field.domain(), PredicateOperator.PHRASE, text=self.phrase)


PredicateInput = Annotated[
    PresencePredicateInput
    | EqualityPredicateInput
    | OrderingPredicateInput
    | AnyOfPredicateInput
    | TextPredicateInput
    | TermsPredicateInput
    | PhrasePredicateInput,
    Field(discriminator="operator"),
]


class PatternNodeInput(WireModel):
    name: str
    kind: Literal["anchor", "associatedData"]
    type_keys: OmissibleInput[NonemptyStrings] = Field(default_factory=_omitted_none)
    uuids: OmissibleInput[NonemptyCanonicalUuids] = Field(default_factory=_omitted_none)
    predicates: Annotated[list[PredicateInput], Field(max_length=PUBLIC_ITEM_LIMIT)] = []
    properties: OmissibleInput[PropertySelectionInput] = Field(default_factory=_omitted_none)
    include_legacy_system: bool = False

    def domain(self):
        return PatternNode(
            self.name,
            PatternNodeKind(self.kind),
            tuple(self.type_keys or ()),
            tuple(self.uuids or ()),
            tuple(value.domain() for value in self.predicates),
            _property_selection(self.properties),
            self.include_legacy_system,
        )


class DirectAssociationInput(WireModel):
    anchor: str
    associated_data: str

    def domain(self):
        return DirectAssociation(self.anchor, self.associated_data)


class PatternLinkInput(WireModel):
    name: str
    source: str
    target: str
    type_keys: OmissibleInput[NonemptyStrings] = Field(default_factory=_omitted_none)
    uuids: OmissibleInput[NonemptyCanonicalUuids] = Field(default_factory=_omitted_none)
    include_legacy_system: bool = False

    def domain(self):
        return PatternLink(
            self.name,
            self.source,
            self.target,
            tuple(self.type_keys or ()),
            tuple(self.uuids or ()),
            self.include_legacy_system,
        )


class PatternSelectionInput(WireModel):
    kind: Literal["pattern"]
    max_matches: int = Field(ge=1, le=PUBLIC_ITEM_LIMIT)
    nodes: Annotated[list[PatternNodeInput], Field(min_length=1, max_length=PUBLIC_ITEM_LIMIT)]
    direct_associations: Annotated[
        list[DirectAssociationInput], Field(max_length=PUBLIC_ITEM_LIMIT)
    ] = []
    links: Annotated[list[PatternLinkInput], Field(max_length=PUBLIC_ITEM_LIMIT)] = []

    def domain(self):
        return PatternSelection(
            self.max_matches,
            tuple(value.domain() for value in self.nodes),
            tuple(value.domain() for value in self.direct_associations),
            tuple(value.domain() for value in self.links),
        )


QuerySelectionInput = Annotated[
    IdentitySelectionInput | PatternSelectionInput, Field(discriminator="kind")
]


class TimeRangeInput(WireModel):
    kind: Literal["time"]
    start: OmissibleInput[CanonicalTimestamp] = Field(default_factory=_omitted_none)
    end: OmissibleInput[CanonicalTimestamp] = Field(default_factory=_omitted_none)

    def domain(self):
        start = None if self.start is None else parse_timestamp(self.start)
        end = None if self.end is None else parse_timestamp(self.end)
        return TimeHistoryRange(start, end)


class SequenceRangeInput(WireModel):
    kind: Literal["sequence"]
    after: OmissibleInput[int] = Field(default_factory=_omitted_none, ge=0)
    through: OmissibleInput[int] = Field(default_factory=_omitted_none, ge=0)

    def domain(self):
        return SequenceHistoryRange(self.after, self.through)


HistoryRangeInput = Annotated[TimeRangeInput | SequenceRangeInput, Field(discriminator="kind")]


class DraftInspectFreshInput(WireModel):
    categories: list[DraftCategoryInput] = Field(default_factory=list, max_length=PUBLIC_ITEM_LIMIT)
    operations: list[DraftOperationInput] = Field(
        default_factory=list, max_length=PUBLIC_ITEM_LIMIT
    )
    type_keys: list[str] = Field(default_factory=list, max_length=PUBLIC_ITEM_LIMIT)
    uuids: list[CanonicalUuid] = Field(default_factory=list, max_length=PUBLIC_ITEM_LIMIT)
    limit: int = Field(ge=1, le=PUBLIC_ITEM_LIMIT)


class DraftInspectContinuationInput(WireModel):
    cursor: str = Field(min_length=1)


DraftInspectInput = DraftInspectFreshInput | DraftInspectContinuationInput


class ValidateFreshInput(WireModel):
    scope: ValidationScopeInput
    limit: int = Field(ge=1, le=PUBLIC_ITEM_LIMIT)


class ValidateContinuationInput(WireModel):
    scope: ValidationScopeInput
    cursor: str = Field(min_length=1)


ValidateInput = ValidateFreshInput | ValidateContinuationInput
