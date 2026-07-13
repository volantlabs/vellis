from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from components.storage.sql import (
    SqlExecutionFailed,
    SqlExecutionResult,
    SqliteStorage,
    SqlOperation,
    SqlQueryResult,
    SqlStoragePathInvalid,
    SqlTransactionFailed,
)
from components.storage.sql.reference import create_reference_component

MODEL_EVIDENCE = {
    "ExecuteSqlContractVerification": (
        "test_execute_query_and_reference_factory",
        "test_insert_identity_is_reported_only_for_actual_inserts",
        "test_failed_transaction_rolls_back",
        "test_storage_handle_serializes_access_from_worker_threads",
        "test_failed_execute_rolls_back_and_handle_remains_usable_from_worker_thread",
    ),
    "QuerySqlContractVerification": (
        "test_execute_query_and_reference_factory",
        "test_query_rejects_mutation_without_leaving_pending_state",
        "test_storage_handle_serializes_access_from_worker_threads",
    ),
    "ExecuteSqlTransactionContractVerification": (
        "test_transaction_commits_ordered_operations",
        "test_failed_transaction_rolls_back",
        "test_transaction_insert_identity_is_operation_specific",
    ),
    "OpenSqlStorageContractVerification": (
        "test_transaction_commits_ordered_operations",
        "test_failed_transaction_rolls_back",
        "test_storage_handle_serializes_access_from_worker_threads",
        "test_failed_execute_rolls_back_and_handle_remains_usable_from_worker_thread",
        "test_database_path_must_not_be_directory",
    ),
    "SqlStorageBoundaryVerification": (
        "test_execute_query_and_reference_factory",
        "test_query_rejects_mutation_without_leaving_pending_state",
        "test_insert_identity_is_reported_only_for_actual_inserts",
        "test_transaction_commits_ordered_operations",
        "test_failed_transaction_rolls_back",
        "test_storage_handle_serializes_access_from_worker_threads",
        "test_failed_execute_rolls_back_and_handle_remains_usable_from_worker_thread",
        "test_database_path_must_not_be_directory",
    ),
}


def test_execute_query_and_reference_factory(tmp_path: Path) -> None:
    storage = create_reference_component(tmp_path / "store.sqlite")

    storage.execute("create table notes (id integer primary key, title text not null)")
    inserted = storage.execute("insert into notes (title) values (?)", ("first",))
    rows = storage.query("select id, title from notes")

    assert inserted.last_inserted_row_id == 1
    assert rows.rows == ({"id": 1, "title": "first"},)


def test_query_rejects_mutation_without_leaving_pending_state(tmp_path: Path) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")
    storage.execute("create table notes (id integer primary key, title text not null)")

    with pytest.raises(SqlExecutionFailed):
        storage.query("insert into notes (title) values ('wrong') returning id")

    storage.execute("insert into notes (title) values ('right')")
    assert storage.query("select id, title from notes").rows == (
        {"id": 1, "title": "right"},
    )


def test_insert_identity_is_reported_only_for_actual_inserts(tmp_path: Path) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")

    created = storage.execute(
        "create table notes (id integer primary key, title text not null)"
    )
    inserted = storage.execute("insert into notes (title) values ('first')")
    updated = storage.execute("update notes set title = 'updated' where id = 1")

    assert created.last_inserted_row_id is None
    assert inserted.last_inserted_row_id == 1
    assert updated.last_inserted_row_id is None


def test_transaction_commits_ordered_operations(tmp_path: Path) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")
    result = storage.transaction(
        (
            SqlOperation("create table events (id integer primary key, name text)"),
            SqlOperation("insert into events (name) values (?)", ("created",)),
            SqlOperation("select name from events", returns_rows=True),
        )
    )

    assert isinstance(result.results[2], SqlQueryResult)
    assert result.results[2].rows == ({"name": "created"},)


def test_transaction_insert_identity_is_operation_specific(tmp_path: Path) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")
    result = storage.transaction(
        (
            SqlOperation("create table events (id integer primary key, name text)"),
            SqlOperation("insert into events (name) values ('created')"),
            SqlOperation("update events set name = 'updated' where id = 1"),
        )
    )

    assert isinstance(result.results[0], SqlExecutionResult)
    assert isinstance(result.results[1], SqlExecutionResult)
    assert isinstance(result.results[2], SqlExecutionResult)
    assert result.results[0].last_inserted_row_id is None
    assert result.results[1].last_inserted_row_id == 1
    assert result.results[2].last_inserted_row_id is None


def test_failed_transaction_rolls_back(tmp_path: Path) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")
    storage.execute("create table events (id integer primary key, name text unique)")

    with pytest.raises(SqlTransactionFailed):
        storage.transaction(
            (
                SqlOperation("insert into events (name) values (?)", ("same",)),
                SqlOperation("insert into events (name) values (?)", ("same",)),
            )
        )

    assert storage.query("select name from events").rows == ()


def test_storage_handle_serializes_access_from_worker_threads(tmp_path: Path) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")
    storage.execute("create table notes (id integer primary key, title text not null)")

    def insert_from_worker() -> int | None:
        return storage.execute(
            "insert into notes (title) values (?)", ("worker",)
        ).last_inserted_row_id

    with ThreadPoolExecutor(max_workers=1) as executor:
        inserted_id = executor.submit(insert_from_worker).result()

    assert inserted_id == 1
    assert storage.query("select title from notes").rows == ({"title": "worker"},)


def test_failed_execute_rolls_back_and_handle_remains_usable_from_worker_thread(
    tmp_path: Path,
) -> None:
    storage = SqliteStorage.open(tmp_path / "store.sqlite")
    storage.execute("create table notes (id integer primary key, title text unique)")
    storage.execute("insert into notes (title) values (?)", ("same",))

    def duplicate_from_worker() -> None:
        with pytest.raises(SqlExecutionFailed):
            storage.execute("insert into notes (title) values (?)", ("same",))

    def insert_after_failure_from_worker() -> int | None:
        return storage.execute(
            "insert into notes (title) values (?)", ("after failure",)
        ).last_inserted_row_id

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(duplicate_from_worker).result()
        inserted_id = executor.submit(insert_after_failure_from_worker).result()

    assert inserted_id == 2
    assert storage.query("select title from notes order by id").rows == (
        {"title": "same"},
        {"title": "after failure"},
    )


def test_database_path_must_not_be_directory(tmp_path: Path) -> None:
    with pytest.raises(SqlStoragePathInvalid):
        SqliteStorage.open(tmp_path)
