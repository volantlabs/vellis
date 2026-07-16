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
from components.rtg.schema.protocol import (
    RtgSchemaDefinitionList,
    RtgSchemaPack,
    RtgSchemaSnapshot,
)


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
class RtgSystemSnapshot:
    graph: RtgGraphSnapshot
    schema: RtgSchemaSnapshot
    constraints: RtgConstraintSnapshot
    migration: RtgMigrationSnapshot


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
    migration_counts_scope: str = "current_migration_store"
    recommended_workflows: tuple[str, ...] = ()
    recommended_next_steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgControllerLiveGraphValidationResult:
    status: str
    mutation_state: str
    accepted: bool
    generated_ids: dict[str, UUID]
    validation_report: RtgValidationReport


@dataclass(frozen=True, slots=True)
class RtgPersistedSnapshotList:
    snapshots: tuple[JsonObject, ...]
    total: int
    next_offset: int | None = None


@dataclass(frozen=True, slots=True)
class RtgPersistedSnapshotDocument:
    relative_path: str
    snapshot: RtgSystemSnapshot


@dataclass(frozen=True, slots=True)
class RtgSnapshotStateCounts:
    anchors: int
    data_objects: int
    links: int
    schema_definitions: int
    constraints: int
    migrations: int


@dataclass(frozen=True, slots=True)
class RtgSnapshotPersistenceResult:
    status: str
    relative_path: str
    size_bytes: int
    digest: str
    state_counts: RtgSnapshotStateCounts


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
    generated_ids: dict[str, UUID] = field(default_factory=dict)
    applied_changes: RtgControllerAppliedChanges = field(
        default_factory=RtgControllerAppliedChanges
    )
    validation_report: RtgValidationReport | None = None
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
        validation_report: RtgValidationReport | None = None,
        diagnostic: JsonObject | None = None,
    ) -> None:
        super().__init__(message, diagnostic=diagnostic)
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


class RtgControllerRecoveryIndeterminate(RtgControllerError):
    """A compensating restore failed, so coordinated state cannot be confirmed."""


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
        """Validate normal live graph CRUD without mutation."""
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
        """Apply one migration cutover as a compensating saga."""
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

    def list_migrations(
        self,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> RtgMigrationRecordList:
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

    def list_schema_definitions_by_type_key(
        self,
        type_key: str,
        kind: str | None = None,
        live: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> RtgSchemaDefinitionList:
        """Return a bounded schema-definition page for one type key."""
        ...

    def get_system_state(self) -> RtgControllerSystemState:
        """Return read-only domain state and recommended next steps."""
        ...

    def export_system_snapshot(self) -> RtgSystemSnapshot:
        """Export a coordinated RTG domain snapshot."""
        ...

    def persist_system_snapshot(self, relative_path: str) -> RtgSnapshotPersistenceResult:
        """Persist a coordinated RTG domain snapshot."""
        ...

    def list_persisted_snapshots(
        self, offset: int = 0, limit: int = 100
    ) -> RtgPersistedSnapshotList:
        """List persisted domain snapshots visible through JSON File Storage."""
        ...

    def load_persisted_snapshot(self, relative_path: str) -> RtgPersistedSnapshotDocument:
        """Load one persisted domain snapshot through JSON File Storage."""
        ...

    def abandon_migration(
        self,
        migration_id: str,
        reason: str | None = None,
    ) -> RtgControllerOperationResult:
        """Abandon a staged migration and prune safe non-live candidates."""
        ...

    def restore_from_snapshot(
        self,
        snapshot: RtgSystemSnapshot,
    ) -> RtgControllerOperationResult:
        """Atomically restore RTG domain state from a coordinated snapshot."""
        ...
