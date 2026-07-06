from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from components.storage.sql import (
    SqlExecutionFailed,
    SqliteStorage,
    SqlOperation,
    SqlQueryResult,
    SqlStoragePathInvalid,
    SqlTransactionFailed,
)
from components.storage.sql.reference import create_reference_component


def test_execute_query_and_reference_factory(tmp_path: Path) -> None:
    storage = create_reference_component(tmp_path / "store.sqlite")

    storage.execute("create table notes (id integer primary key, title text not null)")
    inserted = storage.execute("insert into notes (title) values (?)", ("first",))
    rows = storage.query("select id, title from notes")

    assert inserted.last_inserted_row_id == 1
    assert rows.rows == ({"id": 1, "title": "first"},)


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
