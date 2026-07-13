from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STORAGE_ROOT = Path(".data") / "rtg_knowledge_graph" / "json_file"
DEFAULT_SQL_DATABASE_PATH = Path(".data") / "rtg_knowledge_graph" / "controller.sqlite"
STORAGE_ROOT_ENV_VAR = "RTG_KNOWLEDGE_GRAPH_STORAGE_ROOT"
SQL_DATABASE_PATH_ENV_VAR = "RTG_KNOWLEDGE_GRAPH_SQL_DATABASE_PATH"


@dataclass(frozen=True, slots=True)
class RtgKnowledgeGraphConfig:
    storage_root: Path
    sql_database_path: Path
    install_starter_schema: bool = True
    automatic_recovery: bool = True

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> RtgKnowledgeGraphConfig:
        values = os.environ if env is None else env
        base_dir = Path.cwd() if cwd is None else cwd
        configured_root = Path(values.get(STORAGE_ROOT_ENV_VAR, os.fspath(DEFAULT_STORAGE_ROOT)))
        configured_sql = Path(
            values.get(SQL_DATABASE_PATH_ENV_VAR, os.fspath(DEFAULT_SQL_DATABASE_PATH))
        )

        if configured_root.is_absolute():
            storage_root = configured_root
        else:
            storage_root = base_dir / configured_root
        if configured_sql.is_absolute():
            sql_database_path = configured_sql
        else:
            sql_database_path = base_dir / configured_sql

        return cls(storage_root=storage_root, sql_database_path=sql_database_path)
