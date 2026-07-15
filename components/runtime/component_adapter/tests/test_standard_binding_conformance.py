from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeReference,
    RtgGraphAnchorWrite,
    RtgGraphChangeSet,
    RtgValidationOptions,
)
from components.rtg.change_validation.runtime_binding import (
    create_rtg_change_validator_adapter,
    create_rtg_change_validator_proxy,
)
from components.rtg.constraints import (
    InMemoryRtgConstraints,
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
    RtgConstraintSnapshot,
)
from components.rtg.constraints.runtime_binding import (
    create_rtg_constraints_adapter,
    create_rtg_constraints_proxy,
)
from components.rtg.controller import (
    InProcessRtgController,
    RtgController,
    RtgControllerCutoverOptions,
    RtgControllerError,
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
    RtgControllerValidationFailed,
    RtgControllerValidationOptions,
)
from components.rtg.controller.runtime_binding import (
    create_rtg_controller_adapter,
    create_rtg_controller_proxy,
)
from components.rtg.graph import InMemoryRtgGraph, RtgAnchor, RtgGraphSnapshot
from components.rtg.graph.runtime_binding import (
    create_rtg_graph_adapter,
    create_rtg_graph_proxy,
)
from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationNotFound,
    RtgMigrationRecord,
    RtgMigrationSnapshot,
)
from components.rtg.migration.runtime_binding import (
    create_rtg_migration_adapter,
    create_rtg_migration_proxy,
)
from components.rtg.query import (
    RtgQueryAnchorBucket,
    RtgQueryError,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    SimpleRtgQueryEngine,
)
from components.rtg.query.runtime_binding import (
    create_rtg_query_adapter,
    create_rtg_query_proxy,
)
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaSnapshot,
)
from components.rtg.schema.runtime_binding import (
    create_rtg_schema_adapter,
    create_rtg_schema_proxy,
)
from components.runtime.component_adapter import (
    ComponentRuntimeAdapter,
    RuntimeBindingInvalid,
)
from components.runtime.message_runtime import (
    MessageRuntime,
    RuntimeAddress,
    RuntimeExternalBoundaryDisposition,
    RuntimeExternalBoundaryMode,
    RuntimeHistoryQuery,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimePayload,
    RuntimeReconstructionRequest,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
    SqliteMessageRuntime,
)
from components.storage.json_file import LocalJsonFileStorage
from components.storage.json_file.runtime_binding import (
    create_json_file_storage_adapter,
    create_json_file_storage_proxy,
)
from components.storage.sql import SqliteStorage
from components.storage.sql.runtime_binding import (
    create_sql_storage_adapter,
    create_sql_storage_proxy,
)


@dataclass(frozen=True, slots=True)
class _BindingCase:
    name: str
    contract_id: str
    actions: tuple[str, ...]
    factory: Callable[[Path], ComponentRuntimeAdapter]


def _schema_adapter(_root: Path) -> ComponentRuntimeAdapter:
    return create_rtg_schema_adapter(InMemoryRtgSchema.empty())


def _graph_adapter(_root: Path) -> ComponentRuntimeAdapter:
    return create_rtg_graph_adapter(InMemoryRtgGraph.empty())


def _constraints_adapter(_root: Path) -> ComponentRuntimeAdapter:
    return create_rtg_constraints_adapter(InMemoryRtgConstraints.empty())


def _migration_adapter(_root: Path) -> ComponentRuntimeAdapter:
    return create_rtg_migration_adapter(InMemoryRtgMigration.empty())


def _query_adapter(_root: Path) -> ComponentRuntimeAdapter:
    return create_rtg_query_adapter(SimpleRtgQueryEngine())


def _change_validation_adapter(_root: Path) -> ComponentRuntimeAdapter:
    query = SimpleRtgQueryEngine()
    return create_rtg_change_validator_adapter(
        DeterministicRtgChangeValidator(),
        query=query,
    )


def _json_adapter(root: Path) -> ComponentRuntimeAdapter:
    return create_json_file_storage_adapter(LocalJsonFileStorage.open(root / "json"))


def _sql_adapter(root: Path) -> ComponentRuntimeAdapter:
    return create_sql_storage_adapter(SqliteStorage.open(root / "storage.sqlite"))


def _controller_adapter(root: Path) -> ComponentRuntimeAdapter:
    return create_rtg_controller_adapter(_build_controller(root / "controller"))


_MODEL_SOURCES = {
    "component.rtg.graph": "model/bibliotek/components/component.rtg.graph.sysml",
    "component.rtg.schema": "model/bibliotek/components/component.rtg.schema.sysml",
    "component.rtg.constraints": "model/bibliotek/components/component.rtg.constraints.sysml",
    "component.rtg.migration": "model/bibliotek/components/component.rtg.migration.sysml",
    "component.rtg.query": "model/bibliotek/components/component.rtg.query.sysml",
    "component.rtg.change_validation": (
        "model/bibliotek/components/component.rtg.change_validation.sysml"
    ),
    "component.storage.json_file": ("model/bibliotek/components/component.storage.json_file.sysml"),
    "component.storage.sql": "model/bibliotek/components/component.storage.sql.sysml",
    "component.rtg.controller": "model/bibliotek/components/component.rtg.controller.sysml",
}


