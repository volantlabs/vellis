"""Normalized SQLite encoding for Vellis canonical values.

This module is a physical realization, not RTG authority.  It deliberately stores
addressable scalar fields and child occurrences instead of serialized graph objects or
definition-set documents.  Nested JSON arrays and objects remain one property value;
the public language has no path-level meaning to normalize further.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from decimal import Decimal
from enum import Enum
from sqlite3 import SQLITE_LIMIT_VARIABLE_NUMBER, Connection

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DefinitionEntry,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    PropertyConstraint,
    StringPattern,
    ValueRange,
    ValueShape,
    relationship_identity,
)
from vellis.graph import Anchor, AssociatedDataObject, GraphObject, Link, ObjectKind, SystemMetadata
from vellis.json_value import JsonKind, JsonValue, dumps, json_kind, loads

__all__ = [
    "definition_content_stats",
    "definition_entry_digest",
    "definition_identity",
    "definition_identity_from_stats",
    "definition_set_stats_from_storage",
    "proposal_definition_stats_from_storage",
    "insert_definition_entry",
    "insert_definition_entries",
    "insert_associated_data_value",
    "insert_object_value",
    "json_storage_fields",
    "json_storage_value",
    "load_definition_set",
    "load_object_value",
    "object_identity",
    "normalized_state_identity",
    "adjust_semantic_summary",
    "graph_entry_digest",
    "proposal_entry_digest",
    "recomputed_graph_summary",
    "semantic_identity",
    "semantic_row_summary",
    "verify_state_summaries",
    "verify_proposal_summaries",
    "verify_normalized_identities",
]


def _canonical_decimal(value: Decimal) -> str:
    """Return a context-free exact spelling, collapsing only equal decimal values."""
    if value.is_zero():
        return "0"
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("a non-finite decimal has no canonical JSON-number identity")
    significant = list(digits)
    while significant[-1] == 0:
        significant.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in significant)
    return f"{'-' if sign else ''}{coefficient}e{exponent}"


def semantic_identity(value: object) -> str:
    """Hash a typed, recursively framed semantic value without ambiguous flattening."""
    digest = hashlib.sha256()

    def add(each: object) -> None:
        if each is None:
            digest.update(b"N")
            return
        if isinstance(each, bool):
            digest.update(b"B1" if each else b"B0")
            return
        if isinstance(each, Decimal):
            canonical = _canonical_decimal(each)
            encoded = canonical.encode("ascii")
            digest.update(b"M" + len(encoded).to_bytes(8, "big") + encoded)
            return
        if isinstance(each, Enum):
            add(each.value)
            return
        if isinstance(each, (tuple, list)):
            digest.update(b"L" + len(each).to_bytes(8, "big"))
            for member in each:
                add(member)
            return
        if isinstance(each, (set, frozenset)):
            members = sorted(each, key=semantic_identity)
            digest.update(b"U" + len(members).to_bytes(8, "big"))
            for member in members:
                add(member)
            return
        if isinstance(each, dict):
            members = sorted(each.items())
            digest.update(b"D" + len(members).to_bytes(8, "big"))
            for key, member in members:
                add(key)
                add(member)
            return
        if isinstance(each, int):
            encoded = str(each).encode("ascii")
            digest.update(b"I" + len(encoded).to_bytes(8, "big") + encoded)
            return
        if not isinstance(each, str):
            raise TypeError(f"unsupported semantic identity value: {type(each).__name__}")
        encoded = each.encode("utf-8")
        digest.update(b"S" + len(encoded).to_bytes(8, "big") + encoded)

    add(value)
    return digest.hexdigest()


def semantic_row_summary(rows: Iterable[object]) -> tuple[int, str]:
    """Summarize a keyed or occurrence-bearing row stream with constant memory.

    Every caller includes the row's semantic key (or event occurrence) in each value.
    Count plus a 256-bit modular accumulator therefore preserves multiplicity while
    avoiding a resident tuple proportional to the stored population.
    """
    count = 0
    accumulator = 0
    for row in rows:
        accumulator = (accumulator + int(semantic_identity(row), 16)) % (1 << 256)
        count += 1
    return count, f"{accumulator:064x}"


_IDENTITY_MODULUS = 1 << 256


def adjust_semantic_summary(
    accumulator: str,
    entry_count: int,
    *,
    removed: Iterable[str] = (),
    added: Iterable[str] = (),
) -> tuple[str, int]:
    """Apply bounded member changes to one modular semantic summary."""
    value = int(accumulator, 16)
    count = entry_count
    for digest in removed:
        value = (value - int(digest, 16)) % _IDENTITY_MODULUS
        count -= 1
    for digest in added:
        value = (value + int(digest, 16)) % _IDENTITY_MODULUS
        count += 1
    if count < 0:
        raise ValueError("a semantic summary cannot contain a negative number of entries")
    return f"{value:064x}", count


def graph_entry_digest(uuid: str, content_identity: str) -> str:
    """Return one current graph membership's independently composable digest."""
    return semantic_identity((uuid, content_identity))


def proposal_entry_digest(
    uuid: str, object_kind: str, operation: str, content_identity: str | None
) -> str:
    """Return one keyed proposal entry's path-independent digest."""
    return semantic_identity((uuid, object_kind, operation, content_identity))


def recomputed_graph_summary(connection: Connection) -> tuple[int, str]:
    """Recompute current graph meaning for an explicit full-state integrity boundary."""
    return semantic_row_summary(
        (str(uuid), str(identity))
        for uuid, identity in connection.execute(
            "SELECT c.uuid, v.content_identity FROM current_graph_object AS c"
            " JOIN object_value AS v ON v.id = c.object_value_id"
        )
    )


def normalized_state_identity(connection: Connection) -> str:
    """Commit to normalized current/prospective meaning from maintained summaries."""
    head = connection.execute(
        "SELECT revision, active_definition_set_id, proposed_definition_set_id,"
        " graph_entry_count, graph_accumulator"
        " FROM state_head WHERE id = 0"
    ).fetchone()
    if head is None:
        raise ValueError("normalized state has no head")
    overlay = connection.execute(
        "SELECT accumulator, entry_count FROM proposal_overlay_state WHERE id = 0"
    ).fetchone()
    if overlay is None:
        raise ValueError("normalized state has no proposal-overlay summary")
    return semantic_identity(
        (
            "normalizedState",
            int(head[0]),
            str(head[1]),
            None if head[2] is None else str(head[2]),
            (int(head[3]), str(head[4])),
            semantic_identity(("graphOverlay", str(overlay[0]), int(overlay[1]))),
        )
    )


