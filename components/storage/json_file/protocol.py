from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from os import PathLike
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class JsonDocumentMetadata:
    relative_path: str
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class JsonDocument:
    value: JsonValue
    metadata: JsonDocumentMetadata


@dataclass(frozen=True, slots=True)
class JsonDocumentList:
    documents: tuple[JsonDocumentMetadata, ...]
    total: int
    next_offset: int | None = None


class StorageError(Exception):
    """Base class for JSON File Storage errors."""


class StorageRootInvalid(StorageError):
    """The configured storage root path is not a valid directory root."""


class StorageRootUnavailable(StorageError):
    """The configured storage root could not be created or opened."""


class StoragePermissionDenied(StorageError):
    """The filesystem denied access to the requested storage operation."""


class StoragePathInvalid(StorageError):
    """A relative document or directory path is invalid for this storage root."""


class JsonDocumentNotFound(StorageError):
    """The requested JSON document does not exist."""


class JsonDocumentInvalid(StorageError):
    """The requested JSON document exists but does not contain valid JSON."""


class JsonValueNotSerializable(StorageError):
    """The supplied value cannot be serialized as JSON."""


class StorageWriteFailed(StorageError):
    """A filesystem write operation failed."""


class StorageReadFailed(StorageError):
    """A filesystem read operation failed."""


class StorageDeleteFailed(StorageError):
    """A filesystem delete operation failed."""


class StorageDirectoryNotFound(StorageError):
    """The requested storage directory does not exist."""


class JsonFileStorage(Protocol):
    @classmethod
    def open(cls, root_path: str | PathLike[str]) -> JsonFileStorage:
        """Open a storage handle bound to a local filesystem root."""
        ...

    def write(
        self,
        relative_path: str | PathLike[str],
        json_value: JsonValue,
    ) -> JsonDocumentMetadata:
        """Create or fully replace a JSON document."""
        ...

    def read(self, relative_path: str | PathLike[str]) -> JsonDocument:
        """Read and parse a JSON document."""
        ...

    def delete(self, relative_path: str | PathLike[str]) -> JsonDocumentMetadata:
        """Delete a JSON document."""
        ...

    def list(
        self,
        relative_directory_path: str | PathLike[str] = ".",
        offset: int = 0,
        limit: int = 100,
    ) -> JsonDocumentList:
        """Recursively list JSON documents under a storage directory."""
        ...
