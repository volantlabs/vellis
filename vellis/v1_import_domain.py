"""Typed result values for first-use v1 initialization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class V1ImportError(ValueError):
    """The selected source cannot form or publish the requested initial state."""


class V1PublicationDurabilityError(RuntimeError):
    """The import is published but its directory flush could not be confirmed."""


class V1Disposition(StrEnum):
    PRESERVED = "preserved"
    CONVERTED = "converted"
    OMITTED = "omitted"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class V1Counts:
    definitions: int
    anchors: int
    associated_data: int
    links: int


@dataclass(frozen=True, slots=True)
class V1DispositionCounts:
    preserved: int
    converted: int
    omitted: int
    blocking: int


@dataclass(frozen=True, slots=True)
class V1ImportPreview:
    source_path: Path
    source_sha256: str
    source_byte_count: int
    candidate_sha256: str
    report_sha256: str
    candidate_counts: V1Counts
    disposition_counts: V1DispositionCounts
    acceptable: bool
    report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class V1ImportResult:
    database_path: Path
    report_path: Path
    lineage_uuid: str
    source_sha256: str
    report_sha256: str
    resulting_revision: int = 0
