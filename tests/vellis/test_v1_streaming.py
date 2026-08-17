"""High-value evidence for incremental v1 trust-boundary import."""

from __future__ import annotations

import io
import json
import tracemalloc
from decimal import Decimal
from pathlib import Path

import pytest

from tests.vellis.oracle import materialize_state
from vellis.definitions import (
    DirectAssociationMultiplicityConstraint,
    LinkEnd,
    LinkMultiplicityConstraint,
)
from vellis.json_value import JsonKind, normalize
from vellis.setup import EXIT_FAILED, EXIT_SUCCESS, main
from vellis.store import CanonicalStore
from vellis.v1 import RecoveryDisposition, SnapshotError
from vellis.v1_streaming import preview_v1_stream

REPRESENTATIVE_V1_EXPORT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "v1" / "v1.0-representative-export.json"
)


def _snapshot() -> dict[str, object]:
    return {
        "graph": {
            "anchors": [
                {"uuid": "a1", "type": "Person", "display_name": "Ada", "system": {}},
                {"uuid": "a2", "type": "Place", "display_name": "Home", "system": {}},
            ],
            "data_objects": [
                {
                    "uuid": "d1",
                    "type": "PersonFacts",
                    "properties": {"name": "Ada"},
                    "system": {"origin": "import"},
                }
            ],
            "links": [
                {
                    "uuid": "l1",
                    "type": "lives_in",
                    "source_uuid": "a1",
                    "target_uuid": "a2",
                    "system": {},
                }
            ],
            "anchor_data_index": {"a1": ["d1"]},
        },
        "schema": {
            "definitions": [
                {
                    "uuid": "s1",
                    "kind": "anchor",
                    "type_key": "Person",
                    "description": "A person.",
                    "payload": {"required_data_types": ["PersonFacts"]},
                    "system": {},
                },
                {
                    "uuid": "s2",
                    "kind": "anchor",
                    "type_key": "Place",
                    "description": "A place.",
                    "payload": {},
                    "system": {},
                },
                {
                    "uuid": "s3",
                    "kind": "data_object",
                    "type_key": "PersonFacts",
                    "description": "Facts about a person.",
                    "payload": {
                        "properties": {"name": {"required": True, "value_kinds": ["string"]}}
                    },
                    "system": {},
                },
                {
                    "uuid": "s4",
                    "kind": "link",
                    "type_key": "lives_in",
                    "description": "Someone lives somewhere.",
                    "payload": {
                        "allowed_source_types": ["Person"],
                        "allowed_target_types": ["Place"],
                    },
                    "system": {},
                },
            ]
        },
        "constraints": {"constraints": []},
        "migration": {"migrations": []},
    }


def _write(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _run(arguments: list[str]) -> tuple[int, str, str]:
    out, error = io.StringIO(), io.StringIO()
    result = main(arguments, stdout=out, stderr=error, stdin=io.StringIO("y\n"))
    return result, out.getvalue(), error.getvalue()


def test_preview_reports_complete_counts_without_a_candidate_graph(tmp_path: Path) -> None:
    preview = preview_v1_stream(_write(tmp_path, _snapshot()))

    assert preview.is_acceptable
    assert (preview.anchor_count, preview.data_count, preview.link_count) == (2, 1, 1)
    assert not hasattr(preview, "candidate")


def test_setup_imports_v1_through_normalized_temporary_sqlite(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    code, _out, error = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, _snapshot())), "--yes"]
    )

    assert code == EXIT_SUCCESS, error
    store = CanonicalStore(destination / "vellis.sqlite3")
    try:
        state = materialize_state(store)
        assert {value.uuid for value in state.graph.objects()} == {"a1", "a2", "d1", "l1"}
        assert store.canonical_record_count() == 1
        assert store.verify_projection_from_ledger() == ()
    finally:
        store.close()


