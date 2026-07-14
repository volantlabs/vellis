from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from components.app.catalog.protocol import AppCatalog, AppDescriptor, JsonValue, LaunchSurface
from components.app.launcher.protocol import (
    AppHandoff,
    AppLauncherConfigurationInvalid,
    AppLaunchResult,
    AppSession,
    AppSessionList,
    AppStartFailed,
    AppStopFailed,
    AttachFailed,
    AttachRequest,
    LaunchRejected,
    LaunchRequest,
    LaunchSurfaceNotFound,
    LaunchSurfaceUnsupported,
    RuntimeAdapter,
    RuntimeSurfaceResult,
    SessionNotFound,
    SessionNotLauncherOwned,
    SessionQuery,
)

_OPERATION_LAUNCH = "launch"
_OPERATION_ATTACH = "attach"
_OWNERSHIP_LAUNCHER = "launcher_owned"
_OWNERSHIP_EXTERNAL = "external"
_STATUS_RUNNING = "running"
_STATUS_STOPPED = "stopped"
_STATUS_EXITED = "exited"
_SESSION_POLICY_MULTIPLE = "multiple"
_RUNTIME_CONTROL_HANDOFF = "handoff"
_RUNTIME_STATE_HANDED_OFF = "handed_off"


class InMemoryAppLauncher:
    """In-memory implementation of the App Launcher component."""

    def __init__(
        self,
        app_catalog: AppCatalog,
        runtime_adapter: RuntimeAdapter,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if app_catalog is None:
            raise AppLauncherConfigurationInvalid("app_catalog is required")
        if runtime_adapter is None:
            raise AppLauncherConfigurationInvalid("runtime_adapter is required")
        self._catalog = app_catalog
        self._runtime = runtime_adapter
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._sessions: dict[str, AppSession] = {}

    @classmethod
    def open(
        cls,
        app_catalog: AppCatalog,
        runtime_adapter: RuntimeAdapter,
    ) -> InMemoryAppLauncher:
        return cls(app_catalog, runtime_adapter)

    def launch_app(self, launch_request: LaunchRequest) -> AppLaunchResult:
        app = self._catalog.get_app(launch_request.app_id)
        surface = self._select_surface(app, launch_request.surface_id, _OPERATION_LAUNCH)
        if not self._mode_supports(surface, _OPERATION_LAUNCH):
            raise LaunchSurfaceUnsupported(f"surface does not support launch: {surface.surface_id}")
        if not self._runtime.supports(surface, _OPERATION_LAUNCH):
            raise LaunchSurfaceUnsupported(f"runtime does not support launch: {surface.kind}")

        if surface.runtime_control != _RUNTIME_CONTROL_HANDOFF:
            existing = self._existing_running_session(app.app_id, surface.surface_id)
            if (
                existing is not None
                and surface.details.get("session_policy") != _SESSION_POLICY_MULTIPLE
            ):
                return AppLaunchResult(
                    app=app,
                    session=self._copy_session(existing),
                    reused_existing=True,
                )

        try:
            runtime_result = self._runtime.start(surface)
        except AppStartFailed:
            raise
        except Exception as error:
            raise AppStartFailed(str(error)) from error

        if (
            surface.runtime_control == _RUNTIME_CONTROL_HANDOFF
            or runtime_result.details.get("runtime_state") == _RUNTIME_STATE_HANDED_OFF
        ):
            return AppLaunchResult(
                app=app,
                handoff=self._new_handoff(
                    app_id=app.app_id,
                    surface_id=surface.surface_id,
                    runtime_result=runtime_result,
                ),
            )

        session = self._new_session(
            app_id=app.app_id,
            surface_id=surface.surface_id,
            ownership=_OWNERSHIP_LAUNCHER,
            runtime_result=runtime_result,
        )
        self._sessions[session.session_id] = session
        return AppLaunchResult(app=app, session=self._copy_session(session), reused_existing=False)

    def attach_app(self, attach_request: AttachRequest) -> AppLaunchResult:
        app = self._catalog.get_app(attach_request.app_id)
        surface = self._select_surface(app, attach_request.surface_id, _OPERATION_ATTACH)
        if not self._mode_supports(surface, _OPERATION_ATTACH):
            raise LaunchSurfaceUnsupported(f"surface does not support attach: {surface.surface_id}")
        if not self._runtime.supports(surface, _OPERATION_ATTACH):
            raise LaunchSurfaceUnsupported(f"runtime does not support attach: {surface.kind}")

        try:
            runtime_result = self._runtime.attach(surface)
        except AttachFailed:
            raise
        except Exception as error:
            raise AttachFailed(str(error)) from error

        session = self._new_session(
            app_id=app.app_id,
            surface_id=surface.surface_id,
            ownership=_OWNERSHIP_EXTERNAL,
            runtime_result=runtime_result,
        )
        self._sessions[session.session_id] = session
        return AppLaunchResult(app=app, session=self._copy_session(session), reused_existing=False)

    def stop_session(self, session_id: str) -> AppSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        if session.ownership != _OWNERSHIP_LAUNCHER:
            raise SessionNotLauncherOwned(session_id)
        if session.status == _STATUS_STOPPED:
            return self._copy_session(session)

        try:
            runtime_result = self._runtime.stop(session)
        except AppStopFailed:
            raise
        except Exception as error:
            raise AppStopFailed(str(error)) from error

        stopped = replace(
            session,
            status=_STATUS_STOPPED,
            last_checked_at=self._clock(),
            details=self._copy_json_object({**session.details, **runtime_result.details}),
        )
        self._sessions[session_id] = stopped
        return self._copy_session(stopped)

    def list_sessions(self, session_query: SessionQuery | None = None) -> AppSessionList:
        query = session_query or SessionQuery()
        for session_id, session in tuple(self._sessions.items()):
            self._sessions[session_id] = self._refresh_session(session)
        sessions = tuple(
            self._copy_session(session)
            for session in sorted(self._sessions.values(), key=lambda item: item.session_id)
            if self._matches_query(session, query)
        )
        return AppSessionList(sessions=sessions)

    def _refresh_session(self, session: AppSession) -> AppSession:
        if session.status != _STATUS_RUNNING or session.ownership != _OWNERSHIP_LAUNCHER:
            return session
        try:
            runtime_result = self._runtime.probe(session)
        except Exception as error:
            return replace(
                session,
                last_checked_at=self._clock(),
                details=self._copy_json_object({**session.details, "probe_error": str(error)}),
            )

        runtime_state = runtime_result.details.get("runtime_state")
        status = _STATUS_EXITED if runtime_state == _STATUS_EXITED else session.status
        return replace(
            session,
            status=status,
            endpoint=self._copy_json_object(runtime_result.endpoint or session.endpoint),
            last_checked_at=self._clock(),
            details=self._copy_json_object({**session.details, **runtime_result.details}),
        )

    def _select_surface(
        self,
        app: AppDescriptor,
        requested_surface_id: str | None,
        operation: str,
    ) -> LaunchSurface:
        surface_id = requested_surface_id or app.recommended_surface
        if surface_id is not None:
            for surface in app.launch_surfaces:
                if surface.surface_id == surface_id:
                    return surface
            raise LaunchSurfaceNotFound(surface_id)

        for surface in app.launch_surfaces:
            if self._mode_supports(surface, operation):
                return surface
        raise LaunchSurfaceNotFound(f"no {operation} surface for app: {app.app_id}")

    def _new_session(
        self,
        *,
        app_id: str,
        surface_id: str,
        ownership: str,
        runtime_result: RuntimeSurfaceResult,
    ) -> AppSession:
        now = self._clock()
        session_id = self._id_factory()
        if session_id in self._sessions:
            raise LaunchRejected(f"duplicate session_id: {session_id}")
        return AppSession(
            session_id=session_id,
            app_id=app_id,
            surface_id=surface_id,
            status=_STATUS_RUNNING,
            ownership=ownership,
            endpoint=self._copy_json_object(runtime_result.endpoint),
            started_at=now,
            last_checked_at=now,
            details=self._copy_json_object(runtime_result.details),
        )

    def _new_handoff(
        self,
        *,
        app_id: str,
        surface_id: str,
        runtime_result: RuntimeSurfaceResult,
    ) -> AppHandoff:
        return AppHandoff(
            handoff_id=self._id_factory(),
            app_id=app_id,
            surface_id=surface_id,
            endpoint=self._copy_json_object(runtime_result.endpoint),
            handed_off_at=self._clock(),
            details=self._copy_json_object(runtime_result.details),
        )

    def _existing_running_session(self, app_id: str, surface_id: str) -> AppSession | None:
        for session_id, session in tuple(self._sessions.items()):
            if (
                session.app_id == app_id
                and session.surface_id == surface_id
                and session.status == _STATUS_RUNNING
                and session.ownership == _OWNERSHIP_LAUNCHER
            ):
                refreshed = self._refresh_session(session)
                self._sessions[session_id] = refreshed
                if refreshed.status == _STATUS_RUNNING:
                    return refreshed
        return None

    @staticmethod
    def _mode_supports(surface: LaunchSurface, operation: str) -> bool:
        return surface.mode == operation or surface.mode == "launch_or_attach"

    @staticmethod
    def _matches_query(session: AppSession, query: SessionQuery) -> bool:
        if query.app_id is not None and session.app_id != query.app_id:
            return False
        if query.status is not None and session.status != query.status:
            return False
        if query.ownership is not None and session.ownership != query.ownership:
            return False
        return True

    @classmethod
    def _copy_session(cls, session: AppSession) -> AppSession:
        return replace(
            session,
            endpoint=cls._copy_json_object(session.endpoint),
            details=cls._copy_json_object(session.details),
        )

    @staticmethod
    def _copy_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        serialized = json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
        loaded = json.loads(serialized)
        if not isinstance(loaded, dict):
            return {}
        return loaded


class InMemoryRuntimeAdapter:
    """Runtime adapter for tests and reference compositions; it does not spawn processes."""

    def __init__(self, supported_kinds: tuple[str, ...] = ("mcp_stdio", "localhost_http")) -> None:
        self._supported_kinds = frozenset(supported_kinds)
        self.started_surfaces: list[str] = []
        self.attached_surfaces: list[str] = []
        self.stopped_sessions: list[str] = []

    def supports(self, launch_surface: LaunchSurface, operation: str) -> bool:
        return launch_surface.kind in self._supported_kinds and InMemoryAppLauncher._mode_supports(
            launch_surface,
            operation,
        )

    def start(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        self.started_surfaces.append(launch_surface.surface_id)
        return self._result_for(launch_surface, "started")

    def attach(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        self.attached_surfaces.append(launch_surface.surface_id)
        return self._result_for(launch_surface, "attached")

    def stop(self, session: AppSession) -> RuntimeSurfaceResult:
        self.stopped_sessions.append(session.session_id)
        return RuntimeSurfaceResult(
            endpoint=session.endpoint,
            details={"runtime_state": "stopped"},
        )

    def probe(self, session: AppSession) -> RuntimeSurfaceResult:
        return RuntimeSurfaceResult(
            endpoint=session.endpoint,
            details={"runtime_state": "running"},
        )

    @staticmethod
    def _result_for(launch_surface: LaunchSurface, runtime_state: str) -> RuntimeSurfaceResult:
        endpoint = {"kind": launch_surface.kind, **launch_surface.details}
        return RuntimeSurfaceResult(
            endpoint=endpoint,
            details={"runtime_state": runtime_state},
        )
