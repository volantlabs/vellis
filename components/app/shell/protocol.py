from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from components.app.catalog.protocol import AppCatalog, AppDescriptor
from components.app.launcher.protocol import AppHandoff, AppLauncher, AppSession


@dataclass(frozen=True, slots=True)
class ShellOptions:
    restored_active_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class ShellQuery:
    status: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AppOpenRequest:
    app_id: str
    surface_id: str | None = None
    mode: str = "launch"


@dataclass(frozen=True, slots=True)
class CloseRequest:
    session_id: str | None = None
    stop_runtime: bool = False


@dataclass(frozen=True, slots=True)
class ShellActiveApp:
    app: AppDescriptor
    session: AppSession


@dataclass(frozen=True, slots=True)
class AppShellView:
    apps: tuple[AppDescriptor, ...]
    sessions: tuple[AppSession, ...]
    recent_launches: tuple[AppHandoff, ...]
    active_app: ShellActiveApp | None
    available_commands: tuple[str, ...]
    messages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AppShellCommandResult:
    view: AppShellView
    app: AppDescriptor | None = None
    session: AppSession | None = None
    handoff: AppHandoff | None = None
    message: str = ""


class AppShellError(Exception):
    """Base class for App Shell errors."""


class AppShellConfigurationInvalid(AppShellError):
    """The shell was configured with invalid dependencies."""


class AppShellReadFailed(AppShellError):
    """The shell could not assemble its home view."""


class AppCloseRejected(AppShellError):
    """The requested close behavior is not allowed by shell semantics."""


class AppShell(Protocol):
    @classmethod
    def open(
        cls,
        app_catalog: AppCatalog,
        app_launcher: AppLauncher,
        shell_options: ShellOptions | None = None,
    ) -> AppShell:
        """Open a shell handle bound to catalog and launcher dependencies."""
        ...

    def get_home(self, shell_query: ShellQuery | None = None) -> AppShellView:
        """Return a renderer-neutral shell home view."""
        ...

    def open_app(self, open_request: AppOpenRequest) -> AppShellCommandResult:
        """Open one app through launcher contracts."""
        ...

    def switch_app(self, session_id: str) -> AppShellCommandResult:
        """Make an existing launcher-known session active."""
        ...

    def close_app(self, close_request: CloseRequest) -> AppShellCommandResult:
        """Clear shell active state and optionally stop launcher-owned runtime."""
        ...
