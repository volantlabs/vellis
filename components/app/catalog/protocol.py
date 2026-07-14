from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LaunchSurface:
    surface_id: str
    kind: str
    mode: str
    label: str
    details: dict[str, JsonValue] = field(default_factory=dict)
    runtime_control: str = "managed"


@dataclass(frozen=True, slots=True)
class AppDescriptor:
    app_id: str
    title: str
    summary: str
    status: str
    tags: tuple[str, ...] = ()
    launch_surfaces: tuple[LaunchSurface, ...] = ()
    recommended_surface: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    status: str | None = None
    tags: tuple[str, ...] = ()
    launch_surface_kind: str | None = None


@dataclass(frozen=True, slots=True)
class AppDescriptorList:
    apps: tuple[AppDescriptor, ...]


class AppCatalogError(Exception):
    """Base class for App Catalog errors."""


class AppCatalogUnavailable(AppCatalogError):
    """The descriptor store cannot be opened."""


class AppCatalogStoreInvalid(AppCatalogError):
    """The descriptor store is invalid."""


class AppDescriptorInvalid(AppCatalogError):
    """An app descriptor is invalid."""


class AppIdConflict(AppCatalogError):
    """The descriptor store contains conflicting app identity."""


class AppCatalogWriteFailed(AppCatalogError):
    """The catalog could not persist a write."""


class AppNotFound(AppCatalogError):
    """The requested app descriptor does not exist."""


class AppCatalogReadFailed(AppCatalogError):
    """The catalog could not read descriptors."""


class AppCatalog(Protocol):
    @classmethod
    def open(cls, descriptor_store: Iterable[AppDescriptor] | None = None) -> AppCatalog:
        """Open a catalog handle bound to a descriptor store."""
        ...

    def register_app(self, app_descriptor: AppDescriptor) -> AppDescriptor:
        """Create or replace one app descriptor."""
        ...

    def remove_app(self, app_id: str) -> AppDescriptor:
        """Remove one app descriptor."""
        ...

    def get_app(self, app_id: str) -> AppDescriptor:
        """Return one app descriptor."""
        ...

    def list_apps(self, catalog_query: CatalogQuery | None = None) -> AppDescriptorList:
        """List app descriptors deterministically."""
        ...
