from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from components.rtg.change_validation.protocol import (
    RtgChangeBatch,
    RtgGraphChangeSet,
    RtgValidationReport,
)
from components.rtg.constraints.protocol import RtgConstraintSnapshot
from components.rtg.graph.protocol import (
    JsonObject,
    RtgGraphSnapshot,
    RtgObject,
    RtgTypeCountList,
)
from components.rtg.migration.protocol import (
    RtgMigrationRecord,
    RtgMigrationRecordList,
    RtgMigrationSnapshot,
)
from components.rtg.query.protocol import RtgQueryOptions, RtgQueryResult, RtgQuerySpec
from components.rtg.schema.protocol import RtgSchemaPack, RtgSchemaSnapshot


@dataclass(frozen=True, slots=True)
class RtgControllerValidationOptions:
    tracks: str | tuple[str, ...] = "all"
    finding_limit: int | None = None


@dataclass(frozen=True, slots=True)
class RtgControllerCutoverOptions:
    validation_mode: str = "strict"
    prune_retired: bool = True
    failure_restore: str = "restore_pre_cutover_snapshot"


@dataclass(frozen=True, slots=True)
class RtgControllerDiscoveryOptions:
    include_non_live: bool = False
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class RtgControllerSchemaPackOptions:
    live: bool | None = True
    include_live_counts: bool = True


@dataclass(frozen=True, slots=True)
class RtgControllerReplayOptions:
    start_snapshot: RtgSystemSnapshot | None = None
    start_snapshot_path: str | None = None
    after_ledger_position: int | None = None
    through_ledger_position: int | None = None


@dataclass(frozen=True, slots=True)
class RtgControllerRestoreOptions:
    ledger_mode: str = "record"


@dataclass(frozen=True, slots=True)
class RtgControllerLedgerFailureRecord:
    transaction_id: UUID
    ledger_position: int | None
    operation_name: str
    record_kind: str
    payload_json: str
    failure_message: str
    retry_count: int
    first_failed_timestamp: str
    last_failed_timestamp: str


@dataclass(frozen=True, slots=True)
class RtgSystemSnapshot:
    graph: RtgGraphSnapshot
    schema: RtgSchemaSnapshot
    constraints: RtgConstraintSnapshot
    migration: RtgMigrationSnapshot
    last_ledger_position: int | None = None
    last_transaction_id: UUID | None = None
    last_transaction_timestamp: str | None = None


@dataclass(frozen=True, slots=True)
class RtgAnchorTypeDiscoveryEntry:
    type_key: str
    description: str
    live_count: int


@dataclass(frozen=True, slots=True)
class RtgAnchorTypeDiscoveryResult:
    anchor_types: tuple[RtgAnchorTypeDiscoveryEntry, ...]


@dataclass(frozen=True, slots=True)
class RtgControllerSchemaPack:
    schema_pack: RtgSchemaPack
    live_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class RtgControllerSchemaCounts:
    anchor: int
    data_object: int
    link: int
    total: int


@dataclass(frozen=True, slots=True)
class RtgControllerCandidateCounts:
    schema: int
    constraints: int
    graph: int
    total: int


@dataclass(frozen=True, slots=True)
class RtgControllerMigrationCounts:
    draft: int
    ready: int
    failed: int
    applied: int
    abandoned: int
    total: int


@dataclass(frozen=True, slots=True)
class RtgControllerSystemState:
    state_classification: str
    live_schema_counts: RtgControllerSchemaCounts
    live_object_counts: RtgTypeCountList
    non_live_candidate_counts: RtgControllerCandidateCounts
    migration_counts_by_status: RtgControllerMigrationCounts
    persisted_snapshot_paths: tuple[str, ...]
    ledger_record_count: int
    migration_counts_scope: str = "current_migration_store"
    migration_history_hint: str | None = None
    last_ledger_position: int | None = None
    last_transaction_id: UUID | None = None
    recommended_workflows: tuple[str, ...] = ()
    recommended_next_steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgControllerLiveGraphValidationResult:
    status: str
    mutation_state: str
    accepted: bool
    generated_ids: dict[str, UUID]
    resolved_graph_changes: RtgGraphChangeSet
    validation_report: RtgValidationReport


@dataclass(frozen=True, slots=True)
class RtgControllerReplayVerificationResult:
    status: str
    ledger_records_seen: int
    mutating_requests_replayed: int
    replay_window: JsonObject
    pre_summary: JsonObject
    post_summary: JsonObject
    count_diffs: JsonObject
    validation_report: RtgValidationReport


@dataclass(frozen=True, slots=True)
class RtgControllerMigrationHistory:
    events: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class RtgPersistedSnapshotList:
    snapshots: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class RtgPersistedSnapshotDocument:
    relative_path: str
    snapshot: RtgSystemSnapshot


@dataclass(frozen=True, slots=True)
class RtgControllerAppliedChanges:
    graph_writes: int = 0
    schema_writes: int = 0
    constraint_writes: int = 0
    migration_writes: int = 0
    deletes: int = 0
    live_status_changes: int = 0


@dataclass(frozen=True, slots=True)
class RtgControllerOperationResult:
    status: str
    transaction_id: UUID
    ledger_position: int | None = None
    applied_changes: RtgControllerAppliedChanges = field(
        default_factory=RtgControllerAppliedChanges
    )
    validation_report: RtgValidationReport | None = None
    snapshot: RtgSystemSnapshot | None = None
    details: JsonObject = field(default_factory=dict)


