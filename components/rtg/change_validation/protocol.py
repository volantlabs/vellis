from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from components.rtg.change import RtgChangeReference  # noqa: F401 - compatibility re-export
from components.rtg.constraints.protocol import (
    RtgConstraintChangeSet,
    RtgConstraintDefinitionWrite,
    RtgConstraintLiveStatusChange,
)  # noqa: F401 - compatibility re-exports for one release
from components.rtg.graph.protocol import (
    JsonObject,
    RtgGraphAnchorWrite,
    RtgGraphAssociationChange,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
    RtgGraphLiveStatusChange,
)  # noqa: F401 - compatibility re-exports for one release
from components.rtg.migration.protocol import (
    RtgMigrationChangeSet,
    RtgMigrationEvidenceAddition,
    RtgMigrationRecordWrite,
    RtgMigrationStatusChange,
)  # noqa: F401 - compatibility re-exports for one release
from components.rtg.schema.protocol import (
    RtgSchemaChangeSet,
    RtgSchemaDefinitionWrite,
    RtgSchemaLiveStatusChange,
)  # noqa: F401 - compatibility re-exports for one release

__all__ = [
    "RtgChangeBatch",
    "RtgChangeReference",
    "RtgChangeValidator",
    "RtgConstraintChangeSet",
    "RtgConstraintDefinitionWrite",
    "RtgConstraintLiveStatusChange",
    "RtgGraphAnchorWrite",
    "RtgGraphAssociationChange",
    "RtgGraphChangeSet",
    "RtgGraphDataObjectWrite",
    "RtgGraphLinkWrite",
    "RtgGraphLiveStatusChange",
    "RtgLiveStatusChange",
    "RtgMigrationChangeSet",
    "RtgMigrationEvidenceAddition",
    "RtgMigrationRecordWrite",
    "RtgMigrationStatusChange",
    "RtgSchemaChangeSet",
    "RtgSchemaDefinitionWrite",
    "RtgSchemaLiveStatusChange",
    "RtgValidationError",
    "RtgValidationFinding",
    "RtgValidationInputInvalid",
    "RtgValidationOptions",
    "RtgValidationReport",
]

# One-cycle compatibility alias for callers of the former aggregate-owned type.
RtgLiveStatusChange = RtgSchemaLiveStatusChange


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
