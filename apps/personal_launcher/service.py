from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.personal_launcher.catalog_store import DEFAULT_CATALOG_PATH, load_or_create_catalog
from apps.personal_launcher.runtime import DesktopRuntimeAdapter
from components.app.catalog import (
    AppDescriptor,
    InMemoryAppCatalog,
    JsonValue,
    LaunchSurface,
)
from components.app.launcher import AppHandoff, AppSession, InMemoryAppLauncher
from components.app.shell import (
    AppOpenRequest,
    AppShellCommandResult,
    AppShellView,
    CloseRequest,
    InMemoryAppShell,
)


@dataclass(frozen=True, slots=True)
class PersonalLauncherConfig:
    catalog_path: Path = DEFAULT_CATALOG_PATH
    repo_root: Path = Path.cwd()


class PersonalLauncherService:
    def __init__(self, shell: InMemoryAppShell) -> None:
        self._shell = shell
        self._last_message = ""

    def state(self) -> dict[str, Any]:
        return _view_to_json(self._shell.get_home(), message=self._last_message)

    def launch(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._shell.open_app(
            AppOpenRequest(
                app_id=_required_payload_text(payload, "app_id"),
                surface_id=_optional_payload_text(payload, "surface_id"),
                mode=str(payload.get("mode", "launch")),
            )
        )
        self._last_message = result.message
        return _command_result_to_json(result)

    def switch(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._shell.switch_app(_required_payload_text(payload, "session_id"))
        self._last_message = result.message
        return _command_result_to_json(result)

    def close(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._shell.close_app(
            CloseRequest(
                session_id=_optional_payload_text(payload, "session_id"),
                stop_runtime=bool(payload.get("stop_runtime", False)),
            )
        )
        self._last_message = result.message
        return _command_result_to_json(result)


def build_service(
    config: PersonalLauncherConfig,
    *,
    runtime_adapter: DesktopRuntimeAdapter | None = None,
) -> PersonalLauncherService:
    descriptors = load_or_create_catalog(config.catalog_path, repo_root=config.repo_root)
    catalog = InMemoryAppCatalog.open(descriptors)
    runtime = runtime_adapter or DesktopRuntimeAdapter()
    launcher = InMemoryAppLauncher.open(catalog, runtime)
    shell = InMemoryAppShell.open(catalog, launcher)
    return PersonalLauncherService(shell)


def _command_result_to_json(result: AppShellCommandResult) -> dict[str, Any]:
    return {
        **_view_to_json(result.view, message=result.message),
        "result": {
            "app": _app_to_json(result.app) if result.app is not None else None,
            "session": _session_to_json(result.session) if result.session is not None else None,
            "handoff": _handoff_to_json(result.handoff) if result.handoff is not None else None,
            "message": result.message,
        },
    }


def _view_to_json(view: AppShellView, *, message: str) -> dict[str, Any]:
    active_session_id = view.active_app.session.session_id if view.active_app is not None else None
    return {
        "apps": [_app_to_json(app) for app in view.apps],
        "sessions": [_session_to_json(session) for session in view.sessions],
        "recent_launches": [_handoff_to_json(handoff) for handoff in view.recent_launches],
        "active_session_id": active_session_id,
        "available_commands": list(view.available_commands),
        "message": message,
    }


def _app_to_json(app: AppDescriptor) -> dict[str, Any]:
    return {
        "app_id": app.app_id,
        "title": app.title,
        "summary": app.summary,
        "status": app.status,
        "tags": list(app.tags),
        "launch_surfaces": [_surface_to_json(surface) for surface in app.launch_surfaces],
        "recommended_surface": app.recommended_surface,
        "metadata": app.metadata,
    }


def _surface_to_json(surface: LaunchSurface) -> dict[str, Any]:
    return {
        "surface_id": surface.surface_id,
        "kind": surface.kind,
        "mode": surface.mode,
        "label": surface.label,
        "runtime_control": surface.runtime_control,
        "details": surface.details,
    }


def _handoff_to_json(handoff: AppHandoff) -> dict[str, Any]:
    return {
        "handoff_id": handoff.handoff_id,
        "app_id": handoff.app_id,
        "surface_id": handoff.surface_id,
        "endpoint": handoff.endpoint,
        "handed_off_at": _datetime_to_json(handoff.handed_off_at),
        "details": handoff.details,
    }


def _session_to_json(session: AppSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "app_id": session.app_id,
        "surface_id": session.surface_id,
        "status": session.status,
        "ownership": session.ownership,
        "endpoint": session.endpoint,
        "started_at": _datetime_to_json(session.started_at),
        "last_checked_at": _datetime_to_json(session.last_checked_at),
        "details": session.details,
    }


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _required_payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_payload_text(payload: dict[str, Any], key: str) -> str | None:
    value: JsonValue | object = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a string when provided")
    return value
