from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from components.app.catalog import AppDescriptor, LaunchSurface

DEFAULT_CATALOG_PATH = Path.home() / ".vellis" / "app-catalog.json"
_HANDOFF_KINDS = {"file", "url"}


def load_or_create_catalog(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    *,
    repo_root: Path,
) -> tuple[AppDescriptor, ...]:
    default_records = default_catalog_records(repo_root=repo_root)
    if not catalog_path.exists():
        write_catalog(catalog_path, default_records)
        return load_catalog(catalog_path)
    records = _read_catalog_records(catalog_path)
    merged_records = _merge_default_records(records, default_records)
    if merged_records != records:
        write_catalog(catalog_path, merged_records)
    return tuple(_descriptor_from_record(record) for record in merged_records)


def load_catalog(catalog_path: Path) -> tuple[AppDescriptor, ...]:
    return tuple(_descriptor_from_record(record) for record in _read_catalog_records(catalog_path))


def _read_catalog_records(catalog_path: Path) -> list[dict[str, Any]]:
    try:
        with catalog_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"catalog JSON is invalid: {catalog_path}") from error
    if not isinstance(raw, dict):
        raise ValueError("catalog root must be a JSON object")
    apps = raw.get("apps")
    if not isinstance(apps, list):
        raise ValueError("catalog.apps must be a list")
    records: list[dict[str, Any]] = []
    for item in apps:
        if not isinstance(item, dict):
            raise ValueError("catalog.apps items must be objects")
        records.append(cast(dict[str, Any], item))
    return records


def _merge_default_records(
    records: list[dict[str, Any]],
    default_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    defaults_by_id = {
        app_id: record
        for record in default_records
        if isinstance((app_id := record.get("app_id")), str)
    }
    app_ids = {value for record in records if isinstance((value := record.get("app_id")), str)}
    merged_records = [
        _merge_surface_runtime_controls(record, defaults_by_id.get(str(record.get("app_id"))))
        for record in records
    ]
    for record in default_records:
        app_id = record.get("app_id")
        if isinstance(app_id, str) and app_id not in app_ids:
            merged_records.append(record)
            app_ids.add(app_id)
    return merged_records


def _merge_surface_runtime_controls(
    record: dict[str, Any],
    default_record: dict[str, Any] | None,
) -> dict[str, Any]:
    if default_record is None:
        return record
    surfaces = record.get("launch_surfaces")
    default_surfaces = default_record.get("launch_surfaces")
    if not isinstance(surfaces, list) or not isinstance(default_surfaces, list):
        return record
    defaults_by_id = {
        surface.get("surface_id"): surface
        for surface in default_surfaces
        if isinstance(surface, dict) and isinstance(surface.get("surface_id"), str)
    }
    merged_surfaces: list[object] = []
    changed = False
    for surface in surfaces:
        if not isinstance(surface, dict) or "runtime_control" in surface:
            merged_surfaces.append(surface)
            continue
        default_surface = defaults_by_id.get(surface.get("surface_id"))
        runtime_control = (
            default_surface.get("runtime_control") if isinstance(default_surface, dict) else None
        )
        if not isinstance(runtime_control, str):
            merged_surfaces.append(surface)
            continue
        merged_surfaces.append({**surface, "runtime_control": runtime_control})
        changed = True
    if not changed:
        return record
    return {**record, "launch_surfaces": merged_surfaces}


def write_catalog(catalog_path: Path, records: list[dict[str, Any]]) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "apps": records,
    }
    with catalog_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def default_catalog_records(*, repo_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        {
            "app_id": "codex",
            "title": "Codex",
            "summary": "Open the local Codex desktop app.",
            "status": "active",
            "tags": ["ai", "desktop"],
            "recommended_surface": "open",
            "launch_surfaces": [
                {
                    "surface_id": "open",
                    "kind": "command",
                    "mode": "launch",
                    "label": "Open",
                    "runtime_control": "handoff",
                    "details": {
                        "command": ["open", "-a", "Codex"],
                        "session_policy": "singleton",
                    },
                }
            ],
            "metadata": {
                "accent": "#2563eb",
                "glyph": "CX",
            },
        },
        {
            "app_id": "vellis-workspace",
            "title": "Vellis Workspace",
            "summary": "Open the Vellis repository folder.",
            "status": "active",
            "tags": ["vellis", "workspace"],
            "recommended_surface": "finder",
            "launch_surfaces": [
                {
                    "surface_id": "finder",
                    "kind": "file",
                    "mode": "launch",
                    "label": "Open",
                    "runtime_control": "handoff",
                    "details": {
                        "path": str(repo_root),
                        "session_policy": "singleton",
                    },
                }
            ],
            "metadata": {
                "accent": "#0f766e",
                "glyph": "VL",
            },
        },
        {
            "app_id": "rtg-mcp-info",
            "title": "RTG MCP Info",
            "summary": "Print local RTG MCP metadata in a short terminal-free run.",
            "status": "active",
            "tags": ["vellis", "rtg"],
            "recommended_surface": "dry-run",
            "launch_surfaces": [
                {
                    "surface_id": "dry-run",
                    "kind": "command",
                    "mode": "launch",
                    "label": "Run",
                    "runtime_control": "handoff",
                    "details": {
                        "command": [
                            "uv",
                            "run",
                            "python",
                            "-m",
                            "apps.rtg_knowledge_graph",
                            "serve-mcp",
                            "--dry-run",
                            "--json",
                        ],
                        "cwd": str(repo_root),
                        "session_policy": "multiple",
                    },
                }
            ],
            "metadata": {
                "accent": "#7c2d12",
                "glyph": "RG",
            },
        },
    ]

    desktop_dir = Path.home() / "Desktop"
    for app_path in sorted(desktop_dir.glob("* Apps.app")):
        title = app_path.stem
        app_id = _slug(title)
        records.append(
            {
                "app_id": app_id,
                "title": title,
                "summary": f"Open {title} from the Desktop.",
                "status": "active",
                "tags": ["desktop", "local"],
                "recommended_surface": "open",
                "launch_surfaces": [
                    {
                        "surface_id": "open",
                        "kind": "file",
                        "mode": "launch",
                        "label": "Open",
                        "runtime_control": "handoff",
                        "details": {
                            "path": str(app_path),
                            "session_policy": "singleton",
                        },
                    }
                ],
                "metadata": {
                    "accent": "#9333ea",
                    "glyph": _glyph(title),
                },
            }
        )
    return records