_BINDING_CASES = (
    _BindingCase(
        "graph",
        "component.rtg.graph",
        (
            "export_snapshot",
            "replace_snapshot",
            "put_anchor",
            "put_data_object",
            "put_link",
            "associate_data",
            "dissociate_data",
            "delete_anchor",
            "delete_data_object",
            "delete_link",
            "preview_delete_anchor",
            "preview_delete_data_object",
            "preview_dissociate_data",
            "get_object",
            "list_by_type",
            "list_anchor_data",
            "list_data_anchors",
            "list_incident_links",
            "count_by_type",
        ),
        _graph_adapter,
    ),
    _BindingCase(
        "schema",
        "component.rtg.schema",
        (
            "export_snapshot",
            "replace_snapshot",
            "put_definition",
            "get_definition",
            "list_definitions",
            "list_definitions_by_type_key",
            "list_anchor_data_type_keys",
            "list_link_participation",
            "list_anchor_type_summaries",
            "get_schema_pack",
            "delete_definition",
        ),
        _schema_adapter,
    ),
    _BindingCase(
        "constraints",
        "component.rtg.constraints",
        (
            "export_snapshot",
            "replace_snapshot",
            "put_constraint",
            "get_constraint",
            "list_constraints",
            "list_constraints_by_target",
            "delete_constraint",
        ),
        _constraints_adapter,
    ),
    _BindingCase(
        "migration",
        "component.rtg.migration",
        (
            "export_snapshot",
            "replace_snapshot",
            "put_migration",
            "get_migration",
            "list_migrations",
            "set_status",
            "add_evidence",
            "delete_migration",
        ),
        _migration_adapter,
    ),
    _BindingCase("query", "component.rtg.query", ("execute",), _query_adapter),
    _BindingCase(
        "change_validation",
        "component.rtg.change_validation",
        ("validate_batch", "validate_graph_state"),
        _change_validation_adapter,
    ),
    _BindingCase(
        "json_file",
        "component.storage.json_file",
        ("write", "read", "delete", "list"),
        _json_adapter,
    ),
    _BindingCase(
        "sql",
        "component.storage.sql",
        ("execute", "query", "transaction"),
        _sql_adapter,
    ),
    _BindingCase(
        "controller",
        "component.rtg.controller",
        (
            "apply_live_graph_changes",
            "validate_live_graph_changes",
            "stage_knowledge_changes",
            "apply_migration_cutover",
            "execute_query",
            "get_object",
            "list_migrations",
            "get_migration",
            "validate_graph",
            "discover_anchor_types",
            "get_schema_pack",
            "get_system_state",
            "export_system_snapshot",
            "persist_system_snapshot",
            "list_persisted_snapshots",
            "load_persisted_snapshot",
            "abandon_migration",
            "restore_from_snapshot",
        ),
        _controller_adapter,
    ),
)


@pytest.mark.parametrize("case", _BINDING_CASES, ids=lambda case: case.name)
def test_standard_binding_inventory_is_explicit_and_private_methods_are_not_routable(
    tmp_path: Path,
    case: _BindingCase,
) -> None:
    adapter = case.factory(tmp_path / case.name)
    description = adapter.describe()
    expected_actions = tuple(f"{case.contract_id}.{name}" for name in case.actions)

    assert tuple(action.action_id for action in description.actions) == expected_actions
    assert all(action.component_contract_id == case.contract_id for action in description.actions)
    assert all(action.binding_id == description.binding_id for action in description.actions)
    assert all(
        action.binding_version == description.binding_version == 1 for action in description.actions
    )
    assert all(action.schema_version == 1 for action in description.actions)
    assert all(action.request_codec_version == 1 for action in description.actions)
    assert all(action.result_codec_version == 1 for action in description.actions)
    assert all(action.failure_codec_version == 1 for action in description.actions)
    assert all(
        tuple(failure.failure_name for failure in action.failure_bindings)
        == action.supported_failure_names
        for action in description.actions
    )
    assert all(
        len({argument.name for argument in action.request_arguments})
        == len(action.request_arguments)
        for action in description.actions
    )

    first = description.actions[0]
    address = RuntimeAddress(runtime_id=uuid4(), instance_id=uuid4())
    private_request = RuntimeMessageEnvelope(
        message_id=uuid4(),
        kind=RuntimeMessageKind.REQUEST,
        source=address,
        target=address,
        component_contract_id=case.contract_id,
        action_id=f"{case.contract_id}._private",
        schema_version=first.schema_version,
        trace_id=uuid4(),
        created_at="2026-07-14T00:00:00+00:00",
        payload=RuntimePayload(
            codec_id=first.request_codec_id,
            codec_version=first.request_codec_version,
            content_type=first.request_content_type,
            value={},
        ),
    )
    with pytest.raises(RuntimeBindingInvalid, match="unregistered action"):
        asyncio.run(adapter.dispatch(private_request))


