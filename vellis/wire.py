"""Small deterministic conversion for successor domain values and stored activity JSON."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass

from vellis.domain import ScalarValue, TimestampValue


def wire_value(value):
    if isinstance(value, ScalarValue):
        return {"kind": value.kind.value, "value": value.wire_value()}
    if isinstance(value, TimestampValue):
        return value.canonical
    if isinstance(value, tuple):
        return [wire_value(item) for item in value]
    if isinstance(value, list):
        return [wire_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): wire_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            field.name: wire_value(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def serialize_wire(value) -> str:
    return json.dumps(
        wire_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
