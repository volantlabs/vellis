from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset

ROOT = Path(__file__).resolve().parent
SCHEMA_CALL_PATH = ROOT / "data" / "experience-studio-schema-v0.json"
LIVE_RECORDS_PATH = ROOT / "data" / "ocean-signal-atlas-planning-records.json"
QUERY_DIR = ROOT / "data" / "queries"
DEFAULT_STORAGE_ROOT = Path(".data") / "monographs" / "experience-studio"
DEFAULT_SQL_DATABASE_PATH = DEFAULT_STORAGE_ROOT / "controller.sqlite"
DEFAULT_SNAPSHOT_PATH = "snapshots/experience-studio-alpha.json"
EXPECTED_QUERY_ROWS = {
    "experience-portfolio-query": 1,
    "publication-check-query": 6,
    "source-readiness-query": 1,
}


def load_monograph(
    *,
    storage_root: Path = DEFAULT_STORAGE_ROOT,
    sql_database_path: Path = DEFAULT_SQL_DATABASE_PATH,
    snapshot_path: str = DEFAULT_SNAPSHOT_PATH,
    reset: bool = False,
) -> dict[str, Any]:
    storage_root = storage_root.resolve()
    sql_database_path = sql_database_path.resolve()
    if reset:
        _reset_graph_root(storage_root, sql_database_path)

    composition = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=storage_root,
            sql_database_path=sql_database_path,
        )
    )
    app_status = composition.runner.run()
    toolset = RtgMcpToolset(composition.controller)
    initial_validation = _require_ok(toolset.rtg_validate_graph(), "initial graph validation")
    initial_state = _require_ok(toolset.rtg_get_system_state(), "initial system state")
    if initial_state["state_classification"] != "empty":
        raise RuntimeError(
            "experience_studio graph root is not empty; rerun with --reset only when a clean "
            "reload is intended"
        )

    schema_call = _load_call(SCHEMA_CALL_PATH, "rtg_stage_schema_migration")
    live_call = _load_call(LIVE_RECORDS_PATH, "rtg_apply_live_anchor_records")
    query_calls = {
        path.stem: _load_call(path, "rtg_execute_query")
        for path in sorted(QUERY_DIR.glob("*.json"))
    }

    stage = _require_ok(
        toolset.rtg_stage_schema_migration(**schema_call["arguments"]),
        "schema staging",
    )
    cutover = _require_ok(
        toolset.rtg_apply_migration_cutover(schema_call["arguments"]["migration_id"]),
        "schema cutover",
    )
    seed = _require_ok(
        toolset.rtg_apply_live_anchor_records(
            **live_call["arguments"],
            response_options={"format": "full"},
        ),
        "Ocean Signal Atlas planning seed",
    )
    validation = _require_ok(toolset.rtg_validate_graph(), "populated graph validation")
    system_state = _require_ok(toolset.rtg_get_system_state(), "populated system state")
    query_results = {
        query_name: _require_ok(
            toolset.rtg_execute_query(**query_call["arguments"]),
            f"{query_name} query",
        )
        for query_name, query_call in query_calls.items()
    }
    snapshot = _require_ok(
        toolset.rtg_persist_system_snapshot(snapshot_path, return_snapshot=False),
        "snapshot persistence",
    )
    replay = _require_ok(
        toolset.rtg_verify_replay_from_ledger(),
        "ledger replay verification",
    )

    payload = {
        "status": "loaded",
        "graph_id": "experience_studio",
        "storage_root": str(storage_root),
        "sql_database_path": str(sql_database_path),
        "snapshot_path": snapshot_path,
        "app": app_status.to_json_value(),
        "initial_validation": {
            "accepted": initial_validation["accepted"],
            "finding_count": initial_validation["evidence"]["finding_count"],
        },
        "schema_migration_id": schema_call["arguments"]["migration_id"],
        "generated_schema_definition_count": len(stage["generated_schema_ids"]),
        "cutover_status": cutover["status"],
        "seed_anchor_record_count": len(live_call["arguments"]["anchor_records"]),
        "submitted_link_count": len(seed["submitted_graph_changes"]["link_writes"]),
        "state_classification": system_state["state_classification"],
        "live_object_counts": system_state["live_object_counts"],
        "validation": {
            "accepted": validation["accepted"],
            "finding_count": validation["evidence"]["finding_count"],
        },
        "query_row_counts": {
            query_name: result["row_count"] for query_name, result in sorted(query_results.items())
        },
        "snapshot": snapshot,
        "replay": replay,
        "source_payloads": {
            "schema": _repo_relative(SCHEMA_CALL_PATH),
            "live_records": _repo_relative(LIVE_RECORDS_PATH),
            "queries": [_repo_relative(path) for path in sorted(QUERY_DIR.glob("*.json"))],
        },
    }
    _assert_loader_gates(payload)
    return payload


