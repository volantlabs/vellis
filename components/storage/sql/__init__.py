"""SQLite-backed SQL Storage component."""

from components.storage.sql.implementation import SqliteStorage
from components.storage.sql.protocol import (
    SqlExecutionFailed,
    SqlExecutionResult,
    SqlOperation,
    SqlParameterInvalid,
    SqlParameters,
    SqlQueryResult,
    SqlScalar,
    SqlStatementInvalid,
    SqlStorage,
    SqlStorageError,
    SqlStoragePathInvalid,
    SqlStoragePermissionDenied,
    SqlStorageUnavailable,
    SqlTransactionFailed,
    SqlTransactionResult,
)
from components.storage.sql.runtime_binding import (
    SQL_STORAGE_ACTIONS,
    create_sql_storage_adapter,
)

__all__ = [
    "SqlExecutionFailed",
    "SqlExecutionResult",
    "SqliteStorage",
    "SqlOperation",
    "SqlParameterInvalid",
    "SqlParameters",
    "SqlQueryResult",
    "SqlScalar",
    "SqlStatementInvalid",
    "SqlStorage",
    "SQL_STORAGE_ACTIONS",
    "SqlStorageError",
    "SqlStoragePathInvalid",
    "SqlStoragePermissionDenied",
    "SqlStorageUnavailable",
    "SqlTransactionFailed",
    "SqlTransactionResult",
    "create_sql_storage_adapter",
]