@pytest.mark.parametrize("case", _BINDING_CASES, ids=lambda case: case.name)
def test_standard_binding_failures_match_accepted_model_contracts(
    tmp_path: Path,
    case: _BindingCase,
) -> None:
    model_path = Path(__file__).parents[4] / _MODEL_SOURCES[case.contract_id]
    modeled_failures = _modeled_action_failures(model_path)
    actions = {
        action.action_id.rsplit(".", 1)[-1]: action
        for action in case.factory(tmp_path / case.name).describe().actions
    }

    assert tuple(actions) == case.actions
    assert set(modeled_failures) >= set(case.actions)
    for action_name in case.actions:
        assert actions[action_name].supported_failure_names == modeled_failures[action_name]


def _modeled_action_failures(model_path: Path) -> dict[str, tuple[str, ...]]:
    text = model_path.read_text(encoding="utf-8")
    action_types = {
        _camel_to_snake(feature): action_type
        for feature, action_type in re.findall(
            r"\bperform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", text
        )
    }
    result: dict[str, tuple[str, ...]] = {}
    for feature, action_type in action_types.items():
        definition = re.search(
            rf"\baction def\s+(?:<'[^']+'>\s+)?{re.escape(action_type)}\s*\{{"
            r"(?P<body>.*?)@FailureContract\s*\{(?P<contract>.*?)\}",
            text,
            flags=re.DOTALL,
        )
        if definition is None:
            raise AssertionError(f"{model_path}: {action_type} has no FailureContract")
        error_ids = re.search(
            r"\berrorIds\s*=\s*\((?P<values>.*?)\)",
            definition.group("contract"),
            flags=re.DOTALL,
        )
        if error_ids is None:
            raise AssertionError(f"{model_path}: {action_type} has no errorIds")
        result[feature] = tuple(re.findall(r'"([^"]+)"', error_ids.group("values")))
    return result


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def test_hand_authored_bindings_declare_exact_request_arguments_and_defaults(
    tmp_path: Path,
) -> None:
    query = _query_adapter(tmp_path).describe().actions[0]
    validation = _change_validation_adapter(tmp_path).describe().actions

    assert tuple((item.name, item.required, item.default) for item in query.request_arguments) == (
        ("graph_snapshot", True, None),
        ("query_spec", True, None),
        ("query_options", False, None),
    )
    assert tuple(
        (item.name, item.required, item.default) for item in validation[0].request_arguments
    ) == (
        ("graph_snapshot", True, None),
        ("schema_snapshot", True, None),
        ("constraint_snapshot", True, None),
        ("migration_snapshot", True, None),
        ("change_batch", True, None),
        ("validation_options", False, None),
    )
    assert tuple(
        (item.name, item.required, item.default) for item in validation[1].request_arguments
    ) == (
        ("graph_snapshot", True, None),
        ("schema_snapshot", True, None),
        ("constraint_snapshot", True, None),
        ("migration_snapshot", True, None),
        ("migration_ids", False, None),
        ("validation_options", False, None),
    )


def test_schema_binding_preserves_results_defaults_failures_and_state(tmp_path: Path) -> None:
    direct = InMemoryRtgSchema.empty()
    mediated = InMemoryRtgSchema.empty()
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "schema",
        "component.rtg.schema",
        create_rtg_schema_adapter(mediated),
        create_rtg_schema_proxy,
    )
    definition = _person_definition()
    try:
        assert proxy.put_definition(definition) == direct.put_definition(definition)
        assert proxy.list_definitions() == direct.list_definitions()
        _assert_same_failure(
            lambda: direct.get_definition(UUID(int=999)),
            lambda: proxy.get_definition(UUID(int=999)),
        )
        assert mediated.export_snapshot() == direct.export_snapshot()
    finally:
        runtime.close()


def test_constraints_binding_preserves_typed_query_results_and_state(tmp_path: Path) -> None:
    direct = InMemoryRtgConstraints.empty()
    mediated = InMemoryRtgConstraints.empty()
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "constraints",
        "component.rtg.constraints",
        create_rtg_constraints_adapter(mediated),
        create_rtg_constraints_proxy,
    )
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
    constraint = RtgConstraintDefinition(
        uuid=UUID(int=2),
        kind="cardinality",
        target_type_keys=("Person",),
        display_name="At least one person",
        description="A person is required.",
        payload=RtgConstraintCardinalityPayload(
            query_spec=query_spec,
            counted_binding="person",
            minimum=1,
        ),
    )
    try:
        assert proxy.put_constraint(constraint) == direct.put_constraint(constraint)
        stored = proxy.list_constraints()
        assert stored == direct.list_constraints()
        assert stored.constraints[0].payload.query_spec == query_spec
        _assert_same_failure(
            lambda: direct.get_constraint(UUID(int=999)),
            lambda: proxy.get_constraint(UUID(int=999)),
        )
        assert mediated.export_snapshot() == direct.export_snapshot()
    finally:
        runtime.close()


