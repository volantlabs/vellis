"""App Catalog component."""

from components.app.catalog.implementation import InMemoryAppCatalog
from components.app.catalog.protocol import (
    AppCatalog,
    AppCatalogError,
    AppCatalogReadFailed,
    AppCatalogStoreInvalid,
    AppCatalogUnavailable,
    AppCatalogWriteFailed,
    AppDescriptor,
    AppDescriptorInvalid,
    AppDescriptorList,
    AppIdConflict,
    AppNotFound,
    CatalogQuery,
    JsonValue,
    LaunchSurface,
)

__all__ = [
    "AppCatalog",
    "AppCatalogError",
    "AppCatalogReadFailed",
    "AppCatalogStoreInvalid",
    "AppCatalogUnavailable",
    "AppCatalogWriteFailed",
    "AppDescriptor",
    "AppDescriptorInvalid",
    "AppDescriptorList",
    "AppIdConflict",
    "AppNotFound",
    "CatalogQuery",
    "InMemoryAppCatalog",
    "JsonValue",
    "LaunchSurface",
]
