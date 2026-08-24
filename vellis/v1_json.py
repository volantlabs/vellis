"""Canonical JSON confined to the streamed v1 compatibility boundary."""

from __future__ import annotations

import json
import re
from decimal import Decimal

_NUMBER = re.compile(
    r"(?P<sign>-?)(?P<integer>0|[1-9][0-9]*)"
    r"(?:\.(?P<fraction>[0-9]+))?(?:[eE](?P<exponent>[+-]?[0-9]+))?\Z"
)


def canonical_legacy_json(value: object) -> str:
    """Encode one legacy subtree without passing a number through binary64."""
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("legacy JSON number must be finite")
        return canonical_number(str(value))
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical_legacy_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("legacy JSON object keys must be text")
        members = (
            f"{json.dumps(key, ensure_ascii=False)}:{canonical_legacy_json(value[key])}"
            for key in sorted(value)
        )
        return "{" + ",".join(members) + "}"
    raise ValueError(f"unsupported legacy JSON value: {type(value).__name__}")


def decode_legacy_json(value: str) -> object:
    return json.loads(value, parse_int=int, parse_float=Decimal, parse_constant=_reject_constant)


def canonical_number(value: str) -> str:
    match = _NUMBER.fullmatch(value)
    if match is None:
        raise ValueError("invalid JSON number")
    sign = match.group("sign")
    fraction = match.group("fraction") or ""
    digits = (match.group("integer") + fraction).lstrip("0")
    if digits == "":
        return "0"
    exponent = int(match.group("exponent") or "0") - len(fraction)
    while digits.endswith("0"):
        digits = digits[:-1]
        exponent += 1
    point = len(digits) + exponent
    scientific_exponent = len(digits) - 1 + exponent
    plain_length = _plain_length(digits, exponent, point)
    scientific_length = len(digits) + (1 if len(digits) > 1 else 0)
    scientific_length += 1 + len(str(scientific_exponent))
    if plain_length <= scientific_length:
        body = _plain_number(digits, exponent, point)
    else:
        body = digits[0]
        if len(digits) > 1:
            body += "." + digits[1:]
        body += f"e{scientific_exponent}"
    return sign + body


def _plain_length(digits: str, exponent: int, point: int) -> int:
    if exponent >= 0:
        return len(digits) + exponent
    if point > 0:
        return len(digits) + 1
    return 2 - point + len(digits)


def _plain_number(digits: str, exponent: int, point: int) -> str:
    if exponent >= 0:
        return digits + "0" * exponent
    if point > 0:
        return digits[:point] + "." + digits[point:]
    return "0." + "0" * -point + digits


def _reject_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")
