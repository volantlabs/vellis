# Vellis operation ownership

Generated non-normative reading projection from the parser-backed SysML architecture graph; do not edit by hand.

| Operation | Modeled provider or performed action | Relationship |
|---|---|---|
| `operation.vellis.rtg_abandon_migration` | `BibliotekRtgController::AbandonMigration` | `types` |
| `operation.vellis.rtg_apply_live_anchor_records` | `BibliotekRtgController::ApplyLiveGraphChanges` | `types` |
| `operation.vellis.rtg_apply_live_graph_changes` | `BibliotekRtgController::ApplyLiveGraphChanges` | `types` |
| `operation.vellis.rtg_apply_migration_cutover` | `BibliotekRtgController::ApplyMigrationCutover` | `types` |
| `operation.vellis.rtg_discover_anchor_types` | `BibliotekRtgController::DiscoverAnchorTypes` | `types` |
| `operation.vellis.rtg_execute_query` | `BibliotekRtgController::ExecuteControllerQuery` | `types` |
| `operation.vellis.rtg_export_system_snapshot` | `BibliotekRtgController::ExportSystemSnapshot` | `types` |
| `operation.vellis.rtg_get_migration` | `BibliotekRtgController::ControllerGetMigration` | `types` |
| `operation.vellis.rtg_get_object` | `BibliotekRtgController::ControllerGetObject` | `types` |
| `operation.vellis.rtg_get_operation_outcome` | `BibliotekRuntimeMessageRuntime::LookupRuntimeMessageOutcome` | `types` |
| `operation.vellis.rtg_get_schema_pack` | `BibliotekRtgController::GetControllerSchemaPack` | `types` |
| `operation.vellis.rtg_get_system_state` | `BibliotekRtgController::GetSystemState` | `types` |
| `operation.vellis.rtg_get_usage_guide` | — | No direct provider projection |
| `operation.vellis.rtg_list_migration_history` | `BibliotekRuntimeMessageRuntime::QueryRuntimeHistory` | `types` |
| `operation.vellis.rtg_list_migrations` | `BibliotekRtgController::ControllerListMigrations` | `types` |
| `operation.vellis.rtg_list_persisted_snapshots` | `BibliotekRtgController::ListPersistedSnapshots` | `types` |
| `operation.vellis.rtg_load_persisted_snapshot` | `BibliotekRtgController::LoadPersistedSnapshot` | `types` |
| `operation.vellis.rtg_persist_system_snapshot` | `BibliotekRtgController::PersistSystemSnapshot` | `types` |
| `operation.vellis.rtg_replay_ledger` | `BibliotekRuntimeMessageRuntime::ReconstructRuntimeState` | `types` |
| `operation.vellis.rtg_resolve_anchor_by_fact` | `BibliotekRtgController::ExecuteControllerQuery` | `types` |
| `operation.vellis.rtg_restore_from_snapshot` | `BibliotekRtgController::RestoreFromSnapshot` | `types` |
| `operation.vellis.rtg_stage_knowledge_changes` | `BibliotekRtgController::StageKnowledgeChanges` | `types` |
| `operation.vellis.rtg_stage_schema_migration` | `BibliotekRtgController::ExportSystemSnapshot` | `types` |
| `operation.vellis.rtg_stage_schema_migration` | `BibliotekRtgController::StageKnowledgeChanges` | `types` |
| `operation.vellis.rtg_validate_graph` | `BibliotekRtgController::ValidateGraph` | `types` |
| `operation.vellis.rtg_validate_live_anchor_records` | `BibliotekRtgController::ValidateLiveGraphChanges` | `types` |
| `operation.vellis.rtg_validate_live_graph_changes` | `BibliotekRtgController::ValidateLiveGraphChanges` | `types` |
| `operation.vellis.rtg_verify_replay_from_ledger` | — | No direct provider projection |
