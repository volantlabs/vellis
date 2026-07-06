from __future__ import annotations

import copy
from uuid import UUID, uuid4

from components.rtg.migration.protocol import (
    JsonObject,
    RtgMigrationDeleteRejected,
    RtgMigrationDeleteResult,
    RtgMigrationEvidence,
    RtgMigrationEvidenceInvalid,
    RtgMigrationIdInvalid,
    RtgMigrationNotFound,
    RtgMigrationRecord,
    RtgMigrationRecordInvalid,
    RtgMigrationRecordList,
    RtgMigrationReplacement,
    RtgMigrationSnapshot,
    RtgMigrationStatusInvalid,
    RtgMigrationStatusTransitionInvalid,
)

_STATUSES = {"draft", "ready", "applied", "failed", "abandoned"}
_TERMINAL = {"applied", "abandoned"}
_TRANSITIONS = {
    "draft": {"ready", "abandoned"},
    "ready": {"draft", "applied", "failed", "abandoned"},
    "failed": {"ready", "abandoned"},
    "applied": set(),
    "abandoned": set(),
}


class InMemoryRtgMigration:
    """In-memory implementation of the RTG Migration component."""

    def __init__(self) -> None:
        self._migrations: dict[str, RtgMigrationRecord] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgMigration:
        return cls()

    @classmethod
    def import_snapshot(cls, snapshot: RtgMigrationSnapshot) -> InMemoryRtgMigration:
        migration = cls.empty()
        for record in snapshot.migrations:
            migration.put_migration(record)
        return migration

    def export_snapshot(self) -> RtgMigrationSnapshot:
        return RtgMigrationSnapshot(migrations=tuple(_copy_record(item) for item in self._sorted()))

    def put_migration(self, migration: RtgMigrationRecord) -> RtgMigrationRecord:
        normalized = self._normalize_record(migration)
        migration_id = _record_id(normalized)
        self._migrations[migration_id] = normalized
        return _copy_record(normalized)

    def get_migration(self, migration_id: str) -> RtgMigrationRecord:
        key = _validate_migration_id(migration_id)
        try:
            return _copy_record(self._migrations[key])
        except KeyError as error:
            raise RtgMigrationNotFound(key) from error

    def list_migrations(self, status: str | None = None) -> RtgMigrationRecordList:
        if status is not None:
            _validate_status(status)
        return RtgMigrationRecordList(
            migrations=tuple(
                _copy_record(item)
                for item in self._sorted()
                if status is None or item.status == status
            )
        )

    def set_status(
        self,
        migration_id: str,
        status: str,
        status_metadata: JsonObject | None = None,
    ) -> RtgMigrationRecord:
        key = _validate_migration_id(migration_id)
        target = _validate_status(status)
        current = self.get_migration(key)
        if target != current.status and target not in _TRANSITIONS[current.status]:
            raise RtgMigrationStatusTransitionInvalid(f"{current.status} -> {target}")
        metadata = copy.deepcopy(current.metadata)
        if status_metadata:
            metadata["status_metadata"] = copy.deepcopy(status_metadata)
        updated = RtgMigrationRecord(
            migration_id=current.migration_id,
            description=current.description,
            status=target,
            schema_make_live=current.schema_make_live,
            schema_make_non_live=current.schema_make_non_live,
            constraint_make_live=current.constraint_make_live,
            constraint_make_non_live=current.constraint_make_non_live,
            graph_make_live=current.graph_make_live,
            graph_make_non_live=current.graph_make_non_live,
            schema_replacements=current.schema_replacements,
            constraint_replacements=current.constraint_replacements,
            graph_replacements=current.graph_replacements,
            evidence=current.evidence,
            metadata=metadata,
        )
        self._migrations[key] = updated
        return _copy_record(updated)

    def add_evidence(
        self,
        migration_id: str,
        evidence: RtgMigrationEvidence,
    ) -> RtgMigrationRecord:
        key = _validate_migration_id(migration_id)
        current = self.get_migration(key)
        normalized = _validate_evidence(evidence)
        if any(item.evidence_id == normalized.evidence_id for item in current.evidence):
            raise RtgMigrationEvidenceInvalid(f"duplicate evidence_id: {normalized.evidence_id}")
        updated = RtgMigrationRecord(
            migration_id=current.migration_id,
            description=current.description,
            status=current.status,
            schema_make_live=current.schema_make_live,
            schema_make_non_live=current.schema_make_non_live,
            constraint_make_live=current.constraint_make_live,
            constraint_make_non_live=current.constraint_make_non_live,
            graph_make_live=current.graph_make_live,
            graph_make_non_live=current.graph_make_non_live,
            schema_replacements=current.schema_replacements,
            constraint_replacements=current.constraint_replacements,
            graph_replacements=current.graph_replacements,
            evidence=(*current.evidence, normalized),
            metadata=current.metadata,
        )
        self._migrations[key] = updated
        return _copy_record(updated)

    def delete_migration(self, migration_id: str) -> RtgMigrationDeleteResult:
        key = _validate_migration_id(migration_id)
        current = self.get_migration(key)
        if current.status not in _TERMINAL:
            raise RtgMigrationDeleteRejected(current.status)
        deleted = self._migrations.pop(key)
        return RtgMigrationDeleteResult(deleted_migration=_copy_record(deleted))

    def _normalize_record(self, migration: RtgMigrationRecord) -> RtgMigrationRecord:
        migration_id = (
            _validate_migration_id(migration.migration_id)
            if migration.migration_id is not None
            else str(uuid4())
        )
        status = _validate_status(migration.status)
        if not migration.description:
            raise RtgMigrationRecordInvalid("description is required")
        _validate_disjoint(migration.schema_make_live, migration.schema_make_non_live, "schema")
        _validate_disjoint(
            migration.constraint_make_live, migration.constraint_make_non_live, "constraint"
        )
        _validate_disjoint(migration.graph_make_live, migration.graph_make_non_live, "graph")
        evidence = tuple(_validate_evidence(item) for item in migration.evidence)
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise RtgMigrationEvidenceInvalid("evidence_id values must be unique")
        return RtgMigrationRecord(
            migration_id=migration_id,
            description=migration.description,
            status=status,
            schema_make_live=tuple(migration.schema_make_live),
            schema_make_non_live=tuple(migration.schema_make_non_live),
            constraint_make_live=tuple(migration.constraint_make_live),
            constraint_make_non_live=tuple(migration.constraint_make_non_live),
            graph_make_live=tuple(migration.graph_make_live),
            graph_make_non_live=tuple(migration.graph_make_non_live),
            schema_replacements=tuple(
                _validate_replacement(item) for item in migration.schema_replacements
            ),
            constraint_replacements=tuple(
                _validate_replacement(item) for item in migration.constraint_replacements
            ),
            graph_replacements=tuple(
                _validate_replacement(item) for item in migration.graph_replacements
            ),
            evidence=evidence,
            metadata=copy.deepcopy(migration.metadata),
        )

    def _sorted(self) -> tuple[RtgMigrationRecord, ...]:
        return tuple(sorted(self._migrations.values(), key=lambda item: _record_id(item)))


