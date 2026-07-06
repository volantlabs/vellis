from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Protocol

type SqlScalar = str | int | float | bool | None
type SqlParameters = tuple[SqlScalar, ...] | dict[str, SqlScalar]
type SqlRow = dict[str, SqlScalar]


@dataclass(frozen=True, slots=True)
class SqlExecutionResult:
    affected_row_count: int
    last_inserted_row_id: int | None = None


@dataclass(frozen=True, slots=True)
class SqlQueryResult:
    rows: tuple[SqlRow, ...]


@dataclass(frozen=True, slots=True)
class SqlOperation:
    statement: str
    parameters: SqlParameters = ()
    returns_rows: bool = False


@dataclass(frozen=True, slots=True)
class SqlTransactionResult:
    results: tuple[SqlExecutionResult | SqlQueryResult, ...]


class SqlStorageError(Exception):
    """Base class for SQL Storage errors."""


class SqlStoragePathInvalid(SqlStorageError):
    """The configured database path is invalid."""


class SqlStorageUnavailable(SqlStorageError):
    """The configured database could not be opened."""


class SqlStoragePermissionDenied(SqlStorageError):
    """The filesystem or database denied the requested operation."""


class SqlStatementInvalid(SqlStorageError):
    """A SQL statement is structurally invalid for this operation."""


class SqlParameterInvalid(SqlStorageError):
    """SQL parameters are invalid or unsupported."""


class SqlExecutionFailed(SqlStorageError):
    """A SQL statement failed to execute."""


class SqlTransactionFailed(SqlStorageError):
    """A SQL transaction failed and was rolled back."""


class SqlStorage(Protocol):
    @classmethod
    def open(cls, database_path: str | PathLike[str]) -> SqlStorage:
        """Open a SQLite-backed SQL storage handle."""
        ...

    def execute(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> SqlExecutionResult:
        """Execute one non-row-returning SQL statement."""
        ...

    def query(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> SqlQueryResult:
        """Execute one row-returning SQL statement."""
        ...

    def transaction(self, operations: tuple[SqlOperation, ...]) -> SqlTransactionResult:
        """Execute ordered SQL operations in one transaction."""
        ...
