"""Framework-free requests and results for canonical changes and the sole draft."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vellis.domain import (
    Finding,
    GraphChangeRequest,
    GraphObject,
    ObjectUpsert,
    OperationOutcome,
    TypeDefinition,
    canonical_uuid,
)


class DraftCategory(StrEnum):
    DEFINITIONS = "definitions"
    ANCHORS = "anchors"
    ASSOCIATED_DATA = "associatedData"
    LINKS = "links"


class DraftOperation(StrEnum):
    ADD = "add"
    PATCH = "patch"
    REPLACE = "replace"
    REMOVE = "remove"


class ValidationScope(StrEnum):
    CURRENT = "current"
    DRAFT = "draft"


@dataclass(frozen=True, slots=True)
class DraftChangeRequest:
    definition_upserts: tuple[TypeDefinition, ...] = ()
    definition_removals: tuple[str, ...] = ()
    unstage_definition_keys: tuple[str, ...] = ()
    object_upserts: tuple[ObjectUpsert, ...] = ()
    object_removals: tuple[str, ...] = ()
    unstage_object_uuids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.definition_upserts, tuple) or not all(
            hasattr(value, "type_key") for value in self.definition_upserts
        ):
            raise ValueError("definition upserts must be a tuple of definitions")
        if not isinstance(self.object_upserts, tuple):
            raise ValueError("object upserts must be a tuple")
        for name in (
            "definition_removals",
            "unstage_definition_keys",
            "object_removals",
            "unstage_object_uuids",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(isinstance(value, str) for value in values):
                raise ValueError(f"{name} must be a tuple of text")
        object.__setattr__(
            self, "object_removals", tuple(canonical_uuid(value) for value in self.object_removals)
        )
        object.__setattr__(
            self,
            "unstage_object_uuids",
            tuple(canonical_uuid(value) for value in self.unstage_object_uuids),
        )


@dataclass(frozen=True, slots=True)
class DraftCounts:
    draft_present: bool
    raw_entry_count: int
    effective_change_count: int


@dataclass(frozen=True, slots=True)
class DraftChangeResult:
    outcome: OperationOutcome
    payload: DraftCounts | None = None


@dataclass(frozen=True, slots=True)
class DraftInspectionRequest:
    categories: tuple[DraftCategory, ...] = ()
    operations: tuple[DraftOperation, ...] = ()
    type_keys: tuple[str, ...] = ()
    uuids: tuple[str, ...] = ()
    limit: int | None = None
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.categories, tuple) or not all(
            isinstance(value, DraftCategory) for value in self.categories
        ):
            raise ValueError("draft categories must be a tuple")
        if not isinstance(self.operations, tuple) or not all(
            isinstance(value, DraftOperation) for value in self.operations
        ):
            raise ValueError("draft operations must be a tuple")
        if not isinstance(self.type_keys, tuple) or not all(
            isinstance(value, str) for value in self.type_keys
        ):
            raise ValueError("draft type keys must be a tuple of text")
        if not isinstance(self.uuids, tuple) or not all(
            isinstance(value, str) for value in self.uuids
        ):
            raise ValueError("draft UUIDs must be a tuple of text")
        object.__setattr__(self, "uuids", tuple(canonical_uuid(value) for value in self.uuids))


@dataclass(frozen=True, slots=True)
class DraftInspectionEntry:
    category: DraftCategory
    key: str
    operation: DraftOperation
    current: TypeDefinition | GraphObject | None
    staged: object
    proposed: TypeDefinition | GraphObject | None
    has_effect: bool


@dataclass(frozen=True, slots=True)
class DraftInspectionPayload:
    counts: DraftCounts
    returned_count: int
    entries: tuple[DraftInspectionEntry, ...]
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class DraftInspectionResult:
    outcome: OperationOutcome
    payload: DraftInspectionPayload | None = None


@dataclass(frozen=True, slots=True)
class ValidationRequest:
    scope: ValidationScope
    limit: int | None = None
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationPayload:
    total_findings: int
    clean: bool
    findings: tuple[Finding, ...]
    cursor: str | None = None
    raw_draft_entry_count: int | None = None
    effective_draft_change_count: int | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    outcome: OperationOutcome
    payload: ValidationPayload | None = None


ActiveChangeRequest = GraphChangeRequest
