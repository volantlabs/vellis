from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from load_monograph import (
    DEFAULT_SQL_DATABASE_PATH,
    DEFAULT_STORAGE_ROOT,
    SNAPSHOT_PATH,
)

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from components.rtg.controller import RtgControllerRestoreOptions

GRAPH_ID = "time_room_history"


def _facts_by_anchor(snapshot: Any) -> dict[str, dict[str, Any]]:
    data_by_id = {str(item["uuid"]): item for item in snapshot.graph.data_objects}
    result: dict[str, dict[str, Any]] = {}
    for anchor_id, data_ids in snapshot.graph.anchor_data_index.items():
        if len(data_ids) != 1:
            raise RuntimeError(f"expected one facts record for anchor {anchor_id}")
        result[str(anchor_id)] = data_by_id[str(data_ids[0])]
    return result


def compile_runtime_pack(
    *,
    storage_root: Path = DEFAULT_STORAGE_ROOT,
    sql_database_path: Path = DEFAULT_SQL_DATABASE_PATH,
    snapshot_path: str = SNAPSHOT_PATH,
) -> dict[str, Any]:
    composition = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=storage_root.resolve(),
            sql_database_path=sql_database_path.resolve(),
        )
    )
    composition.runner.run()
    loaded = composition.controller.load_persisted_snapshot(snapshot_path)
    composition.controller.restore_from_snapshot(
        loaded.snapshot,
        RtgControllerRestoreOptions(ledger_mode="skip"),
    )
    validation = composition.controller.validate_graph()
    if not validation.accepted:
        raise RuntimeError("time_room_history snapshot does not validate")

    snapshot = loaded.snapshot
    anchors = {str(item["uuid"]): item for item in snapshot.graph.anchors}
    facts = _facts_by_anchor(snapshot)
    links = tuple(snapshot.graph.links)

    ids_by_type_and_key: dict[tuple[str, str], str] = {}
    for anchor_id, anchor in anchors.items():
        properties = facts[anchor_id]["properties"]
        stable_key = properties.get("stable_key")
        if isinstance(stable_key, str):
            ids_by_type_and_key[(str(anchor["type"]), stable_key)] = anchor_id

    pack_anchor_id = ids_by_type_and_key.get(("RuntimePack", "ada-lovelace-alpha"))
    figure_anchor_id = ids_by_type_and_key.get(("HistoricalFigure", "ada-lovelace"))
    if pack_anchor_id is None or figure_anchor_id is None:
        raise RuntimeError("Ada runtime pack or figure is missing")

    included: dict[str, set[str]] = {
        "HistoricalClaim": set(),
        "ReconstructionScene": set(),
        "LearningPrompt": set(),
        "Misconception": set(),
    }
    pack_link_types = {
        "pack_includes_claim": "HistoricalClaim",
        "pack_includes_scene": "ReconstructionScene",
        "pack_includes_prompt": "LearningPrompt",
        "pack_includes_misconception": "Misconception",
    }
    for link in links:
        if str(link["source_uuid"]) != pack_anchor_id:
            continue
        target_type = pack_link_types.get(str(link["type"]))
        if target_type:
            included[target_type].add(str(link["target_uuid"]))

    source_ids_by_claim: dict[str, list[str]] = {}
    claim_ids_by_scene: dict[str, list[str]] = {}
    claim_ids_by_prompt: dict[str, list[str]] = {}
    claim_ids_by_misconception: dict[str, list[str]] = {}
    for link in links:
        source_id = str(link["source_uuid"])
        target_id = str(link["target_uuid"])
        link_type = str(link["type"])
        if link_type == "claim_supported_by":
            source_ids_by_claim.setdefault(source_id, []).append(target_id)
        elif link_type == "scene_grounded_by":
            claim_ids_by_scene.setdefault(source_id, []).append(target_id)
        elif link_type == "prompt_grounded_by":
            claim_ids_by_prompt.setdefault(source_id, []).append(target_id)
        elif link_type == "misconception_corrected_by":
            claim_ids_by_misconception.setdefault(source_id, []).append(target_id)

    def item(anchor_id: str) -> dict[str, Any]:
        properties = dict(facts[anchor_id]["properties"])
        properties["graph_ref"] = {"graph_id": GRAPH_ID, "local_uuid": anchor_id}
        return properties

    sources = [
        item(anchor_id)
        for anchor_id, anchor in anchors.items()
        if anchor["type"] == "HistoricalSource"
    ]
    source_key_by_id = {entry["graph_ref"]["local_uuid"]: entry["stable_key"] for entry in sources}
    claim_key_by_id = {
        anchor_id: facts[anchor_id]["properties"]["stable_key"]
        for anchor_id in included["HistoricalClaim"]
    }

    claims = []
    for anchor_id in included["HistoricalClaim"]:
        entry = item(anchor_id)
        entry["source_keys"] = sorted(
            source_key_by_id[source_id] for source_id in source_ids_by_claim.get(anchor_id, ())
        )
        if not entry["source_keys"]:
            raise RuntimeError(f"claim has no supporting source: {entry['stable_key']}")
        claims.append(entry)

    def grounded_items(type_key: str, grounding: dict[str, list[str]]) -> list[dict[str, Any]]:
        result = []
        for anchor_id in included[type_key]:
            entry = item(anchor_id)
            entry["claim_keys"] = sorted(
                claim_key_by_id[claim_id] for claim_id in grounding.get(anchor_id, ())
            )
            if not entry["claim_keys"]:
                raise RuntimeError(f"{type_key} has no grounding claim: {entry['stable_key']}")
            result.append(entry)
        return result

    pack = {
        "schema_version": 1,
        "compiled_from": {
            "graph_id": GRAPH_ID,
            "snapshot_path": snapshot_path,
            "snapshot_ledger_position": snapshot.last_ledger_position,
        },
        "pack": item(pack_anchor_id),
        "figure": item(figure_anchor_id),
        "sources": sorted(sources, key=lambda value: value["stable_key"]),
        "claims": sorted(claims, key=lambda value: value["stable_key"]),
        "scenes": sorted(
            grounded_items("ReconstructionScene", claim_ids_by_scene),
            key=lambda value: value["stable_key"],
        ),
        "prompts": sorted(
            grounded_items("LearningPrompt", claim_ids_by_prompt),
            key=lambda value: value["stable_key"],
        ),
        "misconceptions": sorted(
            grounded_items("Misconception", claim_ids_by_misconception),
            key=lambda value: value["stable_key"],
        ),
    }
    _validate_pack(pack)
    return pack


