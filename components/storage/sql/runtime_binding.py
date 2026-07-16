from __future__ import annotations

from components.runtime.component_adapter import (
    ComponentAdapter,
    create_action_catalog,
    create_typed_component_adapter,
    load_runtime_binding_resource,
)
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
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
SQL_STORAGE_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_sql_storage_adapter(storage: SqlStorage) -> ComponentAdapter:
    """Bind an independently durable database as a playback-only external boundary.

    The SQL component deliberately owns neither backup nor replay semantics. Re-executing
    arbitrary statements during runtime reconstruction would corrupt an already durable
    database, so the runtime records each exchange while leaving live state in its bound file.
    """
    return create_typed_component_adapter(
        storage,
        SqlStorage,
        binding=_RUNTIME_BINDING,
        failure_types=(SqlStorageError,),
    )
