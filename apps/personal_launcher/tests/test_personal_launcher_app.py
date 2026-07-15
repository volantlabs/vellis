from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from apps.personal_launcher import runtime as launcher_runtime
from apps.personal_launcher.catalog_store import load_catalog, load_or_create_catalog, write_catalog
from apps.personal_launcher.desktop import install_desktop_app
from apps.personal_launcher.runtime import DesktopRuntimeAdapter
from apps.personal_launcher.service import PersonalLauncherConfig, build_service
from components.app.launcher import AppStartFailed

MODEL_EVIDENCE = {
    "PersonalLauncherCompositionVerification": (
        "test_load_or_create_catalog_merges_missing_builtin_apps_without_overwriting",
        "test_service_records_url_handoff_without_active_session",
        "test_missing_file_surface_fails_without_recording_activity",
        "test_command_surface_records_process_session",
        "test_completed_command_becomes_handoff_instead_of_running_session",
        "test_desktop_installer_writes_mac_app_bundle",
    )
}


def test_catalog_loads_app_descriptors(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    write_catalog(
        catalog_path,
        [
            {
                "app_id": "docs",
                "title": "Docs",
                "summary": "Open docs.",
                "status": "active",
                "tags": ["work"],
                "recommended_surface": "url",
                "launch_surfaces": [
                    {
                        "surface_id": "url",
                        "kind": "url",
                        "mode": "launch",
                        "label": "Open",
                        "details": {"url": "https://example.test"},
                    }
                ],
            }
        ],
    )

    descriptors = load_catalog(catalog_path)

    assert descriptors[0].app_id == "docs"
    assert descriptors[0].launch_surfaces[0].details["url"] == "https://example.test"
    assert descriptors[0].launch_surfaces[0].runtime_control == "handoff"


def test_load_or_create_catalog_merges_missing_builtin_apps_without_overwriting(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    write_catalog(
        catalog_path,
        [
            {
                "app_id": "codex",
                "title": "Codex",
                "summary": "Custom local Codex entry.",
                "status": "active",
                "tags": ["custom"],
                "recommended_surface": "open",
                "launch_surfaces": [
                    {
                        "surface_id": "open",
                        "kind": "command",
                        "mode": "launch",
                        "label": "Open",
                        "details": {"command": ["open", "-a", "Codex"]},
                    }
                ],
            }
        ],
    )

    descriptors = load_or_create_catalog(catalog_path, repo_root=Path.cwd())
    codex = next(app for app in descriptors if app.app_id == "codex")
    workspace = next(app for app in descriptors if app.app_id == "vellis-workspace")
    rtg_info = next(app for app in descriptors if app.app_id == "rtg-mcp-info")

    assert codex.summary == "Custom local Codex entry."
    assert codex.tags == ("custom",)
    assert codex.launch_surfaces[0].runtime_control == "handoff"
    assert workspace.launch_surfaces[0].details["path"] == str(Path.cwd())
    assert rtg_info.launch_surfaces[0].details["command"] == [
        "uv",
        "run",
        "python",
        "-m",
        "apps.rtg_knowledge_graph",
        "serve-mcp",
        "--dry-run",
        "--json",
    ]
    assert {app.app_id for app in load_catalog(catalog_path)} >= {
        "codex",
        "vellis-workspace",
        "rtg-mcp-info",
    }
    persisted_codex = next(app for app in load_catalog(catalog_path) if app.app_id == "codex")
    assert persisted_codex.launch_surfaces[0].runtime_control == "handoff"


def test_service_records_url_handoff_without_active_session(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    write_catalog(
        catalog_path,
        [
            {
                "app_id": "docs",
                "title": "Docs",
                "summary": "Open docs.",
                "status": "active",
                "tags": ["work"],
                "recommended_surface": "url",
                "launch_surfaces": [
                    {
                        "surface_id": "url",
                        "kind": "url",
                        "mode": "launch",
                        "label": "Open",
                        "details": {"url": "https://example.test"},
                    }
                ],
            }
        ],
    )
    opened: list[str] = []
    service = build_service(
        PersonalLauncherConfig(catalog_path=catalog_path, repo_root=tmp_path),
        runtime_adapter=DesktopRuntimeAdapter(url_opener=opened.append),
    )

    result = service.launch({"app_id": "docs", "surface_id": "url"})

    assert opened == ["https://example.test"]
    assert result["active_session_id"] is None
    assert result["result"]["session"] is None
    assert result["result"]["handoff"]["app_id"] == "docs"
    assert result["recent_launches"][0]["app_id"] == "docs"
    assert result["result"]["app"]["title"] == "Docs"


def test_missing_file_surface_fails_without_recording_activity(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    missing_path = tmp_path / "missing.html"
    write_catalog(
        catalog_path,
        [
            {
                "app_id": "missing-file",
                "title": "Missing File",
                "summary": "Open a missing file.",
                "status": "active",
                "tags": ["test"],
                "recommended_surface": "open",
                "launch_surfaces": [
                    {
                        "surface_id": "open",
                        "kind": "file",
                        "mode": "launch",
                        "label": "Open",
                        "details": {"path": str(missing_path)},
                    }
                ],
            }
        ],
    )
    service = build_service(PersonalLauncherConfig(catalog_path=catalog_path, repo_root=tmp_path))

    with pytest.raises(AppStartFailed, match="launch surface path does not exist"):
        service.launch({"app_id": "missing-file"})

    assert service.state()["sessions"] == []
    assert service.state()["recent_launches"] == []


def test_command_surface_records_process_session(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    marker = tmp_path / "marker.json"
    write_catalog(
        catalog_path,
        [
            {
                "app_id": "command",
                "title": "Command",
                "summary": "Run command.",
                "status": "active",
                "tags": ["tool"],
                "recommended_surface": "run",
                "launch_surfaces": [
                    {
                        "surface_id": "run",
                        "kind": "command",
                        "mode": "launch",
                        "label": "Run",
                        "details": {
                            "command": [
                                sys.executable,
                                "-c",
                                (
                                    "import pathlib,time; "
                                    f"pathlib.Path({str(marker)!r}).write_text('ok'); "
                                    "time.sleep(5)"
                                ),
                            ],
                        },
                    }
                ],
            }
        ],
    )
    service = build_service(PersonalLauncherConfig(catalog_path=catalog_path, repo_root=tmp_path))

    result = service.launch({"app_id": "command"})

    assert result["result"]["session"]["endpoint"]["kind"] == "command"
    assert isinstance(result["result"]["session"]["details"]["pid"], int)
    assert result["recent_launches"] == []
    service.close(
        {
            "session_id": result["result"]["session"]["session_id"],
            "stop_runtime": True,
        }
    )


def test_completed_command_becomes_handoff_instead_of_running_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CompletedCommand:
        pid = 12345

        def wait(self, timeout: float) -> int:
            assert timeout == launcher_runtime._STARTUP_GRACE_SECONDS
            return 0

    def start_completed_command(command: object, *, cwd: object = None) -> CompletedCommand:
        assert command == [sys.executable, "-c", "raise SystemExit(0)"]
        assert cwd is None
        return CompletedCommand()

    monkeypatch.setattr(launcher_runtime.subprocess, "Popen", start_completed_command)
    catalog_path = tmp_path / "catalog.json"
    write_catalog(
        catalog_path,
        [
            {
                "app_id": "command",
                "title": "Command",
                "summary": "Run command.",
                "status": "active",
                "tags": ["tool"],
                "recommended_surface": "run",
                "launch_surfaces": [
                    {
                        "surface_id": "run",
                        "kind": "command",
                        "mode": "launch",
                        "label": "Run",
                        "details": {"command": [sys.executable, "-c", "raise SystemExit(0)"]},
                    }
                ],
            }
        ],
    )
    service = build_service(PersonalLauncherConfig(catalog_path=catalog_path, repo_root=tmp_path))

    result = service.launch({"app_id": "command"})

    assert result["result"]["session"] is None
    assert result["result"]["handoff"]["details"]["runtime_state"] == "handed_off"
    assert result["sessions"] == []


def test_desktop_installer_writes_mac_app_bundle(tmp_path: Path) -> None:
    destination = tmp_path / "Vellis Launcher.app"
    launch_agent_path = tmp_path / "com.vellis.personal-launcher.plist"
    runtime_root = tmp_path / "runtime"

    app_path = install_desktop_app(
        repo_root=Path.cwd(),
        destination=destination,
        launch_agent_path=launch_agent_path,
        runtime_root=runtime_root,
        port=19999,
        load_agent=False,
    )

    info = app_path / "Contents" / "Info.plist"
    executable = app_path / "Contents" / "MacOS" / "vellis-launcher"
    icon = app_path / "Contents" / "Resources" / "AppIcon.icns"
    assert info.exists()
    with info.open("rb") as file:
        plist = plistlib.load(file)
    assert plist["CFBundleIconFile"] == "AppIcon"
    assert icon.exists()
    assert icon.stat().st_size > 0
    assert launch_agent_path.exists()
    assert (runtime_root / "apps" / "personal_launcher" / "main.py").exists()
    assert (runtime_root / "components" / "app" / "shell" / "implementation.py").exists()
    assert executable.exists()
    assert executable.stat().st_mode & 0o111
    script = executable.read_text(encoding="utf-8")
    launch_agent = launch_agent_path.read_text(encoding="utf-8")
    assert "apps.personal_launcher" in launch_agent
    assert "/usr/bin/env -i" in launch_agent
    assert "PYTHONPATH" in launch_agent
    assert str(runtime_root) in launch_agent
    assert "http://127.0.0.1:19999/" in script
    assert "--port 19999" in launch_agent
