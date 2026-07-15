from __future__ import annotations

from components.runtime.component_adapter import (
    MethodBindingSpec,
    RuntimeActionIdempotency,
    create_typed_component_adapter,
    create_typed_proxy,
)
from components.runtime.message_runtime import MessageRuntime, RuntimeAddress, RuntimeReplayMode
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
_SPECS = (
    MethodBindingSpec(
        "write",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        externally_effectful=True,
        failure_types=_FAILURES["write"],
    ),
    MethodBindingSpec(
        "read",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["read"],
    ),
    MethodBindingSpec(
        "delete",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        externally_effectful=True,
        failure_types=_FAILURES["delete"],
    ),
    MethodBindingSpec(
        "list",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list"],
    ),
)


def create_json_file_storage_adapter(storage: JsonFileStorage):
    return create_typed_component_adapter(
        storage,
        JsonFileStorage,
        component_contract_id=_CONTRACT,
        binding_id="binding.python.storage.json_file.v1",
        specs=_SPECS,
        failure_types=(StorageError,),
    )


def create_json_file_storage_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> JsonFileStorage:
    return create_typed_proxy(
        runtime,
        source,
        target,
        JsonFileStorage,
        component_contract_id=_CONTRACT,
        specs=_SPECS,
        failure_types=(StorageError,),
    )
