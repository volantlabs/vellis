from __future__ import annotations

from pathlib import Path

from components.rtg.change_validation import (
    RTG_CHANGE_VALIDATION_ACTIONS,
    DeterministicRtgChangeValidator,
    create_rtg_change_validator_adapter,
)
from components.rtg.constraints import (
    RTG_CONSTRAINTS_ACTIONS,
    InMemoryRtgConstraints,
    create_rtg_constraints_adapter,
)
from components.rtg.controller import (
    RTG_CONTROLLER_ACTIONS,
    RtgControllerCoordinator,
    create_rtg_controller_adapter,
)
from components.rtg.graph import (
    RTG_GRAPH_ACTIONS,
    InMemoryRtgGraph,
    create_rtg_graph_adapter,
)
from components.rtg.migration import (
    RTG_MIGRATION_ACTIONS,
    InMemoryRtgMigration,
    create_rtg_migration_adapter,
)
from components.rtg.query import (
    RTG_QUERY_ACTIONS,
    SimpleRtgQueryEngine,
    create_rtg_query_adapter,
)
from components.rtg.schema import (
    RTG_SCHEMA_ACTIONS,
    InMemoryRtgSchema,
    create_rtg_schema_adapter,
)
from components.runtime.component_adapter import ComponentAdapter
from components.storage.json_file import (
    JSON_FILE_STORAGE_ACTIONS,
    LocalJsonFileStorage,
    create_json_file_storage_adapter,
)
from components.storage.sql import SQL_STORAGE_ACTIONS, SqliteStorage, create_sql_storage_adapter


def test_every_reusable_participation_kit_uses_one_adapter_and_exact_catalog(
    tmp_path: Path,
) -> None:
    cases = (
        (create_rtg_graph_adapter(InMemoryRtgGraph.empty()), RTG_GRAPH_ACTIONS),
        (create_rtg_schema_adapter(InMemoryRtgSchema.empty()), RTG_SCHEMA_ACTIONS),
        (
            create_rtg_constraints_adapter(InMemoryRtgConstraints.empty()),
            RTG_CONSTRAINTS_ACTIONS,
        ),
        (
            create_rtg_migration_adapter(InMemoryRtgMigration.empty()),
            RTG_MIGRATION_ACTIONS,
        ),
        (create_rtg_query_adapter(SimpleRtgQueryEngine()), RTG_QUERY_ACTIONS),
        (
            create_rtg_change_validator_adapter(DeterministicRtgChangeValidator()),
            RTG_CHANGE_VALIDATION_ACTIONS,
        ),
        (
            create_json_file_storage_adapter(LocalJsonFileStorage.open(tmp_path / "json")),
            JSON_FILE_STORAGE_ACTIONS,
        ),
        (
            create_sql_storage_adapter(SqliteStorage.open(tmp_path / "records.sqlite")),
            SQL_STORAGE_ACTIONS,
        ),
        (
            create_rtg_controller_adapter(RtgControllerCoordinator()),
            RTG_CONTROLLER_ACTIONS,
        ),
    )
    for adapter, catalog in cases:
        assert type(adapter) is ComponentAdapter
        descriptors = {item.action_id: item for item in adapter.describe().actions}
        assert set(descriptors) == {item.action_id for item in catalog.values()}
        for action in catalog.values():
            descriptor = descriptors[action.action_id]
            assert descriptor.component_contract_id == action.component_contract_id
            assert descriptor.schema_version == action.schema_version
            assert descriptor.request_codec_id == action.request_codec_id
            assert descriptor.concurrency_lane
            assert descriptor.failure_codec_id


def test_packages_export_catalogs_and_adapters_but_no_proxy_factories() -> None:
    import components.rtg.change_validation as validation
    import components.rtg.constraints as constraints
    import components.rtg.controller as controller
    import components.rtg.graph as graph
    import components.rtg.migration as migration
    import components.rtg.query as query
    import components.rtg.schema as schema
    import components.storage.json_file as json_file
    import components.storage.sql as sql

    for package in (
        validation,
        constraints,
        controller,
        graph,
        migration,
        query,
        schema,
        json_file,
        sql,
    ):
        assert not any(name.endswith("_proxy") for name in package.__all__)
        assert not any(
            name.startswith("create_") and name.endswith("_proxy") for name in dir(package)
        )
