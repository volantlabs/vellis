"""Small deterministic conversion for successor domain values and stored activity JSON."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass

from vellis.domain import PropertyDefinition, ScalarValue, TimestampValue
from vellis.public_wire import public_result


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
            and not (
                isinstance(value, PropertyDefinition)
                and field.name == "allowed_values"
                and not value.allowed_values_present
            )
        }
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def serialize_wire(value) -> str:
    # The same public projection used by MCP is constructed before an operation commits.
    # Keeping one projection closes the post-commit "internal form serialized, public form
    # failed" gap without giving the transport transaction ownership.
    return json.dumps(
        public_result(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
