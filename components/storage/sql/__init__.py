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
    "SqlStorageError",
    "SqlStoragePathInvalid",
    "SqlStoragePermissionDenied",
    "SqlStorageUnavailable",
    "SqlTransactionFailed",
    "SqlTransactionResult",
]
