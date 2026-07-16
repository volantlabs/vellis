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
    JSON_FILE_STORAGE_ACTIONS,
    create_json_file_storage_adapter,
)

__all__ = [
    "JsonDocument",
    "JsonDocumentInvalid",
    "JsonDocumentList",
    "JsonDocumentMetadata",
    "JsonDocumentNotFound",
    "JsonFileStorage",
    "JSON_FILE_STORAGE_ACTIONS",
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
]
