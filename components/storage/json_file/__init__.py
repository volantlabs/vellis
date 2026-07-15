"""JSON File Storage component."""

from components.storage.json_file.implementation import LocalJsonFileStorage
from components.storage.json_file.protocol import (
    JsonDocument,
    JsonDocumentInvalid,
    JsonDocumentList,
    JsonDocumentMetadata,
    JsonDocumentNotFound,
    JsonFileStorage,
    JsonValue,
    JsonValueNotSerializable,
    StorageDeleteFailed,
    StorageDirectoryNotFound,
    StorageError,
    StoragePathInvalid,
    StoragePermissionDenied,
    StorageReadFailed,
    StorageRootInvalid,
    StorageRootUnavailable,
    StorageWriteFailed,
)
from components.storage.json_file.runtime_binding import (
    create_json_file_storage_adapter,
    create_json_file_storage_proxy,
)

__all__ = [
    "JsonDocument",
    "JsonDocumentInvalid",
    "JsonDocumentList",
    "JsonDocumentMetadata",
    "JsonDocumentNotFound",
    "JsonFileStorage",
    "JsonValue",
    "JsonValueNotSerializable",
    "LocalJsonFileStorage",
    "StorageDeleteFailed",
    "StorageDirectoryNotFound",
    "StorageError",
    "StoragePathInvalid",
    "StoragePermissionDenied",
    "StorageReadFailed",
    "StorageRootInvalid",
    "StorageRootUnavailable",
    "StorageWriteFailed",
    "create_json_file_storage_adapter",
    "create_json_file_storage_proxy",
]