def test_migration_binding_preserves_defaults_failures_and_no_effect_on_rejection(
    tmp_path: Path,
) -> None:
    direct = InMemoryRtgMigration.empty()
    mediated = InMemoryRtgMigration.empty()
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "migration",
        "component.rtg.migration",
        create_rtg_migration_adapter(mediated),
        create_rtg_migration_proxy,
    )
    record = RtgMigrationRecord(migration_id="m1", description="Migration one")
    try:
        assert proxy.put_migration(record) == direct.put_migration(record)
        assert proxy.list_migrations() == direct.list_migrations()
        direct_before = direct.export_snapshot()
        mediated_before = mediated.export_snapshot()
        _assert_same_failure(
            lambda: direct.delete_migration("m1"),
            lambda: proxy.delete_migration("m1"),
        )
        assert direct.export_snapshot() == direct_before
        assert mediated.export_snapshot() == mediated_before
        assert proxy.set_status("m1", "ready") == direct.set_status("m1", "ready")
        assert mediated.export_snapshot() == direct.export_snapshot()
    finally:
        runtime.close()


def test_snapshot_replacement_bindings_preserve_atomic_idempotent_state_and_failures(
    tmp_path: Path,
) -> None:
    graph_direct = InMemoryRtgGraph.empty()
    graph_mediated = InMemoryRtgGraph.empty()
    graph_runtime, graph_proxy = _runtime_proxy(
        tmp_path,
        "graph-replace",
        "component.rtg.graph",
        create_rtg_graph_adapter(graph_mediated),
        create_rtg_graph_proxy,
    )
    graph_source = InMemoryRtgGraph.empty()
    graph_source.put_anchor(RtgAnchor(UUID(int=801), "Person"))

    schema_direct = InMemoryRtgSchema.empty()
    schema_mediated = InMemoryRtgSchema.empty()
    schema_runtime, schema_proxy = _runtime_proxy(
        tmp_path,
        "schema-replace",
        "component.rtg.schema",
        create_rtg_schema_adapter(schema_mediated),
        create_rtg_schema_proxy,
    )
    schema_source = InMemoryRtgSchema.empty()
    schema_source.put_definition(_person_definition())

    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
    constraint_record = RtgConstraintDefinition(
        uuid=UUID(int=802),
        kind="cardinality",
        target_type_keys=("Person",),
        display_name="Person required",
        description="At least one person.",
        payload=RtgConstraintCardinalityPayload(
            query_spec=query_spec,
            counted_binding="person",
            minimum=1,
        ),
    )
    constraints_direct = InMemoryRtgConstraints.empty()
    constraints_mediated = InMemoryRtgConstraints.empty()
    constraints_runtime, constraints_proxy = _runtime_proxy(
        tmp_path,
        "constraints-replace",
        "component.rtg.constraints",
        create_rtg_constraints_adapter(constraints_mediated),
        create_rtg_constraints_proxy,
    )
    constraints_source = InMemoryRtgConstraints.empty()
    constraints_source.put_constraint(constraint_record)

    migration_direct = InMemoryRtgMigration.empty()
    migration_mediated = InMemoryRtgMigration.empty()
    migration_runtime, migration_proxy = _runtime_proxy(
        tmp_path,
        "migration-replace",
        "component.rtg.migration",
        create_rtg_migration_adapter(migration_mediated),
        create_rtg_migration_proxy,
    )
    migration_source = InMemoryRtgMigration.empty()
    migration_source.put_migration(
        RtgMigrationRecord(migration_id="replacement", description="Replacement")
    )

    try:
        graph_snapshot = graph_source.export_snapshot()
        graph_direct.replace_snapshot(graph_snapshot)
        graph_proxy.replace_snapshot(graph_snapshot)
        graph_proxy.replace_snapshot(graph_snapshot)
        assert graph_mediated.export_snapshot() == graph_direct.export_snapshot()
        malformed_graph = RtgGraphSnapshot(
            anchors=graph_snapshot.anchors,
            data_objects=(),
            links=(),
            anchor_data_index={str(UUID(int=999)): (str(UUID(int=998)),)},
        )
        _assert_same_failure(
            lambda: graph_direct.replace_snapshot(malformed_graph),
            lambda: graph_proxy.replace_snapshot(malformed_graph),
        )
        assert graph_mediated.export_snapshot() == graph_direct.export_snapshot()

        schema_snapshot = schema_source.export_snapshot()
        schema_direct.replace_snapshot(schema_snapshot)
        schema_proxy.replace_snapshot(schema_snapshot)
        schema_proxy.replace_snapshot(schema_snapshot)
        assert schema_mediated.export_snapshot() == schema_direct.export_snapshot()
        malformed_schema = RtgSchemaSnapshot(
            definitions=(schema_snapshot.definitions[0], schema_snapshot.definitions[0])
        )
        _assert_same_failure(
            lambda: schema_direct.replace_snapshot(malformed_schema),
            lambda: schema_proxy.replace_snapshot(malformed_schema),
        )
        assert schema_mediated.export_snapshot() == schema_direct.export_snapshot()

        constraint_snapshot = constraints_source.export_snapshot()
        constraints_direct.replace_snapshot(constraint_snapshot)
        constraints_proxy.replace_snapshot(constraint_snapshot)
        constraints_proxy.replace_snapshot(constraint_snapshot)
        assert constraints_mediated.export_snapshot() == constraints_direct.export_snapshot()
        malformed_constraints = RtgConstraintSnapshot(
            constraints=(
                constraint_snapshot.constraints[0],
                constraint_snapshot.constraints[0],
            )
        )
        _assert_same_failure(
            lambda: constraints_direct.replace_snapshot(malformed_constraints),
            lambda: constraints_proxy.replace_snapshot(malformed_constraints),
        )
        assert constraints_mediated.export_snapshot() == constraints_direct.export_snapshot()

        migration_snapshot = migration_source.export_snapshot()
        migration_direct.replace_snapshot(migration_snapshot)
        migration_proxy.replace_snapshot(migration_snapshot)
        migration_proxy.replace_snapshot(migration_snapshot)
        assert migration_mediated.export_snapshot() == migration_direct.export_snapshot()
        malformed_migration = RtgMigrationSnapshot(
            migrations=(migration_snapshot.migrations[0], migration_snapshot.migrations[0])
        )
        _assert_same_failure(
            lambda: migration_direct.replace_snapshot(malformed_migration),
            lambda: migration_proxy.replace_snapshot(malformed_migration),
        )
        assert migration_mediated.export_snapshot() == migration_direct.export_snapshot()
    finally:
        graph_runtime.close()
        schema_runtime.close()
        constraints_runtime.close()
        migration_runtime.close()


