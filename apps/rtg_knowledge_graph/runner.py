from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import cast

from apps.rtg_knowledge_graph.application_binding import load_application_binding
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import MCP_SERVER_NAME, mcp_launch_metadata
from components.rtg.controller import RTG_CONTROLLER_ACTIONS
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentExecution,
    decode_typed,
    encode_json,
)
from components.storage.json_file import (
    JSON_FILE_STORAGE_ACTIONS,
    JsonDocumentList,
    JsonDocumentMetadata,
    JsonValue,
)

APP_NAME = "rtg_knowledge_graph"
APP_MANIFEST_PATH = "system/app_manifest.json"
_RUNNER_CONTRACT = "application.vellis.runner"
_RUNNER_DESCRIPTORS = load_application_binding(_RUNNER_CONTRACT)
RUNNER_ACTIONS = {
    name: descriptor.action_ref() for name, descriptor in _RUNNER_DESCRIPTORS.items()
}


@dataclass(frozen=True, slots=True)
class RtgKnowledgeGraphRunStatus:
    app_name: str
    storage_root: str
    runtime_database_path: str
    manifest_path: str
    manifest_size_bytes: int | None
    json_document_count: int | None
    rtg_controller_ready: bool

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "app_name": self.app_name,
            "storage_root": self.storage_root,
            "runtime_database_path": self.runtime_database_path,
            "manifest_path": self.manifest_path,
            "manifest_size_bytes": self.manifest_size_bytes,
            "json_document_count": self.json_document_count,
            "rtg_controller_ready": self.rtg_controller_ready,
        }


class RtgKnowledgeGraphRunner:
    def __init__(
        self,
        storage_root: Path,
        runtime_database_path: Path,
        install_starter_schema: bool = True,
        automatic_recovery: bool = True,
        *,
        controller_key: str = "vellis.controller.primary",
        json_storage_key: str = "vellis.storage.json.primary",
    ) -> None:
        self._storage_root = storage_root
        self._runtime_database_path = runtime_database_path
        self._install_starter_schema = install_starter_schema
        self._automatic_recovery = automatic_recovery
        self._controller_key = controller_key
        self._json_storage_key = json_storage_key

    def create_adapter(self) -> ComponentAdapter:
        async def run(
            _args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            result = await self._run(execution)
            await execution.complete(result)

        return ComponentAdapter(
            (
                ActionBinding(
                    descriptor=_RUNNER_DESCRIPTORS["run"],
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                    handler=run,
                ),
            )
        )

    async def _run(self, execution: ComponentExecution) -> RtgKnowledgeGraphRunStatus:
        await execution.call(
            "controller-ready",
            RTG_CONTROLLER_ACTIONS["get_system_state"],
            {},
            target=execution.address_for(self._controller_key),
        )
        metadata_value = await execution.call(
            "write-manifest",
            JSON_FILE_STORAGE_ACTIONS["write"],
            {
                "relative_path": APP_MANIFEST_PATH,
                "json_value": self._manifest_document(),
            },
            target=execution.address_for(self._json_storage_key),
        )
        documents_value = await execution.call(
            "list-documents",
            JSON_FILE_STORAGE_ACTIONS["list"],
            {"relative_directory_path": "."},
            target=execution.address_for(self._json_storage_key),
        )
        manifest_metadata = decode_typed(metadata_value, JsonDocumentMetadata)
        documents = decode_typed(documents_value, JsonDocumentList)

        return RtgKnowledgeGraphRunStatus(
            app_name=APP_NAME,
            storage_root=str(self._storage_root),
            runtime_database_path=str(self._runtime_database_path),
            manifest_path=manifest_metadata.relative_path,
            manifest_size_bytes=manifest_metadata.size_bytes,
            json_document_count=len(documents.documents),
            rtg_controller_ready=True,
        )

    def _manifest_document(self) -> dict[str, JsonValue]:
        mcp = mcp_launch_metadata(
            RtgKnowledgeGraphConfig(
                storage_root=self._storage_root,
                runtime_database_path=self._runtime_database_path,
                install_starter_schema=self._install_starter_schema,
                automatic_recovery=self._automatic_recovery,
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