def test_representative_v1_export_reports_every_unrepresentable_refinement() -> None:
    """The frozen v1.0 codec-shaped fixture spans every supported definition/count form."""
    preview = preview_v1_stream(REPRESENTATIVE_V1_EXPORT)

    assert preview.is_acceptable
    assert (
        preview.anchor_count,
        preview.data_count,
        preview.link_count,
        preview.anchor_type_count,
        preview.data_type_count,
        preview.link_type_count,
    ) == (2, 2, 1, 2, 2, 1)
    dispositions = {finding.disposition for finding in preview.findings}
    assert dispositions == {
        RecoveryDisposition.PRESERVED,
        RecoveryDisposition.SIMPLIFIED,
        RecoveryDisposition.OMITTED,
    }
    report = "\n".join(finding.summary for finding in preview.findings)
    for expected in (
        "non-live anchor retired-1 is not imported",
        "non-live associated-data object retired-data-1 is not imported",
        "non-live link retired-link-1 is not imported",
        "Profile.flexible allowed 2 value kinds",
        "Profile.identifier was a v1 uuid",
        "Profile.unused allowed several value kinds",
        "Profile.weird had a v1 format rule",
        "Profile.whole was a v1 integer",
        "query-pattern constraint query-only rule",
        "future_constraint",
        "1 v1 migration records",
        "v1 link type lives_in named types no live v1 definition describes",
    ):
        assert expected in report


def test_representative_v1_export_preserves_graph_and_starts_one_new_lineage(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "vellis-2"
    code, _out, error = _run(
        ["--data-dir", str(destination), "--from-v1", str(REPRESENTATIVE_V1_EXPORT), "--yes"]
    )

    assert code == EXIT_SUCCESS, error
    store = CanonicalStore(destination / "vellis.sqlite3")
    try:
        state = materialize_state(store)
        assert state.revision == 0
        assert store.canonical_record_count() == 1
        assert store.verify_projection_from_ledger() == ()
        assert {value.uuid for value in state.graph.objects()} == {
            "person-1",
            "place-1",
            "profile-1",
            "note-1",
            "link-1",
        }

        person = state.graph.anchor("person-1")
        profile = state.graph.associated_data_object("profile-1")
        note = state.graph.associated_data_object("note-1")
        link = state.graph.link("link-1")
        assert person is not None and profile is not None and note is not None and link is not None
        assert person.display_name == "Ada"
        assert person.system_metadata.members == normalize(
            {"live": True, "origin": {"source": "v1.0", "ordinal": 1}}
        )
        assert profile.anchor_uuids == ("person-1",)
        assert note.anchor_uuids == ("place-1",)
        assert profile.properties == normalize(
            {
                "name": "Ada",
                "score": Decimal("3.00"),
                "active": True,
                "marker": None,
                "nested": {"numbers": [3, Decimal("3.00")], "flags": [True, None]},
                "sequence": ["first", {"n": Decimal("3.00")}],
                "whole": 3,
                "identifier": "123e4567-e89b-12d3-a456-426614174000",
                "flexible": "stored as text",
                "weird": "kept",
            }
        )
        assert (link.source_uuid, link.target_uuid) == ("person-1", "place-1")

        definitions = state.active_definitions
        assert {value.type_key for value in definitions.anchor_types} == {"Person", "Place"}
        assert {value.type_key for value in definitions.associated_data_types} == {
            "Profile",
            "Note",
        }
        profile_type = definitions.associated_data_type("Profile")
        link_type = definitions.link_type("lives_in")
        assert profile_type is not None and link_type is not None
        rules = {rule.property_name: rule for rule in profile_type.property_constraints}
        assert rules.keys() == {
            "active",
            "flexible",
            "identifier",
            "marker",
            "name",
            "nested",
            "score",
            "sequence",
            "weird",
            "whole",
        }
        assert rules["nested"].json_kind is JsonKind.OBJECT
        assert rules["sequence"].json_kind is JsonKind.ARRAY
        assert rules["whole"].json_kind is JsonKind.NUMBER
        assert rules["identifier"].json_kind is JsonKind.STRING
        assert rules["score"].value_range is not None
        assert rules["score"].value_range.permitted_values == (
            Decimal("3"),
            Decimal("4"),
        )
        assert link_type.endpoint_constraint.permitted_source_type_keys == ("Person",)
        assert link_type.endpoint_constraint.permitted_target_type_keys == ("Place",)

        association_counts = [
            value
            for value in definitions.relationship_constraints
            if isinstance(value, DirectAssociationMultiplicityConstraint)
        ]
        link_counts = [
            value
            for value in definitions.relationship_constraints
            if isinstance(value, LinkMultiplicityConstraint)
        ]
        assert [(value.lower_bound, value.upper_bound) for value in association_counts] == [(1, 1)]
        assert {
            value.constrained_end: (value.lower_bound, value.upper_bound) for value in link_counts
        } == {LinkEnd.SOURCE: (1, 1), LinkEnd.TARGET: (0, 2)}
    finally:
        store.close()


def test_missing_v1_section_is_refused_before_destination_creation(tmp_path: Path) -> None:
    value = _snapshot()
    del value["schema"]
    destination = tmp_path / "vellis"

    code, _out, error = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, value)), "--yes"]
    )

    assert code == EXIT_FAILED
    assert "cannot be read" in error
    assert not destination.exists()