def test_query_binding_preserves_defaults_results_diagnostics_and_read_only_state(
    tmp_path: Path,
) -> None:
    engine = SimpleRtgQueryEngine()
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "query",
        "component.rtg.query",
        create_rtg_query_adapter(engine),
        create_rtg_query_proxy,
    )
    graph = InMemoryRtgGraph.empty()
    graph.put_anchor(RtgAnchor(UUID(int=3), "Person"))
    baseline = graph.export_snapshot()
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
    invalid_spec = RtgQuerySpec(anchor_buckets=())
    try:
        assert proxy.execute(graph, query_spec) == engine.execute(graph, query_spec)
        direct_error, proxy_error = _assert_same_failure(
            lambda: engine.execute(graph, invalid_spec),
            lambda: proxy.execute(graph, invalid_spec),
        )
        assert isinstance(direct_error, RtgQueryError)
        assert isinstance(proxy_error, RtgQueryError)
        assert proxy_error.diagnostic == direct_error.diagnostic
        assert graph.export_snapshot() == baseline
    finally:
        runtime.close()


def test_change_validation_binding_preserves_defaults_failures_and_read_only_state(
    tmp_path: Path,
) -> None:
    validator = DeterministicRtgChangeValidator()
    query = SimpleRtgQueryEngine()
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "change-validation",
        "component.rtg.change_validation",
        create_rtg_change_validator_adapter(validator, query=query),
        create_rtg_change_validator_proxy,
    )
    graph = InMemoryRtgGraph.empty()
    schema = InMemoryRtgSchema.empty()
    constraints = InMemoryRtgConstraints.empty()
    migration = InMemoryRtgMigration.empty()
    baselines = (
        graph.export_snapshot(),
        schema.export_snapshot(),
        constraints.export_snapshot(),
        migration.export_snapshot(),
    )
    try:
        assert proxy.validate_graph_state(
            graph, schema, constraints, migration, query
        ) == validator.validate_graph_state(graph, schema, constraints, migration, query)
        invalid_options = RtgValidationOptions(finding_limit=0)
        _assert_same_failure(
            lambda: validator.validate_graph_state(
                graph,
                schema,
                constraints,
                migration,
                query,
                validation_options=invalid_options,
            ),
            lambda: proxy.validate_graph_state(
                graph,
                schema,
                constraints,
                migration,
                query,
                validation_options=invalid_options,
            ),
        )
        assert baselines == (
            graph.export_snapshot(),
            schema.export_snapshot(),
            constraints.export_snapshot(),
            migration.export_snapshot(),
        )
    finally:
        runtime.close()


def test_json_storage_binding_preserves_results_defaults_failures_and_effects(
    tmp_path: Path,
) -> None:
    storage = LocalJsonFileStorage.open(tmp_path / "documents")
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "json",
        "component.storage.json_file",
        create_json_file_storage_adapter(storage),
        create_json_file_storage_proxy,
    )
    try:
        written = proxy.write("notes/one.json", {"title": "one", "tags": ["test"]})
        assert written == storage.read("notes/one.json").metadata
        assert proxy.read("notes/one.json") == storage.read("notes/one.json")
        assert proxy.list() == storage.list()
        _assert_same_failure(
            lambda: storage.read("missing.json"),
            lambda: proxy.read("missing.json"),
        )
        assert proxy.delete("notes/one.json") == written
        assert storage.list().documents == ()
    finally:
        runtime.close()


