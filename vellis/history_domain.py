"""Typed owner-facing history and activity-mode values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vellis.domain import (
    PUBLIC_ITEM_LIMIT,
    Finding,
    OperationStatus,
    TimestampValue,
    TransitionKind,
    canonical_uuid,
)


class HistoryKind(StrEnum):
    CANONICAL = "canonical"
    ACTIVITY = "activity"


class ActivityMode(StrEnum):
    SEMANTIC = "semantic"
    VERBOSE = "verbose"


class ActivityOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TimeHistoryRange:
    start: TimestampValue | None = None
    end: TimestampValue | None = None

    def __post_init__(self) -> None:
        if self.start is not None and not isinstance(self.start, TimestampValue):
            raise ValueError("history start must be a timestamp")
        if self.end is not None and not isinstance(self.end, TimestampValue):
            raise ValueError("history end must be a timestamp")


@dataclass(frozen=True, slots=True)
class SequenceHistoryRange:
    after: int | None = None
    through: int | None = None

    def __post_init__(self) -> None:
        for value in (self.after, self.through):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("history sequence bounds must be nonnegative integers")


HistoryRange = TimeHistoryRange | SequenceHistoryRange


@dataclass(frozen=True, slots=True)
class HistoryRequest:
    kind: HistoryKind
    maximum_records: int
    range: HistoryRange | None = None
    include_verbose: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.kind, HistoryKind):
            raise ValueError("history kind is invalid")
        if (
            type(self.maximum_records) is not int
            or not 1 <= self.maximum_records <= PUBLIC_ITEM_LIMIT
        ):
            raise ValueError("history maximum must be between 1 and 1000")
        if self.range is not None and not isinstance(
            self.range, TimeHistoryRange | SequenceHistoryRange
        ):
            raise ValueError("history range is invalid")
        if type(self.include_verbose) is not bool:
            raise ValueError("include_verbose must be Boolean")


@dataclass(frozen=True, slots=True)
class CanonicalHistoryEntry:
    revision: int
    recorded_at: TimestampValue
    initiator: str
    source: str | None
    transition_kind: TransitionKind
    summary: str
    affected_type_keys: tuple[str, ...]
    affected_uuids: tuple[str, ...]

    def __post_init__(self) -> None:
        _natural(self.revision, "canonical revision")
        if not isinstance(self.recorded_at, TimestampValue):
            raise ValueError("canonical recorded time is invalid")
        _text(self.initiator, "canonical initiator")
        _optional_text(self.source, "canonical source")
        if not isinstance(self.transition_kind, TransitionKind):
            raise ValueError("canonical transition kind is invalid")
        _text(self.summary, "canonical summary")
        _sorted_unique_text_tuple(self.affected_type_keys, "affected type keys")
        _sorted_unique_uuid_tuple(self.affected_uuids)


@dataclass(frozen=True, slots=True)
class ActivityHistoryEntry:
    sequence: int
    recorded_at: TimestampValue
    capability: str
    outcome: ActivityOutcome
    initiator: str
    source: str | None
    evaluated_revision: int | None
    resulting_revision: int | None
    summary: str
    semantic_payload: object
    verbose_payload: object | None = None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("activity sequence must be positive")
        if not isinstance(self.recorded_at, TimestampValue):
            raise ValueError("activity recorded time is invalid")
        _text(self.capability, "activity capability")
        if not isinstance(self.outcome, ActivityOutcome):
            raise ValueError("activity outcome is invalid")
        _text(self.initiator, "activity initiator")
        _optional_text(self.source, "activity source")
        if self.evaluated_revision is not None:
            _natural(self.evaluated_revision, "evaluated revision")
        if self.resulting_revision is not None:
            _natural(self.resulting_revision, "resulting revision")
        _text(self.summary, "activity summary")
        if not isinstance(self.semantic_payload, dict):
            raise ValueError("semantic activity payload must be an object")


@dataclass(frozen=True, slots=True)
class CanonicalHistoryPayload:
    head_sequence: int
    entries: tuple[CanonicalHistoryEntry, ...]

    def __post_init__(self) -> None:
        _natural(self.head_sequence, "canonical head")
        _instance_tuple(self.entries, CanonicalHistoryEntry, "canonical entries")


@dataclass(frozen=True, slots=True)
class ActivityHistoryPayload:
    head_sequence: int
    entries: tuple[ActivityHistoryEntry, ...]

    def __post_init__(self) -> None:
        _natural(self.head_sequence, "activity head")
        _instance_tuple(self.entries, ActivityHistoryEntry, "activity entries")


HistoryPayload = CanonicalHistoryPayload | ActivityHistoryPayload


@dataclass(frozen=True, slots=True)
class HistoryResult:
    status: OperationStatus
    summary: str
    findings: tuple[Finding, ...]
    evaluated_revision: int | None
    payload: HistoryPayload | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperationStatus):
            raise ValueError("history status is invalid")
        _text(self.summary, "history summary")
        _instance_tuple(self.findings, Finding, "history findings")
        if self.evaluated_revision is not None:
            _natural(self.evaluated_revision, "evaluated revision")
        if self.status is OperationStatus.ACCEPTED and not isinstance(
            self.payload, CanonicalHistoryPayload | ActivityHistoryPayload
        ):
            raise ValueError("accepted history requires its selected payload")
        if self.status is OperationStatus.REJECTED and self.payload is not None:
            raise ValueError("rejected history cannot carry a payload")


def _natural(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")


def _text(value, label):
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{label} must be nonempty text")


def _optional_text(value, label):
    if value is not None:
        _text(value, label)


def _text_tuple(values, label):
    if not isinstance(values, tuple) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{label} must be a tuple of text")


def _sorted_unique_text_tuple(values, label):
    _text_tuple(values, label)
    if any(value == "" for value in values):
        raise ValueError(f"{label} must contain nonempty text")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be sorted and duplicate-free")


def _sorted_unique_uuid_tuple(values):
    _text_tuple(values, "affected UUIDs")
    if any(canonical_uuid(value) != value for value in values):
        raise ValueError("affected UUIDs must be canonical lowercase UUIDs")
    if values != tuple(sorted(set(values))):
        raise ValueError("affected UUIDs must be sorted and duplicate-free")


def _instance_tuple(values, expected, label):
    if not isinstance(values, tuple) or any(not isinstance(value, expected) for value in values):
        raise ValueError(f"{label} have invalid types")