def verify_state_summaries(connection: Connection) -> str | None:
    """Return the first maintained-state summary that differs from normalized rows."""
    head = connection.execute(
        "SELECT graph_entry_count, graph_accumulator FROM state_head WHERE id = 0"
    ).fetchone()
    if head is None:
        return "normalized state has no maintained graph summary"
    actual_count, actual_accumulator = recomputed_graph_summary(connection)
    if (int(head[0]), str(head[1])) != (actual_count, actual_accumulator):
        return "current graph summary does not match its normalized rows"
    return None


def json_storage_fields(value: JsonValue) -> tuple[str, int | None, str | None, str | None]:
    kind = json_kind(value)
    if kind is JsonKind.NULL:
        return kind.value, None, None, None
    if kind is JsonKind.BOOLEAN:
        assert isinstance(value, bool)
        return kind.value, int(value), None, None
    if kind is JsonKind.NUMBER:
        assert isinstance(value, Decimal)
        return kind.value, None, _canonical_decimal(value), None
    if kind is JsonKind.STRING:
        assert isinstance(value, str)
        return kind.value, None, None, value
    return kind.value, None, None, dumps(value)


def json_storage_value(kind: object, boolean: object, number: object, text: object) -> JsonValue:
    parsed = JsonKind(str(kind))
    if parsed is JsonKind.NULL:
        return None
    if parsed is JsonKind.BOOLEAN:
        return bool(boolean)
    if parsed is JsonKind.NUMBER:
        return Decimal(str(number))
    if parsed is JsonKind.STRING:
        return str(text)
    return loads(str(text))


def object_identity(value: GraphObject) -> str:
    common = (
        value.uuid,
        value.type_key,
        tuple(sorted(value.system_metadata.members.items())),
    )
    if isinstance(value, Anchor):
        meaning: object = (ObjectKind.ANCHOR.value, common, value.display_name)
    elif isinstance(value, AssociatedDataObject):
        meaning = (
            ObjectKind.ASSOCIATED_DATA.value,
            common,
            semantic_row_summary(sorted(value.anchor_uuids)),
            tuple(sorted(value.properties.items())),
        )
    else:
        meaning = (ObjectKind.LINK.value, common, value.source_uuid, value.target_uuid)
    return semantic_identity(meaning)


def insert_associated_data_value(
    connection: Connection,
    value_without_anchors: AssociatedDataObject,
    anchor_rows: Callable[[], Iterable[str]],
) -> int:
    """Insert one data value while streaming its potentially high-fanout associations."""
    anchor_summary = semantic_row_summary(anchor_rows())
    common = (
        value_without_anchors.uuid,
        value_without_anchors.type_key,
        tuple(sorted(value_without_anchors.system_metadata.members.items())),
    )
    identity = semantic_identity(
        (
            ObjectKind.ASSOCIATED_DATA.value,
            common,
            anchor_summary,
            tuple(sorted(value_without_anchors.properties.items())),
        )
    )
    existing = connection.execute(
        "SELECT id FROM object_value WHERE content_identity = ?", (identity,)
    ).fetchone()
    if existing is not None:
        return int(existing[0])
    cursor = connection.execute(
        "INSERT INTO object_value"
        " (content_identity, uuid, object_kind, type_key, display_name, source_uuid, target_uuid)"
        " VALUES (?, ?, 'associatedData', ?, NULL, NULL, NULL)",
        (identity, value_without_anchors.uuid, value_without_anchors.type_key),
    )
    assert cursor.lastrowid is not None
    value_id = int(cursor.lastrowid)
    for ordinal, (name, member) in enumerate(
        sorted(value_without_anchors.system_metadata.members.items())
    ):
        connection.execute(
            "INSERT INTO object_metadata"
            " (object_value_id, ordinal, name, json_kind, boolean_value, number_value, text_value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (value_id, ordinal, name, *json_storage_fields(member)),
        )
    connection.executemany(
        "INSERT INTO object_anchor (object_value_id, ordinal, anchor_uuid) VALUES (?, ?, ?)",
        ((value_id, ordinal, anchor) for ordinal, anchor in enumerate(anchor_rows())),
    )
    for ordinal, (name, member) in enumerate(sorted(value_without_anchors.properties.items())):
        connection.execute(
            "INSERT INTO object_property"
            " (object_value_id, ordinal, name, json_kind, boolean_value, number_value, text_value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (value_id, ordinal, name, *json_storage_fields(member)),
        )
    return value_id


def insert_object_value(connection: Connection, value: GraphObject) -> int:
    identity = object_identity(value)
    existing = connection.execute(
        "SELECT id FROM object_value WHERE content_identity = ?", (identity,)
    ).fetchone()
    if existing is not None:
        return int(existing[0])
    if isinstance(value, Anchor):
        kind = ObjectKind.ANCHOR.value
        display_name, source_uuid, target_uuid = value.display_name, None, None
    elif isinstance(value, AssociatedDataObject):
        kind = ObjectKind.ASSOCIATED_DATA.value
        display_name = source_uuid = target_uuid = None
    else:
        kind = ObjectKind.LINK.value
        display_name = None
        source_uuid, target_uuid = value.source_uuid, value.target_uuid
    cursor = connection.execute(
        "INSERT INTO object_value"
        " (content_identity, uuid, object_kind, type_key, display_name, source_uuid, target_uuid)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identity, value.uuid, kind, value.type_key, display_name, source_uuid, target_uuid),
    )
    assert cursor.lastrowid is not None
    value_id = int(cursor.lastrowid)
    for ordinal, (name, member) in enumerate(sorted(value.system_metadata.members.items())):
        connection.execute(
            "INSERT INTO object_metadata"
            " (object_value_id, ordinal, name, json_kind, boolean_value, number_value, text_value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (value_id, ordinal, name, *json_storage_fields(member)),
        )
    if isinstance(value, AssociatedDataObject):
        for ordinal, anchor_uuid in enumerate(value.anchor_uuids):
            connection.execute(
                "INSERT INTO object_anchor"
                " (object_value_id, ordinal, anchor_uuid) VALUES (?, ?, ?)",
                (value_id, ordinal, anchor_uuid),
            )
        for ordinal, (name, member) in enumerate(sorted(value.properties.items())):
            connection.execute(
                "INSERT INTO object_property"
                " (object_value_id, ordinal, name, json_kind, boolean_value,"
                " number_value, text_value)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (value_id, ordinal, name, *json_storage_fields(member)),
            )
    return value_id


