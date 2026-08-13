"""High-value evidence for incremental v1 trust-boundary import."""

from __future__ import annotations

import io
import json
import tracemalloc
from pathlib import Path

import pytest

from tests.vellis.oracle import materialize_state
from vellis.setup import EXIT_FAILED, EXIT_SUCCESS, main
from vellis.store import CanonicalStore
from vellis.v1 import SnapshotError
from vellis.v1_streaming import preview_v1_stream


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
