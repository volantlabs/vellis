from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type UuidInput = UUID | str


@dataclass(frozen=True, slots=True)
class RtgMigrationReplacement:
    old_resource_id: UUID
    new_resource_id: UUID


@dataclass(frozen=True, slots=True)
class RtgMigrationEvidence:
    evidence_id: str
    kind: str
    reference: str
    summary: str
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgMigrationRecord:
    migration_id: str | None
    description: str
    status: str = "draft"
    schema_make_live: tuple[UUID, ...] = ()
    schema_make_non_live: tuple[UUID, ...] = ()
    constraint_make_live: tuple[UUID, ...] = ()
    constraint_make_non_live: tuple[UUID, ...] = ()
    graph_make_live: tuple[UUID, ...] = ()
    graph_make_non_live: tuple[UUID, ...] = ()
    schema_replacements: tuple[RtgMigrationReplacement, ...] = ()
    constraint_replacements: tuple[RtgMigrationReplacement, ...] = ()
    graph_replacements: tuple[RtgMigrationReplacement, ...] = ()
    evidence: tuple[RtgMigrationEvidence, ...] = ()
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgMigrationSnapshot:
    migrations: tuple[RtgMigrationRecord, ...]


@dataclass(frozen=True, slots=True)
class RtgMigrationRecordList:
    migrations: tuple[RtgMigrationRecord, ...]


@dataclass(frozen=True, slots=True)
class RtgMigrationDeleteResult:
    deleted_migration: RtgMigrationRecord


@dataclass(frozen=True, slots=True)
class RtgMigrationCutoverPlan:
    migration_id: str
    schema_make_live: tuple[UUID, ...]
    schema_make_non_live: tuple[UUID, ...]
    constraint_make_live: tuple[UUID, ...]
    constraint_make_non_live: tuple[UUID, ...]
    graph_make_live: tuple[UUID, ...]
    graph_make_non_live: tuple[UUID, ...]
    schema_replacements: tuple[RtgMigrationReplacement, ...]
    constraint_replacements: tuple[RtgMigrationReplacement, ...]
    graph_replacements: tuple[RtgMigrationReplacement, ...]

    @classmethod
    def from_migration(cls, migration: RtgMigrationRecord) -> RtgMigrationCutoverPlan:
        if migration.migration_id is None:
            raise RtgMigrationIdInvalid("migration ID is not concrete")
        return cls(
            migration_id=migration.migration_id,
            schema_make_live=migration.schema_make_live,
            schema_make_non_live=migration.schema_make_non_live,
            constraint_make_live=migration.constraint_make_live,
            constraint_make_non_live=migration.constraint_make_non_live,
            graph_make_live=migration.graph_make_live,
            graph_make_non_live=migration.graph_make_non_live,
            schema_replacements=migration.schema_replacements,
            constraint_replacements=migration.constraint_replacements,
            graph_replacements=migration.graph_replacements,
        )


class RtgMigrationError(Exception):
    """Base class for RTG Migration errors."""


class RtgMigrationNotFound(RtgMigrationError):
    """A requested migration record does not exist."""


class RtgMigrationSnapshotInvalid(RtgMigrationError):
    """A migration snapshot is malformed."""


class RtgMigrationIdInvalid(RtgMigrationError):
    """A migration ID is invalid."""


class RtgMigrationIdConflict(RtgMigrationError):
    """A migration ID conflicts with another migration."""


class RtgMigrationRecordInvalid(RtgMigrationError):
    """A migration record is invalid."""


class RtgMigrationStatusInvalid(RtgMigrationError):
    """A migration status is invalid."""


class RtgMigrationStatusTransitionInvalid(RtgMigrationError):
    """A migration status transition is invalid."""


class RtgMigrationDeleteNotAllowed(RtgMigrationError):
    """A migration record cannot be deleted in its current status."""


# Compatibility aliases for the pre-model Python vocabulary. They are one logical failure.
RtgMigrationDeleteInvalid = RtgMigrationDeleteNotAllowed
RtgMigrationDeleteRejected = RtgMigrationDeleteNotAllowed


class RtgMigrationEvidenceInvalid(RtgMigrationError):
    """Migration evidence is invalid."""


class RtgMigration(Protocol):
    @classmethod
    def empty(cls) -> RtgMigration:
        """Create an empty migration store."""
        ...

    @classmethod
    def import_snapshot(cls, snapshot: RtgMigrationSnapshot) -> RtgMigration:
        """Create a migration store from a snapshot."""
        ...

    def export_snapshot(self) -> RtgMigrationSnapshot:
        """Export a migration snapshot."""
        ...

    def replace_snapshot(self, snapshot: RtgMigrationSnapshot) -> None:
        """Atomically replace all migration state from a validated snapshot."""
        ...

    def put_migration(self, migration: RtgMigrationRecord) -> RtgMigrationRecord:
        """Create or fully replace a migration record."""
        ...

    def get_migration(self, migration_id: str) -> RtgMigrationRecord:
        """Return one migration record."""
        ...

    def list_migrations(self, status: str | None = None) -> RtgMigrationRecordList:
        """List migrations, optionally filtered by status."""
        ...

    def set_status(
        self,
        migration_id: str,
        status: str,
        status_metadata: JsonObject | None = None,
    ) -> RtgMigrationRecord:
        """Transition a migration record status."""
        ...

    def add_evidence(
        self,
        migration_id: str,
        evidence: RtgMigrationEvidence,
    ) -> RtgMigrationRecord:
        """Append evidence to a migration record."""
        ...

    def delete_migration(self, migration_id: str) -> RtgMigrationDeleteResult:
        """Delete a terminal migration record."""
        ...
