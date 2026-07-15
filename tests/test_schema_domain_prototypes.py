from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PROTOTYPE_ROOT = Path("docs/prototypes").resolve()


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_experience_studio_fixtures_recreate_and_replay(tmp_path: Path) -> None:
    root = PROTOTYPE_ROOT / "experience-studio"
    module = _load_module("experience_studio_load_monograph", root / "load_monograph.py")
    storage_root = tmp_path / "experience-studio"

    payload = module.load_monograph(
        storage_root=storage_root,
        sql_database_path=storage_root / "controller.sqlite",
        snapshot_path="snapshots/test-experience-studio-alpha.json",
    )

    assert payload["generated_schema_definition_count"] == 42
    assert payload["seed_anchor_record_count"] == 27
    assert payload["submitted_link_count"] == 39
    assert payload["query_row_counts"] == {
        "experience-portfolio-query": 1,
        "publication-check-query": 6,
        "source-readiness-query": 1,
    }
    assert all(payload["gates"].values())
    assert (storage_root / "snapshots" / "test-experience-studio-alpha.json").is_file()


def test_gothic_ambient_archive_fixtures_recreate_and_replay(tmp_path: Path) -> None:
    root = PROTOTYPE_ROOT / "nocturne-archive"
    module = _load_module("gothic_archive_load_monograph", root / "load_monograph.py")
    storage_root = tmp_path / "gothic-archive"

    payload = module.load_monograph(
        storage_root=storage_root,
        sql_database_path=storage_root / "controller.sqlite",
        snapshot_path="snapshots/test-gothic-alpha.json",
    )

    assert payload["generated_schema_definition_count"] == 40
    assert payload["seed_anchor_record_count"] == 53
    assert payload["submitted_link_count"] == 88
    assert payload["query_row_counts"] == {
        "blood-trail-query": 6,
        "lucy-event-cluster-query": 5,
        "threshold-motif-query": 3,
    }
    assert all(payload["gates"].values())
    assert (storage_root / "snapshots" / "test-gothic-alpha.json").is_file()


def test_time_room_history_fixtures_recreate_replay_and_compile(tmp_path: Path) -> None:
    root = PROTOTYPE_ROOT / "time-room-history"
    module_names = {
        "build_prototype_data",
        "load_monograph",
        "time_room_history_compiler",
    }
    previous_modules = {name: sys.modules.get(name) for name in module_names}
    for name in module_names:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(root))
    try:
        builder = _load_module("build_prototype_data", root / "build_prototype_data.py")
        loader = _load_module("load_monograph", root / "load_monograph.py")
        compiler = _load_module(
            "time_room_history_compiler",
            root / "compile_runtime_pack.py",
        )

        schema_call = _load_json(root / "data" / "time-room-history-schema-v0.json")
        live_call = _load_json(root / "data" / "ada-lovelace-live-records.json")
        assert schema_call["arguments"]["schema_definitions"] == builder.schema_definitions()
        assert live_call["arguments"] == builder.live_records()
        assert {
            path.stem: _load_json(path)
            for path in sorted((root / "data" / "queries").glob("*.json"))
        } == builder.query_calls()

        storage_root = tmp_path / "time-room-history"
        loaded = loader.load_monograph(
            storage_root=storage_root,
            sql_database_path=storage_root / "controller.sqlite",
        )
        assert loaded["generated_schema_definition_count"] == 30
        assert loaded["seed_anchor_record_count"] == 61
        assert loaded["submitted_link_count"] == 217
        assert loaded["query_row_counts"]["claims"] == 20
        assert loaded["query_row_counts"]["sources"] == 6
        assert all(loaded["gates"].values())

        pack = compiler.compile_runtime_pack(
            storage_root=storage_root,
            sql_database_path=storage_root / "controller.sqlite",
        )
        assert len(pack["claims"]) == 20
        assert len(pack["sources"]) == 6
        assert all(claim["source_keys"] for claim in pack["claims"])
        assert all(
            claim["graph_ref"]["graph_id"] == "time_room_history"
            for claim in pack["claims"]
        )
        assert "TimeRoomCompiledPacks['ada-lovelace']" in compiler.render_javascript(pack)
    finally:
        sys.path.remove(str(root))
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
