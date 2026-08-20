"""Closed binary encoding used only for Vellis canonical ledger hashes.

The tag assignments and framing below are part of the ``user_version = 1`` database format.
Changing either requires a new database format decision; it is not an internal refactor.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Final

from vellis.domain import ScalarValue, TimestampValue, canonical_date

ZERO_HASH: Final = bytes(32)
CANONICAL_CONTEXT: Final = "vellis-canonical-1"


class _Tag(IntEnum):
    ABSENT = 0x01
    NULL = 0x02
    FALSE = 0x03
    TRUE = 0x04
    INTEGER = 0x05
    NUMBER = 0x06
    TEXT = 0x07
    DATE = 0x08
    TIMESTAMP = 0x09
    BYTES = 0x0A
    ORDERED = 0x0B
    SET = 0x0C
    RECORD = 0x0D


@dataclass(frozen=True, slots=True)
class Absent:
    """An explicitly absent optional field; distinct from null."""


ABSENT: Final = Absent()


@dataclass(frozen=True, slots=True)
class DateText:
    value: str

    def __post_init__(self) -> None:
        canonical_date(self.value)


@dataclass(frozen=True, slots=True)
class OrderedValues:
    values: tuple[CanonicalValue, ...]


@dataclass(frozen=True, slots=True)
class SetValues:
    values: tuple[CanonicalValue, ...]


@dataclass(frozen=True, slots=True)
class Record:
    """Fields supplied in the fixed order declared by the caller's row schema."""

    fields: tuple[tuple[str, CanonicalValue], ...]


CanonicalValue = (
    Absent
    | None
    | bool
    | int
    | float
    | str
    | bytes
    | DateText
    | TimestampValue
    | ScalarValue
    | OrderedValues
    | SetValues
    | Record
)


@dataclass(frozen=True, slots=True)
class RowDescriptor:
    relation_name: str
    identity: Record
    row_digest: bytes

    def __post_init__(self) -> None:
        if len(self.row_digest) != 32:
            raise ValueError("row digest must contain 32 bytes")


@dataclass(frozen=True, slots=True)
class CanonicalHeader:
    lineage_uuid: str
    revision: int
    recorded_at: TimestampValue
    initiator: str
    source: str | None
    transition_kind: str
    summary: str
    v1_report_digest: bytes | None = None

    def as_record(self) -> Record:
        return Record(
            (
                ("lineageUuid", self.lineage_uuid),
                ("revision", self.revision),
                ("recordedAt", self.recorded_at),
                ("initiator", self.initiator),
                ("source", ABSENT if self.source is None else self.source),
                ("transitionKind", self.transition_kind),
                ("summary", self.summary),
                (
                    "v1ReportDigest",
                    ABSENT if self.v1_report_digest is None else self.v1_report_digest,
                ),
            )
        )


def encode(value: CanonicalValue) -> bytes:
    """Encode one value from the deliberately closed canonical value family."""
    atom = _encode_atom(value)
    if atom is not None:
        return atom
    if isinstance(value, DateText):
        return _variable(_Tag.DATE, value.value.encode("ascii"))
    if isinstance(value, TimestampValue):
        return _variable(_Tag.TIMESTAMP, value.canonical.encode("ascii"))
    if isinstance(value, ScalarValue):
        return _encode_scalar(value)
    if isinstance(value, OrderedValues):
        return _collection(_Tag.ORDERED, tuple(encode(item) for item in value.values))
    if isinstance(value, SetValues):
        members = tuple(sorted(encode(item) for item in value.values))
        return _collection(_Tag.SET, members)
    if isinstance(value, Record):
        return _encode_record(value)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _encode_atom(value: CanonicalValue) -> bytes | None:
    if isinstance(value, Absent):
        return _tag(_Tag.ABSENT)
    if value is None:
        return _tag(_Tag.NULL)
    if value is False:
        return _tag(_Tag.FALSE)
    if value is True:
        return _tag(_Tag.TRUE)
    if isinstance(value, int):
        return _variable(_Tag.INTEGER, str(value).encode("ascii"))
    if isinstance(value, float):
        normalized = ScalarValue.number(value).value
        assert isinstance(normalized, float)
        return _tag(_Tag.NUMBER) + struct.pack(">d", normalized)
    if isinstance(value, str):
        return _variable(_Tag.TEXT, value.encode("utf-8"))
    if isinstance(value, bytes):
        return _variable(_Tag.BYTES, value)
    return None


def row_digest(relation_name: str, identity: Record, content: Record) -> bytes:
    payload = _frame(relation_name.encode("utf-8"))
    payload += _frame(encode(identity))
    payload += _frame(encode(content))
    return hashlib.sha256(payload).digest()


def canonical_record_hash(
    previous_hash: bytes,
    header: CanonicalHeader,
    introduced: tuple[RowDescriptor, ...],
    retired: tuple[RowDescriptor, ...],
) -> bytes:
    if len(previous_hash) != 32:
        raise ValueError("previous canonical hash must contain 32 bytes")
    payload = _frame(CANONICAL_CONTEXT.encode("ascii")) + previous_hash
    payload += _frame(encode(header.as_record()))
    payload += _descriptors(introduced)
    payload += _descriptors(retired)
    return hashlib.sha256(payload).digest()


def _encode_scalar(value: ScalarValue) -> bytes:
    content = value.value
    if isinstance(content, TimestampValue):
        encoded: CanonicalValue = content
    elif value.kind.value == "date":
        assert isinstance(content, str)
        encoded = DateText(content)
    else:
        encoded = content
    return _variable(
        _Tag.RECORD, _frame(value.kind.value.encode("ascii")) + _frame(encode(encoded))
    )


def _encode_record(value: Record) -> bytes:
    fields = tuple(
        _frame(name.encode("utf-8")) + _frame(encode(content)) for name, content in value.fields
    )
    return _collection(_Tag.RECORD, fields)


def _descriptors(values: tuple[RowDescriptor, ...]) -> bytes:
    ordered = sorted(values, key=lambda value: (value.relation_name, encode(value.identity)))
    members = tuple(
        _frame(value.relation_name.encode("utf-8"))
        + _frame(encode(value.identity))
        + _frame(value.row_digest)
        for value in ordered
    )
    return _collection(_Tag.ORDERED, members)


def _collection(tag: _Tag, members: tuple[bytes, ...]) -> bytes:
    return _variable(tag, b"".join(_frame(member) for member in members))


def _variable(tag: _Tag, payload: bytes) -> bytes:
    return _tag(tag) + _frame(payload)


def _tag(value: _Tag) -> bytes:
    return bytes((value,))


def _frame(value: bytes) -> bytes:
    return struct.pack(">Q", len(value)) + value