def _validate_pack(pack: dict[str, Any]) -> None:
    source_keys = {item["stable_key"] for item in pack["sources"]}
    claim_keys = {item["stable_key"] for item in pack["claims"]}
    gates = {
        "one_figure": pack["figure"]["stable_key"] == "ada-lovelace",
        "twenty_claims": len(pack["claims"]) == 20,
        "all_claim_sources_resolve": all(
            set(item["source_keys"]) <= source_keys for item in pack["claims"]
        ),
        "all_grounding_resolves": all(
            set(item["claim_keys"]) <= claim_keys
            for group in ("scenes", "prompts", "misconceptions")
            for item in pack[group]
        ),
        "offline_guardrail": "never require Vellis or a model at runtime"
        in pack["pack"]["guardrails"],
    }
    failed = [name for name, passed in gates.items() if not passed]
    if failed:
        raise RuntimeError(f"runtime pack validation failed: {', '.join(failed)}")


def render_javascript(pack: dict[str, Any]) -> str:
    body = json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False)
    return (
        "// Generated from the validated Vellis time_room_history snapshot.\n"
        "// Regenerate with docs/prototypes/time-room-history/compile_runtime_pack.py.\n"
        "(function (root) {\n"
        "  root.TimeRoomCompiledPacks = root.TimeRoomCompiledPacks || {};\n"
        f"  root.TimeRoomCompiledPacks['ada-lovelace'] = {body};\n"
        "})(typeof window !== 'undefined' ? window : globalThis);\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile an offline Time Room runtime pack from Vellis."
    )
    parser.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE_ROOT)
    parser.add_argument("--sql-database-path", type=Path, default=DEFAULT_SQL_DATABASE_PATH)
    parser.add_argument("--snapshot-path", default=SNAPSHOT_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    pack = compile_runtime_pack(
        storage_root=args.storage_root,
        sql_database_path=args.sql_database_path,
        snapshot_path=args.snapshot_path,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_javascript(pack), encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"compiled={args.output}")
        print(f"claims={len(pack['claims'])}")
        print(f"sources={len(pack['sources'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error))
        raise SystemExit(1) from error
