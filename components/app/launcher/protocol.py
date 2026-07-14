from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from components.app.catalog.protocol import AppCatalog, AppDescriptor, JsonValue, LaunchSurface


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    app_id: str
    surface_id: str | None = None


@dataclass(frozen=True, slots=True)
class AttachRequest:
    app_id: str
    surface_id: str | None = None


@dataclass(frozen=True, slots=True)
class SessionQuery:
    app_id: str | None = None
    status: str | None = None
    ownership: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSurfaceResult:
    endpoint: dict[str, JsonValue] = field(default_factory=dict)
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AppSession:
    session_id: str
    app_id: str
    surface_id: str
    status: str
    ownership: str
    endpoint: dict[str, JsonValue] = field(default_factory=dict)
    started_at: datetime | None = None
    last_checked_at: datetime | None = None
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AppHandoff:
    handoff_id: str
    app_id: str
    surface_id: str
    endpoint: dict[str, JsonValue] = field(default_factory=dict)
    handed_off_at: datetime | None = None
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AppSessionList:
    sessions: tuple[AppSession, ...]


@dataclass(frozen=True, slots=True)
class AppLaunchResult:
    app: AppDescriptor
    session: AppSession | None = None
    handoff: AppHandoff | None = None
    reused_existing: bool = False


class AppLauncherError(Exception):
    """Base class for App Launcher errors."""


class AppLauncherConfigurationInvalid(AppLauncherError):
    """The launcher was configured with invalid dependencies."""


class LaunchSurfaceNotFound(AppLauncherError):
    """The requested launch surface does not exist on the app descriptor."""


class LaunchSurfaceUnsupported(AppLauncherError):
    """The requested launch surface does not support the requested operation."""


class LaunchRejected(AppLauncherError):
    """The launch request was rejected before runtime start."""


class AppStartFailed(AppLauncherError):
    """The runtime adapter failed to start the app surface."""


class AttachFailed(AppLauncherError):
    """The runtime adapter failed to attach to the app surface."""


class SessionNotFound(AppLauncherError):
    """The requested launcher session does not exist."""


class SessionNotLauncherOwned(AppLauncherError):
    """The requested session is not owned by this launcher."""


class AppStopFailed(AppLauncherError):
    """The runtime adapter failed to stop the launcher-owned session."""


class RuntimeAdapter(Protocol):
    def supports(self, launch_surface: LaunchSurface, operation: str) -> bool:
        """Return whether the adapter supports this surface and operation."""
        ...

    def start(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        """Start one launch surface."""
        ...

    def attach(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        """Attach to one launch surface."""
        ...

    def stop(self, session: AppSession) -> RuntimeSurfaceResult:
        """Stop one launcher-owned session."""
        ...

    def probe(self, session: AppSession) -> RuntimeSurfaceResult:
        """Report current surface-level availability for one session."""
        ...


class AppLauncher(Protocol):
    @classmethod
    def open(cls, app_catalog: AppCatalog, runtime_adapter: RuntimeAdapter) -> AppLauncher:
        """Open a launcher handle bound to catalog and runtime dependencies."""
        ...

    def launch_app(self, launch_request: LaunchRequest) -> AppLaunchResult:
        """Launch one catalog-declared app surface."""
        ...

    def attach_app(self, attach_request: AttachRequest) -> AppLaunchResult:
        """Attach to one catalog-declared app surface."""
        ...

    def stop_session(self, session_id: str) -> AppSession:
        """Stop one launcher-owned session."""
        ...

    def list_sessions(self, session_query: SessionQuery | None = None) -> AppSessionList:
        """List launcher-known app sessions."""
        ...