def _validate_migration_id(value: str | None) -> str:
    if not isinstance(value, str) or value == "" or value != value.strip():
        raise RtgMigrationIdInvalid(str(value))
    return value


def _record_id(record: RtgMigrationRecord) -> str:
    if record.migration_id is None:
        raise RtgMigrationIdInvalid("migration ID is not concrete")
    return record.migration_id


def _validate_status(value: str) -> str:
    if value not in _STATUSES:
        raise RtgMigrationStatusInvalid(str(value))
    return value


def _validate_disjoint(left: tuple[UUID, ...], right: tuple[UUID, ...], label: str) -> None:
    overlap = set(left).intersection(right)
    if overlap:
        raise RtgMigrationRecordInvalid(f"{label} make-live and make-non-live overlap")


def _validate_replacement(value: RtgMigrationReplacement) -> RtgMigrationReplacement:
    if not isinstance(value.old_resource_id, UUID) or not isinstance(value.new_resource_id, UUID):
        raise RtgMigrationRecordInvalid("replacement IDs must be UUIDs")
    return copy.deepcopy(value)


def _validate_evidence(evidence: RtgMigrationEvidence) -> RtgMigrationEvidence:
    if not evidence.evidence_id:
        raise RtgMigrationEvidenceInvalid("evidence_id is required")
    if not evidence.kind:
        raise RtgMigrationEvidenceInvalid("kind is required")
    if not evidence.reference:
        raise RtgMigrationEvidenceInvalid("reference is required")
    return copy.deepcopy(evidence)


def _copy_record(record: RtgMigrationRecord) -> RtgMigrationRecord:
    return copy.deepcopy(record)
