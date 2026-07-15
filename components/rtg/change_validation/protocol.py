from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from components.rtg.constraints.protocol import RtgConstraintDefinition
from components.rtg.graph.protocol import JsonObject
from components.rtg.migration.protocol import RtgMigrationEvidence, RtgMigrationRecord
from components.rtg.schema.protocol import RtgSchemaDefinition


@dataclass(frozen=True, slots=True)
class RtgChangeReference:
    resource_id: UUID | str | None = None
    local_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RtgIdentityOverride:
    mode: str
    reason: str
    criterion_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgGraphAnchorWrite:
    ref: RtgChangeReference
    type: str
    display_name: str | None = None
    system: JsonObject = field(default_factory=dict)
    identity_override: RtgIdentityOverride | None = None


@dataclass(frozen=True, slots=True)
class RtgGraphDataObjectWrite:
    ref: RtgChangeReference
    type: str
    properties: JsonObject = field(default_factory=dict)
    system: JsonObject = field(default_factory=dict)
    anchor_refs: tuple[RtgChangeReference, ...] = ()
    identity_override: RtgIdentityOverride | None = None


@dataclass(frozen=True, slots=True)
class RtgGraphLinkWrite:
    ref: RtgChangeReference
    type: str
    source_ref: RtgChangeReference
    target_ref: RtgChangeReference
    system: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgGraphAssociationChange:
    anchor_ref: RtgChangeReference
    data_ref: RtgChangeReference


@dataclass(frozen=True, slots=True)
class RtgGraphLiveStatusChange:
    object_ref: RtgChangeReference
    live: bool


@dataclass(frozen=True, slots=True)
class RtgGraphChangeSet:
    anchor_writes: tuple[RtgGraphAnchorWrite, ...] = ()
    data_object_writes: tuple[RtgGraphDataObjectWrite, ...] = ()
    link_writes: tuple[RtgGraphLinkWrite, ...] = ()
    associate_data: tuple[RtgGraphAssociationChange, ...] = ()
    dissociate_data: tuple[RtgGraphAssociationChange, ...] = ()
    delete_anchors: tuple[RtgChangeReference, ...] = ()
    delete_data_objects: tuple[RtgChangeReference, ...] = ()
    delete_links: tuple[RtgChangeReference, ...] = ()
    set_live: tuple[RtgGraphLiveStatusChange, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgSchemaDefinitionWrite:
    ref: RtgChangeReference
    definition: RtgSchemaDefinition


@dataclass(frozen=True, slots=True)
class RtgLiveStatusChange:
    target_ref: RtgChangeReference
    live: bool


@dataclass(frozen=True, slots=True)
class RtgSchemaChangeSet:
    definition_writes: tuple[RtgSchemaDefinitionWrite, ...] = ()
    delete_definitions: tuple[RtgChangeReference, ...] = ()
    set_live: tuple[RtgLiveStatusChange, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgConstraintDefinitionWrite:
    ref: RtgChangeReference
    constraint: RtgConstraintDefinition


@dataclass(frozen=True, slots=True)
class RtgConstraintChangeSet:
    constraint_writes: tuple[RtgConstraintDefinitionWrite, ...] = ()
    delete_constraints: tuple[RtgChangeReference, ...] = ()
    set_live: tuple[RtgLiveStatusChange, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgMigrationRecordWrite:
    ref: RtgChangeReference
    migration: RtgMigrationRecord


@dataclass(frozen=True, slots=True)
class RtgMigrationStatusChange:
    migration_ref: RtgChangeReference
    status: str
    status_metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgMigrationEvidenceAddition:
    migration_ref: RtgChangeReference
    evidence: RtgMigrationEvidence


@dataclass(frozen=True, slots=True)
class RtgMigrationChangeSet:
    migration_writes: tuple[RtgMigrationRecordWrite, ...] = ()
    delete_migrations: tuple[RtgChangeReference, ...] = ()
    status_changes: tuple[RtgMigrationStatusChange, ...] = ()
    evidence_additions: tuple[RtgMigrationEvidenceAddition, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgChangeBatch:
    graph_changes: RtgGraphChangeSet = field(default_factory=RtgGraphChangeSet)
    schema_changes: RtgSchemaChangeSet = field(default_factory=RtgSchemaChangeSet)
    constraint_changes: RtgConstraintChangeSet = field(default_factory=RtgConstraintChangeSet)
    migration_changes: RtgMigrationChangeSet = field(default_factory=RtgMigrationChangeSet)


@dataclass(frozen=True, slots=True)
class RtgValidationOptions:
    tracks: str | tuple[str, ...] = "all"
    finding_limit: int | None = None


@dataclass(frozen=True, slots=True)
class RtgValidationFinding:
    track: str
    severity: str
    code: str
    message: str
    suggestion: str | None = None
    affected_references: tuple[str, ...] = ()
    diagnostic: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgValidationReport:
    accepted: bool
    findings: tuple[RtgValidationFinding, ...]
    evidence: JsonObject = field(default_factory=dict)


class RtgValidationError(Exception):
    """Base class for RTG Change Validation errors."""


class RtgValidationInputInvalid(RtgValidationError):
    """Validation inputs are structurally unusable."""


class RtgChangeValidator(Protocol):
    def validate_batch(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        change_batch: RtgChangeBatch,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        """Validate one proposed RTG change batch without mutation."""
        ...

    def validate_graph_state(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        """Validate supplied graph/schema/constraint state without mutation."""
        ...