def test_json_storage_binding_marks_all_filesystem_traffic_as_external_exchange(
    tmp_path: Path,
) -> None:
    actions = (
        create_json_file_storage_adapter(LocalJsonFileStorage.open(tmp_path / "external-json"))
        .describe()
        .actions
    )
    by_action = {action.action_id.rsplit(".", maxsplit=1)[-1]: action for action in actions}

    assert set(by_action) == {"write", "read", "delete", "list"}
    assert all(action.replay_mode is RuntimeReplayMode.EXTERNAL_EXCHANGE for action in actions)
    assert by_action["write"].externally_effectful
    assert by_action["delete"].externally_effectful
    assert not by_action["read"].externally_effectful
    assert not by_action["list"].externally_effectful


def test_sql_storage_binding_preserves_results_defaults_failures_and_state(
    tmp_path: Path,
) -> None:
    direct = SqliteStorage.open(tmp_path / "direct.sqlite")
    mediated = SqliteStorage.open(tmp_path / "mediated.sqlite")
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "sql",
        "component.storage.sql",
        create_sql_storage_adapter(mediated),
        create_sql_storage_proxy,
    )
    try:
        create = "create table notes (id integer primary key, title text not null)"
        insert = "insert into notes (title) values ('one')"
        assert proxy.execute(create) == direct.execute(create)
        assert proxy.execute(insert) == direct.execute(insert)
        assert proxy.query("select id, title from notes") == direct.query(
            "select id, title from notes"
        )
        _assert_same_failure(
            lambda: direct.query("insert into notes (title) values ('bad') returning id"),
            lambda: proxy.query("insert into notes (title) values ('bad') returning id"),
        )
        assert mediated.query("select id, title from notes") == direct.query(
            "select id, title from notes"
        )
    finally:
        runtime.close()


def test_sql_storage_binding_marks_durable_database_traffic_as_external_exchange(
    tmp_path: Path,
) -> None:
    actions = (
        create_sql_storage_adapter(SqliteStorage.open(tmp_path / "external.sqlite"))
        .describe()
        .actions
    )
    by_action = {action.action_id.rsplit(".", maxsplit=1)[-1]: action for action in actions}

    assert set(by_action) == {"execute", "query", "transaction"}
    assert all(action.replay_mode is RuntimeReplayMode.EXTERNAL_EXCHANGE for action in actions)
    assert by_action["execute"].externally_effectful
    assert by_action["transaction"].externally_effectful
    assert not by_action["query"].externally_effectful


def test_sql_storage_occurrences_survive_restart_without_reexecuting_traffic(
    tmp_path: Path,
) -> None:
    runtime_path = tmp_path / "runtime.sqlite"
    database_paths = {
        "test.sql.alpha": tmp_path / "alpha.sqlite",
        "test.sql.beta": tmp_path / "beta.sqlite",
    }
    runtime = SqliteMessageRuntime.open(runtime_path, runtime_key="test.sql.restart")
    first_ids: dict[str, UUID] = {}
    try:
        for key, database_path in database_paths.items():
            storage = SqliteStorage.open(database_path)
            registration = runtime.register_adapter(
                instance_key=key,
                component_contract_id="component.storage.sql",
                adapter=create_sql_storage_adapter(storage),
            )
            first_ids[key] = registration.instance_id
            address = runtime.address_for(key)
            proxy = create_sql_storage_proxy(runtime, address, address)
            proxy.execute("create table notes (title text not null)")
            proxy.execute("insert into notes (title) values (?)", (key,))
    finally:
        runtime.close()

    restarted = SqliteMessageRuntime.open(runtime_path, runtime_key="test.sql.restart")
    storages: dict[str, SqliteStorage] = {}
    try:
        for key, database_path in database_paths.items():
            storage = SqliteStorage.open(database_path)
            storages[key] = storage
            registration = restarted.register_adapter(
                instance_key=key,
                component_contract_id="component.storage.sql",
                adapter=create_sql_storage_adapter(storage),
            )
            assert registration.instance_id == first_ids[key]

        assert restarted.health == "ready"
        before = {
            key: storage.query("select title from notes")
            for key, storage in storages.items()
        }
        cursor = restarted.current_position
        report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(through_position=cursor)
        )

        assert report.verified
        assert report.applied_effects == 0
        assert report.external_effects_skipped == 4
        assert report.external_boundaries == tuple(
            RuntimeExternalBoundaryDisposition(
                boundary_id=key,
                mode=RuntimeExternalBoundaryMode.PLAYBACK_ONLY,
            )
            for key in sorted(database_paths)
        )
        assert "external outbound effects were not repeated" in " ".join(report.limitations)
        assert {
            key: storage.query("select title from notes")
            for key, storage in storages.items()
        } == before
        assert before == {
            key: storage.query("select ? as title", (key,))
            for key, storage in storages.items()
        }
    finally:
        restarted.close()