def _load_call(path: Path, expected_tool: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("tool") != expected_tool or not isinstance(payload.get("arguments"), dict):
        raise RuntimeError(f"invalid {expected_tool} fixture: {_repo_relative(path)}")
    return payload


def _require_ok(response: dict[str, Any], label: str) -> dict[str, Any]:
    result = response.get("result")
    if response.get("ok") is not True or not isinstance(result, dict):
        raise RuntimeError(f"{label} failed: {json.dumps(response, sort_keys=True)}")
    return result


def _assert_loader_gates(payload: dict[str, Any]) -> None:
    counts = _counts_by_kind(payload["live_object_counts"])
    anchor_total = sum(counts["anchor"].values())
    data_total = sum(counts["data_object"].values())
    gates = {
        "fresh_graph_validated": payload["initial_validation"]
        == {"accepted": True, "finding_count": 0},
        "state_populated": payload["state_classification"] == "populated",
        "graph_validates": payload["validation"] == {"accepted": True, "finding_count": 0},
        "schema_shape_matches": payload["generated_schema_definition_count"] == 42,
        "all_seed_records_ingested": anchor_total == 27 and data_total == 27,
        "all_seed_links_ingested": payload["submitted_link_count"] == 39,
        "query_counts_match": payload["query_row_counts"] == EXPECTED_QUERY_ROWS,
        "snapshot_persisted": payload["snapshot"]["relative_path"] == payload["snapshot_path"],
        "replay_verified": payload["replay"]["status"] == "replay_verified",
    }
    failed = [name for name, passed in gates.items() if not passed]
    if failed:
        raise RuntimeError(f"Experience Studio loader gates failed: {', '.join(failed)}")
    payload["gates"] = gates


def _counts_by_kind(payload: dict[str, Any]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {"anchor": {}, "data_object": {}, "link": {}}
    for item in payload["counts"]:
        result[item["kind"]][item["type"]] = item["count"]
    return result


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def _reset_graph_root(storage_root: Path, sql_database_path: Path) -> None:
    if storage_root.exists():
        shutil.rmtree(storage_root)
    if sql_database_path.exists() and not _is_relative_to(sql_database_path, storage_root):
        sql_database_path.unlink()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the Experience Studio RTG monograph.")
    parser.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE_ROOT)
    parser.add_argument("--sql-database-path", type=Path, default=DEFAULT_SQL_DATABASE_PATH)
    parser.add_argument("--snapshot-path", default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--reset", action="store_true", help="Delete the target root first.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    payload = load_monograph(
        storage_root=args.storage_root,
        sql_database_path=args.sql_database_path,
        snapshot_path=args.snapshot_path,
        reset=args.reset,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"status={payload['status']}")
    print(f"storage_root={payload['storage_root']}")
    print(f"snapshot_path={payload['snapshot_path']}")
    print(f"query_row_counts={json.dumps(payload['query_row_counts'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
