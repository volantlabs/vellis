from __future__ import annotations

from dataclasses import dataclass

from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.runner import RtgKnowledgeGraphRunner
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import InMemoryRtgSchema
from components.storage.json_file.implementation import LocalJsonFileStorage
from components.storage.sql import SqliteStorage


@dataclass(frozen=True, slots=True)
class RtgKnowledgeGraphComposition:
    config: RtgKnowledgeGraphConfig
    controller: InProcessRtgController
    runner: RtgKnowledgeGraphRunner


def build_app(config: RtgKnowledgeGraphConfig) -> RtgKnowledgeGraphComposition:
    document_storage = LocalJsonFileStorage.open(config.storage_root)
    sql_storage = SqliteStorage.open(config.sql_database_path)
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        InMemoryRtgSchema.empty(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        document_storage,
        sql_storage,
    )
    runner = RtgKnowledgeGraphRunner(
        document_storage=document_storage,
        controller=controller,
        storage_root=config.storage_root,
        sql_database_path=config.sql_database_path,
    )
    return RtgKnowledgeGraphComposition(config=config, controller=controller, runner=runner)
