"""Focused evidence for streamed, reported, first-use v1 initialization."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

import vellis.v1_import_operations as import_operations
import vellis.v1_json as v1_json
import vellis.v1_stage as stage_module
from vellis.audit import audit_database
from vellis.database import connect_database
from vellis.discovery_operations import type_summary
from vellis.domain import (
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    Finding,
    FindingCode,
    LinkTypeDefinition,
    OperationStatus,
    PropertyDefinition,
    ScalarValue,
    SystemEnvelope,
    ValueKind,
)
from vellis.operations import read_state
from vellis.query_domain import (
    GraphQuery,
    IdentityObjectSelection,
    IdentitySelection,
    PropertySelection,
)
from vellis.read_operations import query_graph
from vellis.v1_candidate import stage_definition, stage_object
from vellis.v1_import_domain import (
    V1Counts,
    V1Disposition,
    V1ImportError,
    V1PublicationDurabilityError,
)
from vellis.v1_import_operations import initialize_from_v1, preview_v1_import
from vellis.v1_json import canonical_number
from vellis.v1_pointer import append_pointer
from vellis.v1_provenance import finding_source_pointer, finding_targets
from vellis.v1_report import add_disposition, render_machine_report, write_human_report
from vellis.v1_stage import create_stage

ANCHOR_UUID = "12345678-1234-4234-8234-123456789abc"
DATA_UUID = "22345678-1234-4234-8234-123456789abc"
LINK_UUID = "32345678-1234-4234-8234-123456789abc"


def _snapshot() -> dict[str, object]:
    return {
        "graph": {
            "anchors": [
                {
                    "uuid": ANCHOR_UUID.upper(),
                    "type": "Person",
                    "display_name": "Ada",
                    "system": {"origin": {"source": "v1"}},
                }
            ],
            "data_objects": [
                {
                    "uuid": DATA_UUID,
                    "type": "Profile",
                    "properties": {
                        "active": True,
                        "name": "Ada",
                        "marker": None,
                        "nested": {"n": 1234567890123456789012345678901},
                    },
                    "system": {"live": True, "origin": "v1"},
                }
            ],
            "links": [
                {
                    "uuid": LINK_UUID,
                    "type": "knows",
                    "source_uuid": ANCHOR_UUID,
                    "target_uuid": DATA_UUID,
                    "system": {"live": True},
                }
            ],
            "anchor_data_index": {ANCHOR_UUID: [DATA_UUID]},
        },
        "schema": {
            "definitions": [
                {
                    "uuid": "legacy-definition-person",
                    "kind": "anchor",
                    "type_key": "Person",
                    "description": "A person.",
                    "payload": {"required_data_types": ["Profile"]},
                    "system": {"live": True, "owner": "Ada"},
                },
                {
                    "uuid": "legacy-definition-profile",
                    "kind": "data_object",
                    "type_key": "Profile",
                    "description": "A profile.",
                    "payload": {
                        "properties": {
                            "active": {
                                "required": True,
                                "value_kinds": ["boolean"],
                                "description": "Whether active.",
                            },
                            "name": {
                                "required": True,
                                "value_kinds": ["string"],
                                "description": "Name.",
                            },
                            "marker": {
                                "required": True,
                                "value_kinds": ["string", "null"],
                                "description": "Optional marker.",
                            },
                            "nested": {
                                "required": True,
                                "value_kinds": ["object"],
                                "description": "Nested legacy content.",
                            },
                        }
                    },
                    "system": {"live": True, "owner": "Ada"},
                },
                {
                    "uuid": "legacy-definition-link",
                    "kind": "link",
                    "type_key": "knows",
                    "description": "A person knows a profile.",
                    "payload": {
                        "allowed_source_types": ["Person"],
                        "allowed_target_types": ["Profile"],
                    },
                    "system": {"live": True},
                },
            ]
        },
        "constraints": {"constraints": []},
        "migration": {"migrations": [{"uuid": "old-transition"}]},
    }


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def test_preview_and_confirm_publish_exact_audited_revision_zero(tmp_path: Path) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())
    report = tmp_path / "preview-report.json"
    preview = preview_v1_import(source, report_out=report, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    assert preview.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert preview.report_sha256 == hashlib.sha256(report.read_bytes()).hexdigest()
    assert preview.candidate_counts.definitions == 3
    assert (
        preview.candidate_counts
        == preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z").candidate_counts
    )

    destination = tmp_path / "owner" / "vellis.db"
    result = initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert result.resulting_revision == 0
    assert audit_database(destination).clean
    assert result.report_path.read_bytes() == report.read_bytes()
    assert oct(destination.stat().st_mode & 0o777) == "0o600"
    assert oct(result.report_path.stat().st_mode & 0o777) == "0o600"

    state = read_state(destination)
    assert len(state.definitions) == 3
    assert len(state.graph) == 3
    data = next(value for value in state.graph if isinstance(value, AssociatedData))
    properties = dict(data.properties)
    assert _nonnull(properties, "nested").value == '{"n":1234567890123456789012345678901}'
    assert properties["marker"] is None
    definition = next(
        value for value in state.definitions if isinstance(value, AssociatedDataTypeDefinition)
    )
    rules = {value.name: value for value in definition.properties}
    assert rules["nested"].value_kind is ValueKind.TEXT
    assert rules["marker"].nullable
    assert data.system is not None and data.system.legacy_v1 == '{"origin":"v1"}'
    assert definition.system is not None
    assert definition.system.legacy_v1 == '{"owner":"Ada"}'

    connection = connect_database(destination, read_only=True)
    try:
        record = connection.execute("SELECT * FROM canonical_record").fetchone()
        assert record is not None and int(record["revision"]) == 0
        assert bytes(record["v1_report_digest"]).hex() == preview.report_sha256
        assert int(connection.execute("SELECT count(*) FROM activity_header").fetchone()[0]) == 0
        assert int(connection.execute("SELECT count(*) FROM draft_metadata").fetchone()[0]) == 0
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='v1_initialization_stage'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()

    summary = type_summary(destination)
    assert summary.status is OperationStatus.ACCEPTED
    assert [item.type_key for item in summary.anchor_types or ()] == ["Person"]
    query = query_graph(
        destination,
        GraphQuery(
            IdentitySelection(
                (IdentityObjectSelection(DATA_UUID, PropertySelection(all=True), True),)
            )
        ),
    )
    assert query.status is OperationStatus.ACCEPTED and query.payload is not None
    hydrated = query.payload.objects[0]
    assert hydrated.system is not None and hydrated.system.legacy_v1 == '{"origin":"v1"}'
    assert _nonnull(dict(hydrated.properties or ()), "nested").value == (
        '{"n":1234567890123456789012345678901}'
    )


def test_preview_and_digest_refusal_publish_nothing(tmp_path: Path) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    assert not (tmp_path / "vellis.db").exists()

    changed = _snapshot()
    changed["migration"] = {"migrations": []}  # type: ignore[index]
    _write(source, changed)
    destination = tmp_path / "owner" / "vellis.db"
    with pytest.raises(V1ImportError, match="source digest"):
        initialize_from_v1(
            source,
            destination,
            confirmed_source_sha256=preview.source_sha256,
            confirmed_report_sha256=preview.report_sha256,
            recorded_at="2026-08-20T00:00:00Z",
        )
    assert not destination.exists()
    assert not destination.with_name("v1-import-report.json").exists()


def test_blocking_reference_and_existing_destination_refuse(tmp_path: Path) -> None:
    value = _snapshot()
    value["graph"]["links"][0]["target_uuid"] = "42345678-1234-4234-8234-123456789abc"  # type: ignore[index]
    source = _write(tmp_path / "v1.json", value)
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    assert not preview.acceptable
    destination = tmp_path / "owner" / "vellis.db"
    destination.parent.mkdir(mode=0o700)
    destination.write_bytes(b"occupied")
    with pytest.raises(FileExistsError):
        initialize_from_v1(
            source,
            destination,
            confirmed_source_sha256=preview.source_sha256,
            confirmed_report_sha256=preview.report_sha256,
        )
    assert destination.read_bytes() == b"occupied"


def test_candidate_validation_reports_every_dangling_object_reference(tmp_path: Path) -> None:
    value = _snapshot()
    second_link = dict(value["graph"]["links"][0])  # type: ignore[index]
    second_link["uuid"] = "42345678-1234-4234-8234-123456789abc"
    second_link["target_uuid"] = "52345678-1234-4234-8234-123456789abc"
    value["graph"]["links"][0]["target_uuid"] = (  # type: ignore[index]
        "62345678-1234-4234-8234-123456789abc"
    )
    value["graph"]["links"].append(second_link)  # type: ignore[index]
    report_path = tmp_path / "all-findings.json"
    preview = preview_v1_import(
        _write(tmp_path / "dangling.json", value),
        report_out=report_path,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    findings = [
        item
        for item in json.loads(report_path.read_text())["dispositions"]
        if item["code"] == "candidate-nonconforming"
        and item["sourcePointer"].endswith("/target_uuid")
    ]
    assert [item["sourcePointer"] for item in findings] == [
        "/graph/links/0/target_uuid",
        "/graph/links/1/target_uuid",
    ]
    assert [item.get("targetUuid") for item in findings] == [
        LINK_UUID,
        "42345678-1234-4234-8234-123456789abc",
    ]
    assert {item.get("targetTypeKey") for item in findings} == {"knows"}


def test_candidate_validation_reports_every_cardinality_subject(tmp_path: Path) -> None:
    value = _snapshot()
    second_anchor = "72345678-1234-4234-8234-123456789abc"
    value["graph"]["anchors"].append(  # type: ignore[index]
        {
            "uuid": second_anchor,
            "type": "Person",
            "display_name": "Grace",
            "system": {"live": True},
        }
    )
    value["constraints"]["constraints"].append(  # type: ignore[index]
        _data_count_constraint("needs-two-profiles", ["Person"], 2, 2)
    )
    report_path = tmp_path / "cardinality-findings.json"
    preview = preview_v1_import(
        _write(tmp_path / "cardinality.json", value),
        report_out=report_path,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    findings = [
        item
        for item in json.loads(report_path.read_text())["dispositions"]
        if item["code"] == "candidate-nonconforming" and "objects per anchor" in item["summary"]
    ]
    assert {item["sourcePointer"] for item in findings} == {"/constraints/constraints/0"}
    assert {item.get("targetUuid") for item in findings} == {ANCHOR_UUID, second_anchor}
    assert {item.get("targetTypeKey") for item in findings} == {"Person"}


def test_actual_association_inference_uses_canonical_uuid_identity(tmp_path: Path) -> None:
    value = _snapshot()
    value["schema"]["definitions"][0]["payload"] = {}  # type: ignore[index]
    value["graph"]["data_objects"][0]["uuid"] = DATA_UUID.upper()  # type: ignore[index]
    source = _write(tmp_path / "actual-association.json", value)
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    destination = tmp_path / "actual-association" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definition = next(
        item
        for item in read_state(destination).definitions
        if isinstance(item, AssociatedDataTypeDefinition)
    )
    assert definition.permitted_anchor_type_keys == ("Person",)


@pytest.mark.parametrize(
    ("case", "expected_disposition", "expected_code"),
    [
        ("absent-data", "blocking", "association-invalid"),
        ("absent-anchor", "blocking", "association-invalid"),
        ("invalid-uuid", "blocking", "association-invalid"),
        ("non-live-data", "omitted", "non-live-association"),
        ("non-live-anchor", "omitted", "non-live-association"),
        ("normalized-duplicate", "blocking", "association-invalid"),
    ],
)
def test_every_source_association_is_independently_disposed(
    tmp_path: Path, case: str, expected_disposition: str, expected_code: str
) -> None:
    value = _snapshot()
    value["graph"]["links"] = []  # type: ignore[index]
    index = value["graph"]["anchor_data_index"]  # type: ignore[index]
    missing = "92345678-1234-4234-8234-123456789abc"
    if case == "absent-data":
        index[ANCHOR_UUID] = [missing]  # type: ignore[index]
    elif case == "absent-anchor":
        value["graph"]["anchor_data_index"] = {missing: [DATA_UUID]}  # type: ignore[index]
    elif case == "invalid-uuid":
        index[ANCHOR_UUID] = ["not-a-uuid"]  # type: ignore[index]
    elif case == "non-live-data":
        value["graph"]["data_objects"][0]["system"]["live"] = False  # type: ignore[index]
    elif case == "non-live-anchor":
        value["graph"]["anchors"][0]["system"]["live"] = False  # type: ignore[index]
    else:
        index[ANCHOR_UUID] = [DATA_UUID, DATA_UUID.upper()]  # type: ignore[index]
    report_path = tmp_path / f"{case}.json"
    preview_v1_import(
        _write(tmp_path / f"{case}-source.json", value),
        report_out=report_path,
        recorded_at="2026-08-20T00:00:00Z",
    )
    dispositions = json.loads(report_path.read_text())["dispositions"]
    assert any(
        item["disposition"] == expected_disposition and item["code"] == expected_code
        for item in dispositions
    )


@pytest.mark.parametrize(
    ("malformed", "pointer"),
    [
        (None, f"/graph/anchor_data_index/{ANCHOR_UUID}"),
        (False, f"/graph/anchor_data_index/{ANCHOR_UUID}"),
        ({"uuid": DATA_UUID}, f"/graph/anchor_data_index/{ANCHOR_UUID}"),
        ([None, DATA_UUID], f"/graph/anchor_data_index/{ANCHOR_UUID}/0"),
        ([False, DATA_UUID], f"/graph/anchor_data_index/{ANCHOR_UUID}/0"),
        ([{"uuid": DATA_UUID}, DATA_UUID], f"/graph/anchor_data_index/{ANCHOR_UUID}/0"),
    ],
)
def test_every_malformed_association_container_or_member_blocks_at_source(
    tmp_path: Path, malformed: object, pointer: str
) -> None:
    value = _snapshot()
    value["graph"]["links"] = []  # type: ignore[index]
    value["graph"]["anchor_data_index"][ANCHOR_UUID] = malformed  # type: ignore[index]
    report = tmp_path / "malformed-association.json"
    preview = preview_v1_import(
        _write(tmp_path / "malformed-association-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    dispositions = json.loads(report.read_text())["dispositions"]
    assert any(
        item["code"] == "association-invalid" and item["sourcePointer"] == pointer
        for item in dispositions
    )


def test_association_uuid_normalization_is_reported_and_duplicates_remain_canonical(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    value["graph"]["anchor_data_index"] = {ANCHOR_UUID.upper(): [DATA_UUID.upper()]}  # type: ignore[index]
    report = tmp_path / "association-normalization.json"
    preview = preview_v1_import(
        _write(tmp_path / "association-normalization-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    normalized = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "uuid-normalized"
        and "/graph/anchor_data_index/" in item["sourcePointer"]
    ]
    assert [item["sourcePointer"].rsplit("/", 1)[-1] for item in normalized] == [
        "anchorUuid",
        "dataUuid",
    ]
    preserved = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "association-preserved"
    ]
    assert len(preserved) == 1
    assert preserved[0]["targetUuid"] == DATA_UUID


@pytest.mark.parametrize(
    ("case", "expected_pointer", "expected_targets"),
    [
        ("object-type", "/graph/anchors/0/type", (ANCHOR_UUID, "Missing", None)),
        (
            "object-property",
            "/graph/data_objects/0/properties/name",
            (DATA_UUID, "Profile", "name"),
        ),
        (
            "definition-reference",
            "/schema/definitions/2/payload/allowed_source_types/0",
            (None, "knows", None),
        ),
        ("inferred-definition-reference", "/graph/anchors/1/type", (None, "knows", None)),
    ],
)
def test_candidate_findings_retain_source_provenance(
    tmp_path: Path,
    case: str,
    expected_pointer: str,
    expected_targets: tuple[str | None, str | None, str | None],
) -> None:
    value = _snapshot()
    if case == "object-type":
        value["graph"]["anchors"][0]["type"] = "Missing"  # type: ignore[index]
    elif case == "object-property":
        value["schema"]["definitions"][1]["payload"]["properties"]["name"][  # type: ignore[index]
            "allowed_values"
        ] = ["Grace"]
    elif case == "definition-reference":
        value["schema"]["definitions"][2]["payload"]["allowed_source_types"] = [  # type: ignore[index]
            "Missing"
        ]
    else:
        missing_uuid = "72345678-1234-4234-8234-123456789abc"
        value["graph"]["anchors"].append(  # type: ignore[index]
            {
                "uuid": missing_uuid,
                "type": "Missing",
                "display_name": "Missing",
                "system": {"live": True},
            }
        )
        value["graph"]["links"][0]["source_uuid"] = missing_uuid  # type: ignore[index]
    report = tmp_path / f"provenance-{case}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"provenance-{case}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    findings = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "candidate-nonconforming"
    ]
    selected = [
        item
        for item in findings
        if item["sourcePointer"] == expected_pointer
        and (
            item.get("targetUuid"),
            item.get("targetTypeKey"),
            item.get("targetProperty"),
        )
        == expected_targets
    ]
    assert selected
    pointers = {item["sourcePointer"] for item in findings}
    assert not any(pointer.startswith(("/objects/", "/definitions/")) for pointer in pointers)


def test_special_link_type_path_maps_unknown_endpoint_to_exact_v1_provenance(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    special_type = "knows/bad~key"
    unknown_endpoint = "missing/type~key"
    value["graph"]["links"][0]["type"] = special_type  # type: ignore[index]
    definition = value["schema"]["definitions"][2]  # type: ignore[index]
    definition["type_key"] = special_type  # type: ignore[index]
    definition["payload"]["allowed_source_types"] = [unknown_endpoint]  # type: ignore[index]
    report = tmp_path / "special-type-provenance.json"
    preview = preview_v1_import(
        _write(tmp_path / "special-type-provenance-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    findings = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "candidate-nonconforming"
    ]
    assert any(
        item["sourcePointer"] == "/schema/definitions/2/payload/allowed_source_types/0"
        and item.get("targetTypeKey") == special_type
        for item in findings
    )


def test_missing_required_named_property_has_exact_source_and_target_identity(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    del value["graph"]["data_objects"][0]["properties"]["name"]  # type: ignore[index]
    report = tmp_path / "missing-property.json"
    preview = preview_v1_import(
        _write(tmp_path / "missing-property-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    findings = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "candidate-nonconforming"
    ]
    assert any(
        item["sourcePointer"] == "/graph/data_objects/0/properties/name"
        and item.get("targetUuid") == DATA_UUID
        and item.get("targetTypeKey") == "Profile"
        and item.get("targetProperty") == "name"
        for item in findings
    )


def test_dynamic_property_names_are_escaped_across_conversion_omission_and_findings(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    converted_name = "converted/value~legacy"
    missing_name = "missing/value~required"
    properties = value["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    graph_properties = value["graph"]["data_objects"][0]["properties"]  # type: ignore[index]
    properties[converted_name] = {  # type: ignore[index]
        "required": True,
        "value_kinds": ["object"],
        "description": "Converted special name.",
        "minimum_length": 1,
    }
    graph_properties[converted_name] = {"nested": True}  # type: ignore[index]
    properties[missing_name] = {  # type: ignore[index]
        "required": True,
        "value_kinds": ["string"],
        "description": "Missing special name.",
    }
    report = tmp_path / "escaped-properties.json"
    preview = preview_v1_import(
        _write(tmp_path / "escaped-properties-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    dispositions = json.loads(report.read_text())["dispositions"]
    converted_pointer = "/schema/definitions/1/payload/properties/converted~1value~0legacy"
    missing_pointer = "/graph/data_objects/0/properties/missing~1value~0required"
    assert any(
        item["code"] == "property-json-text"
        and item["sourcePointer"] == converted_pointer
        and item.get("targetProperty") == converted_name
        for item in dispositions
    )
    assert any(
        item["code"] == "property-constraints-omitted"
        and item["sourcePointer"] == converted_pointer
        and item.get("targetProperty") == converted_name
        for item in dispositions
    )
    assert any(
        item["code"] == "candidate-nonconforming"
        and item["sourcePointer"] == missing_pointer
        and item.get("targetProperty") == missing_name
        for item in dispositions
    )


def test_digit_only_property_name_precedes_numeric_candidate_index_in_provenance() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_stage(connection)
        system = SystemEnvelope(0, 0)
        definition = AssociatedDataTypeDefinition(
            "Profile",
            "Profile.",
            ("Person",),
            (
                PropertyDefinition("name", "Name.", ValueKind.TEXT),
                PropertyDefinition("123", "Digits.", ValueKind.TEXT, True),
                PropertyDefinition("", "Empty.", ValueKind.TEXT),
            ),
            Cardinality(1),
            Cardinality(0),
            system,
        )
        value = AssociatedData(
            DATA_UUID,
            "Profile",
            (ANCHOR_UUID,),
            (("123", ScalarValue.text("value")),),
            system,
        )
        stage_definition(connection, definition, "/schema/definitions/1")
        stage_object(connection, value, "/graph/data_objects/0")
        for code in (FindingCode.CONSTRAINT_VIOLATION, FindingCode.MISSING):
            assert (
                finding_source_pointer(
                    connection,
                    Finding(
                        code,
                        "digit property",
                        f"/objects/{DATA_UUID}/properties/123",
                        type_keys=("Profile",),
                        uuids=(DATA_UUID,),
                    ),
                )
                == "/graph/data_objects/0/properties/123"
            )
        assert (
            finding_source_pointer(
                connection,
                Finding(
                    FindingCode.INVALID_VALUE,
                    "digit refinement",
                    "/definitions/Profile/properties/123/allowedValues/0",
                    type_keys=("Profile",),
                ),
            )
            == "/schema/definitions/1/payload/properties/123/allowed_values"
        )
        assert (
            finding_source_pointer(
                connection,
                Finding(
                    FindingCode.INVALID_VALUE,
                    "numeric property index",
                    "/definitions/Profile/properties/0/allowedValues/0",
                    type_keys=("Profile",),
                ),
            )
            == "/schema/definitions/1/payload/properties/name/allowed_values"
        )
        assert (
            finding_source_pointer(
                connection,
                Finding(
                    FindingCode.INVALID_VALUE,
                    "numeric definition and property indices",
                    "/definitions/0/properties/0/allowedValues/0",
                    type_keys=("Profile",),
                ),
            )
            == "/schema/definitions/1/payload/properties/name/allowed_values"
        )
        assert (
            finding_source_pointer(
                connection,
                Finding(
                    FindingCode.INVALID_VALUE,
                    "numeric object property index",
                    f"/objects/{DATA_UUID}/properties/0",
                    type_keys=("Profile",),
                    uuids=(DATA_UUID,),
                ),
            )
            == "/graph/data_objects/0/properties/123"
        )
        target_cases = (
            (f"/objects/{DATA_UUID}/properties/123", "123"),
            (f"/objects/{DATA_UUID}/properties/0", "123"),
            ("/definitions/Profile/properties/123/allowedValues/0", "123"),
            ("/definitions/Profile/properties/0/allowedValues/0", "name"),
            ("/definitions/Profile/properties//name", None),
        )
        for path, expected in target_cases:
            assert (
                finding_targets(
                    connection,
                    Finding(
                        FindingCode.INVALID_VALUE,
                        "target property",
                        path,
                        type_keys=("Profile",),
                        uuids=(DATA_UUID,) if path.startswith("/objects/") else (),
                    ),
                )[2]
                == expected
            )
    finally:
        connection.close()


def test_absent_required_digit_only_property_uses_the_staged_type_definition(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    properties = value["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    properties["123"] = {  # type: ignore[index]
        "required": True,
        "value_kinds": ["string"],
        "description": "Digits.",
    }
    report = tmp_path / "missing-digit-property.json"
    preview = preview_v1_import(
        _write(tmp_path / "missing-digit-property-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "candidate-nonconforming"
        and item["sourcePointer"] == "/graph/data_objects/0/properties/123"
        and item.get("targetProperty") == "123"
        and item.get("targetUuid") == DATA_UUID
        for item in json.loads(report.read_text())["dispositions"]
    )


def test_digit_only_definition_keys_preserve_each_origin_for_a_shared_missing_member(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    definitions = value["schema"]["definitions"]  # type: ignore[index]
    for type_key in ("1", "2"):
        definitions.append(  # type: ignore[union-attr]
            {
                "uuid": f"legacy-definition-{type_key}",
                "kind": "link",
                "type_key": type_key,
                "description": f"Numeric link {type_key}.",
                "payload": {
                    "allowed_source_types": ["SharedMissing"],
                    "allowed_target_types": ["Profile"],
                },
                "system": {"live": True},
            }
        )
    report = tmp_path / "numeric-definition-keys.json"
    preview = preview_v1_import(
        _write(tmp_path / "numeric-definition-keys-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    findings = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "candidate-nonconforming" and item.get("targetTypeKey") in {"1", "2"}
    ]
    assert {
        (item["sourcePointer"], item["targetTypeKey"])
        for item in findings
        if item["sourcePointer"].endswith("/payload/allowed_source_types/0")
    } == {
        ("/schema/definitions/3/payload/allowed_source_types/0", "1"),
        ("/schema/definitions/4/payload/allowed_source_types/0", "2"),
    }


def test_invalid_empty_property_keeps_exact_source_pointer_without_target_identity(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    properties = value["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    properties[""] = {  # type: ignore[index]
        "required": False,
        "value_kinds": ["string"],
        "description": "Invalid empty property.",
    }
    report = tmp_path / "empty-property.json"
    preview = preview_v1_import(
        _write(tmp_path / "empty-property-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "candidate-nonconforming"
        and item["sourcePointer"] == "/schema/definitions/1/payload/properties//name"
        and item.get("targetTypeKey") == "Profile"
        and "targetProperty" not in item
        for item in json.loads(report.read_text())["dispositions"]
    )


def test_report_is_deterministic_and_contains_every_disposition_family(tmp_path: Path) -> None:
    value = _snapshot()
    value["graph"]["anchors"].append(  # type: ignore[index]
        {
            "uuid": "52345678-1234-4234-8234-123456789abc",
            "type": "Retired",
            "display_name": "Old",
            "system": {"live": False},
        }
    )
    source = _write(tmp_path / "v1.json", value)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    one = preview_v1_import(source, report_out=first, recorded_at="2026-08-20T00:00:00Z")
    two = preview_v1_import(source, report_out=second, recorded_at="2026-08-20T00:00:00Z")
    assert one.report_sha256 == two.report_sha256
    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_text(encoding="utf-8"))
    dispositions = {item["disposition"] for item in report["dispositions"]}
    assert {"preserved", "converted", "omitted"} <= dispositions
    assert report["summary"]["blocking"] == 0


def test_machine_and_streamed_human_reports_share_exact_identity_order(tmp_path: Path) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_stage(connection)
        entries = (
            ("c4", "/a", {"target_uuid": LINK_UUID}),
            ("c2", "/a", {"target_type_key": "B"}),
            ("c5", "/z", {}),
            ("c1", "/a", {"target_property": "z"}),
            ("c3", "/a", {"target_type_key": "A"}),
        )
        for code, pointer, targets in entries:
            add_disposition(
                connection,
                V1Disposition.OMITTED,
                code,
                pointer,
                code,
                **targets,
            )
        machine = tmp_path / "machine.json"
        human = tmp_path / "human.txt"
        render_machine_report(
            connection,
            machine,
            source_sha256="01" * 32,
            source_byte_count=1,
            candidate_sha256="02" * 32,
            counts=V1Counts(0, 0, 0, 0),
        )
        write_human_report(
            connection,
            human,
            source_sha256="01" * 32,
            candidate_sha256="02" * 32,
        )
    finally:
        connection.close()
    machine_codes = [item["code"] for item in json.loads(machine.read_text())["dispositions"]]
    human_codes = [
        line.split(" | ")[-1].split(":", 1)[0]
        for line in human.read_text().splitlines()
        if line.startswith("- [")
    ]
    assert machine_codes == human_codes == ["c1", "c3", "c2", "c4", "c5"]


@pytest.mark.parametrize(
    "disposition",
    [
        V1Disposition.PRESERVED,
        V1Disposition.CONVERTED,
        V1Disposition.OMITTED,
        V1Disposition.BLOCKING,
    ],
)
def test_disposition_targets_are_centrally_canonical_and_exact(
    tmp_path: Path, disposition: V1Disposition
) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_stage(connection)
        add_disposition(
            connection,
            disposition,
            f"target-{disposition.value}",
            "/source",
            "target normalization",
            target_uuid=ANCHOR_UUID.upper(),
            target_type_key="Type/With~Marks",
            target_property="property/with~marks",
        )
        add_disposition(
            connection,
            disposition,
            f"invalid-{disposition.value}",
            "/invalid",
            "invalid raw identity remains only in source and summary",
            target_uuid="12345678-raw-value-of-length-36xxxxx",
            target_type_key=17,
            target_property=None,
        )
        report = tmp_path / f"targets-{disposition.value}.json"
        render_machine_report(
            connection,
            report,
            source_sha256="00" * 32,
            source_byte_count=0,
            candidate_sha256="11" * 32,
            counts=V1Counts(0, 0, 0, 0),
        )
        entries = json.loads(report.read_text())["dispositions"]
        normalized = next(item for item in entries if item["sourcePointer"] == "/source")
        assert normalized["targetUuid"] == ANCHOR_UUID
        assert normalized["targetTypeKey"] == "Type/With~Marks"
        assert normalized["targetProperty"] == "property/with~marks"
        invalid = next(item for item in entries if item["sourcePointer"] == "/invalid")
        assert not ({"targetUuid", "targetTypeKey", "targetProperty"} & set(invalid))
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        (("property/with~marks",), "/base/property~1with~0marks"),
        (("type/key", "member~name"), "/base/type~1key/member~0name"),
        ((0, "a/b~c"), "/base/0/a~1b~0c"),
    ],
)
def test_every_dynamic_source_pointer_segment_uses_rfc6901(
    segments: tuple[object, ...], expected: str
) -> None:
    assert append_pointer("/base", *segments) == expected


def test_canonical_number_does_not_expand_rejected_huge_plain_form(monkeypatch) -> None:
    def forbidden(*_args):
        raise AssertionError("huge plain form must not be constructed before length choice")

    monkeypatch.setattr(v1_json, "_plain_number", forbidden)
    assert canonical_number("1e100000000") == "1e100000000"


def test_preview_uses_stream_parser_not_json_load(tmp_path: Path, monkeypatch) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("whole-document json.load must not be used")

    monkeypatch.setattr(json, "load", forbidden)
    assert preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z").acceptable


def test_report_digest_mismatch_and_preboundary_publication_failure_leave_no_files(
    tmp_path: Path, monkeypatch
) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    wrong = tmp_path / "wrong" / "vellis.db"
    with pytest.raises(V1ImportError, match="report digest"):
        initialize_from_v1(
            source,
            wrong,
            confirmed_source_sha256=preview.source_sha256,
            confirmed_report_sha256="00" * 32,
            recorded_at="2026-08-20T00:00:00Z",
        )
    assert not wrong.exists()
    assert not wrong.with_name("v1-import-report.json").exists()

    def fail_rename(source_path, destination_path):
        source_root = Path(source_path)
        destination_root = Path(destination_path)
        assert (source_root / "vellis.db").exists()
        assert (source_root / "v1-import-report.json").exists()
        assert not destination_root.exists()
        raise OSError("injected atomic publication failure")

    monkeypatch.setattr(import_operations.os, "rename", fail_rename)
    destination = tmp_path / "failed" / "vellis.db"
    with pytest.raises(OSError, match="atomic publication"):
        initialize_from_v1(
            source,
            destination,
            confirmed_source_sha256=preview.source_sha256,
            confirmed_report_sha256=preview.report_sha256,
            recorded_at="2026-08-20T00:00:00Z",
        )
    assert not destination.exists()
    assert not destination.with_name("v1-import-report.json").exists()


def test_one_directory_rename_is_the_only_visibility_boundary(tmp_path: Path, monkeypatch) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    destination = tmp_path / "ready" / "vellis.db"
    real_rename = import_operations.os.rename
    calls = 0

    def observe_rename(source_path, destination_path):
        nonlocal calls
        calls += 1
        source_root = Path(source_path)
        destination_root = Path(destination_path)
        assert (source_root / destination.name).exists()
        assert (source_root / "v1-import-report.json").exists()
        assert not destination_root.exists()
        real_rename(source_path, destination_path)
        assert (destination_root / destination.name).exists()
        assert (destination_root / "v1-import-report.json").exists()

    monkeypatch.setattr(import_operations.os, "rename", observe_rename)
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert calls == 1


def test_atomic_publication_replaces_an_existing_empty_private_destination(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    destination = tmp_path / "empty" / "vellis.db"
    destination.parent.mkdir(mode=0o700)
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert destination.exists()
    assert destination.with_name("v1-import-report.json").exists()


def test_post_publication_flush_failure_reports_published_truth(
    tmp_path: Path, monkeypatch
) -> None:
    source = _write(tmp_path / "v1.json", _snapshot())
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    real_flush = import_operations._flush_directory
    calls = 0

    def fail_second_flush(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected directory durability failure")
        return real_flush(path)

    monkeypatch.setattr(import_operations, "_flush_directory", fail_second_flush)
    destination = tmp_path / "published" / "vellis.db"
    with pytest.raises(V1PublicationDurabilityError, match="published"):
        initialize_from_v1(
            source,
            destination,
            confirmed_source_sha256=preview.source_sha256,
            confirmed_report_sha256=preview.report_sha256,
            recorded_at="2026-08-20T00:00:00Z",
        )
    assert destination.exists()
    assert destination.with_name("v1-import-report.json").exists()


def test_malformed_source_and_duplicate_identity_are_reported_without_publication(
    tmp_path: Path,
) -> None:
    malformed = _snapshot()
    malformed["constraints"] = []
    with pytest.raises(V1ImportError, match="complete Vellis v1"):
        preview_v1_import(_write(tmp_path / "malformed.json", malformed))

    duplicate = _snapshot()
    duplicate["graph"]["anchors"].append(  # type: ignore[index]
        {
            "uuid": ANCHOR_UUID,
            "type": "Person",
            "display_name": "Duplicate",
            "system": {"live": True},
        }
    )
    report = tmp_path / "duplicate-report.json"
    preview = preview_v1_import(_write(tmp_path / "duplicate.json", duplicate), report_out=report)
    assert not preview.acceptable
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "duplicate-identity" in codes


@pytest.mark.parametrize(
    ("namespace", "case", "expected_code"),
    [
        ("graph", "same-kind-live", "duplicate-identity"),
        ("graph", "same-kind-nonlive", "duplicate-identity"),
        ("graph", "cross-kind-nonlive", "identity-kind-conflict"),
        ("graph", "normalized-cross-kind", "identity-kind-conflict"),
        ("graph", "invalid-nonlive", "identity-invalid"),
        ("type", "same-kind-live", "duplicate-identity"),
        ("type", "same-kind-nonlive", "duplicate-identity"),
        ("type", "cross-kind-nonlive", "identity-kind-conflict"),
        ("type", "invalid-nonlive", "identity-invalid"),
    ],
)
def test_identity_reservations_scan_every_live_and_nonlive_family_before_omission(
    tmp_path: Path, namespace: str, case: str, expected_code: str
) -> None:
    value = _snapshot()
    if namespace == "graph":
        if case == "invalid-nonlive":
            value["graph"]["anchors"].append(  # type: ignore[index]
                {
                    "uuid": "not-a-uuid",
                    "type": "Person",
                    "display_name": "Retired",
                    "system": {"live": False},
                }
            )
        else:
            kind = "data" if "cross-kind" in case else "anchor"
            duplicate = {
                "uuid": ANCHOR_UUID.upper() if case == "normalized-cross-kind" else ANCHOR_UUID,
                "type": "Profile" if kind == "data" else "Person",
                "system": {"live": "nonlive" not in case},
            }
            if kind == "data":
                duplicate["properties"] = {}
                value["graph"]["data_objects"].append(duplicate)  # type: ignore[index]
            else:
                duplicate["display_name"] = "Duplicate"
                value["graph"]["anchors"].append(duplicate)  # type: ignore[index]
    elif case == "invalid-nonlive":
        value["schema"]["definitions"].append(  # type: ignore[index]
            {
                "kind": "unknown",
                "type_key": "",
                "description": "Invalid.",
                "payload": {},
                "system": {"live": False},
            }
        )
    else:
        definition = {
            "uuid": "duplicate-definition",
            "kind": "link" if "cross-kind" in case else "anchor",
            "type_key": "Person",
            "description": "Duplicate.",
            "payload": {
                "allowed_source_types": ["Person"],
                "allowed_target_types": ["Profile"],
            }
            if "cross-kind" in case
            else {},
            "system": {"live": "nonlive" not in case},
        }
        value["schema"]["definitions"].append(definition)  # type: ignore[index]
    report = tmp_path / f"identity-{namespace}-{case}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"identity-{namespace}-{case}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    dispositions = json.loads(report.read_text())["dispositions"]
    assert any(item["code"] == expected_code for item in dispositions)
    if case == "normalized-cross-kind":
        assert any(item["code"] == "uuid-normalized" for item in dispositions)


def test_type_keys_remain_exact_across_live_and_nonlive_identity_scan(tmp_path: Path) -> None:
    value = _snapshot()
    value["schema"]["definitions"].append(  # type: ignore[index]
        {
            "uuid": "case-distinct",
            "kind": "anchor",
            "type_key": "person",
            "description": "Case-distinct retired key.",
            "payload": {},
            "system": {"live": False},
        }
    )
    report = tmp_path / "case-distinct.json"
    preview = preview_v1_import(
        _write(tmp_path / "case-distinct-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "duplicate-identity" not in codes
    assert "identity-kind-conflict" not in codes


@pytest.mark.parametrize("family", ["anchors", "data_objects", "links", "definitions"])
def test_invalid_liveness_is_a_reported_preservation_failure_not_an_early_abort(
    tmp_path: Path, family: str
) -> None:
    value = _snapshot()
    if family == "definitions":
        entry = value["schema"][family][0]  # type: ignore[index]
    else:
        entry = value["graph"][family][0]  # type: ignore[index]
    entry["system"]["live"] = "false"  # type: ignore[index]
    report = tmp_path / f"invalid-live-{family}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"invalid-live-{family}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "source-entry-invalid"
        for item in json.loads(report.read_text())["dispositions"]
    )


def test_invalid_constraint_liveness_is_reported_without_bypassing_report(tmp_path: Path) -> None:
    value = _snapshot()
    constraint = _data_count_constraint("invalid-live", ["Person"], 0, 1)
    constraint["system"] = {"live": "false"}
    value["constraints"]["constraints"].append(constraint)  # type: ignore[index]
    report = tmp_path / "invalid-constraint-live.json"
    preview = preview_v1_import(
        _write(tmp_path / "invalid-constraint-live-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "constraint-invalid"
        for item in json.loads(report.read_text())["dispositions"]
    )


@pytest.mark.parametrize("family", ["anchors", "data_objects", "links"])
@pytest.mark.parametrize("live", [True, False])
def test_same_kind_repetition_in_every_graph_family_is_not_imported_as_history(
    tmp_path: Path, family: str, live: bool
) -> None:
    value = _snapshot()
    original = dict(value["graph"][family][0])  # type: ignore[index]
    original["system"] = {"live": live}
    value["graph"][family].append(original)  # type: ignore[index]
    report = tmp_path / f"duplicate-{family}-{live}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"duplicate-{family}-{live}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "duplicate-identity"
        for item in json.loads(report.read_text())["dispositions"]
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [("anchors", "data_objects"), ("anchors", "links"), ("data_objects", "links")],
)
def test_every_cross_graph_kind_pair_conflicts_before_nonlive_omission(
    tmp_path: Path, first: str, second: str
) -> None:
    value = _snapshot()
    identity = value["graph"][first][0]["uuid"]  # type: ignore[index]
    value["graph"][second][0]["uuid"] = str(identity).upper()  # type: ignore[index]
    value["graph"][second][0]["system"]["live"] = False  # type: ignore[index]
    report = tmp_path / f"cross-{first}-{second}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"cross-{first}-{second}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    dispositions = json.loads(report.read_text())["dispositions"]
    assert any(item["code"] == "identity-kind-conflict" for item in dispositions)


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("live", [True, False])
def test_same_kind_repetition_in_every_definition_family_is_not_reactivation(
    tmp_path: Path, index: int, live: bool
) -> None:
    value = _snapshot()
    original = dict(value["schema"]["definitions"][index])  # type: ignore[index]
    original["uuid"] = f"duplicate-definition-{index}"
    original["system"] = {"live": live}
    value["schema"]["definitions"].append(original)  # type: ignore[index]
    report = tmp_path / f"duplicate-definition-{index}-{live}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"duplicate-definition-{index}-{live}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "duplicate-identity"
        for item in json.loads(report.read_text())["dispositions"]
    )


@pytest.mark.parametrize(("first", "second"), [(0, 1), (0, 2), (1, 2)])
def test_every_cross_definition_kind_pair_conflicts_before_nonlive_omission(
    tmp_path: Path, first: int, second: int
) -> None:
    value = _snapshot()
    key = value["schema"]["definitions"][first]["type_key"]  # type: ignore[index]
    value["schema"]["definitions"][second]["type_key"] = key  # type: ignore[index]
    value["schema"]["definitions"][second]["system"]["live"] = False  # type: ignore[index]
    report = tmp_path / f"cross-definition-{first}-{second}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"cross-definition-{first}-{second}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert not preview.acceptable
    assert any(
        item["code"] == "identity-kind-conflict"
        for item in json.loads(report.read_text())["dispositions"]
    )


def test_large_source_staging_retains_only_the_current_source_entry(
    tmp_path: Path, monkeypatch
) -> None:
    value = _snapshot()
    anchors = value["graph"]["anchors"]  # type: ignore[index]
    for index in range(1, 301):
        anchors.append(  # type: ignore[union-attr]
            {
                "uuid": f"{index:08x}-1234-4234-8234-{index:012x}",
                "type": "Person",
                "display_name": f"Person {index}",
                "system": {"live": True},
            }
        )
    source = _write(tmp_path / "large.json", value)
    original_items = stage_module.ijson.items

    class Tracked(dict):
        active = 0
        maximum = 0

        def __init__(self, item):
            super().__init__(item)
            type(self).active += 1
            type(self).maximum = max(type(self).maximum, type(self).active)

        def __del__(self):
            type(self).active -= 1

    def tracked_items(*args, **kwargs):
        for item in original_items(*args, **kwargs):
            yield Tracked(item)

    monkeypatch.setattr(stage_module.ijson, "items", tracked_items)
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    assert preview.candidate_counts.anchors == 301
    assert Tracked.maximum <= 2


def test_large_decimal_lexeme_and_nonlive_content_are_explicitly_disposed(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    data = value["graph"]["data_objects"][0]  # type: ignore[index]
    data["properties"]["astronomical"] = "DECIMAL_SENTINEL"  # type: ignore[index]
    definitions = value["schema"]["definitions"]  # type: ignore[index]
    definitions[1]["payload"]["properties"]["astronomical"] = _property_rule(  # type: ignore[index]
        "number", "A number outside binary64."
    )
    definitions.append(  # type: ignore[union-attr]
        {
            "uuid": "legacy-retired-definition",
            "kind": "anchor",
            "type_key": "Retired",
            "description": "Retired.",
            "payload": {},
            "system": {"live": False, "reason": "old"},
        }
    )
    value["graph"]["data_objects"].append(  # type: ignore[index]
        {
            "uuid": "62345678-1234-4234-8234-123456789abc",
            "type": "Profile",
            "properties": {},
            "system": {"live": False},
        }
    )
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        '"DECIMAL_SENTINEL"', "1.23456789012345678901234567890123456789e400"
    )
    source = tmp_path / "decimal.json"
    source.write_text(text, encoding="utf-8")
    report = tmp_path / "decimal-report.json"
    preview = preview_v1_import(source, report_out=report, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    destination = tmp_path / "decimal" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    imported = next(
        item for item in read_state(destination).graph if isinstance(item, AssociatedData)
    )
    assert _nonnull(dict(imported.properties), "astronomical").value == (
        "1.23456789012345678901234567890123456789e400"
    )
    dispositions = json.loads(report.read_text())["dispositions"]
    omitted = [item for item in dispositions if item["disposition"] == "omitted"]
    assert any(item["code"] == "non-live" for item in omitted)
    assert any(item["code"] == "property-json-text" for item in dispositions)


def test_compatible_property_constraints_map_and_unsupported_refinement_is_reported(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    name = value["schema"]["definitions"][1]["payload"]["properties"]["name"]  # type: ignore[index]
    name.update(  # type: ignore[union-attr]
        {
            "allowed_values": ["Ada", "Alice"],
            "minimum_length": 1,
            "maximum_length": 20,
            "pattern": "A.*",
            "format": "legacy-name-format",
        }
    )
    source = _write(tmp_path / "constraints.json", value)
    report = tmp_path / "constraints-report.json"
    preview = preview_v1_import(source, report_out=report, recorded_at="2026-08-20T00:00:00Z")
    destination = tmp_path / "constraints" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definition = next(
        item
        for item in read_state(destination).definitions
        if isinstance(item, AssociatedDataTypeDefinition)
    )
    rule = next(item for item in definition.properties if item.name == "name")
    assert tuple(item.value for item in rule.allowed_values) == ("Ada", "Alice")
    assert (rule.minimum_length, rule.maximum_length, rule.pattern) == (1, 20, "A.*")
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "property-refinement-omitted" in codes


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_values", []),
        ("allowed_values", ["Ada", 1]),
        ("minimum", "A"),
        ("maximum", "Z"),
        ("minimum_length", -1),
        ("maximum_length", "twenty"),
        ("pattern", "(?=unsupported-lookahead)"),
    ],
)
def test_every_supplied_incompatible_property_refinement_is_reported(
    tmp_path: Path, field: str, value: object
) -> None:
    snapshot = _snapshot()
    rule = snapshot["schema"]["definitions"][1]["payload"]["properties"]["name"]  # type: ignore[index]
    rule[field] = value  # type: ignore[index]
    report_path = tmp_path / f"invalid-{field}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"invalid-{field}-source.json", snapshot),
        report_out=report_path,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    dispositions = json.loads(report_path.read_text())["dispositions"]
    assert any(
        item["code"] == "property-constraints-omitted" and item.get("targetProperty") == "name"
        for item in dispositions
    )


@pytest.mark.parametrize("target_kind", ["boolean", "integer", "number", "text", "jsonText"])
@pytest.mark.parametrize(
    ("field", "field_value"),
    [
        ("allowed_values", "kind-value"),
        ("minimum", "kind-minimum"),
        ("maximum", "kind-maximum"),
        ("minimum_length", 1),
        ("maximum_length", 20),
        ("pattern", "A.*"),
    ],
)
def test_every_refinement_field_is_mapped_or_reported_for_every_conversion_path(
    tmp_path: Path, target_kind: str, field: str, field_value: object
) -> None:
    snapshot = _snapshot()
    properties = snapshot["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    data_properties = snapshot["graph"]["data_objects"][0]["properties"]  # type: ignore[index]
    names = {
        "boolean": "active",
        "text": "name",
        "jsonText": "nested",
        "integer": "integerValue",
        "number": "numberValue",
    }
    name = names[target_kind]
    if target_kind == "integer":
        properties[name] = _property_rule("integer", "An integer.")  # type: ignore[index]
        data_properties[name] = 5  # type: ignore[index]
    elif target_kind == "number":
        properties[name] = _property_rule("number", "A number.")  # type: ignore[index]
        data_properties[name] = 5.5  # type: ignore[index]
    rule = properties[name]  # type: ignore[index]
    assert isinstance(rule, dict)
    value_by_kind = {
        "boolean": True,
        "integer": 5,
        "number": 5.5,
        "text": "Ada",
        "jsonText": {"n": 1},
    }
    supplied = [value_by_kind[target_kind]] if field == "allowed_values" else field_value
    if field == "minimum":
        supplied = {"integer": 1, "number": 1.5}.get(target_kind, value_by_kind[target_kind])
    elif field == "maximum":
        supplied = {"integer": 10, "number": 10.0}.get(target_kind, value_by_kind[target_kind])
    rule[field] = supplied
    compatible = field == "allowed_values" and target_kind != "jsonText"
    compatible = compatible or (
        field in {"minimum", "maximum"} and target_kind in {"integer", "number"}
    )
    compatible = compatible or (
        field in {"minimum_length", "maximum_length", "pattern"} and target_kind == "text"
    )
    report = tmp_path / f"matrix-{target_kind}-{field}.json"
    source = _write(tmp_path / f"matrix-{target_kind}-{field}-source.json", snapshot)
    preview = preview_v1_import(source, report_out=report, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    dispositions = json.loads(report.read_text())["dispositions"]
    omitted = [
        item
        for item in dispositions
        if item["code"] == "property-constraints-omitted"
        and item.get("targetTypeKey") == "Profile"
        and item.get("targetProperty") == name
    ]
    assert bool(omitted) is not compatible
    if not compatible:
        return
    destination = tmp_path / f"matrix-{target_kind}-{field}" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definition = next(
        item
        for item in read_state(destination).definitions
        if isinstance(item, AssociatedDataTypeDefinition)
    )
    imported = next(item for item in definition.properties if item.name == name)
    attribute = {
        "allowed_values": "allowed_values",
        "minimum": "minimum",
        "maximum": "maximum",
        "minimum_length": "minimum_length",
        "maximum_length": "maximum_length",
        "pattern": "pattern",
    }[field]
    assert getattr(imported, attribute) not in (None, ())


def test_json_text_conversion_does_not_bypass_unknown_refinement_reporting(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    nested = snapshot["schema"]["definitions"][1]["payload"]["properties"]["nested"]  # type: ignore[index]
    nested["format"] = "legacy-object-format"  # type: ignore[index]
    report = tmp_path / "converted-unknown-refinement.json"
    preview = preview_v1_import(
        _write(tmp_path / "converted-unknown-refinement-source.json", snapshot),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    dispositions = json.loads(report.read_text())["dispositions"]
    assert any(
        item["code"] == "property-refinement-omitted" and item.get("targetProperty") == "nested"
        for item in dispositions
    )


@pytest.mark.parametrize(
    ("collection", "expected_shape", "outcome"),
    [
        ("value-kinds", "list", "blocking"),
        ("required-data-types", "list", "blocking"),
        ("optional-data-types", "list", "blocking"),
        ("allowed-source-types", "list", "blocking"),
        ("allowed-target-types", "list", "blocking"),
        ("definition-properties", "map", "blocking"),
        ("graph-properties", "map", "blocking"),
        ("anchor-buckets", "list", "omitted"),
        ("data-requirements", "list", "omitted"),
        ("group-bindings", "list", "omitted"),
    ],
)
@pytest.mark.parametrize("wrong_shape", ["scalar", "object", "null"])
def test_every_collection_shape_is_blocked_or_explicitly_omitted(
    tmp_path: Path,
    collection: str,
    expected_shape: str,
    outcome: str,
    wrong_shape: str,
) -> None:
    value = _snapshot()
    malformed_by_shape = {
        "list": {"scalar": "wrong", "object": {}, "null": None},
        "map": {"scalar": "wrong", "object": [], "null": None},
    }
    malformed = malformed_by_shape[expected_shape][wrong_shape]
    if collection == "value-kinds":
        value["schema"]["definitions"][1]["payload"]["properties"]["name"][  # type: ignore[index]
            "value_kinds"
        ] = malformed
    elif collection in {"required-data-types", "optional-data-types"}:
        field = collection.replace("-", "_")
        value["schema"]["definitions"][0]["payload"][field] = malformed  # type: ignore[index]
    elif collection in {"allowed-source-types", "allowed-target-types"}:
        field = collection.replace("-", "_")
        value["schema"]["definitions"][2]["payload"][field] = malformed  # type: ignore[index]
    elif collection == "definition-properties":
        value["schema"]["definitions"][1]["payload"]["properties"] = malformed  # type: ignore[index]
    elif collection == "graph-properties":
        value["graph"]["data_objects"][0]["properties"] = malformed  # type: ignore[index]
    else:
        constraint = _data_count_constraint("collection", ["Person"], 0, 1)
        payload = constraint["payload"]
        assert isinstance(payload, dict)
        query = payload["query_spec"]
        assert isinstance(query, dict)
        if collection == "anchor-buckets":
            query["anchor_buckets"] = malformed
        elif collection == "data-requirements":
            query["data_requirements"] = malformed
        else:
            payload["group_by_bindings"] = malformed
        value["constraints"]["constraints"].append(constraint)  # type: ignore[index]
    report = tmp_path / f"collection-{collection}-{wrong_shape}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"collection-{collection}-{wrong_shape}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    dispositions = json.loads(report.read_text())["dispositions"]
    if outcome == "blocking":
        assert not preview.acceptable
        assert any(item["disposition"] == "blocking" for item in dispositions)
    else:
        assert preview.acceptable
        assert any(item["code"] == "relationship-rule-omitted" for item in dispositions)


def test_absent_refinements_stay_absent_and_compatible_numeric_bounds_map(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    data = snapshot["graph"]["data_objects"][0]  # type: ignore[index]
    data["properties"]["score"] = 3.25  # type: ignore[index]
    properties = snapshot["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    properties["score"] = {  # type: ignore[index]
        "required": True,
        "value_kinds": ["number"],
        "description": "Score.",
        "allowed_values": [1, 3.25],
        "minimum": 1,
        "maximum": 4,
    }
    report_path = tmp_path / "compatible-refinements.json"
    source = _write(tmp_path / "compatible-refinements-source.json", snapshot)
    preview = preview_v1_import(source, report_out=report_path, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    dispositions = json.loads(report_path.read_text())["dispositions"]
    assert not any(
        item["code"] == "property-constraints-omitted"
        and item.get("targetProperty") in {"name", "score"}
        for item in dispositions
    )
    destination = tmp_path / "compatible-refinements" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definition = next(
        item
        for item in read_state(destination).definitions
        if isinstance(item, AssociatedDataTypeDefinition)
    )
    score = next(item for item in definition.properties if item.name == "score")
    assert [value.value for value in score.allowed_values] == [1.0, 3.25]
    assert score.minimum is not None and score.minimum.value == 1.0
    assert score.maximum is not None and score.maximum.value == 4.0


def test_property_wide_inference_preserves_scalars_and_exact_converted_json(
    tmp_path: Path,
) -> None:
    value = _snapshot()
    data = value["graph"]["data_objects"][0]  # type: ignore[index]
    properties = data["properties"]
    properties.update(  # type: ignore[union-attr]
        {
            "integer": 9007199254740991,
            "number": 3.25,
            "unsafe": 9007199254740992,
            "mixed": "literal text",
            "array": ["first", None, {"large": 123456789012345678901234567890}],
            "calendarText": "2026-08-20",
        }
    )
    declared = value["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    declared.update(  # type: ignore[union-attr]
        {
            "integer": _property_rule("integer", "Safe integer."),
            "number": _property_rule("number", "Finite number."),
            "unsafe": _property_rule("integer", "Unsafe integer."),
            "mixed": {
                "required": True,
                "value_kinds": ["string", "number"],
                "description": "Mixed property.",
            },
            "array": _property_rule("list", "Nested array."),
            "calendarText": _property_rule("string", "Calendar-looking text."),
        }
    )
    source = _write(tmp_path / "v1.json", value)
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    destination = tmp_path / "owner" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    state = read_state(destination)
    definition = next(
        item for item in state.definitions if isinstance(item, AssociatedDataTypeDefinition)
    )
    rules = {item.name: item for item in definition.properties}
    assert rules["integer"].value_kind is ValueKind.INTEGER
    assert rules["number"].value_kind is ValueKind.NUMBER
    assert rules["calendarText"].value_kind is ValueKind.TEXT
    assert rules["unsafe"].value_kind is ValueKind.TEXT
    assert rules["mixed"].value_kind is ValueKind.TEXT
    assert rules["array"].value_kind is ValueKind.TEXT
    imported = next(item for item in state.graph if isinstance(item, AssociatedData))
    stored = dict(imported.properties)
    assert _nonnull(stored, "unsafe").value == "9007199254740992"
    assert _nonnull(stored, "mixed").value == '"literal text"'
    assert _nonnull(stored, "array").value == (
        '["first",null,{"large":123456789012345678901234567890}]'
    )
    assert _nonnull(stored, "calendarText").value == "2026-08-20"


def test_public_v1_empty_property_descriptions_are_reported_conversions(tmp_path: Path) -> None:
    value = _snapshot()
    properties = value["schema"]["definitions"][1]["payload"]["properties"]  # type: ignore[index]
    properties["active"]["description"] = ""  # type: ignore[index]
    properties["name"].pop("description")  # type: ignore[index]
    report = tmp_path / "empty-descriptions.json"

    preview = preview_v1_import(
        _write(tmp_path / "empty-descriptions-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )

    assert preview.acceptable
    destination = tmp_path / "owner" / "vellis.db"
    initialize_from_v1(
        tmp_path / "empty-descriptions-source.json",
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definition = next(
        item
        for item in read_state(destination).definitions
        if isinstance(item, AssociatedDataTypeDefinition)
    )
    descriptions = {item.name: item.description for item in definition.properties}
    assert descriptions["active"] == "Imported v1 property active."
    assert descriptions["name"] == "Imported v1 property name."
    converted = [
        item
        for item in json.loads(report.read_text())["dispositions"]
        if item["code"] == "property-description-filled"
    ]
    assert [item["targetProperty"] for item in converted] == ["active", "name"]


def test_exact_local_bounds_map_and_subset_overlap_is_omitted(tmp_path: Path) -> None:
    value = _snapshot()
    constraints = value["constraints"]["constraints"]  # type: ignore[index]
    constraints.extend(  # type: ignore[union-attr]
        [
            _data_count_constraint("profile-count", ["Person"], 0, 1),
            _anchor_count_constraint("profile-anchor-count", ["Person"], 1, 1),
            _link_count_constraint("knows-source-count", "source", 0, 2),
            _link_count_constraint("knows-target-count", "target", 0, 3),
        ]
    )
    source = _write(tmp_path / "exact.json", value)
    preview = preview_v1_import(source, recorded_at="2026-08-20T00:00:00Z")
    destination = tmp_path / "exact" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definitions = read_state(destination).definitions
    data = next(item for item in definitions if isinstance(item, AssociatedDataTypeDefinition))
    link = next(item for item in definitions if isinstance(item, LinkTypeDefinition))
    assert data.objects_per_anchor == Cardinality(0, 1)
    assert data.anchors_per_object == Cardinality(1, 1)
    assert link.links_per_source == Cardinality(0, 2)
    assert link.links_per_target == Cardinality(0, 3)

    overlap = _snapshot()
    overlap["schema"]["definitions"].append(  # type: ignore[index]
        {
            "uuid": "legacy-definition-group",
            "kind": "anchor",
            "type_key": "Group",
            "description": "A group.",
            "payload": {"optional_data_types": ["Profile"]},
            "system": {"live": True},
        }
    )
    overlap_constraints = overlap["constraints"]["constraints"]  # type: ignore[index]
    overlap_constraints.extend(  # type: ignore[union-attr]
        [
            _data_count_constraint("complete", ["Person", "Group"], 0, 1),
            _data_count_constraint("subset", ["Person"], 1, 1),
        ]
    )
    overlap_source = _write(tmp_path / "overlap.json", overlap)
    report = tmp_path / "overlap-report.json"
    overlap_preview = preview_v1_import(
        overlap_source, report_out=report, recorded_at="2026-08-20T00:00:00Z"
    )
    assert overlap_preview.acceptable
    overlap_destination = tmp_path / "overlap" / "vellis.db"
    initialize_from_v1(
        overlap_source,
        overlap_destination,
        confirmed_source_sha256=overlap_preview.source_sha256,
        confirmed_report_sha256=overlap_preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    overlap_data = next(
        item
        for item in read_state(overlap_destination).definitions
        if isinstance(item, AssociatedDataTypeDefinition)
    )
    assert overlap_data.objects_per_anchor == Cardinality(0)
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "overlapping-relationship-rule" in codes
    assert "relationship-rule-omitted" in codes


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("objectsPerAnchor", Cardinality(0, 1)),
        ("anchorsPerObject", Cardinality(1, 1)),
        ("linksPerSource", Cardinality(0, 2)),
        ("linksPerTarget", Cardinality(0, 2)),
    ],
)
def test_local_bounds_use_final_inferred_permitted_population(
    tmp_path: Path, role: str, expected: Cardinality
) -> None:
    value = _inferred_population_snapshot(role, exact=True)
    source = _write(tmp_path / f"inferred-{role}.json", value)
    report = tmp_path / f"inferred-{role}-report.json"
    preview = preview_v1_import(source, report_out=report, recorded_at="2026-08-20T00:00:00Z")
    assert preview.acceptable
    assert any(
        item["code"] == "local-bound-mapped"
        for item in json.loads(report.read_text())["dispositions"]
    )
    destination = tmp_path / f"inferred-{role}" / "vellis.db"
    initialize_from_v1(
        source,
        destination,
        confirmed_source_sha256=preview.source_sha256,
        confirmed_report_sha256=preview.report_sha256,
        recorded_at="2026-08-20T00:00:00Z",
    )
    definitions = read_state(destination).definitions
    definition = next(
        item
        for item in definitions
        if item.type_key == ("Profile" if role.startswith(("anchors", "objects")) else "knows")
    )
    attribute = {
        "objectsPerAnchor": "objects_per_anchor",
        "anchorsPerObject": "anchors_per_object",
        "linksPerSource": "links_per_source",
        "linksPerTarget": "links_per_target",
    }[role]
    assert getattr(definition, attribute) == expected


@pytest.mark.parametrize(
    "role", ["objectsPerAnchor", "anchorsPerObject", "linksPerSource", "linksPerTarget"]
)
def test_inferred_population_subset_never_maps_as_a_local_bound(tmp_path: Path, role: str) -> None:
    value = _inferred_population_snapshot(role, exact=False)
    report = tmp_path / f"subset-{role}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"subset-{role}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "relationship-rule-omitted" in codes
    assert "local-bound-mapped" not in codes


@pytest.mark.parametrize(
    "role", ["objectsPerAnchor", "anchorsPerObject", "linksPerSource", "linksPerTarget"]
)
@pytest.mark.parametrize("conflict", ["filtered", "grouped", "extra-requirement", "subset"])
def test_any_targeted_nonreducible_rule_suppresses_exact_mapping_for_the_role(
    tmp_path: Path, role: str, conflict: str
) -> None:
    value = _inferred_population_snapshot(role, exact=True)
    constraints = value["constraints"]["constraints"]  # type: ignore[index]
    incompatible = deepcopy(constraints[0])  # type: ignore[index]
    incompatible["uuid"] = f"conflict-{role}-{conflict}"
    payload = incompatible["payload"]
    assert isinstance(payload, dict)
    query = payload["query_spec"]
    assert isinstance(query, dict)
    requirements_name = (
        "data_requirements" if role.startswith(("anchors", "objects")) else "link_requirements"
    )
    requirements = query[requirements_name]
    assert isinstance(requirements, list)
    requirement = requirements[0]
    assert isinstance(requirement, dict)
    if conflict == "filtered":
        requirement["uuid_filter"] = [DATA_UUID]
    elif conflict == "grouped":
        payload["group_by_bindings"].append("extra")  # type: ignore[union-attr]
    elif conflict == "extra-requirement":
        extra = dict(requirement)
        extra["name"] = "extra"
        requirements.append(extra)
    else:
        buckets = query["anchor_buckets"]
        assert isinstance(buckets, list)
        relevant = 1 if role == "linksPerTarget" else 0
        bucket = buckets[relevant]
        assert isinstance(bucket, dict)
        keys = bucket["anchor_type_keys"]
        assert isinstance(keys, list)
        bucket["anchor_type_keys"] = keys[:1]
    constraints.append(incompatible)  # type: ignore[union-attr]
    report = tmp_path / f"overlap-{role}-{conflict}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"overlap-{role}-{conflict}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    entries = json.loads(report.read_text())["dispositions"]
    assert not any(item["code"] == "local-bound-mapped" for item in entries)
    assert any(item["code"] == "overlapping-relationship-rule" for item in entries)
    assert any(item["code"] == "relationship-rule-omitted" for item in entries)


@pytest.mark.parametrize("role", ["linksPerSource", "linksPerTarget"])
@pytest.mark.parametrize(
    ("members", "suppresses_exact"),
    [
        (["knows", "other"], True),
        (["knows", 7], True),
        (["knows", "knows"], True),
        (["other", 7], False),
        ([], False),
        ("knows", False),
    ],
)
def test_link_overlap_extracts_every_recognizable_type_from_nonexact_members(
    tmp_path: Path, role: str, members: object, suppresses_exact: bool
) -> None:
    value = _inferred_population_snapshot(role, exact=True)
    constraints = value["constraints"]["constraints"]  # type: ignore[index]
    incompatible = deepcopy(constraints[0])  # type: ignore[index]
    incompatible["uuid"] = f"multi-{role}"
    requirement = incompatible["payload"]["query_spec"]["link_requirements"][0]  # type: ignore[index]
    requirement["link_type_keys"] = members  # type: ignore[index]
    constraints.append(incompatible)  # type: ignore[union-attr]
    report = tmp_path / f"multi-{role}-{str(members)}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"multi-{role}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    entries = json.loads(report.read_text())["dispositions"]
    assert any(item["code"] == "relationship-rule-omitted" for item in entries)
    assert any(item["code"] == "local-bound-mapped" for item in entries) is not suppresses_exact
    assert any(item["code"] == "overlapping-relationship-rule" for item in entries) is (
        suppresses_exact
    )


@pytest.mark.parametrize(
    "role", ["objectsPerAnchor", "anchorsPerObject", "linksPerSource", "linksPerTarget"]
)
def test_selector_name_collision_is_nonexact_but_suppresses_its_complete_role(
    tmp_path: Path, role: str
) -> None:
    value = _inferred_population_snapshot(role, exact=True)
    constraints = value["constraints"]["constraints"]  # type: ignore[index]
    incompatible = deepcopy(constraints[0])  # type: ignore[index]
    incompatible["uuid"] = f"collision-{role}"
    payload = incompatible["payload"]
    query = payload["query_spec"]  # type: ignore[index]
    requirements_name = (
        "data_requirements" if role.startswith(("anchors", "objects")) else "link_requirements"
    )
    requirement = query[requirements_name][0]  # type: ignore[index]
    bucket_field = {
        "objectsPerAnchor": "anchor_bucket",
        "anchorsPerObject": "anchor_bucket",
        "linksPerSource": "source_bucket",
        "linksPerTarget": "target_bucket",
    }[role]
    colliding_name = requirement[bucket_field]  # type: ignore[index]
    requirement["name"] = colliding_name  # type: ignore[index]
    payload["counted_binding"] = colliding_name  # type: ignore[index]
    payload["group_by_bindings"] = [colliding_name]  # type: ignore[index]
    constraints.append(incompatible)  # type: ignore[union-attr]
    report = tmp_path / f"collision-{role}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"collision-{role}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "relationship-rule-omitted" in codes
    assert "overlapping-relationship-rule" in codes
    assert "local-bound-mapped" not in codes


def test_cross_kind_selector_name_collision_suppresses_the_recognizable_data_role(
    tmp_path: Path,
) -> None:
    value = _inferred_population_snapshot("objectsPerAnchor", exact=True)
    constraints = value["constraints"]["constraints"]  # type: ignore[index]
    incompatible = deepcopy(constraints[0])  # type: ignore[index]
    incompatible["uuid"] = "cross-kind-collision"
    payload = incompatible["payload"]
    query = payload["query_spec"]  # type: ignore[index]
    query["anchor_buckets"].append(  # type: ignore[index]
        {"name": "target", "anchor_type_keys": ["Profile"]}
    )
    query["link_requirements"] = [  # type: ignore[index]
        {
            "name": "profile",
            "source_bucket": "anchor",
            "target_bucket": "target",
            "link_type_keys": ["knows"],
            "required": False,
        }
    ]
    constraints.append(incompatible)  # type: ignore[union-attr]
    report = tmp_path / "cross-kind-collision.json"
    preview = preview_v1_import(
        _write(tmp_path / "cross-kind-collision-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert {"relationship-rule-omitted", "overlapping-relationship-rule"} <= codes
    assert "local-bound-mapped" not in codes


@pytest.mark.parametrize(
    "role", ["objectsPerAnchor", "anchorsPerObject", "linksPerSource", "linksPerTarget"]
)
@pytest.mark.parametrize("broken_pair", ["counted", "grouped"])
def test_unrelated_broken_count_group_pair_does_not_suppress_safe_exact_mapping(
    tmp_path: Path, role: str, broken_pair: str
) -> None:
    value = _inferred_population_snapshot(role, exact=True)
    constraints = value["constraints"]["constraints"]  # type: ignore[index]
    incompatible = deepcopy(constraints[0])  # type: ignore[index]
    incompatible["uuid"] = f"broken-{role}-{broken_pair}"
    payload = incompatible["payload"]
    if broken_pair == "counted":
        payload["counted_binding"] = "unrelated"
    else:
        payload["group_by_bindings"] = ["unrelated"]
    constraints.append(incompatible)  # type: ignore[union-attr]
    report = tmp_path / f"broken-{role}-{broken_pair}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"broken-{role}-{broken_pair}-source.json", value),
        report_out=report,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    codes = {item["code"] for item in json.loads(report.read_text())["dispositions"]}
    assert "relationship-rule-omitted" in codes
    assert "local-bound-mapped" in codes
    assert "overlapping-relationship-rule" not in codes


@pytest.mark.parametrize(
    "case",
    [
        "payload-extra",
        "return-projections",
        "return-aggregation",
        "query-limit",
        "bucket-uuid-filter",
        "bucket-predicate",
        "data-predicates",
        "data-uuid-filter",
        "data-required-join",
        "data-selected-shape",
        "additional-requirement",
        "link-uuid-filter",
        "link-required-join",
    ],
)
def test_every_population_or_result_narrowing_field_prevents_bound_mapping(
    tmp_path: Path, case: str
) -> None:
    value = _snapshot()
    link_case = case.startswith("link-")
    constraint = (
        _link_count_constraint("candidate", "source", 0, 2)
        if link_case
        else _data_count_constraint("candidate", ["Person"], 0, 1)
    )
    payload = constraint["payload"]
    assert isinstance(payload, dict)
    query = payload["query_spec"]
    assert isinstance(query, dict)
    anchors = query["anchor_buckets"]
    assert isinstance(anchors, list)
    requirements = query["link_requirements" if link_case else "data_requirements"]
    assert isinstance(requirements, list)
    requirement = requirements[0]
    assert isinstance(requirement, dict)
    if case == "payload-extra":
        payload["where"] = {"fictional": True}
    elif case == "return-projections":
        query["return_spec"] = {"projections": [{"name": "selected"}]}
    elif case == "return-aggregation":
        query["return_spec"] = {"aggregations": [{"operator": "count"}]}
    elif case == "query-limit":
        query["maximum_results"] = 10
    elif case == "bucket-uuid-filter":
        anchors[0]["uuid_filter"] = [ANCHOR_UUID]  # type: ignore[index]
    elif case == "bucket-predicate":
        anchors[0]["predicates"] = [{"field": "displayName"}]  # type: ignore[index]
    elif case.endswith("uuid-filter"):
        requirement["uuid_filter"] = [DATA_UUID]
    elif case.endswith("required-join"):
        requirement["required"] = True
    elif case == "data-predicates":
        requirement["predicates"] = [{"property": "name", "equal": "Ada"}]
    elif case == "data-selected-shape":
        requirement["selected_properties"] = ["name"]
    else:
        requirements.append(dict(requirement))
    value["constraints"]["constraints"].append(constraint)  # type: ignore[index]
    report_path = tmp_path / f"narrow-{case}.json"
    preview = preview_v1_import(
        _write(tmp_path / f"narrow-{case}-source.json", value),
        report_out=report_path,
        recorded_at="2026-08-20T00:00:00Z",
    )
    assert preview.acceptable
    codes = {item["code"] for item in json.loads(report_path.read_text())["dispositions"]}
    assert "relationship-rule-omitted" in codes
    assert "local-bound-mapped" not in codes


def _property_rule(kind: str, description: str) -> dict[str, object]:
    return {"required": True, "value_kinds": [kind], "description": description}


def _nonnull(values: dict[str, ScalarValue | None], name: str) -> ScalarValue:
    value = values[name]
    assert value is not None
    return value


def _data_count_constraint(
    uuid: str, anchor_types: list[str], minimum: int, maximum: int
) -> dict[str, object]:
    return {
        "uuid": uuid,
        "kind": "cardinality",
        "payload": {
            "query_spec": {
                "anchor_buckets": [{"name": "anchor", "anchor_type_keys": anchor_types}],
                "data_requirements": [
                    {
                        "name": "profile",
                        "anchor_bucket": "anchor",
                        "data_type_key": "Profile",
                        "required": False,
                    }
                ],
            },
            "counted_binding": "profile",
            "group_by_bindings": ["anchor"],
            "minimum": minimum,
            "maximum": maximum,
        },
        "system": {"live": True},
    }


def _link_count_constraint(uuid: str, group: str, minimum: int, maximum: int) -> dict[str, object]:
    return {
        "uuid": uuid,
        "kind": "cardinality",
        "payload": {
            "query_spec": {
                "anchor_buckets": [
                    {"name": "source", "anchor_type_keys": ["Person"]},
                    {"name": "target", "anchor_type_keys": ["Profile"]},
                ],
                "link_requirements": [
                    {
                        "name": "relationship",
                        "source_bucket": "source",
                        "target_bucket": "target",
                        "link_type_keys": ["knows"],
                        "required": False,
                    }
                ],
            },
            "counted_binding": "relationship",
            "group_by_bindings": [group],
            "minimum": minimum,
            "maximum": maximum,
        },
        "system": {"live": True},
    }


def _inferred_population_snapshot(role: str, *, exact: bool) -> dict[str, object]:
    value = _snapshot()
    group_uuid = "72345678-1234-4234-8234-123456789abc"
    value["schema"]["definitions"].append(  # type: ignore[index]
        {
            "uuid": "legacy-definition-group",
            "kind": "anchor",
            "type_key": "Group",
            "description": "A group.",
            "payload": {},
            "system": {"live": True},
        }
    )
    value["graph"]["anchors"].append(  # type: ignore[index]
        {
            "uuid": group_uuid,
            "type": "Group",
            "display_name": "Group",
            "system": {"live": True},
        }
    )
    base_type = "Profile" if role == "linksPerTarget" else "Person"
    population = [base_type, "Group"] if exact else [base_type]
    if role.startswith(("anchors", "objects")):
        value["graph"]["anchor_data_index"] = {group_uuid: [DATA_UUID]}  # type: ignore[index]
        constraint = (
            _anchor_count_constraint("inferred", population, 1, 1)
            if role == "anchorsPerObject"
            else _data_count_constraint("inferred", population, 0, 1)
        )
    else:
        group = "source" if role == "linksPerSource" else "target"
        value["graph"]["links"][0][f"{group}_uuid"] = group_uuid  # type: ignore[index]
        constraint = _link_count_constraint("inferred", group, 0, 2)
        query = constraint["payload"]["query_spec"]  # type: ignore[index]
        bucket = 0 if group == "source" else 1
        query["anchor_buckets"][bucket]["anchor_type_keys"] = population  # type: ignore[index]
    value["constraints"]["constraints"].append(constraint)  # type: ignore[index]
    return value


def _anchor_count_constraint(
    uuid: str, anchor_types: list[str], minimum: int, maximum: int
) -> dict[str, object]:
    value = _data_count_constraint(uuid, anchor_types, minimum, maximum)
    payload = value["payload"]
    assert isinstance(payload, dict)
    payload["counted_binding"] = "anchor"
    payload["group_by_bindings"] = ["profile"]
    return value
