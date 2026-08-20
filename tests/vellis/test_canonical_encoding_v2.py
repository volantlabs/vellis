"""Mutation-sensitive evidence for the VEL2 canonical encoder."""

from __future__ import annotations

import math

import pytest

from vellis.canonical_encoding import (
    ABSENT,
    ZERO_HASH,
    CanonicalHeader,
    OrderedValues,
    Record,
    RowDescriptor,
    SetValues,
    canonical_record_hash,
    encode,
    row_digest,
)
from vellis.domain import ScalarValue, parse_timestamp


def test_type_tags_keep_absence_null_boolean_integer_and_number_distinct() -> None:
    encodings = {encode(value) for value in (ABSENT, None, False, True, 0, 0.0)}
    assert len(encodings) == 6
    assert encode(-0.0) == encode(0.0)
    assert encode(ScalarValue.number(-0.0)) == encode(ScalarValue.number(0.0))


def test_ordered_and_set_like_collections_have_selected_ordering() -> None:
    assert encode(OrderedValues(("a", "b"))) != encode(OrderedValues(("b", "a")))
    assert encode(SetValues(("a", "b"))) == encode(SetValues(("b", "a")))


def test_record_field_order_is_explicit_and_semantically_significant() -> None:
    first = Record((("a", 1), ("b", 2)))
    second = Record((("b", 2), ("a", 1)))
    assert encode(first) != encode(second)


def test_encoder_rejects_values_outside_its_closed_family() -> None:
    with pytest.raises(TypeError, match="unsupported canonical value"):
        encode({"arbitrary": "json"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite binary64"):
        ScalarValue.number(math.inf)


def test_row_digest_changes_for_relation_identity_or_content() -> None:
    identity = Record((("uuid", "12345678-1234-4234-8234-123456789abc"),))
    content = Record((("typeKey", "life.person"),))
    baseline = row_digest("graph_object_version", identity, content)
    assert baseline != row_digest("definition_version", identity, content)
    assert baseline != row_digest("graph_object_version", Record((("uuid", "different"),)), content)
    assert baseline != row_digest(
        "graph_object_version", identity, Record((("typeKey", "life.group"),))
    )


def test_record_hash_sorts_descriptors_but_detects_header_and_row_changes() -> None:
    identity_a = Record((("typeKey", "a"),))
    identity_b = Record((("typeKey", "b"),))
    row_a = RowDescriptor("definition_version", identity_a, bytes.fromhex("01" * 32))
    row_b = RowDescriptor("definition_version", identity_b, bytes.fromhex("02" * 32))
    header = CanonicalHeader(
        lineage_uuid="12345678-1234-4234-8234-123456789abc",
        revision=0,
        recorded_at=parse_timestamp("2026-08-20T00:00:00Z"),
        initiator="owner",
        source=None,
        transition_kind="initialization",
        summary="Initialized blank Vellis database",
    )
    baseline = canonical_record_hash(ZERO_HASH, header, (row_b, row_a), ())
    assert baseline == canonical_record_hash(ZERO_HASH, header, (row_a, row_b), ())
    changed_row = RowDescriptor("definition_version", identity_b, bytes.fromhex("03" * 32))
    assert baseline != canonical_record_hash(ZERO_HASH, header, (row_a, changed_row), ())
    changed_header = CanonicalHeader(
        lineage_uuid=header.lineage_uuid,
        revision=0,
        recorded_at=header.recorded_at,
        initiator=header.initiator,
        source=None,
        transition_kind=header.transition_kind,
        summary="Different summary",
    )
    assert baseline != canonical_record_hash(ZERO_HASH, changed_header, (row_a, row_b), ())
