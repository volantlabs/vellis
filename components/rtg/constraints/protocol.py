from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from components.rtg.change import RtgChangeReference
from components.rtg.query.protocol import RtgQuerySpec

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type UuidInput = UUID | str


@dataclass(frozen=True, slots=True)
class RtgConstraintQueryPatternPayload:
    query_spec: RtgQuerySpec
    expectation: str


@dataclass(frozen=True, slots=True)
class RtgConstraintCardinalityPayload:
    query_spec: RtgQuerySpec
    counted_binding: str
    group_by_bindings: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


type RtgConstraintPayload = RtgConstraintQueryPatternPayload | RtgConstraintCardinalityPayload


@dataclass(frozen=True, slots=True)
class RtgConstraintDefinition:
    uuid: UUID | None
    kind: str
    target_type_keys: tuple[str, ...]
    display_name: str
    description: str
    payload: RtgConstraintPayload
    system: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgConstraintSnapshot:
    constraints: tuple[RtgConstraintDefinition, ...]


@dataclass(frozen=True, slots=True)
class RtgConstraintDefinitionWrite:
    ref: RtgChangeReference
    constraint: RtgConstraintDefinition


@dataclass(frozen=True, slots=True)
class RtgConstraintLiveStatusChange:
    target_ref: RtgChangeReference
    live: bool


@dataclass(frozen=True, slots=True)
class RtgConstraintChangeSet:
    constraint_writes: tuple[RtgConstraintDefinitionWrite, ...] = ()
    delete_constraints: tuple[RtgChangeReference, ...] = ()
    set_live: tuple[RtgConstraintLiveStatusChange, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgConstraintBatchResult:
    writes: int = 0
    deletes: int = 0
    live_changes: int = 0


@dataclass(frozen=True, slots=True)
class RtgConstraintCountSummary:
    live_total: int = 0
    non_live_total: int = 0


@dataclass(frozen=True, slots=True)
class RtgConstraintDeleteResult:
    deleted_constraint: RtgConstraintDefinition


@dataclass(frozen=True, slots=True)
class RtgConstraintDefinitionList:
    constraints: tuple[RtgConstraintDefinition, ...]


class RtgConstraintError(Exception):
    """Base class for RTG Constraint errors."""


class RtgConstraintNotFound(RtgConstraintError):
    """A requested constraint definition does not exist."""


class RtgConstraintSnapshotInvalid(RtgConstraintError):
    """A constraint snapshot is malformed."""


class RtgConstraintUuidInvalid(RtgConstraintError):
    """A constraint UUID is not parseable."""


class RtgConstraintUuidConflict(RtgConstraintError):
    """A constraint UUID conflicts with another constraint."""


class RtgConstraintKindInvalid(RtgConstraintError):
    """A constraint kind is invalid."""


class RtgConstraintDefinitionInvalid(RtgConstraintError):
    """A constraint definition is structurally invalid."""


class RtgConstraintPayloadInvalid(RtgConstraintError):
    """A constraint payload is invalid."""


class RtgConstraintTargetInvalid(RtgConstraintError):
    """A constraint target lookup key is invalid."""


class RtgConstraintSystemValueInvalid(RtgConstraintError):
    """A constraint system value is invalid."""


class RtgConstraints(Protocol):
    @classmethod
    def empty(cls) -> RtgConstraints:
        """Create an empty constraint registry."""
        ...

    @classmethod
    def import_snapshot(cls, snapshot: RtgConstraintSnapshot) -> RtgConstraints:
        """Create a constraint registry from a snapshot."""
        ...

    def export_snapshot(self) -> RtgConstraintSnapshot:
        """Export a constraint snapshot."""
        ...

    def replace_snapshot(self, snapshot: RtgConstraintSnapshot) -> None:
        """Atomically replace all constraint state from a validated snapshot."""
        ...

    def apply_batch(self, changes: RtgConstraintChangeSet) -> RtgConstraintBatchResult:
        """Apply one constraint-local change set atomically."""
        ...

    def count_summary(self) -> RtgConstraintCountSummary:
        """Return bounded constraint counts without materializing definitions."""
        ...

    def put_constraint(self, constraint: RtgConstraintDefinition) -> RtgConstraintDefinition:
        """Create or fully replace one constraint definition."""
        ...

    def get_constraint(self, constraint_uuid: UuidInput) -> RtgConstraintDefinition:
        """Return one constraint definition."""
        ...

    def list_constraints(
        self,
        kind: str | None = None,
        live: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> RtgConstraintDefinitionList:
        """List constraints, optionally filtered by kind and live status."""
        ...

    def list_constraints_by_target(
        self,
        target_type_key: str,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgConstraintDefinitionList:
        """List constraints that target a schema type key."""
        ...

    def delete_constraint(self, constraint_uuid: UuidInput) -> RtgConstraintDeleteResult:
        """Delete one constraint definition."""
        ...
