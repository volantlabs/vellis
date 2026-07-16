from __future__ import annotations

from components.runtime.component_adapter import (
    ComponentAdapter,
    create_action_catalog,
    create_typed_component_adapter,
    load_runtime_binding_resource,
)
from components.storage.json_file.protocol import (
    JsonDocumentInvalid,
    JsonDocumentNotFound,
    JsonFileStorage,
    JsonValueNotSerializable,
    StorageDeleteFailed,
    StorageDirectoryNotFound,
    StorageError,
    StoragePathInvalid,
    StoragePermissionDenied,
    StorageReadFailed,
    StorageWriteFailed,
)

_CONTRACT = "component.storage.json_file"
_FAILURES: dict[str, tuple[type[StorageError], ...]] = {
    "write": (
        StoragePathInvalid,
        JsonValueNotSerializable,
        StoragePermissionDenied,
        StorageWriteFailed,
    ),
    "read": (
        StoragePathInvalid,
        JsonDocumentNotFound,
        JsonDocumentInvalid,
        StoragePermissionDenied,
        StorageReadFailed,
    ),
    "delete": (
        StoragePathInvalid,
        JsonDocumentNotFound,
        StoragePermissionDenied,
        StorageDeleteFailed,
    ),
    "list": (
        StoragePathInvalid,
        StorageDirectoryNotFound,
        StoragePermissionDenied,
        StorageReadFailed,
    ),
}
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
JSON_FILE_STORAGE_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_json_file_storage_adapter(storage: JsonFileStorage) -> ComponentAdapter:
    return create_typed_component_adapter(
        storage,
        JsonFileStorage,
        binding=_RUNTIME_BINDING,
        failure_types=(StorageError,),
    )
