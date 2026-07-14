from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from components.app.catalog.protocol import AppCatalog, AppNotFound, CatalogQuery
from components.app.launcher.protocol import (
    AppHandoff,
    AppLauncher,
    AppSession,
    AttachRequest,
    LaunchRequest,
    SessionNotFound,
    SessionNotLauncherOwned,
)
from components.app.shell.protocol import (
    AppCloseRejected,
    AppOpenRequest,
    AppShellCommandResult,
    AppShellConfigurationInvalid,
    AppShellView,
    CloseRequest,
    ShellActiveApp,
    ShellOptions,
    ShellQuery,
)

_COMMANDS = ("open_app", "switch_app", "close_app")
_MODE_LAUNCH = "launch"
_MODE_ATTACH = "attach"
_RECENT_HANDOFF_LIMIT = 10


class InMemoryAppShell:
    """In-memory implementation of the App Shell component."""

    def __init__(
        self,
        app_catalog: AppCatalog,
        app_launcher: AppLauncher,
        shell_options: ShellOptions | None = None,
    ) -> None:
        if app_catalog is None:
            raise AppShellConfigurationInvalid("app_catalog is required")
        if app_launcher is None:
            raise AppShellConfigurationInvalid("app_launcher is required")
        self._catalog = app_catalog
        self._launcher = app_launcher
        self._active_session_id = (
            shell_options.restored_active_session_id if shell_options is not None else None
        )
        self._selected_surface_by_app: dict[str, str] = {}
        self._recent_app_ids: list[str] = []
        self._recent_handoffs: list[AppHandoff] = []

    @classmethod
    def open(
        cls,
        app_catalog: AppCatalog,
        app_launcher: AppLauncher,
        shell_options: ShellOptions | None = None,
    ) -> InMemoryAppShell:
        return cls(app_catalog, app_launcher, shell_options)

    def get_home(self, shell_query: ShellQuery | None = None) -> AppShellView:
        query = shell_query or ShellQuery()
        apps = self._catalog.list_apps(
            CatalogQuery(status=query.status, tags=query.tags),
        ).apps
        sessions = self._launcher.list_sessions().sessions
        active = self._active_app(sessions)
        return AppShellView(
            apps=apps,
            sessions=sessions,
            recent_launches=tuple(self._copy_handoff(item) for item in self._recent_handoffs),
            active_app=active,
            available_commands=_COMMANDS,
        )

    def open_app(self, open_request: AppOpenRequest) -> AppShellCommandResult:
        if open_request.mode == _MODE_LAUNCH:
            result = self._launcher.launch_app(
                LaunchRequest(open_request.app_id, surface_id=open_request.surface_id)
            )
        elif open_request.mode == _MODE_ATTACH:
            result = self._launcher.attach_app(
                AttachRequest(open_request.app_id, surface_id=open_request.surface_id)
            )
        else:
            raise AppCloseRejected(f"unsupported open mode: {open_request.mode}")

        if result.session is not None:
            self._active_session_id = result.session.session_id
        elif result.handoff is not None:
            self._remember_handoff(result.handoff)
        else:
            raise AppCloseRejected("launcher returned neither a session nor a handoff")
        if open_request.surface_id is not None:
            self._selected_surface_by_app[open_request.app_id] = open_request.surface_id
        self._remember_app(open_request.app_id)
        return AppShellCommandResult(
            view=self.get_home(),
            app=result.app,
            session=result.session,
            handoff=result.handoff,
            message=f"Opened {result.app.title}.",
        )

    def switch_app(self, session_id: str) -> AppShellCommandResult:
        sessions = self._launcher.list_sessions().sessions
        session = self._find_session(sessions, session_id)
        app = self._catalog.get_app(session.app_id)
        self._active_session_id = session.session_id
        self._remember_app(app.app_id)
        return AppShellCommandResult(
            view=self.get_home(),
            app=app,
            session=session,
            message=f"Switched to {app.title}.",
        )

    def close_app(self, close_request: CloseRequest) -> AppShellCommandResult:
        target_session_id = close_request.session_id or self._active_session_id
        if target_session_id is None:
            raise AppCloseRejected("no active app to close")

        sessions = self._launcher.list_sessions().sessions
        session = self._find_session(sessions, target_session_id)
        app = self._catalog.get_app(session.app_id)

        if close_request.stop_runtime:
            try:
                session = self._launcher.stop_session(target_session_id)
            except SessionNotLauncherOwned as error:
                raise AppCloseRejected(str(error)) from error

        if self._active_session_id == target_session_id:
            self._active_session_id = None

        return AppShellCommandResult(
            view=self.get_home(),
            app=app,
            session=session,
            message=f"Closed {app.title}.",
        )

    def _active_app(self, sessions: tuple[AppSession, ...]) -> ShellActiveApp | None:
        if self._active_session_id is None:
            return None
        try:
            session = self._find_session(sessions, self._active_session_id)
            if session.status != "running":
                return None
            return ShellActiveApp(app=self._catalog.get_app(session.app_id), session=session)
        except AppNotFound, SessionNotFound:
            self._active_session_id = None
            return None

    @staticmethod
    def _find_session(sessions: tuple[AppSession, ...], session_id: str) -> AppSession:
        for session in sessions:
            if session.session_id == session_id:
                return session
        raise SessionNotFound(session_id)

    def _remember_app(self, app_id: str) -> None:
        if app_id in self._recent_app_ids:
            self._recent_app_ids.remove(app_id)
        self._recent_app_ids.insert(0, app_id)

    def _remember_handoff(self, handoff: AppHandoff) -> None:
        self._recent_handoffs.insert(0, self._copy_handoff(handoff))
        del self._recent_handoffs[_RECENT_HANDOFF_LIMIT:]

    @staticmethod
    def _copy_handoff(handoff: AppHandoff) -> AppHandoff:
        return replace(
            handoff,
            endpoint=deepcopy(handoff.endpoint),
            details=deepcopy(handoff.details),
        )

    @property
    def selected_surface_by_app(self) -> dict[str, str]:
        return dict(self._selected_surface_by_app)

    @property
    def recent_app_ids(self) -> tuple[str, ...]:
        return tuple(self._recent_app_ids)
