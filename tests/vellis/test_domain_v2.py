"""Focused evidence for the scalar and invariant distinctions in the VEL2 domain."""

from __future__ import annotations

import math

import pytest

from vellis.domain import (
    SAFE_INTEGER_MAXIMUM,
    SAFE_INTEGER_MINIMUM,
    Anchor,
    AnchorTypeDefinition,
    AnchorUpsert,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    DefinitionKind,
    Finding,
    FindingCode,
    GraphChangeRequest,
    Link,
    LinkTypeDefinition,
    ObjectKind,
    OperationOutcome,
    OperationStatus,
    PropertyDefinition,
    RevisionState,
    ScalarValue,
    SystemEnvelope,
    TimestampValue,
    ValueKind,
    canonical_date,
    canonical_number_text,
    canonical_uuid,
    parse_timestamp,
)
from vellis.domain_validation import (
    definition_set_findings,
    graph_cardinality_findings,
    graph_findings,
    property_definition_findings,
    property_value_findings,
    type_definition_findings,
)

PERSON_UUID = "12345678-1234-4234-8234-123456789abc"
DATA_UUID = "22345678-1234-4234-8234-123456789abc"
LINK_UUID = "32345678-1234-4234-8234-123456789abc"
SYSTEM = SystemEnvelope(created_revision=0, last_changed_revision=0)


def test_uuid_input_accepts_hyphenated_uppercase_and_returns_lowercase() -> None:
    assert canonical_uuid(PERSON_UUID.upper()) == PERSON_UUID
    for malformed in (
        PERSON_UUID.replace("-", ""),
        "{12345678-1234-4234-8234-123456789abc}",
        "not-a-uuid",
    ):
        with pytest.raises(ValueError, match="hyphenated UUID"):
            canonical_uuid(malformed)


def test_dynamic_domain_finding_paths_are_rfc6901_pointers() -> None:
    link_type = LinkTypeDefinition(
        "link/type~key",
        "Special link.",
        ("missing/source~type",),
        ("Person",),
        Cardinality(0),
        Cardinality(0),
        system=SYSTEM,
    )
    definition_paths = {
        finding.path for finding in type_definition_findings(link_type, (), require_system=True)
    }
    assert (
        "/definitions/link~1type~0key/permittedSourceTypeKeys/missing~1source~0type"
        in definition_paths
    )

    property_name = "required/property~name"
    property_paths = {
        finding.path
        for finding in property_value_findings(
            (),
            (PropertyDefinition(property_name, "Special property.", ValueKind.TEXT, True),),
            path=f"/objects/{DATA_UUID}/properties",
        )
    }
    assert f"/objects/{DATA_UUID}/properties/required~1property~0name" in property_paths

    data_type = AssociatedDataTypeDefinition(
        "data/type~key",
        "Special data.",
        ("Person",),
        (),
        Cardinality(1, 1),
        Cardinality(0),
        SYSTEM,
    )
    data = AssociatedData(DATA_UUID, data_type.type_key, (PERSON_UUID, LINK_UUID), (), SYSTEM)
    cardinality_paths = {
        finding.path
        for finding in graph_cardinality_findings(
            (
                Anchor(PERSON_UUID, "Person", "One", SYSTEM),
                Anchor(LINK_UUID, "Person", "Two", SYSTEM),
                data,
            ),
            (AnchorTypeDefinition("Person", "A person.", SYSTEM), data_type),
        )
    }
    assert f"/objects/{DATA_UUID}" in cardinality_paths


def test_safe_integer_boundaries_are_distinct_from_boolean() -> None:
    assert ScalarValue.integer(SAFE_INTEGER_MINIMUM).wire_value() == SAFE_INTEGER_MINIMUM
    assert ScalarValue.integer(SAFE_INTEGER_MAXIMUM).wire_value() == SAFE_INTEGER_MAXIMUM
    with pytest.raises(ValueError, match="safe-integer"):
        ScalarValue.integer(SAFE_INTEGER_MAXIMUM + 1)
    with pytest.raises(ValueError, match="not a Boolean"):
        ScalarValue.integer(True)


