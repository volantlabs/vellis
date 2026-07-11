from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import cast

from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import MCP_SERVER_NAME, mcp_launch_metadata
from components.rtg.controller import InProcessRtgController
from components.storage.json_file.protocol import JsonFileStorage, JsonValue

APP_NAME = "rtg_knowledge_graph"
APP_MANIFEST_PATH = "system/app_manifest.json"


@dataclass(frozen=True, slots=True)
class RtgKnowledgeGraphRunStatus:
    app_name: str
    storage_root: str
    sql_database_path: str
    manifest_path: str
    manifest_size_bytes: int
    json_document_count: int
    rtg_controller_ready: bool

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "app_name": self.app_name,
            "storage_root": self.storage_root,
            "sql_database_path": self.sql_database_path,
            "manifest_path": self.manifest_path,
            "manifest_size_bytes": self.manifest_size_bytes,
            "json_document_count": self.json_document_count,
            "rtg_controller_ready": self.rtg_controller_ready,
        }


class RtgKnowledgeGraphRunner:
    def __init__(
        self,
        document_storage: JsonFileStorage,
        controller: InProcessRtgController,
        storage_root: Path,
        sql_database_path: Path,
    ) -> None:
        self._document_storage = document_storage
        self._controller = controller
        self._storage_root = storage_root
        self._sql_database_path = sql_database_path

    def run(self) -> RtgKnowledgeGraphRunStatus:
        self._controller.export_system_snapshot()
        manifest = self._manifest_document()
        manifest_metadata = self._document_storage.write(APP_MANIFEST_PATH, manifest)
        documents = self._document_storage.list(".")

        return RtgKnowledgeGraphRunStatus(
            app_name=APP_NAME,
            storage_root=str(self._storage_root),
            sql_database_path=str(self._sql_database_path),
            manifest_path=manifest_metadata.relative_path,
            manifest_size_bytes=manifest_metadata.size_bytes,
            json_document_count=len(documents.documents),
            rtg_controller_ready=True,
        )

    def _manifest_document(self) -> dict[str, JsonValue]:
        mcp = mcp_launch_metadata(
            RtgKnowledgeGraphConfig(
                storage_root=self._storage_root,
                sql_database_path=self._sql_database_path,
            )
        )
        resource = files("apps.rtg_knowledge_graph.resources").joinpath("model_app_manifest.json")
        manifest = cast(dict[str, JsonValue], json.loads(resource.read_text(encoding="utf-8")))
        manifest["interfaces"] = [
            {
                "kind": "mcp",
                "server_name": MCP_SERVER_NAME,
                "transport": "stdio",
                "launch_mode": mcp["launch_mode"],
                "state_mode": mcp["state_mode"],
                "eval_prompt_path": mcp["eval_prompt_path"],
                "recommended_eval_prompt": mcp["recommended_eval_prompt"],
                "eval_prompts": mcp["eval_prompts"],
                "guides": mcp["guides"],
                "first_call": mcp["first_call"],
                "transports": mcp["transports"],
                "launch": mcp["launch"],
                "client_config": mcp["client_config"],
            }
        ]
        return manifest
