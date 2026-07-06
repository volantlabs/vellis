from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type UuidInput = UUID | str


@dataclass(frozen=True, slots=True)
class RtgSchemaField:
    required: bool
    value_kinds: tuple[str, ...]
    properties: dict[str, RtgSchemaField] = field(default_factory=dict)
    items: RtgSchemaField | None = None


@dataclass(frozen=True, slots=True)
class RtgAnchorSchemaPayload:
    required_data_types: tuple[str, ...] = ()
    optional_data_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgDataObjectSchemaPayload:
    properties: dict[str, RtgSchemaField] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgLinkSchemaPayload:
    allowed_source_types: tuple[str, ...]
    allowed_target_types: tuple[str, ...]


type RtgSchemaPayload = RtgAnchorSchemaPayload | RtgDataObjectSchemaPayload | RtgLinkSchemaPayload


@dataclass(frozen=True, slots=True)
class RtgSchemaDefinition:
    uuid: UUID | None
    kind: str
    type_key: str
    description: str
    payload: RtgSchemaPayload
    system: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgSchemaSnapshot:
    definitions: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class RtgSchemaDeleteResult:
    deleted_definition: RtgSchemaDefinition


@dataclass(frozen=True, slots=True)
class RtgSchemaDefinitionList:
    definitions: tuple[RtgSchemaDefinition, ...]


@dataclass(frozen=True, slots=True)
class RtgSchemaAssociatedDataTypeList:
    required_data_types: tuple[str, ...]
    optional_data_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RtgSchemaLinkParticipation:
    definition_uuid: UUID
    type_key: str
    direction: str
    allowed_source_types: tuple[str, ...]
    allowed_target_types: tuple[str, ...]
    live: bool


@dataclass(frozen=True, slots=True)
class RtgSchemaLinkParticipationList:
    links: tuple[RtgSchemaLinkParticipation, ...]


@dataclass(frozen=True, slots=True)
class RtgSchemaAnchorTypeSummary:
    definition_uuid: UUID
    type_key: str
    description: str
    live: bool


@dataclass(frozen=True, slots=True)
class RtgSchemaAnchorTypeSummaryList:
    anchor_types: tuple[RtgSchemaAnchorTypeSummary, ...]


@dataclass(frozen=True, slots=True)
class RtgSchemaPack:
    anchor_schemas: tuple[RtgSchemaDefinition, ...]
    associated_data_object_schemas: tuple[RtgSchemaDefinition, ...]
    link_schemas: tuple[RtgSchemaDefinition, ...]


class RtgSchemaError(Exception):
    """Base class for RTG Schema errors."""


class RtgSchemaDefinitionNotFound(RtgSchemaError):
    """A requested schema definition does not exist."""


class RtgSchemaSnapshotInvalid(RtgSchemaError):
    """A schema snapshot is malformed or internally inconsistent."""


class RtgSchemaUuidInvalid(RtgSchemaError):
    """A schema definition UUID is not parseable."""


class RtgSchemaUuidConflict(RtgSchemaError):
    """A schema definition UUID conflicts with another definition."""


class RtgSchemaKindInvalid(RtgSchemaError):
    """A schema definition kind is invalid."""


class RtgSchemaTypeInvalid(RtgSchemaError):
    """A schema type key is invalid."""


class RtgSchemaLiveConflict(RtgSchemaError):
    """A live schema definition conflicts with another live type key."""


class RtgSchemaPayloadInvalid(RtgSchemaError):
    """A schema definition payload is invalid."""


class RtgSchemaSystemValueInvalid(RtgSchemaError):
    """A schema definition system value is invalid."""


class RtgSchema(Protocol):
    @classmethod
    def empty(cls) -> RtgSchema:
        """Create an empty in-memory schema registry."""
        ...

    @classmethod
    def import_snapshot(cls, snapshot: RtgSchemaSnapshot) -> RtgSchema:
        """Create a schema registry from a snapshot."""
        ...

    def export_snapshot(self) -> RtgSchemaSnapshot:
        """Export a JSON-compatible schema snapshot."""
        ...

    def put_definition(self, definition: RtgSchemaDefinition) -> RtgSchemaDefinition:
        """Create or fully replace a schema definition."""
        ...

    def get_definition(self, definition_uuid: UuidInput) -> RtgSchemaDefinition:
        """Return one schema definition."""
        ...

    def list_definitions(
        self,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgSchemaDefinitionList:
        """List definitions, optionally filtered by kind and live status."""
        ...

    def list_definitions_by_type_key(
        self,
        schema_type_key: str,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgSchemaDefinitionList:
        """List definitions for one schema type key."""
        ...

    def list_anchor_data_type_keys(
        self,
        anchor_type_key: str,
        live: bool | None = True,
    ) -> RtgSchemaAssociatedDataTypeList:
        """List associated data type keys for one anchor schema."""
        ...

    def list_link_participation(
        self,
        type_key: str,
        direction: str = "both",
        live: bool | None = True,
    ) -> RtgSchemaLinkParticipationList:
        """List link schemas that mention a type key."""
        ...

    def list_anchor_type_summaries(
        self,
        live: bool | None = True,
    ) -> RtgSchemaAnchorTypeSummaryList:
        """List anchor schema type summaries."""
        ...

    def get_schema_pack(
        self,
        anchor_type_keys: tuple[str, ...],
        live: bool | None = True,
    ) -> RtgSchemaPack:
        """Return expanded schema-only details for anchor types."""
        ...

    def delete_definition(self, definition_uuid: UuidInput) -> RtgSchemaDeleteResult:
        """Delete one schema definition."""
        ...