def test_wrong_shaped_v1_sections_are_not_accepted_as_an_empty_snapshot(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"graph": [], "schema": [], "constraints": [], "migration": []},
    )

    with pytest.raises(SnapshotError, match="invalid shapes"):
        preview_v1_stream(path)


def test_an_explicit_rule_overlapping_a_required_data_rule_is_merged(tmp_path: Path) -> None:
    value = _snapshot()
    constraints = value["constraints"]
    assert isinstance(constraints, dict)
    constraints["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "one set of facts per person",
            "description": "A person carries exactly one set of facts.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 1,
            },
            "system": {},
        }
    ]

    preview = preview_v1_stream(_write(tmp_path, value))

    assert preview.is_acceptable


def test_invalid_graph_is_reported_and_never_published(tmp_path: Path) -> None:
    value = _snapshot()
    graph = value["graph"]
    assert isinstance(graph, dict)
    graph["links"][0]["target_uuid"] = "missing"  # type: ignore[index]
    destination = tmp_path / "vellis"

    code, _out, _error = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, value)), "--yes"]
    )

    assert code == EXIT_FAILED
    assert not destination.exists()


def test_non_json_v1_input_is_a_typed_snapshot_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(SnapshotError):
        preview_v1_stream(path)


def test_skewed_hundred_thousand_associations_are_staged_with_bounded_memory(
    tmp_path: Path,
) -> None:
    """One high-fanout data value is normalized from SQL rows, never a resident array."""
    population = 100_000
    path = tmp_path / "high-fanout-v1.json"
    with path.open("w", encoding="utf-8") as output:
        output.write('{"graph":{"anchors":[')
        for ordinal in range(population):
            if ordinal:
                output.write(",")
            json.dump(
                {
                    "uuid": f"a{ordinal}",
                    "type": "Person",
                    "display_name": f"Person {ordinal}",
                    "system": {},
                },
                output,
            )
        output.write(
            '],"data_objects":[{"uuid":"d1","type":"PersonFacts",'
            '"properties":{"name":"Shared"},"system":{}}],"links":[],'
            '"anchor_data_index":{'
        )
        for ordinal in range(population):
            if ordinal:
                output.write(",")
            output.write(f'"a{ordinal}":["d1"]')
        output.write(
            '}},"schema":{"definitions":['
            '{"uuid":"s1","kind":"anchor","type_key":"Person",'
            '"description":"A person.","payload":{"required_data_types":["PersonFacts"]},'
            '"system":{}},'
            '{"uuid":"s2","kind":"data_object","type_key":"PersonFacts",'
            '"description":"Facts.","payload":{"properties":{"name":'
            '{"required":true,"value_kinds":["string"]}}},"system":{}}]},'
            '"constraints":{"constraints":[]},"migration":{"migrations":[]}}'
        )

    tracemalloc.start()
    preview = preview_v1_stream(path)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert preview.is_acceptable
    assert (preview.anchor_count, preview.data_count) == (population, 1)
    assert peak < 20 * 1024 * 1024