def _descriptor_from_record(record: dict[str, Any]) -> AppDescriptor:
    surfaces = record.get("launch_surfaces", [])
    if not isinstance(surfaces, list):
        raise ValueError("launch_surfaces must be a list")
    tags = record.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError("tags must be a list")
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    return AppDescriptor(
        app_id=_required_str(record, "app_id"),
        title=_required_str(record, "title"),
        summary=str(record.get("summary", "")),
        status=_required_str(record, "status"),
        tags=tuple(str(item) for item in tags),
        launch_surfaces=tuple(
            _surface_from_record(cast(dict[str, Any], item)) for item in surfaces
        ),
        recommended_surface=cast(str | None, record.get("recommended_surface")),
        metadata=metadata,
    )


def _surface_from_record(record: dict[str, Any]) -> LaunchSurface:
    details = record.get("details", {})
    if not isinstance(details, dict):
        raise ValueError("launch surface details must be an object")
    kind = _required_str(record, "kind")
    runtime_control = record.get("runtime_control")
    if runtime_control is None:
        runtime_control = "handoff" if kind in _HANDOFF_KINDS else "managed"
    if not isinstance(runtime_control, str) or not runtime_control.strip():
        raise ValueError("runtime_control must be a non-empty string")
    return LaunchSurface(
        surface_id=_required_str(record, "surface_id"),
        kind=kind,
        mode=_required_str(record, "mode"),
        label=_required_str(record, "label"),
        details=details,
        runtime_control=runtime_control,
    )


def _required_str(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _slug(value: str) -> str:
    lowered = value.lower().replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "desktop-app"


def _glyph(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    if not parts:
        return "AP"
    return "".join(part[0] for part in parts[:2]).upper()
