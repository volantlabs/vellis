from __future__ import annotations

import copy
from uuid import UUID, uuid4

from components.rtg.migration.protocol import (
    JsonObject,
    RtgMigrationDeleteNotAllowed,
    RtgMigrationDeleteResult,
    RtgMigrationEvidence,
    RtgMigrationEvidenceInvalid,
    RtgMigrationIdConflict,
    RtgMigrationIdInvalid,
    RtgMigrationNotFound,
    RtgMigrationRecord,
    RtgMigrationRecordInvalid,
    RtgMigrationRecordList,
    RtgMigrationReplacement,
    RtgMigrationSnapshot,
    RtgMigrationSnapshotInvalid,
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
        if not isinstance(snapshot, RtgMigrationSnapshot) or not isinstance(
            snapshot.migrations, tuple
        ):
            raise RtgMigrationSnapshotInvalid("snapshot must contain a migration tuple")
        migration = cls.empty()
        normalized: dict[str, RtgMigrationRecord] = {}
        for record in snapshot.migrations:
            if not isinstance(record, RtgMigrationRecord):
                raise RtgMigrationSnapshotInvalid("snapshot contains a non-migration record")
            candidate = migration._normalize_record(record)
            migration_id = _record_id(candidate)
            if migration_id in normalized:
                raise RtgMigrationIdConflict(migration_id)
            normalized[migration_id] = candidate
        migration._migrations = normalized
        return migration

    def export_snapshot(self) -> RtgMigrationSnapshot:
        return RtgMigrationSnapshot(migrations=tuple(_copy_record(item) for item in self._sorted()))

    def put_migration(self, migration: RtgMigrationRecord) -> RtgMigrationRecord:
        if not isinstance(migration, RtgMigrationRecord):
            raise RtgMigrationRecordInvalid("migration must be a migration record")
        normalized = self._normalize_record(migration)
        migration_id = _record_id(normalized)
        current = self._migrations.get(migration_id)
        if current is not None and not _transition_allowed(current.status, normalized.status):
            raise RtgMigrationStatusTransitionInvalid(
                f"{current.status} -> {normalized.status}"
            )
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
        if not _transition_allowed(current.status, target):
            raise RtgMigrationStatusTransitionInvalid(f"{current.status} -> {target}")
        normalized_status_metadata = _validate_json_object(
            status_metadata if status_metadata is not None else {}, "status_metadata"
        )
        metadata = copy.deepcopy(current.metadata)
        metadata["status_metadata"] = normalized_status_metadata
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
            raise RtgMigrationDeleteNotAllowed(current.status)
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
        schema_make_live = _normalize_uuid_set(migration.schema_make_live, "schema_make_live")
        schema_make_non_live = _normalize_uuid_set(
            migration.schema_make_non_live, "schema_make_non_live"
        )
        constraint_make_live = _normalize_uuid_set(
            migration.constraint_make_live, "constraint_make_live"
        )
        constraint_make_non_live = _normalize_uuid_set(
            migration.constraint_make_non_live, "constraint_make_non_live"
        )
        graph_make_live = _normalize_uuid_set(migration.graph_make_live, "graph_make_live")
        graph_make_non_live = _normalize_uuid_set(
            migration.graph_make_non_live, "graph_make_non_live"
        )
        schema_replacements = _normalize_replacements(
            migration.schema_replacements,
            schema_make_live,
            schema_make_non_live,
            "schema",
        )
        constraint_replacements = _normalize_replacements(
            migration.constraint_replacements,
            constraint_make_live,
            constraint_make_non_live,
            "constraint",
        )
        graph_replacements = _normalize_replacements(
            migration.graph_replacements,
            graph_make_live,
            graph_make_non_live,
            "graph",
        )
        evidence = tuple(_validate_evidence(item) for item in migration.evidence)
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise RtgMigrationEvidenceInvalid("evidence_id values must be unique")
        return RtgMigrationRecord(
            migration_id=migration_id,
            description=migration.description,
            status=status,
            schema_make_live=schema_make_live,
            schema_make_non_live=schema_make_non_live,
            constraint_make_live=constraint_make_live,
            constraint_make_non_live=constraint_make_non_live,
            graph_make_live=graph_make_live,
            graph_make_non_live=graph_make_non_live,
            schema_replacements=schema_replacements,
            constraint_replacements=constraint_replacements,
            graph_replacements=graph_replacements,
            evidence=evidence,
            metadata=_validate_json_object(migration.metadata, "metadata"),
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


def _transition_allowed(current: str, requested: str) -> bool:
    return current == requested or requested in _TRANSITIONS[current]


def _validate_disjoint(left: tuple[UUID, ...], right: tuple[UUID, ...], label: str) -> None:
    overlap = set(left).intersection(right)
    if overlap:
        raise RtgMigrationRecordInvalid(f"{label} make-live and make-non-live overlap")


def _normalize_uuid_set(values: tuple[UUID, ...], label: str) -> tuple[UUID, ...]:
    if not isinstance(values, tuple) or any(not isinstance(value, UUID) for value in values):
        raise RtgMigrationRecordInvalid(f"{label} must contain UUIDs")
    if len(set(values)) != len(values):
        raise RtgMigrationRecordInvalid(f"{label} must not contain duplicates")
    return tuple(sorted(values, key=str))


def _validate_replacement(value: RtgMigrationReplacement) -> RtgMigrationReplacement:
    if not isinstance(value.old_resource_id, UUID) or not isinstance(value.new_resource_id, UUID):
        raise RtgMigrationRecordInvalid("replacement IDs must be UUIDs")
    if value.old_resource_id == value.new_resource_id:
        raise RtgMigrationRecordInvalid("replacement IDs must be different")
    return copy.deepcopy(value)


def _normalize_replacements(
    values: tuple[RtgMigrationReplacement, ...],
    make_live: tuple[UUID, ...],
    make_non_live: tuple[UUID, ...],
    label: str,
) -> tuple[RtgMigrationReplacement, ...]:
    if not isinstance(values, tuple):
        raise RtgMigrationRecordInvalid(f"{label} replacements must be a tuple")
    normalized = tuple(_validate_replacement(value) for value in values)
    old_ids = tuple(value.old_resource_id for value in normalized)
    new_ids = tuple(value.new_resource_id for value in normalized)
    if len(set(old_ids)) != len(old_ids) or len(set(new_ids)) != len(new_ids):
        raise RtgMigrationRecordInvalid(f"{label} replacements must be one-to-one")
    if any(value not in make_non_live for value in old_ids):
        raise RtgMigrationRecordInvalid(
            f"{label} replacement old IDs must be in make_non_live"
        )
    if any(value not in make_live for value in new_ids):
        raise RtgMigrationRecordInvalid(f"{label} replacement new IDs must be in make_live")
    return tuple(
        sorted(normalized, key=lambda item: (str(item.old_resource_id), str(item.new_resource_id)))
    )


def _validate_evidence(evidence: RtgMigrationEvidence) -> RtgMigrationEvidence:
    if not isinstance(evidence, RtgMigrationEvidence):
        raise RtgMigrationEvidenceInvalid("evidence must be a migration evidence value")
    if not evidence.evidence_id:
        raise RtgMigrationEvidenceInvalid("evidence_id is required")
    if not evidence.kind:
        raise RtgMigrationEvidenceInvalid("kind is required")
    if not evidence.reference:
        raise RtgMigrationEvidenceInvalid("reference is required")
    return RtgMigrationEvidence(
        evidence_id=evidence.evidence_id,
        kind=evidence.kind,
        reference=evidence.reference,
        summary=evidence.summary,
        metadata=_validate_json_object(evidence.metadata, "evidence metadata", evidence=True),
    )


def _validate_json_object(
    value: object, label: str, *, evidence: bool = False
) -> JsonObject:
    error_type = RtgMigrationEvidenceInvalid if evidence else RtgMigrationRecordInvalid
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise error_type(f"{label} must be a JSON object")
    if not all(_is_json_value(item) for item in value.values()):
        raise error_type(f"{label} contains a non-JSON value")
    return copy.deepcopy(value)


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int | float):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False


def _copy_record(record: RtgMigrationRecord) -> RtgMigrationRecord:
    return copy.deepcopy(record)