class RtgControllerError(Exception):
    """Base class for RTG Controller errors."""

    def __init__(self, message: str, *, diagnostic: JsonObject | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic or {}


class RtgControllerConfigurationInvalid(RtgControllerError):
    """The supplied controller dependencies are invalid."""


class RtgControllerValidationFailed(RtgControllerError):
    """Validation rejected a controller operation."""

    def __init__(
        self,
        message: str,
        *,
        transaction_id: UUID | None = None,
        validation_report: RtgValidationReport | None = None,
        diagnostic: JsonObject | None = None,
    ) -> None:
        super().__init__(message, diagnostic=diagnostic)
        self.transaction_id = transaction_id
        self.validation_report = validation_report


class RtgControllerPreconditionFailed(RtgControllerError):
    """A controller-owned precondition failed."""


class RtgControllerApplyFailed(RtgControllerError):
    """A controller mutation failed."""


class RtgControllerObjectNotFound(RtgControllerError):
    """A graph object does not exist."""


class RtgControllerDiscoveryFailed(RtgControllerError):
    """A discovery or schema-pack operation failed."""


class RtgControllerSnapshotFailed(RtgControllerError):
    """A snapshot operation failed."""


class RtgControllerReplayFailed(RtgControllerError):
    """A ledger replay operation failed."""


class RtgController(Protocol):
    @classmethod
    def open(
        cls,
        graph: object,
        schema: object,
        constraints: object,
        migration: object,
        change_validator: object,
        query_engine: object,
        json_storage: object,
        sql_storage: object,
    ) -> RtgController:
        """Open a controller bound to RTG component implementations."""
        ...

    def apply_live_graph_changes(
        self,
        graph_changes: RtgGraphChangeSet,
        validation_mode: str = "strict",
    ) -> RtgControllerOperationResult:
        """Validate and apply normal live graph CRUD."""
        ...

    def validate_live_graph_changes(
        self,
        graph_changes: RtgGraphChangeSet,
        validation_options: RtgControllerValidationOptions | None = None,
    ) -> RtgControllerLiveGraphValidationResult:
        """Validate normal live graph CRUD without mutation or ledger writes."""
        ...

    def stage_knowledge_changes(
        self,
        knowledge_changes: RtgChangeBatch,
        validation_mode: str = "strict",
    ) -> RtgControllerOperationResult:
        """Validate and stage migration-scoped knowledge-engineering changes."""
        ...

    def apply_migration_cutover(
        self,
        migration_id: str,
        cutover_options: RtgControllerCutoverOptions | None = None,
    ) -> RtgControllerOperationResult:
        """Apply one migration cutover."""
        ...

    def execute_query(
        self,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        """Execute a query through the controller."""
        ...

    def get_object(self, object_uuid: UUID | str) -> RtgObject:
        """Read a graph object by UUID."""
        ...

    def list_migrations(self, status: str | None = None) -> RtgMigrationRecordList:
        """List migration records."""
        ...

    def get_migration(self, migration_id: str) -> RtgMigrationRecord:
        """Read one migration record."""
        ...

    def validate_graph(
        self,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgControllerValidationOptions | None = None,
    ) -> RtgValidationReport:
        """Validate current or projected graph state."""
        ...

    def discover_anchor_types(
        self,
        discovery_options: RtgControllerDiscoveryOptions | None = None,
    ) -> RtgAnchorTypeDiscoveryResult:
        """Return basic anchor type discovery."""
        ...

    def get_schema_pack(
        self,
        anchor_type_keys: tuple[str, ...],
        schema_pack_options: RtgControllerSchemaPackOptions | None = None,
    ) -> RtgControllerSchemaPack:
        """Return schema details plus live counts."""
        ...

    def get_system_state(self) -> RtgControllerSystemState:
        """Return read-only controller state and recommended next steps."""
        ...

    def export_system_snapshot(self) -> RtgSystemSnapshot:
        """Export a coordinated RTG system snapshot."""
        ...

    def persist_system_snapshot(self, relative_path: str) -> RtgControllerOperationResult:
        """Persist a coordinated RTG system snapshot."""
        ...

    def list_persisted_snapshots(self) -> RtgPersistedSnapshotList:
        """List persisted system snapshots visible through JSON File Storage."""
        ...

    def load_persisted_snapshot(self, relative_path: str) -> RtgPersistedSnapshotDocument:
        """Load one persisted system snapshot through JSON File Storage."""
        ...

    def abandon_migration(
        self,
        migration_id: str,
        reason: str | None = None,
    ) -> RtgControllerOperationResult:
        """Abandon a staged migration and prune safe non-live candidates."""
        ...

    def replay_ledger(
        self,
        replay_options: RtgControllerReplayOptions | None = None,
    ) -> RtgControllerOperationResult:
        """Replay successful mutating ledger records."""
        ...

    def verify_replay_from_ledger(
        self,
        replay_options: RtgControllerReplayOptions | None = None,
    ) -> RtgControllerReplayVerificationResult:
        """Replay into isolated scratch controller state without mutating current state."""
        ...

    def list_migration_history(self) -> RtgControllerMigrationHistory:
        """Return ledger-backed migration events."""
        ...

    def flush_ledger_failures(self) -> RtgControllerOperationResult:
        """Flush queued controller ledger failures."""
        ...

    def restore_from_snapshot(
        self,
        snapshot: RtgSystemSnapshot,
        restore_options: RtgControllerRestoreOptions | None = None,
    ) -> RtgControllerOperationResult:
        """Restore RTG state from a coordinated system snapshot."""
        ...