def test_controller_binding_preserves_defaults_results_failures_and_coordinated_state(
    tmp_path: Path,
) -> None:
    direct = _build_controller(tmp_path / "direct-controller")
    mediated = _build_controller(tmp_path / "mediated-controller")
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "controller",
        "component.rtg.controller",
        create_rtg_controller_adapter(mediated),
        create_rtg_controller_proxy,
    )
    graph_changes = RtgGraphChangeSet(
        anchor_writes=(
            RtgGraphAnchorWrite(
                ref=RtgChangeReference(resource_id=UUID(int=4)),
                type="Person",
            ),
        )
    )
    try:
        assert proxy.get_system_state() == direct.get_system_state()
        assert proxy.apply_live_graph_changes(graph_changes) == direct.apply_live_graph_changes(
            graph_changes
        )
        assert mediated.export_system_snapshot() == direct.export_system_snapshot()
        direct_error, proxy_error = _assert_same_failure(
            lambda: direct.get_object(UUID(int=999)),
            lambda: proxy.get_object(UUID(int=999)),
        )
        assert isinstance(direct_error, RtgControllerError)
        assert isinstance(proxy_error, RtgControllerError)
        assert proxy_error.diagnostic == direct_error.diagnostic
        missing_direct, missing_proxy = _assert_same_failure(
            lambda: direct.get_migration("missing"),
            lambda: proxy.get_migration("missing"),
        )
        assert isinstance(missing_direct, RtgMigrationNotFound)
        assert isinstance(missing_proxy, RtgMigrationNotFound)
        invalid_query = RtgQuerySpec(
            anchor_buckets=(
                RtgQueryAnchorBucket("person", ("Person",)),
                RtgQueryAnchorBucket("person", ("Person",)),
            )
        )
        query_direct, query_proxy = _assert_same_failure(
            lambda: direct.execute_query(invalid_query),
            lambda: proxy.execute_query(invalid_query),
        )
        assert isinstance(query_direct, RtgQuerySpecInvalid)
        assert isinstance(query_proxy, RtgQuerySpecInvalid)
        invalid_validation = RtgControllerValidationOptions(tracks=("not-a-track",))
        validation_direct, validation_proxy = _assert_same_failure(
            lambda: direct.validate_graph(validation_options=invalid_validation),
            lambda: proxy.validate_graph(validation_options=invalid_validation),
        )
        assert isinstance(validation_direct, RtgControllerValidationFailed)
        assert isinstance(validation_proxy, RtgControllerValidationFailed)
        assert mediated.export_system_snapshot() == direct.export_system_snapshot()
    finally:
        runtime.close()


def test_controller_binding_declares_exact_failures_and_indeterminate_compensation(
    tmp_path: Path,
) -> None:
    adapter = create_rtg_controller_adapter(_build_controller(tmp_path / "descriptor"))
    actions = {action.action_id.rsplit(".", 1)[-1]: action for action in adapter.describe().actions}

    assert actions["get_migration"].supported_failure_names == ("RtgMigrationNotFound",)
    assert actions["execute_query"].supported_failure_names == (
        "RtgQuerySpecInvalid",
        "RtgQueryUnsupported",
    )
    for action_name in ("apply_migration_cutover", "restore_from_snapshot"):
        failures = {
            failure.failure_name: failure for failure in actions[action_name].failure_bindings
        }
        assert failures["RtgControllerRecoveryIndeterminate"].trace_disposition is (
            RuntimeTraceDisposition.INDETERMINATE
        )
        assert failures["RtgControllerRecoveryIndeterminate"].replay_mode is (
            RuntimeReplayMode.NO_STATE_EFFECT
        )
    cutover_failures = {
        failure.failure_name: failure
        for failure in actions["apply_migration_cutover"].failure_bindings
    }
    assert cutover_failures["RtgControllerPreconditionFailed"].trace_disposition is (
        RuntimeTraceDisposition.ABORTED
    )
    assert cutover_failures["RtgControllerPreconditionFailed"].replay_mode is (
        RuntimeReplayMode.NO_STATE_EFFECT
    )
    for failure_name in ("RtgControllerValidationFailed", "RtgControllerApplyFailed"):
        assert cutover_failures[failure_name].trace_disposition is (
            RuntimeTraceDisposition.COMMITTED
        )
        assert cutover_failures[failure_name].replay_mode is (RuntimeReplayMode.CANONICAL_EFFECT)


def test_controller_cutover_preconditions_abort_without_canonical_effect(
    tmp_path: Path,
) -> None:
    controller = _build_controller(tmp_path / "controller")
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "controller-precondition",
        "component.rtg.controller",
        create_rtg_controller_adapter(controller),
        create_rtg_controller_proxy,
    )
    try:
        with pytest.raises(RtgControllerPreconditionFailed):
            proxy.apply_migration_cutover("missing")
        with pytest.raises(RtgControllerPreconditionFailed, match="validation_mode"):
            proxy.apply_migration_cutover(
                "missing",
                RtgControllerCutoverOptions(validation_mode="invalid"),
            )

        action_id = "component.rtg.controller.apply_migration_cutover"
        aborted = runtime.query_history_sync(
            RuntimeHistoryQuery(
                action_id=action_id,
                fact_type="trace_aborted",
                limit=10,
            )
        )
        effects = runtime.query_history_sync(
            RuntimeHistoryQuery(
                action_id=action_id,
                fact_type="canonical_effect",
                limit=10,
            )
        )
        assert len(aborted.facts) == 2
        assert effects.facts == ()
    finally:
        runtime.close()