def load_object_value(connection: Connection, value_id: int) -> GraphObject:
    row = connection.execute(
        "SELECT uuid, object_kind, type_key, display_name, source_uuid, target_uuid"
        " FROM object_value WHERE id = ?",
        (value_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown object value {value_id}")
    metadata = {
        str(name): json_storage_value(kind, boolean, number, text)
        for name, kind, boolean, number, text in connection.execute(
            "SELECT name, json_kind, boolean_value, number_value, text_value"
            " FROM object_metadata WHERE object_value_id = ? ORDER BY ordinal",
            (value_id,),
        )
    }
    system_metadata = SystemMetadata(metadata)
    uuid, kind, type_key, display_name, source_uuid, target_uuid = row
    if kind == ObjectKind.ANCHOR.value:
        return Anchor(str(uuid), str(type_key), str(display_name), system_metadata)
    if kind == ObjectKind.ASSOCIATED_DATA.value:
        anchors = tuple(
            str(each[0])
            for each in connection.execute(
                "SELECT anchor_uuid FROM object_anchor WHERE object_value_id = ? ORDER BY ordinal",
                (value_id,),
            )
        )
        properties = {
            str(name): json_storage_value(value_kind, boolean, number, text)
            for name, value_kind, boolean, number, text in connection.execute(
                "SELECT name, json_kind, boolean_value, number_value, text_value"
                " FROM object_property WHERE object_value_id = ? ORDER BY ordinal",
                (value_id,),
            )
        }
        return AssociatedDataObject(str(uuid), str(type_key), anchors, properties, system_metadata)
    return Link(str(uuid), str(type_key), str(source_uuid), str(target_uuid), system_metadata)


def _definition_members(definitions: GraphDefinitionSet) -> tuple[object, ...]:
    """Return independently hashable members of unordered definition-set meaning."""

    def ordered(values: list[object]) -> tuple[object, ...]:
        return tuple(sorted(values, key=semantic_identity))

    anchors: list[object] = [
        ("anchor", value.type_key, value.description) for value in definitions.anchor_types
    ]
    data_types: list[object] = []
    for value in definitions.associated_data_types:
        rules: list[object] = []
        for rule in value.property_constraints:
            shape = (
                None
                if rule.value_shape is None
                else (rule.value_shape.minimum_size, rule.value_shape.maximum_size)
            )
            value_range = (
                None
                if rule.value_range is None
                else (
                    rule.value_range.lower_bound,
                    rule.value_range.upper_bound,
                    ordered(list(rule.value_range.permitted_values)),
                )
            )
            rules.append(
                (
                    rule.property_name,
                    rule.required,
                    rule.json_kind.value,
                    rule.description,
                    shape,
                    value_range,
                    None if rule.pattern is None else rule.pattern.expression,
                )
            )
        data_types.append(
            (
                "data",
                value.type_key,
                value.description,
                tuple(sorted(value.permitted_anchor_type_keys)),
                ordered(rules),
            )
        )
    links: list[object] = [
        (
            "link",
            value.type_key,
            value.description,
            value.endpoint_constraint.description,
            tuple(sorted(value.endpoint_constraint.permitted_source_type_keys)),
            tuple(sorted(value.endpoint_constraint.permitted_target_type_keys)),
        )
        for value in definitions.link_types
    ]
    relationships: list[object] = []
    for rule in definitions.relationship_constraints:
        if isinstance(rule, LinkMultiplicityConstraint):
            relationships.append(
                (
                    "linkMultiplicity",
                    rule.link_type_key,
                    rule.constrained_end.value,
                    tuple(sorted(rule.constrained_endpoint_type_keys)),
                    tuple(sorted(rule.opposite_endpoint_type_keys)),
                    rule.lower_bound,
                    rule.upper_bound,
                    rule.description,
                )
            )
        else:
            relationships.append(
                (
                    "directAssociationMultiplicity",
                    rule.constrained_end.value,
                    tuple(sorted(rule.anchor_type_keys)),
                    tuple(sorted(rule.associated_data_type_keys)),
                    rule.lower_bound,
                    rule.upper_bound,
                    rule.description,
                )
            )
    return (*anchors, *data_types, *links, *relationships)


def definition_content_stats(definitions: GraphDefinitionSet) -> tuple[str, int]:
    """Return a composable cryptographic multiset summary of definition meaning.

    Modular addition preserves duplicate occurrences and lets a sparse proposal replace
    one natural-keyed member without traversing the untouched definition population.
    Member digests include their definition kind and complete canonical semantic value.
    """

    members = _definition_members(definitions)
    accumulator = sum(int(semantic_identity(member), 16) for member in members)
    return f"{accumulator % _IDENTITY_MODULUS:064x}", len(members)


def definition_entry_digest(definitions: GraphDefinitionSet) -> str:
    """Return the semantic digest of one normalized definition member."""

    members = _definition_members(definitions)
    if len(members) != 1:
        raise ValueError("a definition entry digest requires exactly one member")
    return semantic_identity(members[0])


def definition_identity_from_stats(accumulator: str, entry_count: int) -> str:
    """Derive the canonical set identity from its composable content summary."""

    return semantic_identity(("definitionSet", entry_count, accumulator))


def definition_identity(definitions: GraphDefinitionSet) -> str:
    """Return a path-independent identity aligned with definition-set equality."""

    return definition_identity_from_stats(*definition_content_stats(definitions))


def definition_set_stats_from_storage(connection: Connection, identity: str) -> tuple[str, int]:
    """Recompute one physical or structurally shared definition-set summary."""
    overlay = connection.execute(
        "SELECT base_definition_set_id FROM definition_set_overlay WHERE definition_set_id = ?",
        (identity,),
    ).fetchone()
    if overlay is None:
        accumulator = 0
        count = 0
        for (type_key,) in connection.execute(
            "SELECT DISTINCT type_key FROM definition_type WHERE definition_set_id = ?",
            (identity,),
        ):
            value = load_definition_set(
                connection, identity, type_keys={str(type_key)}, relationship_keys=set()
            )
            digest, member_count = definition_content_stats(value)
            accumulator = (accumulator + int(digest, 16)) % _IDENTITY_MODULUS
            count += member_count
        for (natural_key,) in connection.execute(
            "SELECT DISTINCT natural_key FROM definition_multiplicity_rule"
            " WHERE definition_set_id = ?",
            (identity,),
        ):
            value = load_definition_set(
                connection, identity, type_keys=set(), relationship_keys={str(natural_key)}
            )
            digest, member_count = definition_content_stats(value)
            accumulator = (accumulator + int(digest, 16)) % _IDENTITY_MODULUS
            count += member_count
        return f"{accumulator:064x}", count

    base_identity = str(overlay[0])
    base = connection.execute(
        "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
        (base_identity,),
    ).fetchone()
    if base is None:
        raise ValueError(f"unknown base definition-set identity {base_identity!r}")
    accumulator, count = int(str(base[0]), 16), int(base[1])
    for key, operation, value_set_id in connection.execute(
        "SELECT type_key, operation, value_set_id FROM definition_set_type_override"
        " WHERE definition_set_id = ?",
        (identity,),
    ):
        prior_digest, prior_count = _definition_entry_stats_from_storage(
            connection, base_identity, "type", str(key)
        )
        accumulator = (accumulator - int(prior_digest, 16)) % _IDENTITY_MODULUS
        count -= prior_count
        if operation == "upsert":
            value = connection.execute(
                "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
                (value_set_id,),
            ).fetchone()
            if value is None:
                raise ValueError("definition override names an unknown value")
            accumulator = (accumulator + int(str(value[0]), 16)) % _IDENTITY_MODULUS
            count += int(value[1])
    for key, operation, value_set_id in connection.execute(
        "SELECT natural_key, operation, value_set_id"
        " FROM definition_set_relationship_override WHERE definition_set_id = ?",
        (identity,),
    ):
        prior_digest, prior_count = _definition_entry_stats_from_storage(
            connection, base_identity, "relationship", str(key)
        )
        accumulator = (accumulator - int(prior_digest, 16)) % _IDENTITY_MODULUS
        count -= prior_count
        if operation == "upsert":
            value = connection.execute(
                "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
                (value_set_id,),
            ).fetchone()
            if value is None:
                raise ValueError("definition override names an unknown value")
            accumulator = (accumulator + int(str(value[0]), 16)) % _IDENTITY_MODULUS
            count += int(value[1])
    return f"{accumulator:064x}", count


def _definition_entry_stats_from_storage(
    connection: Connection, identity: str, entity_kind: str, key: str
) -> tuple[str, int]:
    overlay = connection.execute(
        "SELECT base_definition_set_id FROM definition_set_overlay WHERE definition_set_id = ?",
        (identity,),
    ).fetchone()
    if overlay is not None:
        table, column = (
            ("definition_set_type_override", "type_key")
            if entity_kind == "type"
            else ("definition_set_relationship_override", "natural_key")
        )
        override = connection.execute(
            f"SELECT operation, value_set_id FROM {table}"  # noqa: S608
            f" WHERE definition_set_id = ? AND {column} = ?",  # noqa: S608
            (identity, key),
        ).fetchone()
        if override is not None:
            if override[0] == "delete":
                return "0" * 64, 0
            row = connection.execute(
                "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
                (override[1],),
            ).fetchone()
            if row is None:
                raise ValueError("definition override names an unknown value")
            return str(row[0]), int(row[1])
        return _definition_entry_stats_from_storage(connection, str(overlay[0]), entity_kind, key)
    value = load_definition_set(
        connection,
        identity,
        type_keys={key} if entity_kind == "type" else set(),
        relationship_keys={key} if entity_kind == "relationship" else set(),
    )
    return definition_content_stats(value)


def proposal_definition_stats_from_storage(connection: Connection) -> tuple[str, int]:
    """Recompute the effective proposal summary from active meaning and sparse edits."""
    head = connection.execute(
        "SELECT active_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    if head is None:
        raise ValueError("proposal definitions have no active base")
    active_identity = str(head[0])
    active = connection.execute(
        "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
        (active_identity,),
    ).fetchone()
    if active is None:
        raise ValueError("proposal definitions name an unknown active set")
    accumulator, count = int(str(active[0]), 16), int(active[1])
    for entity_kind, key, operation, value_set_id in connection.execute(
        "SELECT 'type', type_key, operation, value_set_id FROM proposal_definition_type"
        " UNION ALL SELECT 'relationship', natural_key, operation, value_set_id"
        " FROM proposal_definition_relationship"
    ):
        prior_digest, prior_count = _definition_entry_stats_from_storage(
            connection, active_identity, str(entity_kind), str(key)
        )
        accumulator = (accumulator - int(prior_digest, 16)) % _IDENTITY_MODULUS
        count -= prior_count
        if operation == "upsert":
            value = connection.execute(
                "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
                (value_set_id,),
            ).fetchone()
            if value is None:
                raise ValueError("proposal definition edit names an unknown value")
            accumulator = (accumulator + int(str(value[0]), 16)) % _IDENTITY_MODULUS
            count += int(value[1])
    return f"{accumulator:064x}", count


def verify_proposal_summaries(connection: Connection) -> str | None:
    """Verify every maintained sparse-proposal summary and cross-row identity."""
    overlay = connection.execute(
        "SELECT accumulator, entry_count FROM proposal_overlay_state WHERE id = 0"
    ).fetchone()
    if overlay is None:
        return "proposal overlay has no summary state"
    actual_count = int(connection.execute("SELECT count(*) FROM proposal_entry").fetchone()[0])
    actual_accumulator = 0
    for uuid, kind, operation, identity in connection.execute(
        "SELECT p.uuid, p.object_kind, p.operation, v.content_identity"
        " FROM proposal_entry AS p LEFT JOIN object_value AS v ON v.id = p.object_value_id"
    ):
        actual_accumulator ^= int(
            proposal_entry_digest(
                str(uuid),
                str(kind),
                str(operation),
                None if identity is None else str(identity),
            ),
            16,
        )
    if (str(overlay[0]), int(overlay[1])) != (f"{actual_accumulator:064x}", actual_count):
        return "proposal overlay summary does not match its entries"
    actual_counts = {
        (str(kind), str(operation)): int(count)
        for kind, operation, count in connection.execute(
            "SELECT object_kind, operation, count(*) FROM proposal_entry"
            " GROUP BY object_kind, operation"
        )
    }
    stored_counts = {
        (str(kind), str(operation)): int(count)
        for kind, operation, count in connection.execute(
            "SELECT object_kind, operation, entry_count FROM proposal_overlay_count"
        )
    }
    if actual_counts != {key: value for key, value in stored_counts.items() if value}:
        return "proposal overlay counts do not match its entries"
    definition = connection.execute(
        "SELECT accumulator, entry_count, effective_accumulator, effective_entry_count, identity"
        " FROM proposal_definition_state WHERE id = 0"
    ).fetchone()
    if definition is None:
        return "proposal definitions have no summary state"
    edit_accumulator = 0
    edit_count = 0
    for key, operation, value in connection.execute(
        "SELECT type_key, operation, value_set_id FROM proposal_definition_type"
        " UNION ALL SELECT natural_key, operation, value_set_id"
        " FROM proposal_definition_relationship"
    ):
        edit_accumulator ^= int(
            semantic_identity((str(key), str(operation), None if value is None else str(value))),
            16,
        )
        edit_count += 1
    if (str(definition[0]), int(definition[1])) != (
        f"{edit_accumulator:064x}",
        edit_count,
    ):
        return "proposal definition summary does not match its keyed edits"
    if definition[4] is None:
        if any(value is not None for value in definition[2:]):
            return "absent proposal definitions retain effective summary state"
        return None
    if definition[2] is None or definition[3] is None:
        return "proposal definition identity has no effective content summary"
    actual_effective = proposal_definition_stats_from_storage(connection)
    if (str(definition[2]), int(definition[3])) != actual_effective:
        return "proposal effective definition summary does not match its normalized edits"
    if definition_identity_from_stats(*actual_effective) != str(definition[4]):
        return "proposal definition identity does not match its effective content summary"
    head = connection.execute(
        "SELECT proposed_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    if head is None or str(head[0]) != str(definition[4]):
        return "proposal definition identity does not match the state head"
    return None


def verify_normalized_identities(connection: Connection) -> str | None:
    """Return the first stale normalized content identity using bounded entry loads."""
    for value_id, stored_identity in connection.execute(
        "SELECT id, content_identity FROM object_value ORDER BY id"
    ):
        try:
            actual_identity = object_identity(load_object_value(connection, int(value_id)))
        except (TypeError, ValueError, ArithmeticError) as error:
            return f"object value {value_id} cannot be decoded: {error}"
        if actual_identity != str(stored_identity):
            return f"object value {value_id} does not match its semantic identity"

    for (set_identity,) in connection.execute(
        "SELECT identity FROM definition_set ORDER BY identity"
    ):
        overlay = connection.execute(
            "SELECT 1 FROM definition_set_overlay WHERE definition_set_id = ?",
            (set_identity,),
        ).fetchone()
        if overlay is not None:
            computed_accumulator, count = definition_set_stats_from_storage(
                connection, str(set_identity)
            )
            stored = connection.execute(
                "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
                (set_identity,),
            ).fetchone()
            assert stored is not None
            if (str(stored[0]), int(stored[1])) != (computed_accumulator, count):
                return f"definition set {set_identity} does not match its content summary"
            if definition_identity_from_stats(computed_accumulator, count) != str(set_identity):
                return f"definition set {set_identity} does not match its semantic identity"
            continue
        accumulator = 0
        count = 0
        for (type_key,) in connection.execute(
            "SELECT DISTINCT type_key FROM definition_type WHERE definition_set_id = ?"
            " ORDER BY type_key",
            (set_identity,),
        ):
            definitions = load_definition_set(
                connection,
                str(set_identity),
                type_keys={str(type_key)},
                relationship_keys=set(),
            )
            members = _definition_members(definitions)
            accumulator += sum(int(semantic_identity(member), 16) for member in members)
            count += len(members)
        for (natural_key,) in connection.execute(
            "SELECT DISTINCT natural_key FROM definition_multiplicity_rule"
            " WHERE definition_set_id = ? ORDER BY natural_key",
            (set_identity,),
        ):
            definitions = load_definition_set(
                connection,
                str(set_identity),
                type_keys=set(),
                relationship_keys={str(natural_key)},
            )
            members = _definition_members(definitions)
            accumulator += sum(int(semantic_identity(member), 16) for member in members)
            count += len(members)
        computed_accumulator = f"{accumulator % _IDENTITY_MODULUS:064x}"
        stored = connection.execute(
            "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
            (set_identity,),
        ).fetchone()
        assert stored is not None
        if (str(stored[0]), int(stored[1])) != (computed_accumulator, count):
            return f"definition set {set_identity} does not match its content summary"
        if definition_identity_from_stats(computed_accumulator, count) != str(set_identity):
            return f"definition set {set_identity} does not match its semantic identity"
    head = connection.execute(
        "SELECT active_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    if head is not None:
        accumulator = 0
        count = 0
        for entity_kind, source_table, source_key in (
            ("type", "current_definition_type_source", "type_key"),
            ("relationship", "current_definition_relationship_source", "natural_key"),
        ):
            for key, value_set_id in connection.execute(
                f"SELECT {source_key}, value_set_id FROM {source_table}"  # noqa: S608
            ):
                entry_accumulator, entry_count = _definition_entry_stats_from_storage(
                    connection, str(value_set_id), entity_kind, str(key)
                )
                accumulator = (accumulator + int(entry_accumulator, 16)) % _IDENTITY_MODULUS
                count += entry_count
        if definition_identity_from_stats(f"{accumulator:064x}", count) != str(head[0]):
            return "current definition membership does not match the active definition identity"
    return None


def insert_definition_entry(connection: Connection, definitions: GraphDefinitionSet) -> str:
    """Normalize exactly one immutable definition entry."""
    accumulator, entry_count = definition_content_stats(definitions)
    if entry_count != 1:
        raise ValueError("normalized definition insertion requires exactly one entry")
    identity = definition_identity_from_stats(accumulator, entry_count)
    if connection.execute(
        "SELECT 1 FROM definition_set WHERE identity = ?", (identity,)
    ).fetchone():
        return identity
    connection.execute(
        "INSERT INTO definition_set (identity, content_accumulator, entry_count) VALUES (?, ?, ?)",
        (identity, accumulator, entry_count),
    )
    occurrence = 0
    for kind, values in (
        (ObjectKind.ANCHOR.value, definitions.anchor_types),
        (ObjectKind.ASSOCIATED_DATA.value, definitions.associated_data_types),
        (ObjectKind.LINK.value, definitions.link_types),
    ):
        for value in values:
            connection.execute(
                "INSERT INTO definition_type"
                " (definition_set_id, occurrence, object_kind, type_key, description)"
                " VALUES (?, ?, ?, ?, ?)",
                (identity, occurrence, kind, value.type_key, value.description),
            )
            if isinstance(value, AssociatedDataTypeDefinition):
                for ordinal, anchor_type in enumerate(value.permitted_anchor_type_keys):
                    connection.execute(
                        "INSERT INTO definition_anchor_permission VALUES (?, ?, ?, ?)",
                        (identity, occurrence, ordinal, anchor_type),
                    )
                for ordinal, rule in enumerate(value.property_constraints):
                    shape = rule.value_shape
                    value_range = rule.value_range
                    connection.execute(
                        "INSERT INTO definition_property_rule"
                        " (definition_set_id, type_occurrence, occurrence, property_name, required,"
                        " json_kind, description, minimum_size, maximum_size, lower_kind,"
                        " lower_value, upper_kind, upper_value, pattern)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            identity,
                            occurrence,
                            ordinal,
                            rule.property_name,
                            int(rule.required),
                            rule.json_kind.value,
                            rule.description,
                            None if shape is None else shape.minimum_size,
                            None if shape is None else shape.maximum_size,
                            None
                            if value_range is None or value_range.lower_bound is None
                            else json_kind(value_range.lower_bound).value,
                            None
                            if value_range is None or value_range.lower_bound is None
                            else dumps(value_range.lower_bound),
                            None
                            if value_range is None or value_range.upper_bound is None
                            else json_kind(value_range.upper_bound).value,
                            None
                            if value_range is None or value_range.upper_bound is None
                            else dumps(value_range.upper_bound),
                            None if rule.pattern is None else rule.pattern.expression,
                        ),
                    )
                    if value_range is not None:
                        for permitted_ordinal, permitted in enumerate(value_range.permitted_values):
                            connection.execute(
                                "INSERT INTO definition_permitted_value VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    identity,
                                    occurrence,
                                    ordinal,
                                    permitted_ordinal,
                                    json_kind(permitted).value,
                                    dumps(permitted),
                                ),
                            )
            elif isinstance(value, LinkTypeDefinition):
                endpoint = value.endpoint_constraint
                connection.execute(
                    "INSERT INTO definition_endpoint_rule VALUES (?, ?, ?)",
                    (identity, occurrence, endpoint.description),
                )
                for role, type_keys in (
                    ("source", endpoint.permitted_source_type_keys),
                    ("target", endpoint.permitted_target_type_keys),
                ):
                    for ordinal, type_key in enumerate(type_keys):
                        connection.execute(
                            "INSERT INTO definition_endpoint_permission VALUES (?, ?, ?, ?, ?)",
                            (identity, occurrence, role, ordinal, type_key),
                        )
            occurrence += 1
    for occurrence, rule in enumerate(definitions.relationship_constraints):
        if isinstance(rule, LinkMultiplicityConstraint):
            kind = "linkMultiplicity"
            link_type_key = rule.link_type_key
            constrained_end = rule.constrained_end.value
            first, second = rule.constrained_endpoint_type_keys, rule.opposite_endpoint_type_keys
        else:
            kind = "directAssociationMultiplicity"
            link_type_key = None
            constrained_end = rule.constrained_end.value
            first, second = rule.anchor_type_keys, rule.associated_data_type_keys
        connection.execute(
            "INSERT INTO definition_multiplicity_rule"
            " (definition_set_id, occurrence, natural_key, rule_kind, link_type_key,"
            " constrained_end,"
            " lower_bound, upper_bound, description)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identity,
                occurrence,
                semantic_identity(relationship_identity(rule)),
                kind,
                link_type_key,
                constrained_end,
                rule.lower_bound,
                rule.upper_bound,
                rule.description,
            ),
        )
        for role, members in (("first", first), ("second", second)):
            for ordinal, type_key in enumerate(members):
                connection.execute(
                    "INSERT INTO definition_multiplicity_participant VALUES (?, ?, ?, ?, ?)",
                    (identity, occurrence, role, ordinal, type_key),
                )
    return identity


def insert_definition_entries(connection: Connection, entries: Iterable[DefinitionEntry]) -> str:
    """Normalize a streamed definition population into one content-addressed set."""
    connection.execute(
        "CREATE TEMP TABLE IF NOT EXISTS normalized_definition_entry"
        " (ordinal INTEGER PRIMARY KEY, value_set_id TEXT NOT NULL,"
        " created INTEGER NOT NULL)"
    )
    connection.execute("DELETE FROM normalized_definition_entry")
    accumulator = 0
    entry_count = 0
    for ordinal, entry in enumerate(entries):
        if isinstance(entry, AnchorTypeDefinition):
            one = GraphDefinitionSet(anchor_types=(entry,))
        elif isinstance(entry, AssociatedDataTypeDefinition):
            one = GraphDefinitionSet(associated_data_types=(entry,))
        elif isinstance(entry, LinkTypeDefinition):
            one = GraphDefinitionSet(link_types=(entry,))
        else:
            one = GraphDefinitionSet(relationship_constraints=(entry,))
        one_identity = definition_identity(one)
        existed = connection.execute(
            "SELECT 1 FROM definition_set WHERE identity = ?", (one_identity,)
        ).fetchone()
        value_set_id = insert_definition_entry(connection, one)
        row = connection.execute(
            "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
            (value_set_id,),
        ).fetchone()
        assert row is not None
        accumulator = (accumulator + int(str(row[0]), 16)) % _IDENTITY_MODULUS
        entry_count += int(row[1])
        connection.execute(
            "INSERT INTO normalized_definition_entry VALUES (?, ?, ?)",
            (ordinal, value_set_id, int(existed is None)),
        )
    summary = f"{accumulator:064x}"
    identity = definition_identity_from_stats(summary, entry_count)
    if connection.execute(
        "SELECT 1 FROM definition_set WHERE identity = ?", (identity,)
    ).fetchone():
        _delete_staged_definition_entries(connection, identity)
        return identity
    connection.execute(
        "INSERT INTO definition_set VALUES (?, ?, ?)", (identity, summary, entry_count)
    )
    type_occurrence = 0
    relationship_occurrence = 0
    for (source_identity,) in connection.execute(
        "SELECT value_set_id FROM normalized_definition_entry ORDER BY ordinal"
    ):
        source_type = connection.execute(
            "SELECT occurrence, object_kind, type_key, description FROM definition_type"
            " WHERE definition_set_id = ?",
            (source_identity,),
        ).fetchone()
        if source_type is not None:
            source_occurrence = int(source_type[0])
            connection.execute(
                "INSERT INTO definition_type VALUES (?, ?, ?, ?, ?)",
                (identity, type_occurrence, *source_type[1:]),
            )
            for table, columns in (
                ("definition_anchor_permission", "occurrence, anchor_type_key"),
                (
                    "definition_property_rule",
                    "occurrence, property_name, required, json_kind, description,"
                    " minimum_size, maximum_size, lower_kind, lower_value, upper_kind,"
                    " upper_value, pattern",
                ),
                ("definition_endpoint_rule", "description"),
                ("definition_endpoint_permission", "role, occurrence, type_key"),
            ):
                connection.execute(
                    f"INSERT INTO {table} SELECT ?, ?, {columns} FROM {table}"  # noqa: S608
                    " WHERE definition_set_id = ? AND type_occurrence = ?",
                    (identity, type_occurrence, source_identity, source_occurrence),
                )
            connection.execute(
                "INSERT INTO definition_permitted_value"
                " SELECT ?, ?, property_occurrence, occurrence, json_kind, json_value"
                " FROM definition_permitted_value WHERE definition_set_id = ?"
                " AND type_occurrence = ?",
                (identity, type_occurrence, source_identity, source_occurrence),
            )
            type_occurrence += 1
            continue
        source_rule = connection.execute(
            "SELECT occurrence, natural_key, rule_kind, link_type_key, constrained_end,"
            " lower_bound, upper_bound, description FROM definition_multiplicity_rule"
            " WHERE definition_set_id = ?",
            (source_identity,),
        ).fetchone()
        assert source_rule is not None
        source_occurrence = int(source_rule[0])
        connection.execute(
            "INSERT INTO definition_multiplicity_rule VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (identity, relationship_occurrence, *source_rule[1:]),
        )
        connection.execute(
            "INSERT INTO definition_multiplicity_participant"
            " SELECT ?, ?, role, occurrence, type_key"
            " FROM definition_multiplicity_participant"
            " WHERE definition_set_id = ? AND rule_occurrence = ?",
            (identity, relationship_occurrence, source_identity, source_occurrence),
        )
        relationship_occurrence += 1
    _delete_staged_definition_entries(connection, identity)
    return identity


def _delete_staged_definition_entries(connection: Connection, retained_identity: str) -> None:
    """Remove one-entry construction sets after their rows have been combined."""
    for (source_value,) in connection.execute(
        "SELECT DISTINCT value_set_id FROM normalized_definition_entry"
        " WHERE created = 1 AND value_set_id != ?",
        (retained_identity,),
    ):
        source_identity = str(source_value)
        for table in (
            "definition_permitted_value",
            "definition_property_rule",
            "definition_anchor_permission",
            "definition_endpoint_permission",
            "definition_endpoint_rule",
            "definition_multiplicity_participant",
            "definition_multiplicity_rule",
            "definition_type",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE definition_set_id = ?",  # noqa: S608
                (source_identity,),
            )
        connection.execute("DELETE FROM definition_set WHERE identity = ?", (source_identity,))


def _parameter_chunks(
    connection: Connection, values: set[str], *, reserved: int = 0
) -> Iterable[tuple[str, ...]]:
    size = max(1, min(400, connection.getlimit(SQLITE_LIMIT_VARIABLE_NUMBER) - reserved))
    ordered = sorted(values)
    return (tuple(ordered[start : start + size]) for start in range(0, len(ordered), size))


def load_definition_set(
    connection: Connection,
    identity: str,
    *,
    type_keys: set[str] | None = None,
    constrained_type_keys: set[str] | None = None,
    relationship_keys: set[str] | None = None,
    one_entry: bool = False,
) -> GraphDefinitionSet:
    """Load request-local or explicitly one-entry definition meaning.

    ``None`` means the complete collection. An explicit set selects only matching
    natural identities. Relationship rules are selected independently by the type keys
    at their constrained participant end, which is the subset an affected-neighborhood
    mutation can make newly false.
    """
    if (
        type_keys is None
        and constrained_type_keys is None
        and relationship_keys is None
        and not one_entry
    ):
        raise ValueError("complete definition-set materialization is not a production operation")
    if one_entry:
        entry = connection.execute(
            "SELECT entry_count FROM definition_set WHERE identity = ?", (identity,)
        ).fetchone()
        if entry is None:
            raise ValueError(f"unknown definition-set identity {identity!r}")
        if int(entry[0]) != 1:
            raise ValueError("definition entry reference names more than one entry")
    if (
        connection.execute(
            "SELECT 1 FROM definition_set WHERE identity = ?", (identity,)
        ).fetchone()
        is None
    ):
        raise ValueError(f"unknown definition-set identity {identity!r}")
    overlay = connection.execute(
        "SELECT base_definition_set_id FROM definition_set_overlay WHERE definition_set_id = ?",
        (identity,),
    ).fetchone()
    if overlay is not None:
        base = load_definition_set(
            connection,
            str(overlay[0]),
            type_keys=type_keys,
            constrained_type_keys=constrained_type_keys,
            relationship_keys=relationship_keys,
        )
        anchor_map = {value.type_key: value for value in base.anchor_types}
        data_type_map = {value.type_key: value for value in base.associated_data_types}
        link_type_map = {value.type_key: value for value in base.link_types}
        relationship_map = {
            semantic_identity(relationship_identity(value)): value
            for value in base.relationship_constraints
        }
        type_sql = (
            "SELECT type_key, operation, value_set_id FROM definition_set_type_override"
            " WHERE definition_set_id = ?"
        )
        overlay_type_parameters: tuple[object, ...] = (identity,)
        if type_keys is not None:
            if not type_keys:
                type_rows = ()
            else:
                type_rows = (
                    row
                    for chunk in _parameter_chunks(connection, type_keys, reserved=1)
                    for row in connection.execute(
                        type_sql + " AND type_key IN (" + ", ".join("?" for _ in chunk) + ")",
                        (identity, *chunk),
                    )
                )
        else:
            type_rows = connection.execute(type_sql, overlay_type_parameters)
        for key, operation, value_set_id in type_rows:
            text_key = str(key)
            anchor_map.pop(text_key, None)
            data_type_map.pop(text_key, None)
            link_type_map.pop(text_key, None)
            if operation != "upsert":
                continue
            value = load_definition_set(
                connection,
                str(value_set_id),
                type_keys={text_key},
                relationship_keys=set(),
                one_entry=True,
            )
            anchor_map.update((entry.type_key, entry) for entry in value.anchor_types)
            data_type_map.update((entry.type_key, entry) for entry in value.associated_data_types)
            link_type_map.update((entry.type_key, entry) for entry in value.link_types)
        relationship_sql = (
            "SELECT natural_key, operation, value_set_id"
            " FROM definition_set_relationship_override WHERE definition_set_id = ?"
        )
        overlay_relationship_parameters: tuple[object, ...] = (identity,)
        if relationship_keys is not None:
            if not relationship_keys:
                relationship_rows = ()
            else:
                relationship_rows = (
                    row
                    for chunk in _parameter_chunks(connection, relationship_keys, reserved=1)
                    for row in connection.execute(
                        relationship_sql
                        + " AND natural_key IN ("
                        + ", ".join("?" for _ in chunk)
                        + ")",
                        (identity, *chunk),
                    )
                )
        else:
            relationship_rows = connection.execute(
                relationship_sql, overlay_relationship_parameters
            )
        for key, operation, value_set_id in relationship_rows:
            text_key = str(key)
            if constrained_type_keys is not None and text_key not in relationship_map:
                if operation != "upsert":
                    continue
                candidate = load_definition_set(
                    connection,
                    str(value_set_id),
                    type_keys=set(),
                    relationship_keys={text_key},
                    one_entry=True,
                )
                if not any(
                    type_key in constrained_type_keys
                    for rule in candidate.relationship_constraints
                    for type_key in (
                        rule.constrained_endpoint_type_keys
                        if isinstance(rule, LinkMultiplicityConstraint)
                        else (
                            rule.anchor_type_keys
                            if rule.constrained_end.value == "anchor"
                            else rule.associated_data_type_keys
                        )
                    )
                ):
                    continue
            relationship_map.pop(text_key, None)
            if operation != "upsert":
                continue
            value = load_definition_set(
                connection,
                str(value_set_id),
                type_keys=set(),
                relationship_keys={text_key},
                one_entry=True,
            )
            relationship_map.update(
                (semantic_identity(relationship_identity(entry)), entry)
                for entry in value.relationship_constraints
            )
        return GraphDefinitionSet(
            tuple(anchor_map[key] for key in sorted(anchor_map)),
            tuple(data_type_map[key] for key in sorted(data_type_map)),
            tuple(link_type_map[key] for key in sorted(link_type_map)),
            tuple(relationship_map[key] for key in sorted(relationship_map)),
        )
    anchors: list[AnchorTypeDefinition] = []
    data_types: list[AssociatedDataTypeDefinition] = []
    link_types: list[LinkTypeDefinition] = []
    type_sql = (
        "SELECT occurrence, object_kind, type_key, description FROM definition_type"
        " WHERE definition_set_id = ?"
    )
    type_parameters: list[object] = [identity]
    if type_keys is not None:
        if not type_keys:
            type_rows = ()
        else:
            type_rows = sorted(
                (
                    row
                    for chunk in _parameter_chunks(connection, type_keys, reserved=1)
                    for row in connection.execute(
                        type_sql + " AND type_key IN (" + ", ".join("?" for _ in chunk) + ")",
                        (identity, *chunk),
                    )
                ),
                key=lambda row: int(row[0]),
            )
    else:
        type_rows = connection.execute(type_sql + " ORDER BY occurrence", tuple(type_parameters))
    for occurrence, kind, type_key, description in type_rows:
        if kind == ObjectKind.ANCHOR.value:
            anchors.append(AnchorTypeDefinition(str(type_key), description))
        elif kind == ObjectKind.ASSOCIATED_DATA.value:
            permitted = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT anchor_type_key FROM definition_anchor_permission"
                    " WHERE definition_set_id = ? AND type_occurrence = ? ORDER BY occurrence",
                    (identity, occurrence),
                )
            )
            properties: list[PropertyConstraint] = []
            for row in connection.execute(
                "SELECT occurrence, property_name, required, json_kind, description,"
                " minimum_size, maximum_size,"
                " lower_kind, lower_value, upper_kind, upper_value, pattern"
                " FROM definition_property_rule WHERE definition_set_id = ?"
                " AND type_occurrence = ? ORDER BY occurrence",
                (identity, occurrence),
            ):
                (
                    rule_occurrence,
                    name,
                    required,
                    kind_name,
                    rule_description,
                    minimum,
                    maximum,
                    lower_kind,
                    lower,
                    upper_kind,
                    upper,
                    pattern,
                ) = row
                permitted_values = tuple(
                    loads(str(value))
                    for _, value in connection.execute(
                        "SELECT json_kind, json_value FROM definition_permitted_value"
                        " WHERE definition_set_id = ? AND type_occurrence = ?"
                        " AND property_occurrence = ? ORDER BY occurrence",
                        (identity, occurrence, rule_occurrence),
                    )
                )
                value_shape = (
                    None if minimum is None and maximum is None else ValueShape(minimum, maximum)
                )
                value_range = None
                if lower is not None or upper is not None or permitted_values:
                    value_range = ValueRange(
                        None if lower is None else loads(str(lower)),
                        None if upper is None else loads(str(upper)),
                        permitted_values,
                    )
                properties.append(
                    PropertyConstraint(
                        str(name),
                        bool(required),
                        JsonKind(str(kind_name)),
                        rule_description,
                        value_shape,
                        value_range,
                        None if pattern is None else StringPattern(str(pattern)),
                    )
                )
            data_types.append(
                AssociatedDataTypeDefinition(
                    str(type_key), permitted, tuple(properties), description
                )
            )
        else:
            endpoint_description_row = connection.execute(
                "SELECT description FROM definition_endpoint_rule"
                " WHERE definition_set_id = ? AND type_occurrence = ?",
                (identity, occurrence),
            ).fetchone()
            source = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT type_key FROM definition_endpoint_permission"
                    " WHERE definition_set_id = ?"
                    " AND type_occurrence = ? AND role = 'source' ORDER BY occurrence",
                    (identity, occurrence),
                )
            )
            target = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT type_key FROM definition_endpoint_permission"
                    " WHERE definition_set_id = ?"
                    " AND type_occurrence = ? AND role = 'target' ORDER BY occurrence",
                    (identity, occurrence),
                )
            )
            link_types.append(
                LinkTypeDefinition(
                    str(type_key),
                    EndpointConstraint(
                        source,
                        target,
                        None if endpoint_description_row is None else endpoint_description_row[0],
                    ),
                    description,
                )
            )
    relationships = []
    relationship_sql = (
        "SELECT r.occurrence, r.rule_kind, r.link_type_key, r.constrained_end,"
        " r.lower_bound, r.upper_bound, r.description"
        " FROM definition_multiplicity_rule AS r"
    )
    relationship_parameters: list[object] = [identity]
    if relationship_keys is not None:
        if not relationship_keys:
            relationship_rows = ()
        else:
            relationship_rows = sorted(
                (
                    row
                    for chunk in _parameter_chunks(connection, relationship_keys, reserved=1)
                    for row in connection.execute(
                        relationship_sql
                        + " WHERE r.definition_set_id = ? AND r.natural_key IN ("
                        + ", ".join("?" for _ in chunk)
                        + ")",
                        (identity, *chunk),
                    )
                ),
                key=lambda row: int(row[0]),
            )
    elif constrained_type_keys is not None:
        if not constrained_type_keys:
            relationship_rows = ()
        else:
            relationship_rows = sorted(
                {
                    int(row[0]): row
                    for chunk in _parameter_chunks(connection, constrained_type_keys, reserved=1)
                    for row in connection.execute(
                        relationship_sql + " JOIN definition_multiplicity_participant AS p"
                        " ON p.definition_set_id = r.definition_set_id"
                        " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                        " WHERE r.definition_set_id = ? AND p.type_key IN ("
                        + ", ".join("?" for _ in chunk)
                        + ") GROUP BY r.definition_set_id, r.occurrence",
                        (identity, *chunk),
                    )
                }.values(),
                key=lambda row: int(row[0]),
            )
    else:
        relationship_sql += " WHERE r.definition_set_id = ?"
        relationship_rows = connection.execute(
            relationship_sql + " ORDER BY r.occurrence",
            tuple(relationship_parameters),
        )
    for occurrence, kind, link_type, end, lower, upper, description in relationship_rows:

        def members(role: str, rule_occurrence: int = int(occurrence)) -> tuple[str, ...]:
            return tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT type_key FROM definition_multiplicity_participant"
                    " WHERE definition_set_id = ?"
                    " AND rule_occurrence = ? AND role = ? ORDER BY occurrence",
                    (identity, rule_occurrence, role),
                )
            )

        if kind == "linkMultiplicity":
            relationships.append(
                LinkMultiplicityConstraint(
                    str(link_type),
                    LinkEnd(str(end)),
                    members("first"),
                    members("second"),
                    int(lower),
                    upper,
                    description,
                )
            )
        else:
            relationships.append(
                DirectAssociationMultiplicityConstraint(
                    DirectAssociationEnd(str(end)),
                    members("first"),
                    members("second"),
                    int(lower),
                    upper,
                    description,
                )
            )
    return GraphDefinitionSet(
        tuple(anchors), tuple(data_types), tuple(link_types), tuple(relationships)
    )
