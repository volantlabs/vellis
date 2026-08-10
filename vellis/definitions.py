"""Owner-described graph definitions, constraints, and their natural identities.

Realizes ``RTG::'Definition Object'`` and its specializations, ``RTG::'Property
Constraint'``, ``RTG::'Endpoint Constraint'``, the two multiplicity constraints,
``RTG::'Graph Definition Set'``, and the definition portion of
``VellisRequirements::canonicalSemanticEquality`` and
``VellisRequirements::graphInvariants``.

The model references other definitions by object reference. Because a type
definition's natural identity *is* its type key and the model already requires every
reference to resolve inside one set, this realization carries type keys rather than
object references. That keeps one authority for each definition and makes an
unresolved reference a validation finding rather than an unrepresentable state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from vellis.json_value import (
    MAXIMUM_STORED_INTEGER_EXPONENT,
    JsonKind,
    JsonValue,
    json_equal,
    json_kind,
    normalize,
    unencodable_reason,
)
from vellis.outcomes import ValidationFinding
from vellis.patterns import PatternError, compile_pattern

__all__ = [
    "AnchorTypeDefinition",
    "AssociatedDataTypeDefinition",
    "DirectAssociationEnd",
    "DirectAssociationMultiplicityConstraint",
    "EndpointConstraint",
    "GraphDefinitionSet",
    "LinkEnd",
    "LinkMultiplicityConstraint",
    "LinkTypeDefinition",
    "PropertyConstraint",
    "RelationshipConstraint",
    "StringPattern",
    "ValueRange",
    "ValueShape",
    "definition_set_equal",
    "relationship_identity",
    "relationship_label",
    "validate_definition_set",
]


class LinkEnd(Enum):
    """Which end of a directed link a multiplicity rule constrains."""

    SOURCE = "source"
    TARGET = "target"


class DirectAssociationEnd(Enum):
    """Which end of an anchor/associated-data association a multiplicity rule constrains."""

    ANCHOR = "anchor"
    ASSOCIATED_DATA = "associatedData"


@dataclass(frozen=True, slots=True)
class ValueShape:
    """A closed size condition for a string, array, or object value."""

    minimum_size: int | None = None
    maximum_size: int | None = None


@dataclass(frozen=True, slots=True)
class ValueRange:
    """A closed permitted-value condition.

    Numeric bounds are inclusive. When bounds and permitted values coexist, a value
    must satisfy both. Values are normalized on construction, so a non-finite bound is
    refused here rather than reaching a comparison that would raise or, worse, silently
    reject every value the owner stores.
    """

    lower_bound: JsonValue | None = None
    upper_bound: JsonValue | None = None
    permitted_values: tuple[JsonValue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "lower_bound", None if self.lower_bound is None else normalize(self.lower_bound)
        )
        object.__setattr__(
            self, "upper_bound", None if self.upper_bound is None else normalize(self.upper_bound)
        )
        object.__setattr__(
            self, "permitted_values", tuple(normalize(each) for each in self.permitted_values)
        )


@dataclass(frozen=True, slots=True)
class StringPattern:
    """A Google RE2 expression evaluated with whole-string ``FullMatch`` semantics."""

    expression: str


@dataclass(frozen=True, slots=True)
class PropertyConstraint:
    """Governs one associated-data property.

    Present conditions apply conjunctively. The natural identity is the owning
    associated-data type key plus this property name.
    """

    property_name: str
    required: bool
    json_kind: JsonKind
    description: str | None = None
    value_shape: ValueShape | None = None
    value_range: ValueRange | None = None
    pattern: StringPattern | None = None


@dataclass(frozen=True, slots=True)
class AnchorTypeDefinition:
    """A stable, independently identifiable concept type."""

    type_key: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class AssociatedDataTypeDefinition:
    """Governs one typed fact group and the anchor types that may ground it."""

    type_key: str
    permitted_anchor_type_keys: tuple[str, ...] = ()
    property_constraints: tuple[PropertyConstraint, ...] = ()
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointConstraint:
    """States the permitted source and target endpoint types of one link type."""

    permitted_source_type_keys: tuple[str, ...] = ()
    permitted_target_type_keys: tuple[str, ...] = ()
    description: str | None = None


@dataclass(frozen=True, slots=True)
class LinkTypeDefinition:
    """A typed directed relationship and its endpoint constraint."""

    type_key: str
    endpoint_constraint: EndpointConstraint = EndpointConstraint()
    description: str | None = None


@dataclass(frozen=True, slots=True)
class LinkMultiplicityConstraint:
    """Counts links of one type at a selected end.

    The natural identity is the link type key, the constrained end, and the two
    unordered participating type-key sets.
    """

    link_type_key: str
    constrained_end: LinkEnd
    constrained_endpoint_type_keys: tuple[str, ...]
    opposite_endpoint_type_keys: tuple[str, ...]
    lower_bound: int
    upper_bound: int | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DirectAssociationMultiplicityConstraint:
    """Counts identity-free anchor/associated-data associations at a selected end.

    The natural identity is the constrained end and the two unordered participating
    type-key sets.
    """

    constrained_end: DirectAssociationEnd
    anchor_type_keys: tuple[str, ...]
    associated_data_type_keys: tuple[str, ...]
    lower_bound: int
    upper_bound: int | None = None
    description: str | None = None


RelationshipConstraint = LinkMultiplicityConstraint | DirectAssociationMultiplicityConstraint

_SIZED_KINDS = frozenset({JsonKind.STRING, JsonKind.ARRAY, JsonKind.OBJECT})


@dataclass(frozen=True, slots=True)
class GraphDefinitionSet:
    """The complete active graph vocabulary and its constraints."""

    anchor_types: tuple[AnchorTypeDefinition, ...] = ()
    associated_data_types: tuple[AssociatedDataTypeDefinition, ...] = ()
    link_types: tuple[LinkTypeDefinition, ...] = ()
    relationship_constraints: tuple[RelationshipConstraint, ...] = ()

    def anchor_type(self, type_key: str) -> AnchorTypeDefinition | None:
        return next((each for each in self.anchor_types if each.type_key == type_key), None)

    def associated_data_type(self, type_key: str) -> AssociatedDataTypeDefinition | None:
        return next(
            (each for each in self.associated_data_types if each.type_key == type_key), None
        )

    def link_type(self, type_key: str) -> LinkTypeDefinition | None:
        return next((each for each in self.link_types if each.type_key == type_key), None)

    def is_endpoint_type(self, type_key: str) -> bool:
        return (
            self.anchor_type(type_key) is not None
            or self.associated_data_type(type_key) is not None
        )


# --- Natural identity ---------------------------------------------------------------


def relationship_identity(constraint: RelationshipConstraint) -> tuple[object, ...]:
    """Return the modeled natural identity of one relationship constraint."""
    if isinstance(constraint, LinkMultiplicityConstraint):
        return (
            "linkMultiplicity",
            constraint.link_type_key,
            constraint.constrained_end,
            frozenset(constraint.constrained_endpoint_type_keys),
            frozenset(constraint.opposite_endpoint_type_keys),
        )
    return (
        "directAssociationMultiplicity",
        constraint.constrained_end,
        frozenset(constraint.anchor_type_keys),
        frozenset(constraint.associated_data_type_keys),
    )


def relationship_label(constraint: RelationshipConstraint) -> str:
    """Return a stable, readable identity for use in findings."""
    identity = relationship_identity(constraint)
    parts = [
        "{" + ",".join(sorted(part)) + "}" if isinstance(part, frozenset) else str(part)
        for part in identity[1:]
    ]
    return f"{identity[0]}:" + "|".join(parts)


# --- Canonical semantic equality ----------------------------------------------------


def _json_values_equal_as_set(left: Sequence[JsonValue], right: Sequence[JsonValue]) -> bool:
    if len(left) != len(right):
        return False
    unmatched = list(right)
    for value in left:
        for index, candidate in enumerate(unmatched):
            if json_equal(value, candidate):
                del unmatched[index]
                break
        else:
            return False
    return True


def _optional_json_equal(left: JsonValue | None, right: JsonValue | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return json_equal(left, right)


def _value_range_equal(left: ValueRange | None, right: ValueRange | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return (
        _optional_json_equal(left.lower_bound, right.lower_bound)
        and _optional_json_equal(left.upper_bound, right.upper_bound)
        and _json_values_equal_as_set(left.permitted_values, right.permitted_values)
    )


def _property_constraint_equal(left: PropertyConstraint, right: PropertyConstraint) -> bool:
    return (
        left.required == right.required
        and left.json_kind is right.json_kind
        and left.description == right.description
        and left.value_shape == right.value_shape
        and _value_range_equal(left.value_range, right.value_range)
        and left.pattern == right.pattern
    )


def _by_key[T](items: Sequence[T], attribute: str) -> dict[str, T] | None:
    """Key ``items`` by a natural-identity attribute, or ``None`` when one repeats.

    Duplicate natural identities are invalid, but a stored set is not revalidated on
    every read. Returning ``None`` keeps equality from silently collapsing two
    definitions into one and calling that the same set as a set holding one.
    """
    keyed: dict[str, T] = {}
    for item in items:
        value = getattr(item, attribute)
        assert isinstance(value, str)
        keyed[value] = item
    return keyed if len(keyed) == len(items) else None


def definition_set_equal(left: GraphDefinitionSet, right: GraphDefinitionSet) -> bool:
    """Compare two definition sets by canonical semantic equality.

    Comparison keys on the modeled natural identities and includes definition kind,
    descriptions, and every structured rule. Unordered collections compare without
    order significance; reordering them is an effective no-op.
    """
    if not _anchor_types_equal(left, right):
        return False
    if not _associated_data_types_equal(left, right):
        return False
    if not _link_types_equal(left, right):
        return False
    return _relationship_constraints_equal(left, right)


def _anchor_types_equal(left: GraphDefinitionSet, right: GraphDefinitionSet) -> bool:
    first = _by_key(left.anchor_types, "type_key")
    second = _by_key(right.anchor_types, "type_key")
    if first is None or second is None or first.keys() != second.keys():
        return False
    return all(
        definition.description == second[key].description for key, definition in first.items()
    )


def _associated_data_types_equal(left: GraphDefinitionSet, right: GraphDefinitionSet) -> bool:
    first = _by_key(left.associated_data_types, "type_key")
    second = _by_key(right.associated_data_types, "type_key")
    if first is None or second is None or first.keys() != second.keys():
        return False
    for key, definition in first.items():
        other = second[key]
        if definition.description != other.description:
            return False
        if frozenset(definition.permitted_anchor_type_keys) != frozenset(
            other.permitted_anchor_type_keys
        ):
            return False
        properties = _by_key(definition.property_constraints, "property_name")
        other_properties = _by_key(other.property_constraints, "property_name")
        if (
            properties is None
            or other_properties is None
            or properties.keys() != other_properties.keys()
        ):
            return False
        for name, constraint in properties.items():
            if not _property_constraint_equal(constraint, other_properties[name]):
                return False
    return True


def _endpoint_constraint_equal(left: EndpointConstraint, right: EndpointConstraint) -> bool:
    return (
        left.description == right.description
        and frozenset(left.permitted_source_type_keys)
        == frozenset(right.permitted_source_type_keys)
        and frozenset(left.permitted_target_type_keys)
        == frozenset(right.permitted_target_type_keys)
    )


def _link_types_equal(left: GraphDefinitionSet, right: GraphDefinitionSet) -> bool:
    first = _by_key(left.link_types, "type_key")
    second = _by_key(right.link_types, "type_key")
    if first is None or second is None or first.keys() != second.keys():
        return False
    for key, definition in first.items():
        other = second[key]
        if definition.description != other.description:
            return False
        if not _endpoint_constraint_equal(
            definition.endpoint_constraint, other.endpoint_constraint
        ):
            return False
    return True


def _relationship_constraints_equal(left: GraphDefinitionSet, right: GraphDefinitionSet) -> bool:
    first = {relationship_identity(each): each for each in left.relationship_constraints}
    second = {relationship_identity(each): each for each in right.relationship_constraints}
    if (
        len(first) != len(left.relationship_constraints)
        or len(second) != len(right.relationship_constraints)
        or first.keys() != second.keys()
    ):
        return False
    for identity, constraint in first.items():
        other = second[identity]
        if (
            constraint.lower_bound != other.lower_bound
            or constraint.upper_bound != other.upper_bound
            or constraint.description != other.description
        ):
            return False
    return True


# --- Internal validity --------------------------------------------------------------


def validate_definition_set(
    definitions: GraphDefinitionSet, *, require_descriptions: bool = True
) -> tuple[ValidationFinding, ...]:
    """Return every finding that makes ``definitions`` internally invalid.

    ``require_descriptions`` is true for a set that is or is becoming active. A
    proposal still being edited may omit descriptions; that omission is reported as a
    finding by its own caller rather than treated as structural corruption here.
    """
    findings: list[ValidationFinding] = []
    _check_text_is_storable(definitions, findings)
    _check_type_key_namespace(definitions, findings)
    for anchor_type in definitions.anchor_types:
        _check_description(
            anchor_type.description,
            f"anchorType:{anchor_type.type_key}",
            require_descriptions,
            findings,
        )
    for data_type in definitions.associated_data_types:
        _check_associated_data_type(definitions, data_type, require_descriptions, findings)
    for link_type in definitions.link_types:
        _check_link_type(definitions, link_type, require_descriptions, findings)
    _check_relationship_constraints(definitions, require_descriptions, findings)
    return tuple(findings)


def _check_text_is_storable(
    definitions: GraphDefinitionSet, findings: list[ValidationFinding]
) -> None:
    """Report definition text that cannot be encoded.

    Type keys, names, descriptions, and pattern expressions are ordinary text rather
    than JSON values, so nothing else screens them. Reporting it here keeps an
    unencodable definition a finding instead of an error raised by the store or the
    pattern engine much later.

    Every text field a definition set can carry is walked, including the relationship
    constraints' descriptions: a screen with one hole in it is the same defect as no
    screen, just harder to notice.
    """

    def check(text: str | None, label: str) -> None:
        if text is None:
            return
        reason = unencodable_reason(text)
        if reason is not None:
            findings.append(
                ValidationFinding(summary=f"{label} {reason}", implicated_definitions=(label,))
            )

    for anchor_type in definitions.anchor_types:
        check(anchor_type.type_key, f"anchorType:{anchor_type.type_key!a}")
        check(anchor_type.description, f"anchorType:{anchor_type.type_key!a} description")
    for data_type in definitions.associated_data_types:
        label = f"associatedDataType:{data_type.type_key!a}"
        check(data_type.type_key, label)
        check(data_type.description, f"{label} description")
        for constraint in data_type.property_constraints:
            property_label = f"property:{data_type.type_key!a}.{constraint.property_name!a}"
            check(constraint.property_name, property_label)
            check(constraint.description, f"{property_label} description")
            if constraint.pattern is not None:
                check(constraint.pattern.expression, f"{property_label} pattern")
    for link_type in definitions.link_types:
        label = f"linkType:{link_type.type_key!a}"
        check(link_type.type_key, label)
        check(link_type.description, f"{label} description")
        check(
            link_type.endpoint_constraint.description,
            f"endpointConstraint:{link_type.type_key!a} description",
        )
    for constraint in definitions.relationship_constraints:
        check(constraint.description, f"{relationship_label(constraint)} description")


def _check_description(
    description: str | None, label: str, required: bool, findings: list[ValidationFinding]
) -> None:
    if not required:
        return
    if description is None or not description:
        findings.append(
            ValidationFinding(
                summary=f"{label} has no non-empty owner-readable description",
                implicated_definitions=(label,),
            )
        )


def _check_type_key_namespace(
    definitions: GraphDefinitionSet, findings: list[ValidationFinding]
) -> None:
    seen: dict[str, str] = {}
    families: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("anchorType", tuple(each.type_key for each in definitions.anchor_types)),
        (
            "associatedDataType",
            tuple(each.type_key for each in definitions.associated_data_types),
        ),
        ("linkType", tuple(each.type_key for each in definitions.link_types)),
    )
    for family, keys in families:
        for type_key in keys:
            label = f"{family}:{type_key}"
            if not type_key:
                findings.append(
                    ValidationFinding(
                        summary=f"{family} has an empty type key", implicated_definitions=(label,)
                    )
                )
                continue
            if type_key in seen:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"type key {type_key!r} is declared by both {seen[type_key]} and "
                            f"{family}; the type-key namespace is shared"
                        ),
                        implicated_definitions=(f"{seen[type_key]}:{type_key}", label),
                    )
                )
                continue
            seen[type_key] = family


def _check_associated_data_type(
    definitions: GraphDefinitionSet,
    data_type: AssociatedDataTypeDefinition,
    require_descriptions: bool,
    findings: list[ValidationFinding],
) -> None:
    label = f"associatedDataType:{data_type.type_key}"
    _check_description(data_type.description, label, require_descriptions, findings)
    if not data_type.permitted_anchor_type_keys:
        findings.append(
            ValidationFinding(
                summary=f"{label} permits no anchor type; at least one is required",
                implicated_definitions=(label,),
            )
        )
    _check_unique_members(
        data_type.permitted_anchor_type_keys, f"{label} permitted anchor types", label, findings
    )
    for anchor_key in data_type.permitted_anchor_type_keys:
        if definitions.anchor_type(anchor_key) is None:
            findings.append(
                ValidationFinding(
                    summary=f"{label} permits unknown anchor type {anchor_key!r}",
                    implicated_definitions=(label,),
                )
            )
    seen_names: set[str] = set()
    for constraint in data_type.property_constraints:
        property_label = f"property:{data_type.type_key}.{constraint.property_name}"
        if not constraint.property_name:
            findings.append(
                ValidationFinding(
                    summary=f"{label} declares a property with an empty name",
                    implicated_definitions=(label,),
                )
            )
        elif constraint.property_name in seen_names:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} declares property {constraint.property_name!r} more than once"
                    ),
                    implicated_definitions=(property_label,),
                )
            )
        else:
            seen_names.add(constraint.property_name)
        _check_description(constraint.description, property_label, require_descriptions, findings)
        _check_property_constraint(constraint, property_label, findings)


def _check_property_constraint(
    constraint: PropertyConstraint, label: str, findings: list[ValidationFinding]
) -> None:
    _check_value_shape(constraint, label, findings)
    _check_value_range(constraint, label, findings)
    _check_pattern(constraint, label, findings)


def _check_value_shape(
    constraint: PropertyConstraint, label: str, findings: list[ValidationFinding]
) -> None:
    shape = constraint.value_shape
    if shape is None:
        return
    if constraint.json_kind not in _SIZED_KINDS:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} carries a size condition, which is valid only for string, "
                    f"array, or object values, not {constraint.json_kind.value}"
                ),
                implicated_definitions=(label,),
            )
        )
        return
    if shape.minimum_size is None and shape.maximum_size is None:
        findings.append(
            ValidationFinding(
                summary=f"{label} has a size condition with no bound",
                implicated_definitions=(label,),
            )
        )
        return
    for bound_name, bound in (("minimum", shape.minimum_size), ("maximum", shape.maximum_size)):
        _check_storable_bound(bound, f"{bound_name} size", label, findings)
        if bound is not None and bound < 0:
            findings.append(
                ValidationFinding(
                    summary=f"{label} has a negative {bound_name} size",
                    implicated_definitions=(label,),
                )
            )
    if (
        shape.minimum_size is not None
        and shape.maximum_size is not None
        and shape.maximum_size < shape.minimum_size
    ):
        findings.append(
            ValidationFinding(
                summary=f"{label} has an inverted size condition",
                implicated_definitions=(label,),
            )
        )


def _check_value_range(
    constraint: PropertyConstraint, label: str, findings: list[ValidationFinding]
) -> None:
    value_range = constraint.value_range
    if value_range is None:
        return
    has_bound = value_range.lower_bound is not None or value_range.upper_bound is not None
    if not has_bound and not value_range.permitted_values:
        findings.append(
            ValidationFinding(
                summary=f"{label} has a value range with no bound and no permitted value",
                implicated_definitions=(label,),
            )
        )
    for bound_name, bound in (
        ("lower", value_range.lower_bound),
        ("upper", value_range.upper_bound),
    ):
        if bound is None:
            continue
        if json_kind(bound) is not JsonKind.NUMBER:
            findings.append(
                ValidationFinding(
                    summary=f"{label} has a non-numeric {bound_name} bound",
                    implicated_definitions=(label,),
                )
            )
        elif constraint.json_kind is not JsonKind.NUMBER:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} has a numeric {bound_name} bound but governs "
                        f"{constraint.json_kind.value}"
                    ),
                    implicated_definitions=(label,),
                )
            )
    lower, upper = value_range.lower_bound, value_range.upper_bound
    if isinstance(lower, Decimal) and isinstance(upper, Decimal) and upper < lower:
        findings.append(
            ValidationFinding(
                summary=f"{label} has an inverted numeric range",
                implicated_definitions=(label,),
            )
        )
    _check_permitted_values(constraint, value_range, label, findings)


def _check_permitted_values(
    constraint: PropertyConstraint,
    value_range: ValueRange,
    label: str,
    findings: list[ValidationFinding],
) -> None:
    accepted: list[JsonValue] = []
    for value in value_range.permitted_values:
        if json_kind(value) is not constraint.json_kind:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} permits a {json_kind(value).value} value but governs "
                        f"{constraint.json_kind.value}"
                    ),
                    implicated_definitions=(label,),
                )
            )
            continue
        if any(json_equal(value, seen) for seen in accepted):
            findings.append(
                ValidationFinding(
                    summary=f"{label} lists a duplicate permitted value",
                    implicated_definitions=(label,),
                )
            )
            continue
        accepted.append(value)


def _check_pattern(
    constraint: PropertyConstraint, label: str, findings: list[ValidationFinding]
) -> None:
    pattern = constraint.pattern
    if pattern is None:
        return
    if constraint.json_kind is not JsonKind.STRING:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} carries a string pattern but governs {constraint.json_kind.value}"
                ),
                implicated_definitions=(label,),
            )
        )
        return
    try:
        compiled = compile_pattern(pattern.expression)
    except PatternError as error:
        findings.append(
            ValidationFinding(
                summary=f"{label} has an invalid pattern: {error}",
                implicated_definitions=(label,),
            )
        )
        return
    if constraint.value_range is None:
        return
    for value in constraint.value_range.permitted_values:
        if isinstance(value, str) and not compiled.matches(value):
            findings.append(
                ValidationFinding(
                    summary=f"{label} permits {value!r}, which its own pattern does not match",
                    implicated_definitions=(label,),
                )
            )


def _check_link_type(
    definitions: GraphDefinitionSet,
    link_type: LinkTypeDefinition,
    require_descriptions: bool,
    findings: list[ValidationFinding],
) -> None:
    label = f"linkType:{link_type.type_key}"
    _check_description(link_type.description, label, require_descriptions, findings)
    constraint = link_type.endpoint_constraint
    endpoint_label = f"endpointConstraint:{link_type.type_key}"
    _check_description(constraint.description, endpoint_label, require_descriptions, findings)
    ends = (
        ("source", constraint.permitted_source_type_keys),
        ("target", constraint.permitted_target_type_keys),
    )
    for end_name, keys in ends:
        if not keys:
            findings.append(
                ValidationFinding(
                    summary=f"{endpoint_label} permits no {end_name} type",
                    implicated_definitions=(endpoint_label,),
                )
            )
        _check_unique_members(keys, f"{endpoint_label} {end_name} types", endpoint_label, findings)
        for type_key in keys:
            if not definitions.is_endpoint_type(type_key):
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"{endpoint_label} permits {end_name} type {type_key!r}, which is "
                            "not an active anchor or associated-data type"
                        ),
                        implicated_definitions=(endpoint_label,),
                    )
                )


def _check_unique_members(
    members: Sequence[str], description: str, label: str, findings: list[ValidationFinding]
) -> None:
    seen: set[str] = set()
    for member in members:
        if member in seen:
            findings.append(
                ValidationFinding(
                    summary=f"{description} list {member!r} more than once",
                    implicated_definitions=(label,),
                )
            )
        seen.add(member)


def _check_relationship_constraints(
    definitions: GraphDefinitionSet,
    require_descriptions: bool,
    findings: list[ValidationFinding],
) -> None:
    seen: set[tuple[object, ...]] = set()
    for constraint in definitions.relationship_constraints:
        label = relationship_label(constraint)
        _check_description(constraint.description, label, require_descriptions, findings)
        identity = relationship_identity(constraint)
        if identity in seen:
            findings.append(
                ValidationFinding(
                    summary=f"{label} duplicates another multiplicity rule's natural identity",
                    implicated_definitions=(label,),
                )
            )
        seen.add(identity)
        _check_multiplicity_bounds(constraint, label, findings)
        if isinstance(constraint, LinkMultiplicityConstraint):
            _check_link_multiplicity(definitions, constraint, label, findings)
        else:
            _check_direct_association_multiplicity(definitions, constraint, label, findings)


def _check_storable_bound(
    bound: int | None, description: str, label: str, findings: list[ValidationFinding]
) -> None:
    """Reject a bound too large to survive the round trip through storage.

    The decoder refuses such a number, so accepting one here would establish canonical
    state that could never be read back.
    """
    if bound is not None and abs(bound) >= 10**MAXIMUM_STORED_INTEGER_EXPONENT:
        findings.append(
            ValidationFinding(
                summary=f"{label} has a {description} too large to be stored",
                implicated_definitions=(label,),
            )
        )


def _check_multiplicity_bounds(
    constraint: RelationshipConstraint, label: str, findings: list[ValidationFinding]
) -> None:
    _check_storable_bound(constraint.lower_bound, "lower bound", label, findings)
    _check_storable_bound(constraint.upper_bound, "upper bound", label, findings)
    if constraint.lower_bound < 0:
        findings.append(
            ValidationFinding(
                summary=f"{label} has a negative lower bound", implicated_definitions=(label,)
            )
        )
    if constraint.upper_bound is not None and constraint.upper_bound < constraint.lower_bound:
        findings.append(
            ValidationFinding(
                summary=f"{label} has an upper bound below its lower bound",
                implicated_definitions=(label,),
            )
        )


def _check_link_multiplicity(
    definitions: GraphDefinitionSet,
    constraint: LinkMultiplicityConstraint,
    label: str,
    findings: list[ValidationFinding],
) -> None:
    if definitions.link_type(constraint.link_type_key) is None:
        findings.append(
            ValidationFinding(
                summary=f"{label} references unknown link type {constraint.link_type_key!r}",
                implicated_definitions=(label,),
            )
        )
    participants = (
        ("constrained", constraint.constrained_endpoint_type_keys),
        ("opposite", constraint.opposite_endpoint_type_keys),
    )
    for role, keys in participants:
        if not keys:
            findings.append(
                ValidationFinding(
                    summary=f"{label} names no {role} endpoint type",
                    implicated_definitions=(label,),
                )
            )
        _check_unique_members(keys, f"{label} {role} endpoint types", label, findings)
        for type_key in keys:
            if not definitions.is_endpoint_type(type_key):
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"{label} names {role} endpoint type {type_key!r}, which is not an "
                            "active anchor or associated-data type"
                        ),
                        implicated_definitions=(label,),
                    )
                )


def _check_direct_association_multiplicity(
    definitions: GraphDefinitionSet,
    constraint: DirectAssociationMultiplicityConstraint,
    label: str,
    findings: list[ValidationFinding],
) -> None:
    if not constraint.anchor_type_keys:
        findings.append(
            ValidationFinding(
                summary=f"{label} names no anchor type", implicated_definitions=(label,)
            )
        )
    if not constraint.associated_data_type_keys:
        findings.append(
            ValidationFinding(
                summary=f"{label} names no associated-data type", implicated_definitions=(label,)
            )
        )
    _check_unique_members(constraint.anchor_type_keys, f"{label} anchor types", label, findings)
    _check_unique_members(
        constraint.associated_data_type_keys, f"{label} associated-data types", label, findings
    )
    for type_key in constraint.anchor_type_keys:
        if definitions.anchor_type(type_key) is None:
            findings.append(
                ValidationFinding(
                    summary=f"{label} names {type_key!r}, which is not an active anchor type",
                    implicated_definitions=(label,),
                )
            )
    for type_key in constraint.associated_data_type_keys:
        if definitions.associated_data_type(type_key) is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} names {type_key!r}, which is not an active associated-data type"
                    ),
                    implicated_definitions=(label,),
                )
            )
