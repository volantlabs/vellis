from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from threading import RLock

from components.storage.sql.protocol import (
    SqlExecutionFailed,
    SqlExecutionResult,
    SqlOperation,
    SqlParameterInvalid,
    SqlParameters,
    SqlQueryResult,
    SqlScalar,
    SqlStatementInvalid,
    SqlStoragePathInvalid,
    SqlStoragePermissionDenied,
    SqlStorageUnavailable,
    SqlTransactionFailed,
    SqlTransactionResult,
)


class SqliteStorage:
    """SQLite implementation of the generic SQL Storage component."""

    def __init__(self, database_path: str | PathLike[str]) -> None:
        self._path = self._validate_path(database_path)
        self._lock = RLock()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self._path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        except PermissionError as error:
            raise SqlStoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise SqlStorageUnavailable(str(error)) from error
        except sqlite3.Error as error:
            raise SqlStorageUnavailable(str(error)) from error

    @classmethod
    def open(cls, database_path: str | PathLike[str]) -> SqliteStorage:
        return cls(database_path)

    @property
    def database_path(self) -> Path:
        return self._path

    def execute(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> SqlExecutionResult:
        self._validate_statement(statement)
        normalized_parameters = _validate_parameters(parameters)
        with self._lock:
            try:
                cursor = self._connection.execute(statement, normalized_parameters)
                self._connection.commit()
                return SqlExecutionResult(
                    affected_row_count=cursor.rowcount,
                    last_inserted_row_id=cursor.lastrowid,
                )
            except sqlite3.ProgrammingError as error:
                raise SqlParameterInvalid(str(error)) from error
            except sqlite3.Error as error:
                self._connection.rollback()
                raise SqlExecutionFailed(str(error)) from error

    def query(
        self,
        statement: str,
        parameters: SqlParameters = (),
    ) -> SqlQueryResult:
        self._validate_statement(statement)
        normalized_parameters = _validate_parameters(parameters)
        try:
            with self._lock:
                cursor = self._connection.execute(statement, normalized_parameters)
                rows = tuple(_row_to_json_object(row) for row in cursor.fetchall())
            return SqlQueryResult(rows=rows)
        except sqlite3.ProgrammingError as error:
            raise SqlParameterInvalid(str(error)) from error
        except sqlite3.Error as error:
            raise SqlExecutionFailed(str(error)) from error

    def transaction(self, operations: tuple[SqlOperation, ...]) -> SqlTransactionResult:
        if not operations:
            return SqlTransactionResult(results=())

        results: list[SqlExecutionResult | SqlQueryResult] = []
        try:
            with self._lock:
                with self._connection:
                    for operation in operations:
                        self._validate_statement(operation.statement)
                        parameters = _validate_parameters(operation.parameters)
                        cursor = self._connection.execute(operation.statement, parameters)
                        if operation.returns_rows:
                            results.append(
                                SqlQueryResult(
                                    rows=tuple(
                                        _row_to_json_object(row) for row in cursor.fetchall()
                                    )
                                )
                            )
                        else:
                            results.append(
                                SqlExecutionResult(
                                    affected_row_count=cursor.rowcount,
                                    last_inserted_row_id=cursor.lastrowid,
                                )
                            )
        except sqlite3.ProgrammingError as error:
            raise SqlParameterInvalid(str(error)) from error
        except sqlite3.Error as error:
            raise SqlTransactionFailed(str(error)) from error

        return SqlTransactionResult(results=tuple(results))

    @staticmethod
    def _validate_path(database_path: str | PathLike[str]) -> Path:
        raw = Path(database_path)
        if str(database_path) == "":
            raise SqlStoragePathInvalid("database_path must not be empty")
        if raw.exists() and raw.is_dir():
            raise SqlStoragePathInvalid("database_path must not be a directory")
        return raw

    @staticmethod
    def _validate_statement(statement: str) -> None:
        if not isinstance(statement, str) or not statement.strip():
            raise SqlStatementInvalid("SQL statement must be a non-empty string")


def _validate_parameters(
    parameters: SqlParameters,
) -> Sequence[SqlScalar] | Mapping[str, SqlScalar]:
    if isinstance(parameters, tuple):
        for value in parameters:
            _validate_scalar(value)
        return parameters
    if isinstance(parameters, dict):
        for key, value in parameters.items():
            if not isinstance(key, str):
                raise SqlParameterInvalid("named parameter keys must be strings")
            _validate_scalar(value)
        return parameters
    raise SqlParameterInvalid("parameters must be a tuple or dict")


def _validate_scalar(value: SqlScalar) -> None:
    if value is not None and not isinstance(value, str | int | float | bool):
        raise SqlParameterInvalid(f"unsupported SQL parameter value: {value!r}")


def _row_to_json_object(row: sqlite3.Row) -> dict[str, SqlScalar]:
    result: dict[str, SqlScalar] = {}
    for key in row.keys():
        value = row[key]
        _validate_scalar(value)
        result[key] = value
    return result
