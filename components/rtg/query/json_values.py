from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import TypeGuard

from components.rtg.graph.protocol import JsonValue


def json_value_equal(left: JsonValue, right: JsonValue) -> bool:
    """Compare JSON values with kind-aware, exact numeric semantics."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) or _is_number(right):
        return (
            _is_number(left)
            and _is_number(right)
            and _number_decimal(left) == _number_decimal(right)
        )
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(json_value_equal(a, b) for a, b in zip(left, right, strict=True))
        )
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return left.keys() == right.keys() and all(
        json_value_equal(left[key], right[key]) for key in left
    )


def canonical_json_key(value: JsonValue) -> str:
    """Return a deterministic key consistent with ``json_value_equal``."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"boolean:{str(value).lower()}"
    if _is_number(value):
        return f"number:{_canonical_number(value)}"
    if isinstance(value, str):
        return f"string:{json.dumps(value, ensure_ascii=False)}"
    if isinstance(value, list):
        return "list:[" + ",".join(canonical_json_key(item) for item in value) + "]"
    if not isinstance(value, dict):
        raise TypeError("unsupported JSON value")
    return (
        "object:{"
        + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{canonical_json_key(value[key])}"
            for key in sorted(value)
        )
        + "}"
    )


def json_number_decimal(value: object) -> Decimal:
    """Return the exact finite Decimal value used by RTG JSON-number semantics."""
    return _number_decimal(value)


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number_decimal(value: object) -> Decimal:
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, float) and math.isfinite(value):
        return Decimal(str(value))
    raise ValueError("JSON numbers must be finite integers or floats")


def _canonical_number(value: object) -> str:
    number = _number_decimal(value)
    if number == 0:
        return "0"
    sign, raw_digits, decimal_exponent = number.as_tuple()
    exponent = int(decimal_exponent)
    digits = list(raw_digits)
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    magnitude = "".join(str(digit) for digit in digits)
    prefix = "-" if sign else ""
    return f"{prefix}{magnitude}e{exponent}"