def test_controller_binding_records_failed_snapshot_compensation_as_indeterminate(
    tmp_path: Path,
) -> None:
    graph = _FailingSnapshotReplacementGraph(InMemoryRtgGraph.empty())
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(_person_definition())
    controller = InProcessRtgController.open(
        graph,
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "indeterminate-json"),
    )
    runtime, proxy = _runtime_proxy(
        tmp_path,
        "controller-indeterminate",
        "component.rtg.controller",
        create_rtg_controller_adapter(controller),
        create_rtg_controller_proxy,
    )
    try:
        with pytest.raises(RtgControllerRecoveryIndeterminate):
            proxy.restore_from_snapshot(controller.export_system_snapshot())

        terminal = runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="trace_indeterminate", limit=10)
        )
        assert len(terminal.facts) == 1
    finally:
        runtime.close()


def _runtime_proxy[T](
    root: Path,
    key: str,
    contract_id: str,
    adapter: ComponentRuntimeAdapter,
    proxy_factory: Callable[[MessageRuntime, RuntimeAddress, RuntimeAddress], T],
) -> tuple[SqliteMessageRuntime, T]:
    runtime = SqliteMessageRuntime.open(
        root / f"{key}.runtime.sqlite",
        runtime_key=f"test.standard-binding.{key}",
    )
    registration = runtime.register_adapter(
        instance_key=f"test.{key}.primary",
        component_contract_id=contract_id,
        adapter=adapter,
    )
    address = runtime.address_for(registration.instance_key)
    return runtime, proxy_factory(runtime, address, address)


def _assert_same_failure(
    direct_call: Callable[[], object],
    proxy_call: Callable[[], object],
) -> tuple[Exception, Exception]:
    direct_error = _capture_failure(direct_call)
    proxy_error = _capture_failure(proxy_call)
    assert type(proxy_error) is type(direct_error)
    assert str(proxy_error) == str(direct_error)
    return direct_error, proxy_error


def _capture_failure(call: Callable[[], object]) -> Exception:
    with pytest.raises(Exception) as captured:
        call()
    return captured.value


def _person_definition() -> RtgSchemaDefinition:
    return RtgSchemaDefinition(
        uuid=UUID(int=1),
        kind="anchor",
        type_key="Person",
        description="Person.",
        payload=RtgAnchorSchemaPayload(),
    )


class _FailingSnapshotReplacementGraph:
    def __init__(self, delegate: InMemoryRtgGraph) -> None:
        self._delegate = delegate

    @classmethod
    def import_snapshot(cls, snapshot: RtgGraphSnapshot) -> _FailingSnapshotReplacementGraph:
        return cls(InMemoryRtgGraph.import_snapshot(snapshot))

    def export_snapshot(self) -> RtgGraphSnapshot:
        return self._delegate.export_snapshot()

    def replace_snapshot(self, _snapshot: RtgGraphSnapshot) -> None:
        raise RuntimeError("graph snapshot replacement failed")

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


def _build_controller(root: Path) -> RtgController:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(_person_definition())
    return InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(root / "json"),
    )


def assert_standard_binding_conformance(root: Path) -> None:
    """Run the complete standard-binding suite for modeled evidence aggregation."""
    for case in _BINDING_CASES:
        test_standard_binding_inventory_is_explicit_and_private_methods_are_not_routable(
            root / "inventory",
            case,
        )
    test_hand_authored_bindings_declare_exact_request_arguments_and_defaults(root / "arguments")
    test_schema_binding_preserves_results_defaults_failures_and_state(root / "schema")
    test_constraints_binding_preserves_typed_query_results_and_state(root / "constraints")
    test_migration_binding_preserves_defaults_failures_and_no_effect_on_rejection(
        root / "migration"
    )
    test_snapshot_replacement_bindings_preserve_atomic_idempotent_state_and_failures(
        root / "snapshot-replacement"
    )
    test_query_binding_preserves_defaults_results_diagnostics_and_read_only_state(root / "query")
    test_change_validation_binding_preserves_defaults_failures_and_read_only_state(
        root / "change-validation"
    )
    test_json_storage_binding_preserves_results_defaults_failures_and_effects(root / "json")
    test_sql_storage_binding_preserves_results_defaults_failures_and_state(root / "sql")
    test_controller_binding_preserves_defaults_results_failures_and_coordinated_state(
        root / "controller"
    )
    test_controller_binding_declares_exact_failures_and_indeterminate_compensation(
        root / "controller-failures"
    )
    test_controller_cutover_preconditions_abort_without_canonical_effect(
        root / "controller-preconditions"
    )
    test_controller_binding_records_failed_snapshot_compensation_as_indeterminate(
        root / "controller-indeterminate"
    )
