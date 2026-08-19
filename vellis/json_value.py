"""Lossless JSON values and their canonical semantic equality.

Realizes ``RTG::'JSON Value'``, ``RTG::'JSON Object'``, and ``RTG::'JSON Kind'``,
together with the JSON portion of ``VellisRequirements::canonicalSemanticEquality``:
equality is kind-sensitive, numbers compare by exact mathematical value, strings
compare by exact Unicode code-point sequence without normalization, arrays compare
recursively in order, objects compare recursively without member-order significance,
and a missing member stays distinct from a present null.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated

from pydantic import PlainValidator, WithJsonSchema

# Which JSON kind a value has is meaning here, not a detail of how it was parsed, so
# reading one is this module's decision and not a union heuristic's. Left to the union, a
# Boolean is tried before an exact decimal and read leniently accepts the numbers one and
# zero: an owner who stores 1 gets back true. Where a declaration says the property is a
# number that surfaces as a refusal, but inside an array or object no declaration reaches
# the member, so the substitution is silent and canonical. Field-level strictness does not
# repair it either, because a caller validating leniently overrides it. `normalize` already
# reads a value exactly — Boolean before integer, and every number to exact decimal — so
# validation goes through it and the union stands as the type it produces.
#
# The published shape says only that any JSON value belongs here. The default schema for an
# exact decimal describes a string, which would tell an agent the wrong thing about what it
# is holding and what it may write back, and the real constraint on a stored value is the
# owner's own definitions, which this could not express in any case.
type JsonValue = Annotated[
    None | bool | Decimal | str | list[JsonValue] | dict[str, JsonValue],
    PlainValidator(lambda value: normalize(value)),
    WithJsonSchema(
        {"description": "Any JSON value: an object, array, string, number, boolean, or null."}
    ),
]

# Stored integers must satisfy abs(value) < 10 ** this exponent. The write-side validity
# check and the decoder both use it, so the two directions describe exactly the same set
# of states: nothing acceptable is unreadable, and nothing readable is refused on write.
MAXIMUM_STORED_INTEGER_EXPONENT = 30

# The deepest nesting a stored JSON value may carry. Serializing and comparing a value
# recurse about twice per level, so accepting anything this side of the interpreter's
# limit would let a value be built that could not afterwards be written or compared.
# One screen at the point of entry keeps every later traversal safe.
MAXIMUM_NESTING_DEPTH = 100

__all__ = [
    "MAXIMUM_NESTING_DEPTH",
    "MAXIMUM_STORED_INTEGER_EXPONENT",
    "JsonKind",
    "JsonValue",
    "JsonValueError",
    "dumps",
    "json_equal",
    "json_kind",
    "loads",
    "normalize",
    "unencodable_reason",
    "value_size",
]


class JsonValueError(ValueError):
    """Raised when a value cannot form a lossless JSON value."""


class JsonKind(Enum):
    """The six JSON kinds RTG distinguishes."""

    NULL = "nullValue"
    BOOLEAN = "booleanValue"
    NUMBER = "numberValue"
    STRING = "stringValue"
    ARRAY = "arrayValue"
    OBJECT = "objectValue"


def normalize(value: object, _depth: int = 0) -> JsonValue:
    """Return ``value`` as a lossless JSON value, or raise :class:`JsonValueError`.

    Numbers become :class:`~decimal.Decimal` so that later comparison is by exact
    mathematical value rather than by binary floating-point identity. An ``int`` is
    already exact; a ``float`` is read through its shortest round-tripping literal
    so ``0.1`` does not acquire binary noise it never had in JSON text.

    Nesting is bounded here, at the point of entry, so that anything this function
    accepts can afterwards be serialized and compared without exhausting the stack.
    """
    if _depth > MAXIMUM_NESTING_DEPTH:
        raise JsonValueError(
            f"value nests deeper than {MAXIMUM_NESTING_DEPTH} levels, which is deeper "
            "than a stored value may be"
        )
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise JsonValueError(f"non-finite number is not a JSON value: {value!r}")
        return value
    if isinstance(value, float):
        try:
            candidate = Decimal(repr(value))
        except InvalidOperation as error:  # pragma: no cover - repr always parses
            raise JsonValueError(f"number is not a JSON value: {value!r}") from error
        if not candidate.is_finite():
            raise JsonValueError(f"non-finite number is not a JSON value: {value!r}")
        return candidate
    if isinstance(value, str):
        _reject_lone_surrogates(value)
        return value
    if isinstance(value, Mapping):
        members: dict[str, JsonValue] = {}
        for key, member in value.items():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(key, str):
                raise JsonValueError(f"JSON object member name must be a string: {key!r}")
            # A member name is stored and matched exactly as a member value is, so it is
            # screened the same way. Screening only values would leave the hole open.
            _reject_lone_surrogates(key)
            members[key] = normalize(member, _depth + 1)
        return members
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise JsonValueError("binary data is not a JSON value")
    if isinstance(value, Sequence):
        return [  # pyright: ignore[reportUnknownVariableType]
            normalize(element, _depth + 1)
            for element in value  # pyright: ignore[reportUnknownVariableType]
        ]
    raise JsonValueError(f"unsupported JSON value: {value!r}")


def _reject_lone_surrogates(value: str) -> None:
    """Refuse text that cannot be encoded, so it cannot reach storage or matching.

    Python strings can hold an unpaired surrogate, and a JSON escape can produce one,
    but no UTF-8 encoder will take one. Admitting it here would defer the failure
    to whichever component encodes first — the store or the pattern engine — where it
    would surface as an uncaught encoding error instead of a validation finding.
    """
    for character in value:
        if 0xD800 <= ord(character) <= 0xDFFF:
            raise JsonValueError(
                f"string contains the unpaired surrogate U+{ord(character):04X}, "
                "which is not encodable text"
            )


def unencodable_reason(text: str) -> str | None:
    """Return why ``text`` cannot be stored, or ``None`` when it can.

    Definition text — type keys, names, descriptions, pattern expressions — is ordinary
    Python text rather than a JSON value, so it does not pass through :func:`normalize`.
    It still has to be encodable, because it reaches the same store and the same engine.
    """
    for character in text:
        if 0xD800 <= ord(character) <= 0xDFFF:
            return f"contains the unpaired surrogate U+{ord(character):04X}, which is not encodable"
    return None


def json_kind(value: JsonValue) -> JsonKind:
    """Return the JSON kind of an already normalized value.

    An un-normalized value raises rather than being reported as an object, so a raw
    ``int`` or a foreign object cannot travel further as a misidentified kind.
    """
    if value is None:
        return JsonKind.NULL
    if isinstance(value, bool):
        return JsonKind.BOOLEAN
    if isinstance(value, Decimal):
        return JsonKind.NUMBER
    if isinstance(value, str):
        return JsonKind.STRING
    if isinstance(value, list):
        return JsonKind.ARRAY
    if isinstance(value, dict):
        return JsonKind.OBJECT
    raise JsonValueError(f"value is not a normalized JSON value: {value!r}")


def json_equal(left: JsonValue, right: JsonValue) -> bool:
    """Compare two normalized JSON values by canonical semantic equality."""
    left_kind = json_kind(left)
    if left_kind is not json_kind(right):
        return False
    if left_kind is JsonKind.NULL:
        return True
    if left_kind is JsonKind.BOOLEAN:
        return left is right
    if left_kind is JsonKind.NUMBER:
        assert isinstance(left, Decimal) and isinstance(right, Decimal)
        return left.compare(right) == 0
    if left_kind is JsonKind.STRING:
        return left == right
    if left_kind is JsonKind.ARRAY:
        assert isinstance(left, list) and isinstance(right, list)
        return len(left) == len(right) and all(
            json_equal(element, other) for element, other in zip(left, right, strict=True)
        )
    assert isinstance(left, dict) and isinstance(right, dict)
    if left.keys() != right.keys():
        return False
    return all(json_equal(member, right[name]) for name, member in left.items())


def _json_equality_key(value: JsonValue) -> tuple[object, ...]:
    """Return the immutable key for canonical semantic JSON equality.

    This is deliberately a value key, not a serialization or persisted identity.
    Its kind tag keeps Booleans distinct from Python-equal numbers, while Decimal's
    exact numeric equality makes equivalent spellings such as ``1`` and ``1.0``
    share a key. Arrays retain order and object members are ordered only inside the
    key because their declaration order has no meaning.

    Callers use one key construction per collection member for set and counter work;
    recursive construction visits each nested member once.
    """
    kind = json_kind(value)
    if kind is JsonKind.NULL:
        return (kind,)
    if kind is JsonKind.BOOLEAN:
        assert isinstance(value, bool)
        return (kind, value)
    if kind is JsonKind.NUMBER:
        assert isinstance(value, Decimal)
        return (kind, value)
    if kind is JsonKind.STRING:
        assert isinstance(value, str)
        return (kind, value)
    if kind is JsonKind.ARRAY:
        assert isinstance(value, list)
        return (kind, tuple(_json_equality_key(element) for element in value))
    assert isinstance(value, dict)
    return (
        kind,
        tuple(
            (name, _json_equality_key(member))
            for name, member in sorted(value.items(), key=lambda item: item[0])
        ),
    )


def value_size(value: JsonValue) -> int | None:
    """Return the size a value shape may constrain, or ``None`` when it has none.

    String size is the number of Unicode code points without normalization; array
    and object size are the number of elements and members respectively.
    """
    kind = json_kind(value)
    if kind is JsonKind.STRING:
        assert isinstance(value, str)
        return len(value)
    if kind is JsonKind.ARRAY:
        assert isinstance(value, list)
        return len(value)
    if kind is JsonKind.OBJECT:
        assert isinstance(value, dict)
        return len(value)
    return None


def loads(text: str) -> JsonValue:
    """Parse JSON text into lossless JSON values."""
    try:
        parsed = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    except (ValueError, ArithmeticError) as error:
        # A number whose exponent is outside the decimal library's range raises
        # InvalidOperation, which is an ArithmeticError rather than a ValueError.
        raise JsonValueError(f"malformed JSON text: {error}") from error
    except RecursionError as error:
        raise JsonValueError("JSON text nests too deeply to read") from error
    return normalize(parsed)


def dumps(value: JsonValue) -> str:
    """Serialize a normalized JSON value, preserving numeric text exactly.

    Object members are written in sorted order so that a stored form is stable;
    member order carries no meaning, so sorting loses nothing.
    """
    kind = json_kind(value)
    if kind is JsonKind.NULL:
        return "null"
    if kind is JsonKind.BOOLEAN:
        return "true" if value else "false"
    if kind is JsonKind.NUMBER:
        assert isinstance(value, Decimal)
        return str(value)
    if kind is JsonKind.STRING:
        assert isinstance(value, str)
        return json.dumps(value, ensure_ascii=False)
    if kind is JsonKind.ARRAY:
        assert isinstance(value, list)
        return "[" + ",".join(dumps(element) for element in value) + "]"
    assert isinstance(value, dict)
    members = (
        f"{json.dumps(name, ensure_ascii=False)}:{dumps(member)}"
        for name, member in sorted(value.items())
    )
    return "{" + ",".join(members) + "}"