def test_number_is_finite_binary64_with_canonical_positive_zero() -> None:
    value = ScalarValue.number(-0.0)
    assert value.value == 0.0
    assert isinstance(value.value, float)
    assert math.copysign(1.0, value.value) == 1.0
    assert canonical_number_text(1.0) == "1.0"
    assert canonical_number_text(1e20) == "1.0e20"
    assert canonical_number_text(1e-7) == "1e-7"
    for invalid in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValueError, match="finite binary64"):
            ScalarValue.number(invalid)
    for invalid in (10**400, -(10**400)):
        with pytest.raises(ValueError, match="finite binary64"):
            ScalarValue.number(invalid)


def test_raw_scalar_and_timestamp_construction_cannot_bypass_invariants() -> None:
    with pytest.raises(ValueError, match="ValueKind"):
        ScalarValue("text", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite binary64"):
        ScalarValue(ValueKind.NUMBER, math.nan)
    with pytest.raises(ValueError, match="safe-integer"):
        ScalarValue(ValueKind.INTEGER, SAFE_INTEGER_MAXIMUM + 1)
    with pytest.raises(ValueError, match="canonical instant"):
        TimestampValue(0, 1, "1970-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="must be integers"):
        TimestampValue(False, 0, "1970-01-01T00:00:00Z")  # type: ignore[arg-type]


def test_fixed_kinds_and_numeric_domain_fields_cannot_be_overridden() -> None:
    with pytest.raises(TypeError):
        AnchorTypeDefinition("test.anchor", "Anchor", kind=DefinitionKind.LINK)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Anchor(PERSON_UUID, "test.anchor", "Owner", kind=ObjectKind.LINK)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        AnchorUpsert(PERSON_UUID, kind=ObjectKind.LINK)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        RevisionState(0, kind="current")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="cardinality bounds must be integers"):
        Cardinality(False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="system revisions must be integers"):
        SystemEnvelope(False, 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nonnegative integer"):
        GraphChangeRequest(False)  # type: ignore[arg-type]


def test_property_and_system_raw_construction_enforces_structural_types() -> None:
    with pytest.raises(ValueError, match="ValueKind"):
        PropertyDefinition("name", "description", "text")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be Boolean"):
        PropertyDefinition("name", "description", ValueKind.TEXT, required=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be an integer"):
        PropertyDefinition("name", "description", ValueKind.TEXT, minimum_length=True)
    with pytest.raises(ValueError, match="canonical JSON text"):
        SystemEnvelope(0, 0, "not-json")
    with pytest.raises(ValueError, match="canonical JSON text"):
        SystemEnvelope(0, 0, '{"z":1, "a":2}')
    assert SystemEnvelope(0, 0, '{"a":2,"z":1}').legacy_v1 == '{"a":2,"z":1}'
    exact = '{"large":1e400,"precise":0.12345678901234567890123456789}'
    assert SystemEnvelope(0, 0, exact).legacy_v1 == exact
    with pytest.raises(ValueError, match="canonical JSON text"):
        SystemEnvelope(0, 0, '{"number":3.00}')


def test_findings_and_outcomes_are_wire_safe_and_deterministically_ordered() -> None:
    uppercase_uuid = PERSON_UUID.upper()
    later = Finding(
        FindingCode.UNKNOWN,
        "later",
        "/z",
        ("z", "a", "z"),
        (uppercase_uuid, PERSON_UUID),
    )
    earlier = Finding(FindingCode.MISSING, "earlier", "/a")
    assert later.type_keys == ("a", "z")
    assert later.uuids == (PERSON_UUID,)
    outcome = OperationOutcome(OperationStatus.REJECTED, "rejected", (later, earlier))
    assert outcome.findings == (earlier, later)
    with pytest.raises(ValueError, match="summary must be nonempty"):
        Finding(FindingCode.MISSING, "")
    with pytest.raises(ValueError, match="hyphenated UUID"):
        Finding(FindingCode.MISSING, "missing", uuids=("not-a-uuid",))


def test_date_is_exact_proleptic_gregorian_text() -> None:
    assert canonical_date("2000-02-29") == "2000-02-29"
    for invalid in ("1900-02-29", "2024-2-01", "0000-01-01"):
        with pytest.raises(ValueError):
            canonical_date(invalid)


def test_timestamp_normalizes_instant_and_fraction_to_utc() -> None:
    parsed = parse_timestamp("2026-01-02T03:04:05.120000000+02:30")
    assert parsed.canonical == "2026-01-02T00:34:05.12Z"
    assert parse_timestamp("2026-01-02T00:34:05.12Z") == parsed
    assert parse_timestamp("2026-01-02T00:34:05.000Z").canonical.endswith("05Z")


@pytest.mark.parametrize(
    "value",
    (
        "2026-01-02T03:04Z",
        "2026-01-02 03:04:05Z",
        "2026-01-02T03:04:60Z",
        "2026-01-02T03:04:05.1234567890Z",
        "2026-01-02T03:04:05",
        "2026-01-02T03:04:05-00:00",
    ),
)
def test_timestamp_rejects_noncontract_forms(value: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(value)


def test_property_definition_rejects_cross_kind_and_self_inconsistent_rules() -> None:
    definition = PropertyDefinition(
        name="label",
        description="A constrained label",
        value_kind=ValueKind.TEXT,
        allowed_values=(ScalarValue.text("too long"), ScalarValue.text("too long")),
        minimum=ScalarValue.integer(1),
        minimum_length=1,
        maximum_length=3,
        pattern="[a-z]+",
    )
    codes = {finding.code.value for finding in property_definition_findings(definition)}
    assert {"duplicate", "invalidValue", "kindMismatch", "constraintViolation"} <= codes


def test_null_is_present_and_distinct_from_absence() -> None:
    rules = (
        PropertyDefinition(
            name="requiredNullable",
            description="Required but nullable",
            value_kind=ValueKind.TEXT,
            required=True,
            nullable=True,
            minimum_length=100,
        ),
    )
    assert property_value_findings((("requiredNullable", None),), rules, path="/properties") == ()
    findings = property_value_findings((), rules, path="/properties")
    assert [finding.code.value for finding in findings] == ["missing"]


def test_definition_references_and_complete_graph_cardinality_are_validated() -> None:
    definitions = _definitions()
    assert definition_set_findings(definitions, require_system=True) == ()
    graph = (
        Anchor(PERSON_UUID, "life.person", "Owner", SYSTEM),
        AssociatedData(
            DATA_UUID,
            "life.person.details",
            (PERSON_UUID,),
            (("nickname", ScalarValue.text("M")),),
            SYSTEM,
        ),
        Link(LINK_UUID, "life.knows", PERSON_UUID, DATA_UUID, SYSTEM),
    )
    assert graph_findings(graph, definitions, require_system=True) == ()

    missing_detail = (graph[0], graph[2])
    findings = graph_findings(missing_detail, definitions, require_system=True)
    assert {finding.code.value for finding in findings} == {
        "cardinalityViolation",
        "unknown",
    }


def test_all_four_local_cardinality_roles_cover_exact_minimum_maximum_and_unbounded() -> None:
    definitions = _cardinality_definitions()
    a1, a2, a3, data, forward, reverse = _cardinality_graph()
    assert graph_findings((a1, a2, data, forward, reverse), definitions, require_system=True) == ()

    too_few = AssociatedData(data.uuid, data.type_key, (a1.uuid,), system=SYSTEM)
    findings = graph_findings((a1, a2, too_few, forward, reverse), definitions, require_system=True)
    assert _has_cardinality_for(findings, data.uuid, "anchors per object")

    too_many = AssociatedData(data.uuid, data.type_key, (a1.uuid, a2.uuid, a3.uuid), system=SYSTEM)
    findings = graph_findings(
        (a1, a2, a3, too_many, forward, reverse), definitions, require_system=True
    )
    assert _has_cardinality_for(findings, data.uuid, "anchors per object")

    extra_data = tuple(
        AssociatedData(
            f"{index:08d}-1234-4234-8234-123456789abc",
            data.type_key,
            (a1.uuid, a2.uuid),
            system=SYSTEM,
        )
        for index in (4, 5)
    )
    findings = graph_findings(
        (a1, a2, data, *extra_data, forward, reverse), definitions, require_system=True
    )
    assert _has_cardinality_for(findings, a1.uuid, "objects per anchor")
    assert _has_cardinality_for(findings, a2.uuid, "objects per anchor")

    no_links = graph_findings((a1, a2, data), definitions, require_system=True)
    assert _has_cardinality_for(no_links, a1.uuid, "links per source")
    assert _has_cardinality_for(no_links, a1.uuid, "links per target")

    many_links = tuple(
        Link(
            f"{index:08d}-1234-4234-8234-123456789abc",
            "test.link",
            a1.uuid if index % 2 else a2.uuid,
            a2.uuid if index % 2 else a1.uuid,
            SYSTEM,
        )
        for index in range(10, 16)
    )
    findings = graph_findings((a1, a2, data, *many_links), definitions, require_system=True)
    assert _has_cardinality_for(findings, a1.uuid, "links per source")
    assert _has_cardinality_for(findings, a1.uuid, "links per target")

    unbounded = (
        definitions[0],
        definitions[1],
        LinkTypeDefinition(
            "test.link",
            "Unbounded link",
            ("test.a", "test.b"),
            ("test.a", "test.b"),
            Cardinality(0),
            Cardinality(0),
            SYSTEM,
        ),
    )
    assert not any(
        finding.code.value == "cardinalityViolation"
        for finding in graph_findings((a1, a2, *many_links), unbounded, require_system=True)
    )


def _definitions() -> tuple[AnchorTypeDefinition, AssociatedDataTypeDefinition, LinkTypeDefinition]:
    return (
        AnchorTypeDefinition("life.person", "A person", SYSTEM),
        AssociatedDataTypeDefinition(
            "life.person.details",
            "Person details",
            ("life.person",),
            (
                PropertyDefinition(
                    "nickname",
                    "A nickname",
                    ValueKind.TEXT,
                ),
            ),
            Cardinality(1, 1),
            Cardinality(1, 1),
            SYSTEM,
        ),
        LinkTypeDefinition(
            "life.knows",
            "Knowledge relationship",
            ("life.person",),
            ("life.person.details",),
            Cardinality(0),
            Cardinality(0),
            SYSTEM,
        ),
    )


def _cardinality_definitions() -> tuple:
    return (
        AnchorTypeDefinition("test.a", "A", SYSTEM),
        AnchorTypeDefinition("test.b", "B", SYSTEM),
        AssociatedDataTypeDefinition(
            "test.data",
            "Data",
            ("test.a", "test.b"),
            (),
            Cardinality(2, 2),
            Cardinality(1, 2),
            SYSTEM,
        ),
        LinkTypeDefinition(
            "test.link",
            "Link",
            ("test.a", "test.b"),
            ("test.a", "test.b"),
            Cardinality(1, 2),
            Cardinality(1, 2),
            SYSTEM,
        ),
    )


def _cardinality_graph() -> tuple[Anchor, Anchor, Anchor, AssociatedData, Link, Link]:
    a1 = Anchor("a0000001-1234-4234-8234-123456789abc", "test.a", "A1", SYSTEM)
    a2 = Anchor("a0000002-1234-4234-8234-123456789abc", "test.b", "A2", SYSTEM)
    a3 = Anchor("a0000003-1234-4234-8234-123456789abc", "test.a", "A3", SYSTEM)
    data = AssociatedData(
        "d0000001-1234-4234-8234-123456789abc",
        "test.data",
        (a1.uuid, a2.uuid),
        system=SYSTEM,
    )
    forward = Link("10000001-1234-4234-8234-123456789abc", "test.link", a1.uuid, a2.uuid, SYSTEM)
    reverse = Link("10000002-1234-4234-8234-123456789abc", "test.link", a2.uuid, a1.uuid, SYSTEM)
    return a1, a2, a3, data, forward, reverse


def _has_cardinality_for(findings: tuple, uuid: str, text: str) -> bool:
    return any(
        finding.code.value == "cardinalityViolation"
        and uuid in finding.uuids
        and text in finding.summary
        for finding in findings
    )
