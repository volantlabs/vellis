from __future__ import annotations

from components.runtime.component_adapter import (
    MethodBindingSpec,
    RuntimeActionIdempotency,
    create_typed_component_adapter,
    create_typed_proxy,
)
from components.runtime.message_runtime import MessageRuntime, RuntimeAddress, RuntimeReplayMode
from components.storage.sql.protocol import (
    SqlExecutionFailed,
    SqlParameterInvalid,
    SqlStatementInvalid,
    SqlStorage,
    SqlStorageError,
    SqlStoragePermissionDenied,
    SqlTransactionFailed,
)

_CONTRACT = "component.storage.sql"
_FAILURES: dict[str, tuple[type[SqlStorageError], ...]] = {
    "execute": (
        SqlStatementInvalid,
        SqlParameterInvalid,
        SqlExecutionFailed,
        SqlStoragePermissionDenied,
    ),
    "query": (
        SqlStatementInvalid,
        SqlParameterInvalid,
        SqlExecutionFailed,
        SqlStoragePermissionDenied,
    ),
    "transaction": (
        SqlStatementInvalid,
        SqlParameterInvalid,
        SqlTransactionFailed,
        SqlStoragePermissionDenied,
    ),
}
_SPECS = (
    MethodBindingSpec(
        "execute",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.UNSPECIFIED,
        externally_effectful=True,
        failure_types=_FAILURES["execute"],
    ),
    MethodBindingSpec(
        "query",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["query"],
    ),
    MethodBindingSpec(
        "transaction",
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeActionIdempotency.UNSPECIFIED,
        externally_effectful=True,
        failure_types=_FAILURES["transaction"],
    ),
)


def create_sql_storage_adapter(storage: SqlStorage):
    """Bind an independently durable database as a playback-only external boundary.

    The SQL component deliberately owns neither backup nor replay semantics. Re-executing
    arbitrary statements during runtime reconstruction would corrupt an already durable
    database, so the runtime records each exchange while leaving live state in its bound file.
    """
    return create_typed_component_adapter(
        storage,
        SqlStorage,
        component_contract_id=_CONTRACT,
        binding_id="binding.python.storage.sql.v1",
        specs=_SPECS,
        failure_types=(SqlStorageError,),
    )


def create_sql_storage_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> SqlStorage:
    return create_typed_proxy(
        runtime,
        source,
        target,
        SqlStorage,
        component_contract_id=_CONTRACT,
        specs=_SPECS,
        failure_types=(SqlStorageError,),
    )
