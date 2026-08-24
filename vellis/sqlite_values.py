"""Explicit SQLite representations for Vellis scalar values."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from vellis.domain import ScalarValue, TimestampValue, ValueKind, canonical_number_text


def scalar_text(value: ScalarValue) -> str:
    content = value.value
    if value.kind is ValueKind.BOOLEAN:
        return "true" if content is True else "false"
    if value.kind is ValueKind.INTEGER:
        assert isinstance(content, int) and not isinstance(content, bool)
        return str(content)
    if value.kind is ValueKind.NUMBER:
        assert isinstance(content, float)
        return canonical_number_text(content)
    if isinstance(content, TimestampValue):
        return content.canonical
    assert isinstance(content, str)
    return content


def scalar_from_text(kind: str, value: str) -> ScalarValue:
    selected = ValueKind(kind)
    if selected is ValueKind.BOOLEAN:
        if value not in {"true", "false"}:
            raise ValueError("stored Boolean text is invalid")
        return ScalarValue.boolean(value == "true")
    if selected is ValueKind.INTEGER:
        return ScalarValue.integer(int(value))
    if selected is ValueKind.NUMBER:
        return ScalarValue.number(float(value))
    if selected is ValueKind.TEXT:
        return ScalarValue.text(value)
    if selected is ValueKind.DATE:
        return ScalarValue.date(value)
    return ScalarValue.timestamp(value)


def property_columns(value: ScalarValue | None, declared_kind: ValueKind) -> dict[str, object]:
    columns: dict[str, object] = {
        "value_kind": declared_kind.value,
        "is_null": int(value is None),
        "boolean_value": None,
        "integer_value": None,
        "number_value": None,
        "text_value": None,
        "date_value": None,
        "timestamp_epoch_seconds": None,
        "timestamp_nanosecond": None,
        "timestamp_text": None,
    }
    if value is None:
        return columns
    if value.kind is not declared_kind:
        raise ValueError("property value kind differs from its declaration")
    content = value.value
    if declared_kind is ValueKind.BOOLEAN:
        assert isinstance(content, bool)
        columns["boolean_value"] = int(content)
    elif declared_kind is ValueKind.INTEGER:
        assert isinstance(content, int) and not isinstance(content, bool)
        columns["integer_value"] = content
    elif declared_kind is ValueKind.NUMBER:
        assert isinstance(content, float)
        columns["number_value"] = content
    elif declared_kind is ValueKind.TEXT:
        assert isinstance(content, str)
        columns["text_value"] = content
    elif declared_kind is ValueKind.DATE:
        assert isinstance(content, str)
        columns["date_value"] = content
    else:
        assert isinstance(content, TimestampValue)
        columns["timestamp_epoch_seconds"] = content.epoch_seconds
        columns["timestamp_nanosecond"] = content.nanosecond
        columns["timestamp_text"] = content.canonical
    return columns


def bound_columns(value: ScalarValue | None, prefix: str) -> dict[str, object]:
    columns: dict[str, object] = {
        f"{prefix}_kind": None,
        f"{prefix}_integer": None,
        f"{prefix}_number": None,
        f"{prefix}_date": None,
        f"{prefix}_timestamp_epoch_seconds": None,
        f"{prefix}_timestamp_nanosecond": None,
        f"{prefix}_timestamp_text": None,
    }
    if value is None:
        return columns
    columns[f"{prefix}_kind"] = value.kind.value
    content = value.value
    if value.kind is ValueKind.INTEGER:
        assert isinstance(content, int) and not isinstance(content, bool)
        columns[f"{prefix}_integer"] = content
    elif value.kind is ValueKind.NUMBER:
        assert isinstance(content, float)
        columns[f"{prefix}_number"] = content
    elif value.kind is ValueKind.DATE:
        assert isinstance(content, str)
        columns[f"{prefix}_date"] = content
    elif value.kind is ValueKind.TIMESTAMP:
        assert isinstance(content, TimestampValue)
        columns[f"{prefix}_timestamp_epoch_seconds"] = content.epoch_seconds
        columns[f"{prefix}_timestamp_nanosecond"] = content.nanosecond
        columns[f"{prefix}_timestamp_text"] = content.canonical
    else:
        raise ValueError("only integer, number, date, or timestamp may be a bound")
    return columns


def bound_from_row(row: sqlite3.Row | Mapping[str, object], prefix: str) -> ScalarValue | None:
    kind_value = row[f"{prefix}_kind"]
    if kind_value is None:
        return None
    kind = ValueKind(str(kind_value))
    if kind is ValueKind.INTEGER:
        return ScalarValue.integer(_stored_int(row[f"{prefix}_integer"]))
    if kind is ValueKind.NUMBER:
        return ScalarValue.number(_stored_float(row[f"{prefix}_number"]))
    if kind is ValueKind.DATE:
        return ScalarValue.date(str(row[f"{prefix}_date"]))
    if kind is ValueKind.TIMESTAMP:
        return ScalarValue.timestamp(str(row[f"{prefix}_timestamp_text"]))
    raise ValueError("stored property bound kind is invalid")


def property_from_row(row: sqlite3.Row | Mapping[str, object]) -> ScalarValue | None:
    if bool(row["is_null"]):
        return None
    kind = ValueKind(str(row["value_kind"]))
    if kind is ValueKind.BOOLEAN:
        return ScalarValue.boolean(bool(row["boolean_value"]))
    if kind is ValueKind.INTEGER:
        return ScalarValue.integer(_stored_int(row["integer_value"]))
    if kind is ValueKind.NUMBER:
        return ScalarValue.number(_stored_float(row["number_value"]))
    if kind is ValueKind.TEXT:
        return ScalarValue.text(str(row["text_value"]))
    if kind is ValueKind.DATE:
        return ScalarValue.date(str(row["date_value"]))
    return ScalarValue.timestamp(str(row["timestamp_text"]))


def _stored_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("stored integer representation is invalid")
    return value


def _stored_float(value: object) -> float:
    if not isinstance(value, float):
        raise ValueError("stored number representation is invalid")
    return value
