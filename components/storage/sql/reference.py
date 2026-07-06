from __future__ import annotations

from os import PathLike

from components.storage.sql.implementation import SqliteStorage
from components.storage.sql.protocol import SqlStorage


def create_reference_component(database_path: str | PathLike[str]) -> SqlStorage:
    return SqliteStorage.open(database_path)
