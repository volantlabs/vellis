"""Bounded-memory canonical NDJSON export and import for normalized Vellis stores."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from vellis.canonical import now
from vellis.definitions import relationship_identity
from vellis.normalized import (
    definition_content_stats,
    definition_entry_digest,
    definition_identity_from_stats,
    load_definition_set,
    normalized_state_identity,
    semantic_identity,
    semantic_row_summary,
    verify_normalized_identities,
)
from vellis.outcomes import ValidationScope
from vellis.store import APPLICATION_ID, SCHEMA_VERSION, CanonicalStore, StoreError

__all__ = [
    "SnapshotMetadata",
    "TailMetadata",
    "export_ndjson",
    "export_tail_ndjson",
    "import_ndjson",
]

FORMAT = "vellis-normalized-ndjson"
VERSION = 1
TAIL_FORMAT = "vellis-normalized-tail-ndjson"

# Parent-before-child captured-state order. Canonical history, activity, assessments,
# and expired presence intervals are deliberately absent: import establishes one new
# owned history base at the captured revision rather than claiming the source history.
TABLES = (
    "definition_set",
    "definition_type",
    "definition_anchor_permission",
    "definition_property_rule",
    "definition_permitted_value",
    "definition_endpoint_rule",
    "definition_endpoint_permission",
    "definition_multiplicity_rule",
    "definition_multiplicity_participant",
    "object_value",
    "object_metadata",
    "object_property",
    "object_anchor",
    "canonical_record",
    "state_head",
    "graph_presence_interval",
    "proposal_entry",
    "proposal_overlay_state",
    "proposal_overlay_count",
    "proposal_definition_state",
    "proposal_definition_type",
    "proposal_definition_relationship",
)

DEFINITION_TABLES = TABLES[:9]
OBJECT_TABLES = TABLES[9:13]
TAIL_TABLES = (
    *DEFINITION_TABLES,
    *OBJECT_TABLES,
    "canonical_record",
    "canonical_graph_event",
    "canonical_proposal_event",
    "canonical_definition_proposal_event",
    "canonical_definition_event",
)

_CAPTURED_DEFINITION_IDS = """(
    SELECT active_definition_set_id FROM state_head WHERE id = 0
    UNION SELECT proposed_definition_set_id FROM state_head
          WHERE id = 0 AND proposed_definition_set_id IS NOT NULL
    UNION SELECT base_definition_set_id FROM proposal_definition_state
          WHERE id = 0 AND base_definition_set_id IS NOT NULL
    UNION SELECT value_set_id FROM proposal_definition_type WHERE value_set_id IS NOT NULL
    UNION SELECT value_set_id FROM proposal_definition_relationship WHERE value_set_id IS NOT NULL
)"""

_CAPTURED_OBJECT_VALUE_IDS = """(
    SELECT object_value_id FROM graph_presence_interval WHERE valid_to_revision IS NULL
    UNION SELECT object_value_id FROM proposal_entry WHERE object_value_id IS NOT NULL
    UNION SELECT base_object_value_id FROM proposal_entry WHERE base_object_value_id IS NOT NULL
)"""

FILTERS = {
    "definition_set": f" WHERE identity IN {_CAPTURED_DEFINITION_IDS}",
    "definition_type": f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}",
    "definition_anchor_permission": (f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}"),
    "definition_property_rule": f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}",
    "definition_permitted_value": f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}",
    "definition_endpoint_rule": f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}",
    "definition_endpoint_permission": (f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}"),
    "definition_multiplicity_rule": (f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}"),
    "definition_multiplicity_participant": (
        f" WHERE definition_set_id IN {_CAPTURED_DEFINITION_IDS}"
    ),
    "object_value": f" WHERE id IN {_CAPTURED_OBJECT_VALUE_IDS}",
    "object_metadata": f" WHERE object_value_id IN {_CAPTURED_OBJECT_VALUE_IDS}",
    "object_property": f" WHERE object_value_id IN {_CAPTURED_OBJECT_VALUE_IDS}",
    "object_anchor": f" WHERE object_value_id IN {_CAPTURED_OBJECT_VALUE_IDS}",
    "canonical_record": (
        " WHERE established_revision = (SELECT established_by FROM state_head WHERE id = 0)"
    ),
    "graph_presence_interval": " WHERE valid_to_revision IS NULL",
}


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Small immutable export/import result: revision, record identity, row count, digest."""

    revision: int
    record_identity: str
    row_count: int
    digest: str
    row_buffer_bound: int


@dataclass(frozen=True, slots=True)
class TailMetadata:
    """Bounded metadata for one contiguous canonical tail stream."""

    preceding_revision: int
    through_revision: int
    through_record_identity: str
    row_count: int
    digest: str
    row_buffer_bound: int


def _line(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})"))


def _order(connection: sqlite3.Connection, table: str) -> str:
    info = list(connection.execute(f"PRAGMA table_info({table})"))
    primary = [str(row[1]) for row in sorted(info, key=lambda row: int(row[5])) if int(row[5])]
    columns = primary or [str(row[1]) for row in info]
    return ", ".join(f'"{column}"' for column in columns)


def _order_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    info = list(connection.execute(f"PRAGMA table_info({table})"))
    primary = [str(row[1]) for row in sorted(info, key=lambda row: int(row[5])) if int(row[5])]
    return tuple(primary or [str(row[1]) for row in info])


def _sort_key(
    values: dict[str, object], columns: tuple[str, ...]
) -> tuple[tuple[int, object], ...]:
    return tuple((0, "") if values[column] is None else (1, values[column]) for column in columns)


def _captured_state_identity(connection: sqlite3.Connection) -> str:
    try:
        return normalized_state_identity(connection)
    except ValueError as error:
        raise StoreError(str(error)) from error


def _verify_proposal_summaries(connection: sqlite3.Connection) -> str | None:
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
            semantic_identity(
                (
                    str(uuid),
                    str(kind),
                    str(operation),
                    None if identity is None else str(identity),
                )
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
    if any(stored_counts.get(key, 0) != value for key, value in actual_counts.items()) or any(
        value != actual_counts.get(key, 0) for key, value in stored_counts.items()
    ):
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
    if (str(definition[0]), int(definition[1])) != (f"{edit_accumulator:064x}", edit_count):
        return "proposal definition summary does not match its keyed edits"
    if definition[4] is not None:
        if definition[2] is None or definition[3] is None:
            return "proposal definition identity has no effective content summary"
        if definition_identity_from_stats(str(definition[2]), int(definition[3])) != str(
            definition[4]
        ):
            return "proposal definition identity does not match its effective content summary"
    return None


def export_ndjson(path: Path, output: TextIO, *, batch_size: int = 256) -> SnapshotMetadata:
    """Export one committed SQLite snapshot using fixed-size row buffers."""
    if batch_size <= 0:
        raise ValueError("snapshot batch size must be positive")
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        if int(connection.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID:
            raise StoreError("the source is not a Vellis store")
        connection.execute("BEGIN")
        head = connection.execute(
            "SELECT h.revision, r.record_identity FROM state_head AS h"
            " JOIN canonical_record AS r ON r.established_revision = h.established_by"
            " WHERE h.id = 0"
        ).fetchone()
        if head is None:
            raise StoreError("the source has no established canonical state")
        counts = {
            "definitions": int(
                connection.execute(
                    f"SELECT count(*) FROM definition_set{FILTERS['definition_set']}"
                ).fetchone()[0]
            ),
            "graphObjects": int(
                connection.execute(
                    "SELECT count(*) FROM graph_presence_interval WHERE valid_to_revision IS NULL"
                ).fetchone()[0]
            ),
            "proposalEntries": int(
                connection.execute("SELECT count(*) FROM proposal_entry").fetchone()[0]
            ),
        }
        header = {
            "kind": "header",
            "format": FORMAT,
            "version": VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "revision": int(head[0]),
            "recordIdentity": str(head[1]),
            "sourceLedgerIdentity": str(
                connection.execute("SELECT identity FROM ledger WHERE id = 0").fetchone()[0]
            ),
            "stateIdentity": _captured_state_identity(connection),
            "semanticCounts": counts,
            "rowBufferBound": batch_size,
        }
        digest = hashlib.sha256()
        encoded = _line(header)
        output.write(encoded.decode("utf-8"))
        digest.update(encoded)
        row_count = 0
        for table in TABLES:
            columns = _columns(connection, table)
            cursor = connection.execute(
                f'SELECT * FROM "{table}"{FILTERS.get(table, "")}'
                f" ORDER BY {_order(connection, table)}"
            )
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    record = {
                        "kind": "row",
                        "table": table,
                        "values": dict(zip(columns, row, strict=True)),
                    }
                    encoded = _line(record)
                    output.write(encoded.decode("utf-8"))
                    digest.update(encoded)
                    row_count += 1
        value = digest.hexdigest()
        output.write(
            _line({"kind": "footer", "rowCount": row_count, "digest": value}).decode("utf-8")
        )
        connection.execute("COMMIT")
        return SnapshotMetadata(int(head[0]), str(head[1]), row_count, value, batch_size)
    except BaseException:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def export_tail_ndjson(
    path: Path,
    output: TextIO,
    *,
    after_revision: int,
    after_record_identity: str,
    batch_size: int = 256,
) -> TailMetadata:
    """Stream normalized values and records after one exact source record."""
    if batch_size <= 0:
        raise ValueError("tail batch size must be positive")
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        if int(connection.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID:
            raise StoreError("the source is not a Vellis store")
        connection.execute("BEGIN")
        preceding = connection.execute(
            "SELECT record_identity FROM canonical_record WHERE established_revision = ?",
            (after_revision,),
        ).fetchone()
        if preceding is None or str(preceding[0]) != after_record_identity:
            raise StoreError("tail base does not identify an exact source record")
        head = connection.execute(
            "SELECT h.revision, r.record_identity FROM state_head AS h"
            " JOIN canonical_record AS r ON r.established_revision = h.established_by"
            " WHERE h.id = 0"
        ).fetchone()
        ledger = connection.execute("SELECT identity FROM ledger WHERE id = 0").fetchone()
        if head is None or ledger is None or int(head[0]) <= after_revision:
            raise StoreError("the source has no later canonical tail")
        connection.execute("CREATE TEMP TABLE tail_definition_id(identity TEXT PRIMARY KEY)")
        connection.execute(
            "INSERT OR IGNORE INTO tail_definition_id"
            " SELECT active_definition_set_id FROM canonical_definition_event"
            " WHERE established_revision > ? AND active_definition_set_id IS NOT NULL"
            " UNION SELECT proposed_definition_set_id FROM canonical_definition_event"
            " WHERE established_revision > ? AND proposed_definition_set_id IS NOT NULL"
            " UNION SELECT value_set_id FROM canonical_definition_proposal_event"
            " WHERE established_revision > ? AND value_set_id IS NOT NULL",
            (after_revision, after_revision, after_revision),
        )
        connection.execute("CREATE TEMP TABLE tail_object_id(id INTEGER PRIMARY KEY)")
        connection.execute(
            "INSERT OR IGNORE INTO tail_object_id"
            " SELECT object_value_id FROM canonical_graph_event"
            " WHERE established_revision > ? AND object_value_id IS NOT NULL"
            " UNION SELECT object_value_id FROM canonical_proposal_event"
            " WHERE established_revision > ? AND object_value_id IS NOT NULL",
            (after_revision, after_revision),
        )
        header = {
            "kind": "tailHeader",
            "format": TAIL_FORMAT,
            "version": VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "sourceLedgerIdentity": str(ledger[0]),
            "precedingRevision": after_revision,
            "precedingRecordIdentity": after_record_identity,
            "throughRevision": int(head[0]),
            "throughRecordIdentity": str(head[1]),
            "throughStateIdentity": _captured_state_identity(connection),
            "rowBufferBound": batch_size,
        }
        digest = hashlib.sha256()
        encoded = _line(header)
        output.write(encoded.decode())
        digest.update(encoded)
        row_count = 0
        for table in TAIL_TABLES:
            if table in DEFINITION_TABLES:
                key = "identity" if table == "definition_set" else "definition_set_id"
                where = f" WHERE {key} IN (SELECT identity FROM tail_definition_id)"
            elif table in OBJECT_TABLES:
                key = "id" if table == "object_value" else "object_value_id"
                where = f" WHERE {key} IN (SELECT id FROM tail_object_id)"
            else:
                where = " WHERE established_revision > ?"
            columns = _columns(connection, table)
            parameters: tuple[object, ...] = (
                () if table in (*DEFINITION_TABLES, *OBJECT_TABLES) else (after_revision,)
            )
            cursor = connection.execute(
                f'SELECT * FROM "{table}"{where} ORDER BY {_order(connection, table)}',
                parameters,
            )
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    encoded = _line(
                        {
                            "kind": "tailRow",
                            "table": table,
                            "values": dict(zip(columns, row, strict=True)),
                        }
                    )
                    output.write(encoded.decode())
                    digest.update(encoded)
                    row_count += 1
        value = digest.hexdigest()
        output.write(_line({"kind": "tailFooter", "rowCount": row_count, "digest": value}).decode())
        connection.execute("COMMIT")
        return TailMetadata(
            after_revision,
            int(head[0]),
            str(head[1]),
            row_count,
            value,
            batch_size,
        )
    except BaseException:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def _records(source: TextIO) -> Iterator[tuple[dict[str, object], bytes]]:
    for line_number, text in enumerate(source, start=1):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise StoreError(f"snapshot line {line_number} is not JSON: {error}") from error
        if not isinstance(value, dict):
            raise StoreError(f"snapshot line {line_number} is not an object")
        yield value, text.encode("utf-8")


def _insert_exact(connection: sqlite3.Connection, table: str, values: dict[str, object]) -> None:
    columns = _columns(connection, table)
    primary = _order_columns(connection, table)
    where = " AND ".join(f'"{name}" IS ?' for name in primary)
    existing = connection.execute(
        f'SELECT * FROM "{table}" WHERE {where}', tuple(values[name] for name in primary)
    ).fetchone()
    wanted = tuple(values[name] for name in columns)
    if existing is not None:
        if tuple(existing) != wanted:
            raise StoreError(f"tail conflicts with existing normalized {table} content")
        return
    names = ", ".join(f'"{name}"' for name in columns)
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', wanted)


def _tail_event_identity(connection: sqlite3.Connection, revision: int, kind: str) -> str:
    def events(table: str, columns: str) -> tuple[int, str]:
        return semantic_row_summary(
            tuple(row)
            for row in connection.execute(
                f"SELECT occurrence, {columns} FROM {table}"
                " WHERE established_revision = ? ORDER BY occurrence",
                (revision,),
            )
        )

    graph = events(
        "canonical_graph_event",
        "operation, object_kind, uuid,"
        " (SELECT content_identity FROM object_value WHERE id = object_value_id)",
    )
    proposal = events(
        "canonical_proposal_event",
        "operation, object_kind, uuid,"
        " (SELECT content_identity FROM object_value WHERE id = object_value_id)",
    )
    definition_proposal = events(
        "canonical_definition_proposal_event",
        "entity_kind, natural_key, operation, value_set_id",
    )
    definition = connection.execute(
        "SELECT active_definition_set_id, delta_disposition, proposed_definition_set_id"
        " FROM canonical_definition_event WHERE established_revision = ?",
        (revision,),
    ).fetchone()
    return semantic_identity(
        (
            "canonicalEvents",
            kind,
            (0, "0" * 64),
            graph,
            proposal,
            definition_proposal,
            None if definition is None else tuple(definition),
        )
    )


def _tail_event_error(connection: sqlite3.Connection, revision: int) -> str | None:
    """Validate normalized event domains and key/value mappings before applying them."""
    duplicate = connection.execute(
        "SELECT uuid FROM canonical_graph_event WHERE established_revision = ?"
        " GROUP BY uuid HAVING count(*) != 1 LIMIT 1",
        (revision,),
    ).fetchone()
    if duplicate is not None:
        return "tail graph transition commands one UUID more than once"
    invalid = connection.execute(
        "SELECT 1 FROM canonical_graph_event AS e LEFT JOIN object_value AS v"
        " ON v.id = e.object_value_id WHERE e.established_revision = ? AND ("
        " e.operation NOT IN ('upsert', 'delete')"
        " OR e.object_kind NOT IN ('anchor', 'associatedData', 'link')"
        " OR (e.operation = 'delete' AND e.object_value_id IS NOT NULL)"
        " OR (e.operation = 'upsert' AND (v.id IS NULL OR v.uuid != e.uuid"
        " OR v.object_kind != e.object_kind))) LIMIT 1",
        (revision,),
    ).fetchone()
    if invalid is not None:
        return "tail graph event does not match its normalized object value"
    for operation, object_kind, uuid, value_id in connection.execute(
        "SELECT operation, object_kind, uuid, object_value_id FROM canonical_graph_event"
        " WHERE established_revision = ? ORDER BY occurrence",
        (revision,),
    ):
        prior = connection.execute(
            "SELECT object_kind, object_value_id FROM current_graph_object WHERE uuid = ?",
            (uuid,),
        ).fetchone()
        if operation == "delete" and (prior is None or str(prior[0]) != str(object_kind)):
            return "tail graph transition deletes an absent or different-kind object"
        if operation == "upsert" and prior is not None:
            if str(prior[0]) != str(object_kind):
                return "tail graph transition changes an established object kind"
            if int(prior[1]) == int(value_id):
                return "tail graph transition contains an ineffective upsert"
    duplicate = connection.execute(
        "SELECT uuid FROM canonical_proposal_event WHERE established_revision = ?"
        " GROUP BY uuid HAVING count(*) != 1 LIMIT 1",
        (revision,),
    ).fetchone()
    if duplicate is not None:
        return "tail proposal transition commands one UUID more than once"
    invalid = connection.execute(
        "SELECT 1 FROM canonical_proposal_event AS e LEFT JOIN object_value AS v"
        " ON v.id = e.object_value_id WHERE e.established_revision = ? AND ("
        " e.operation NOT IN ('upsert', 'delete', 'unstage')"
        " OR e.object_kind NOT IN ('anchor', 'associatedData', 'link')"
        " OR (e.operation IN ('delete', 'unstage') AND e.object_value_id IS NOT NULL)"
        " OR (e.operation = 'upsert' AND (v.id IS NULL OR v.uuid != e.uuid"
        " OR v.object_kind != e.object_kind))) LIMIT 1",
        (revision,),
    ).fetchone()
    if invalid is not None:
        return "tail proposal event does not match its normalized object value"
    for operation, object_kind, uuid, value_id in connection.execute(
        "SELECT operation, object_kind, uuid, object_value_id"
        " FROM canonical_proposal_event WHERE established_revision = ? ORDER BY occurrence",
        (revision,),
    ):
        staged = connection.execute(
            "SELECT object_kind, operation, object_value_id FROM proposal_entry WHERE uuid = ?",
            (uuid,),
        ).fetchone()
        active = connection.execute(
            "SELECT object_kind, object_value_id FROM current_graph_object WHERE uuid = ?", (uuid,)
        ).fetchone()
        if operation == "unstage" and staged is None:
            return "tail proposal transition unstages an absent entry"
        if operation == "unstage" and staged is not None and str(staged[0]) != str(object_kind):
            return "tail proposal transition unstages a different-kind entry"
        if operation == "delete":
            if active is None or str(active[0]) != str(object_kind):
                return "tail proposal transition deletes an absent or different-kind object"
            if staged is not None and str(staged[0]) != str(object_kind):
                return "tail proposal transition replaces a different-kind staged entry"
            if staged is not None and str(staged[1]) == "delete":
                return "tail proposal transition repeats an existing deletion"
        if operation == "upsert":
            if active is not None and str(active[0]) != str(object_kind):
                return "tail proposal transition changes an established object kind"
            if active is not None and int(active[1]) == int(value_id):
                return "tail proposal upsert should unstage active-equivalent meaning"
            if staged is not None and (
                str(staged[0]) != str(object_kind)
                or (
                    str(staged[1]) == "upsert"
                    and staged[2] is not None
                    and int(staged[2]) == int(value_id)
                )
            ):
                return "tail proposal transition is kind-incompatible or ineffective"
    duplicate = connection.execute(
        "SELECT entity_kind, natural_key FROM canonical_definition_proposal_event"
        " WHERE established_revision = ? GROUP BY entity_kind, natural_key"
        " HAVING count(*) != 1 LIMIT 1",
        (revision,),
    ).fetchone()
    if duplicate is not None:
        return "tail definition transition commands one natural key more than once"
    active_row = connection.execute(
        "SELECT active_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    if active_row is None:
        return "tail definition transition has no active definition base"
    active_identity = str(active_row[0])
    for entity_kind, natural_key, operation, value_set_id in connection.execute(
        "SELECT entity_kind, natural_key, operation, value_set_id"
        " FROM canonical_definition_proposal_event WHERE established_revision = ?",
        (revision,),
    ):
        if entity_kind not in {"type", "relationship"} or operation not in {
            "upsert",
            "delete",
            "unstage",
        }:
            return "tail definition-proposal event has an invalid domain value"
        table, key_column = (
            ("proposal_definition_type", "type_key")
            if entity_kind == "type"
            else ("proposal_definition_relationship", "natural_key")
        )
        staged = connection.execute(
            f"SELECT operation, value_set_id FROM {table} WHERE {key_column} = ?",
            (natural_key,),
        ).fetchone()
        active = load_definition_set(
            connection,
            active_identity,
            type_keys={str(natural_key)} if entity_kind == "type" else set(),
            relationship_keys={str(natural_key)} if entity_kind == "relationship" else set(),
        )
        active_count = definition_content_stats(active)[1]
        if operation == "unstage" and staged is None:
            return "tail definition transition unstages an absent entry"
        if operation == "delete":
            if active_count == 0:
                return "tail definition transition deletes an absent definition"
            if staged is not None and str(staged[0]) == "delete":
                return "tail definition transition repeats an existing deletion"
        if operation != "upsert":
            if value_set_id is not None:
                return "tail definition removal carries a normalized value"
            continue
        if value_set_id is None:
            return "tail definition upsert has no normalized value"
        if (
            staged is not None
            and str(staged[0]) == "upsert"
            and str(staged[1]) == str(value_set_id)
        ):
            return "tail definition transition contains an ineffective upsert"
        if active_count == 1 and definition_identity_from_stats(
            *definition_content_stats(active)
        ) == str(value_set_id):
            return "tail definition upsert should unstage active-equivalent meaning"
        value = load_definition_set(connection, str(value_set_id))
        if definition_content_stats(value)[1] != 1:
            return "tail definition upsert is not one normalized definition entry"
        if entity_kind == "type":
            types = (*value.anchor_types, *value.associated_data_types, *value.link_types)
            actual_key = types[0].type_key if len(types) == 1 else None
        else:
            actual_key = (
                semantic_identity(relationship_identity(value.relationship_constraints[0]))
                if len(value.relationship_constraints) == 1
                else None
            )
        if actual_key != str(natural_key):
            return "tail definition-proposal key does not match its normalized value"
    return None


def _rebuild_proposal_summaries(connection: sqlite3.Connection) -> None:
    accumulator = 0
    counts: dict[tuple[str, str], int] = {}
    for uuid, kind, operation, identity in connection.execute(
        "SELECT p.uuid, p.object_kind, p.operation, v.content_identity"
        " FROM proposal_entry AS p LEFT JOIN object_value AS v ON v.id = p.object_value_id"
    ):
        accumulator ^= int(
            semantic_identity(
                (str(uuid), str(kind), str(operation), None if identity is None else str(identity))
            ),
            16,
        )
        key = (str(kind), str(operation))
        counts[key] = counts.get(key, 0) + 1
    connection.execute(
        "UPDATE proposal_overlay_state SET accumulator = ?, entry_count = ? WHERE id = 0",
        (f"{accumulator:064x}", sum(counts.values())),
    )
    connection.execute("UPDATE proposal_overlay_count SET entry_count = 0")
    for (kind, operation), count in counts.items():
        connection.execute(
            "UPDATE proposal_overlay_count SET entry_count = ?"
            " WHERE object_kind = ? AND operation = ?",
            (count, kind, operation),
        )

    state = connection.execute(
        "SELECT active_definition_set_id, proposed_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    assert state is not None
    active_identity, proposed_identity = str(state[0]), state[1]
    edit_accumulator = 0
    edit_count = 0
    effective = connection.execute(
        "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
        (active_identity,),
    ).fetchone()
    assert effective is not None
    effective_accumulator, effective_count = int(str(effective[0]), 16), int(effective[1])
    for entity_kind, key, operation, value_set_id in connection.execute(
        "SELECT 'type', type_key, operation, value_set_id FROM proposal_definition_type"
        " UNION ALL SELECT 'relationship', natural_key, operation, value_set_id"
        " FROM proposal_definition_relationship"
    ):
        edit_accumulator ^= int(
            semantic_identity(
                (str(key), str(operation), None if value_set_id is None else str(value_set_id))
            ),
            16,
        )
        edit_count += 1
        active = load_definition_set(
            connection,
            active_identity,
            type_keys={str(key)} if entity_kind == "type" else set(),
            relationship_keys={str(key)} if entity_kind == "relationship" else set(),
        )
        active_count = definition_content_stats(active)[1]
        if active_count:
            effective_accumulator = (
                effective_accumulator - int(definition_entry_digest(active), 16)
            ) % (1 << 256)
            effective_count -= 1
        if operation == "upsert":
            value = connection.execute(
                "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
                (value_set_id,),
            ).fetchone()
            if value is None or int(value[1]) != 1:
                raise StoreError("tail proposal definition entry is not one normalized value")
            effective_accumulator = (effective_accumulator + int(str(value[0]), 16)) % (1 << 256)
            effective_count += 1
    expected_identity = definition_identity_from_stats(
        f"{effective_accumulator:064x}", effective_count
    )
    if proposed_identity is not None and expected_identity != str(proposed_identity):
        raise StoreError("tail proposal definitions do not reconstruct their semantic identity")
    connection.execute(
        "UPDATE proposal_definition_state SET base_definition_set_id = ?, accumulator = ?,"
        " entry_count = ?, effective_accumulator = ?, effective_entry_count = ?, identity = ?"
        " WHERE id = 0",
        (
            None if proposed_identity is None else active_identity,
            f"{edit_accumulator:064x}",
            edit_count,
            None if proposed_identity is None else f"{effective_accumulator:064x}",
            None if proposed_identity is None else effective_count,
            proposed_identity,
        ),
    )


def _tail_record_is_compatible(
    kind: str,
    event_counts: dict[str, int],
    definition: tuple[object, ...],
    prior_proposed_identity: object,
) -> bool:
    graph = event_counts["canonical_graph_event"]
    proposal = event_counts["canonical_proposal_event"]
    definition_proposal = event_counts["canonical_definition_proposal_event"]
    if kind == "graphMutation":
        return (
            bool(graph)
            and not proposal
            and not definition_proposal
            and definition
            == (
                None,
                "unchanged",
                None,
            )
        )
    if kind == "definitionDeltaChange":
        if graph or definition[0] is not None:
            return False
        if definition[1] == "present":
            return definition[2] is not None and bool(proposal or definition_proposal)
        return (
            definition[1:] == ("absent", None)
            and not proposal
            and not definition_proposal
            and prior_proposed_identity is not None
        )
    if kind == "definitionActivation":
        return (
            not proposal
            and not definition_proposal
            and prior_proposed_identity is not None
            and definition[0] is not None
            and str(definition[0]) == str(prior_proposed_identity)
            and definition[1:] == ("absent", None)
        )
    if kind == "historicalRestoration":
        return (
            not proposal
            and not definition_proposal
            and prior_proposed_identity is None
            and definition[0] is not None
            and definition[1:] == ("absent", None)
        )
    return False


def _activation_events_match_overlay(connection: sqlite3.Connection, revision: int) -> bool:
    difference = connection.execute(
        "SELECT 1 FROM (SELECT operation, object_kind, uuid, object_value_id"
        " FROM proposal_entry EXCEPT SELECT operation, object_kind, uuid,"
        " object_value_id FROM canonical_graph_event WHERE established_revision = ?)"
        " UNION ALL SELECT 1 FROM (SELECT operation, object_kind, uuid, object_value_id"
        " FROM canonical_graph_event WHERE established_revision = ? EXCEPT SELECT"
        " operation, object_kind, uuid, object_value_id FROM proposal_entry) LIMIT 1",
        (revision, revision),
    ).fetchone()
    return difference is None


def _apply_tail_stream(
    connection: sqlite3.Connection,
    tail: TextIO,
    snapshot_header: dict[str, object],
) -> dict[str, object]:
    records = _records(tail)
    header, header_bytes = next(records)
    if (
        header.get("kind") != "tailHeader"
        or header.get("format") != TAIL_FORMAT
        or header.get("version") != VERSION
        or header.get("schemaVersion") != SCHEMA_VERSION
        or header.get("sourceLedgerIdentity") != snapshot_header.get("sourceLedgerIdentity")
        or int(str(header.get("precedingRevision", -1))) != int(str(snapshot_header["revision"]))
        or header.get("precedingRecordIdentity") != snapshot_header.get("recordIdentity")
    ):
        raise StoreError("tail does not follow the exact captured source record")
    digest = hashlib.sha256(header_bytes)
    row_count = 0
    footer: dict[str, object] | None = None
    position = -1
    prior_key: tuple[tuple[int, object], ...] | None = None
    connection.execute(
        "CREATE TEMP TABLE tail_object_map ("
        "source_id INTEGER PRIMARY KEY, destination_id INTEGER NOT NULL)"
    )
    for record, encoded in records:
        if record.get("kind") == "tailFooter":
            footer = record
            break
        if record.get("kind") != "tailRow" or record.get("table") not in TAIL_TABLES:
            raise StoreError("tail contains an unknown record kind or table")
        table = str(record["table"])
        table_position = TAIL_TABLES.index(table)
        if table_position < position:
            raise StoreError("tail tables are not in canonical order")
        if table_position != position:
            position, prior_key = table_position, None
        values = record.get("values")
        if not isinstance(values, dict) or set(values) != set(_columns(connection, table)):
            raise StoreError(f"tail row for {table} has incompatible columns")
        key = _sort_key(values, _order_columns(connection, table))
        if prior_key is not None and key <= prior_key:
            raise StoreError(f"tail rows for {table} are not in canonical order")
        prior_key = key
        if table == "object_value":
            source_id = int(str(values["id"]))
            existing = connection.execute(
                "SELECT id FROM object_value WHERE content_identity = ?",
                (values["content_identity"],),
            ).fetchone()
            if existing is None:
                copied = dict(values)
                copied.pop("id")
                columns = tuple(copied)
                cursor = connection.execute(
                    "INSERT INTO object_value ("
                    + ",".join(columns)
                    + ") VALUES ("
                    + ",".join("?" for _ in columns)
                    + ")",
                    tuple(copied[column] for column in columns),
                )
                assert cursor.lastrowid is not None
                destination_id = int(cursor.lastrowid)
            else:
                destination_id = int(existing[0])
            connection.execute(
                "INSERT INTO tail_object_map VALUES (?, ?)", (source_id, destination_id)
            )
        else:
            copied = dict(values)
            if table in (*OBJECT_TABLES[1:], "canonical_graph_event", "canonical_proposal_event"):
                value_id = copied.get("object_value_id")
                if value_id is not None:
                    mapped = connection.execute(
                        "SELECT destination_id FROM tail_object_map WHERE source_id = ?",
                        (int(str(value_id)),),
                    ).fetchone()
                    if mapped is None:
                        raise StoreError("tail object child precedes its normalized value")
                    copied["object_value_id"] = int(mapped[0])
            _insert_exact(connection, table, copied)
        digest.update(encoded)
        row_count += 1
    if (
        footer is None
        or int(str(footer.get("rowCount", -1))) != row_count
        or footer.get("digest") != digest.hexdigest()
    ):
        raise StoreError("tail row count or digest does not match its footer")
    try:
        next(records)
    except StopIteration:
        pass
    else:
        raise StoreError("tail carries records after its footer")

    previous_revision = int(str(header["precedingRevision"]))
    previous_identity = str(header["precedingRecordIdentity"])
    for row in connection.execute(
        "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
        " prior_revision, record_identity, prior_record_identity, content_identity"
        ", resulting_state_identity, event_identity"
        " FROM canonical_record WHERE established_revision > ? ORDER BY established_revision",
        (previous_revision,),
    ):
        revision, kind = int(row[0]), str(row[1])
        prior_proposal = connection.execute(
            "SELECT proposed_definition_set_id FROM state_head WHERE id = 0"
        ).fetchone()
        if prior_proposal is None:
            raise StoreError("tail transition has no reconstructed prior state")
        prior_proposed_identity = prior_proposal[0]
        if (
            revision != previous_revision + 1
            or row[6] != previous_revision
            or row[8] != previous_identity
        ):
            raise StoreError("tail canonical lineage has a gap, duplicate, or reorder")
        event_counts: dict[str, int] = {}
        for table in (
            "canonical_graph_event",
            "canonical_proposal_event",
            "canonical_definition_proposal_event",
        ):
            event_row = connection.execute(
                f"SELECT count(*), min(occurrence), max(occurrence) FROM {table}"
                " WHERE established_revision = ?",
                (revision,),
            ).fetchone()
            assert event_row is not None
            count = int(event_row[0])
            event_counts[table] = count
            if count and (int(event_row[1]) != 0 or int(event_row[2]) != count - 1):
                raise StoreError("tail event occurrences are not complete and contiguous")
        definition = connection.execute(
            "SELECT active_definition_set_id, delta_disposition, proposed_definition_set_id"
            " FROM canonical_definition_event WHERE established_revision = ?",
            (revision,),
        ).fetchone()
        if definition is None:
            raise StoreError("tail record has no definition disposition")
        if not _tail_record_is_compatible(
            kind, event_counts, tuple(definition), prior_proposed_identity
        ):
            raise StoreError("tail record kind has incompatible event families")
        if kind == "definitionActivation" and not _activation_events_match_overlay(
            connection, revision
        ):
            raise StoreError("tail activation events do not equal the staged graph overlay")
        event_error = _tail_event_error(connection, revision)
        if event_error is not None:
            raise StoreError(event_error)

        for operation, _object_kind, uuid, value_id in connection.execute(
            "SELECT operation, object_kind, uuid, object_value_id FROM canonical_graph_event"
            " WHERE established_revision = ? ORDER BY occurrence",
            (revision,),
        ):
            connection.execute(
                "UPDATE graph_presence_interval SET valid_to_revision = ?"
                " WHERE uuid = ? AND valid_to_revision IS NULL",
                (revision, uuid),
            )
            if operation == "upsert":
                connection.execute(
                    "INSERT INTO graph_presence_interval"
                    " SELECT ?, id, object_kind, type_key, source_uuid, target_uuid, ?, NULL"
                    " FROM object_value WHERE id = ?",
                    (uuid, revision, value_id),
                )
            elif operation != "delete":
                raise StoreError("tail has an invalid graph event")
        for operation, object_kind, uuid, value_id in connection.execute(
            "SELECT operation, object_kind, uuid, object_value_id FROM canonical_proposal_event"
            " WHERE established_revision = ? ORDER BY occurrence",
            (revision,),
        ):
            if operation == "unstage":
                connection.execute("DELETE FROM proposal_entry WHERE uuid = ?", (uuid,))
            else:
                base = connection.execute(
                    "SELECT object_value_id FROM current_graph_object WHERE uuid = ?", (uuid,)
                ).fetchone()
                connection.execute(
                    "INSERT INTO proposal_entry VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(uuid) DO UPDATE SET object_kind=excluded.object_kind,"
                    " operation=excluded.operation, object_value_id=excluded.object_value_id,"
                    " base_object_value_id=excluded.base_object_value_id",
                    (
                        uuid,
                        object_kind,
                        operation,
                        value_id,
                        None if base is None else base[0],
                    ),
                )
        for entity_kind, natural_key, operation, value_set_id in connection.execute(
            "SELECT entity_kind, natural_key, operation, value_set_id"
            " FROM canonical_definition_proposal_event WHERE established_revision = ?"
            " ORDER BY occurrence",
            (revision,),
        ):
            table, key = (
                ("proposal_definition_type", "type_key")
                if entity_kind == "type"
                else ("proposal_definition_relationship", "natural_key")
            )
            if operation == "unstage":
                connection.execute(f"DELETE FROM {table} WHERE {key} = ?", (natural_key,))
            else:
                connection.execute(
                    f"INSERT INTO {table} VALUES (?, ?, ?) ON CONFLICT({key}) DO UPDATE SET"
                    " operation=excluded.operation, value_set_id=excluded.value_set_id",
                    (natural_key, operation, value_set_id),
                )
        active, disposition, proposed = definition
        if active is not None:
            connection.execute(
                "UPDATE state_head SET active_definition_set_id = ? WHERE id = 0", (active,)
            )
        if disposition == "present":
            connection.execute(
                "UPDATE state_head SET proposed_definition_set_id = ? WHERE id = 0", (proposed,)
            )
        elif disposition == "absent":
            connection.execute("DELETE FROM proposal_entry")
            connection.execute("DELETE FROM proposal_definition_type")
            connection.execute("DELETE FROM proposal_definition_relationship")
            connection.execute(
                "UPDATE state_head SET proposed_definition_set_id = NULL WHERE id = 0"
            )
        elif disposition != "unchanged":
            raise StoreError("tail has an invalid definition disposition")
        connection.execute(
            "UPDATE state_head SET revision = ?, established_by = ? WHERE id = 0",
            (revision, revision),
        )
        if disposition == "present":
            proposal_state = connection.execute(
                "SELECT active_definition_set_id, proposed_definition_set_id,"
                " (SELECT count(*) FROM proposal_entry) FROM state_head WHERE id = 0"
            ).fetchone()
            assert proposal_state is not None
            if str(proposal_state[0]) == str(proposal_state[1]) and int(proposal_state[2]) == 0:
                raise StoreError("tail transition leaves an empty active-equivalent proposal")
        state_identity = _captured_state_identity(connection)
        derived_event = _tail_event_identity(connection, revision, kind)
        derived_content = semantic_identity(
            ("canonicalRecordContent", derived_event, state_identity)
        )
        derived_record = semantic_identity(
            (
                str(header["sourceLedgerIdentity"]),
                previous_identity,
                revision,
                kind,
                str(row[2]),
                str(row[3]),
                row[4],
                str(row[5]),
                derived_content,
            )
        )
        if (
            derived_content != str(row[9])
            or derived_record != str(row[7])
            or state_identity != str(row[10])
            or derived_event != str(row[11])
        ):
            raise StoreError(
                "tail record does not bind its normalized events, state, and lineage"
                f" at revision {revision}: state {state_identity} != {row[10]}"
            )
        previous_revision, previous_identity = revision, str(row[7])
    _rebuild_proposal_summaries(connection)
    if (
        previous_revision != int(str(header["throughRevision"]))
        or previous_identity != str(header["throughRecordIdentity"])
        or _captured_state_identity(connection) != str(header["throughStateIdentity"])
    ):
        raise StoreError("tail does not reconstruct its claimed final canonical state")
    return header


def import_ndjson(
    source: TextIO, destination: Path, *, tail: TextIO | None = None
) -> SnapshotMetadata:
    """Verify into temporary SQLite and atomically establish an empty destination."""
    if destination.exists():
        raise StoreError("snapshot import requires an empty destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".import", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    store: CanonicalStore | None = None
    try:
        store = CanonicalStore(temporary)
        store.close()
        store = None
        connection = sqlite3.connect(temporary, isolation_level=None)
        try:
            records = _records(source)
            header, header_bytes = next(records)
            if (
                header.get("kind") != "header"
                or header.get("format") != FORMAT
                or header.get("version") != VERSION
                or header.get("schemaVersion") != SCHEMA_VERSION
            ):
                raise StoreError("snapshot header is incompatible with this build")
            digest = hashlib.sha256(header_bytes)
            row_count = 0
            footer: dict[str, object] | None = None
            table_position = -1
            prior_key: tuple[tuple[int, object], ...] | None = None
            connection.execute("BEGIN IMMEDIATE")
            for record, encoded in records:
                if record.get("kind") == "footer":
                    footer = record
                    break
                if record.get("kind") != "row" or record.get("table") not in TABLES:
                    raise StoreError("snapshot contains an unknown record kind or table")
                table = str(record["table"])
                position = TABLES.index(table)
                if position < table_position:
                    raise StoreError("snapshot tables are not in canonical order")
                if position != table_position:
                    table_position = position
                    prior_key = None
                values = record.get("values")
                columns = _columns(connection, table)
                if not isinstance(values, dict) or set(values) != set(columns):
                    raise StoreError(f"snapshot row for {table} has incompatible columns")
                key = _sort_key(values, _order_columns(connection, table))
                if prior_key is not None and key <= prior_key:
                    raise StoreError(f"snapshot rows for {table} are not in canonical order")
                prior_key = key
                placeholders = ", ".join("?" for _ in columns)
                names = ", ".join(f'"{name}"' for name in columns)
                connection.execute(
                    f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
                    tuple(values[name] for name in columns),
                )
                digest.update(encoded)
                row_count += 1
            if footer is None:
                raise StoreError("snapshot has no footer")
            if (
                int(str(footer.get("rowCount", -1))) != row_count
                or footer.get("digest") != digest.hexdigest()
            ):
                raise StoreError("snapshot row count or digest does not match its footer")
            try:
                next(records)
            except StopIteration:
                pass
            else:
                raise StoreError("snapshot carries records after its footer")
            head = connection.execute(
                "SELECT h.revision, r.record_identity FROM state_head AS h"
                " JOIN canonical_record AS r ON r.established_revision = h.established_by"
                " WHERE h.id = 0"
            ).fetchone()
            if (
                head is None
                or int(head[0]) != int(str(header["revision"]))
                or str(head[1]) != str(header["recordIdentity"])
            ):
                raise StoreError("snapshot head does not match its header")
            record = connection.execute(
                "SELECT established_revision, record_kind, recorded_at, initiator, source,"
                " summary, prior_record_identity, record_identity, content_identity,"
                " resulting_state_identity, event_identity"
                " FROM canonical_record"
            ).fetchone()
            if record is None or semantic_identity(
                (
                    str(header["sourceLedgerIdentity"]),
                    record[6],
                    int(record[0]),
                    str(record[1]),
                    str(record[2]),
                    str(record[3]),
                    record[4],
                    str(record[5]),
                    str(record[8]),
                )
            ) != str(record[7]):
                raise StoreError("snapshot captured-record identity is invalid")
            if semantic_identity(
                ("canonicalRecordContent", str(record[10]), str(record[9]))
            ) != str(record[8]):
                raise StoreError("snapshot captured record does not bind its resulting state")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise StoreError("snapshot violates normalized relational integrity")
            identity_error = verify_normalized_identities(connection)
            if identity_error is not None:
                raise StoreError(identity_error)
            proposal_error = _verify_proposal_summaries(connection)
            if proposal_error is not None:
                raise StoreError(proposal_error)
            captured_state_identity = _captured_state_identity(connection)
            if (
                captured_state_identity != str(header.get("stateIdentity"))
                or record is None
                or str(record[9]) != captured_state_identity
            ):
                raise StoreError("snapshot state does not match its captured semantic identity")
            counts = header.get("semanticCounts")
            if not isinstance(counts, dict) or counts != {
                "definitions": int(
                    connection.execute("SELECT count(*) FROM definition_set").fetchone()[0]
                ),
                "graphObjects": int(
                    connection.execute(
                        "SELECT count(*) FROM graph_presence_interval"
                        " WHERE valid_to_revision IS NULL"
                    ).fetchone()[0]
                ),
                "proposalEntries": int(
                    connection.execute("SELECT count(*) FROM proposal_entry").fetchone()[0]
                ),
            }:
                raise StoreError("snapshot semantic counts do not match its rows")
            result_header = header if tail is None else _apply_tail_stream(connection, tail, header)
            identity_error = verify_normalized_identities(connection)
            if identity_error is not None:
                raise StoreError(identity_error)
            proposal_error = _verify_proposal_summaries(connection)
            if proposal_error is not None:
                raise StoreError(proposal_error)
            _establish_fresh_lineage(connection, result_header)
            connection.execute("COMMIT")
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()
        verified = CanonicalStore(temporary)
        try:
            projection_findings = verified.verify_projection_from_ledger()
            if projection_findings:
                raise StoreError(projection_findings[0].summary)
            _revision, relation, definition_id, _overlay = verified.conformance_context(
                ValidationScope.GRAPH_CONFORMANCE
            )
            assert definition_id is not None
            first_finding = next(verified.iter_conformance_findings(relation, definition_id), None)
            if first_finding is not None:
                raise StoreError(f"snapshot state does not conform: {first_finding.summary}")
        finally:
            verified.close()
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise StoreError("snapshot destination was established concurrently") from error
        temporary.unlink()
        return SnapshotMetadata(
            int(str(result_header.get("throughRevision", result_header.get("revision")))),
            str(result_header.get("throughRecordIdentity", result_header.get("recordIdentity"))),
            row_count,
            digest.hexdigest(),
            int(str(header["rowBufferBound"])),
        )
    except (StopIteration, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        raise StoreError(f"snapshot import failed: {error}") from error
    finally:
        if store is not None:
            store.close()
        temporary.unlink(missing_ok=True)


def _establish_fresh_lineage(connection: sqlite3.Connection, header: dict[str, object]) -> None:
    """Collapse captured source state into one new owned initial record in SQL."""
    head = connection.execute(
        "SELECT revision, active_definition_set_id, proposed_definition_set_id"
        " FROM state_head WHERE id = 0"
    ).fetchone()
    if head is None:
        raise StoreError("snapshot has no captured state head")
    revision, active_identity, proposed_identity = int(head[0]), str(head[1]), head[2]
    captured_identity = str(header.get("throughRecordIdentity", header.get("recordIdentity")))
    ledger_identity = secrets.token_hex(16)
    recorded_at = now().isoformat()
    base_graph = semantic_row_summary(
        (str(uuid), str(identity))
        for uuid, identity in connection.execute(
            "SELECT p.uuid, v.content_identity FROM graph_presence_interval AS p"
            " JOIN object_value AS v ON v.id = p.object_value_id"
            " WHERE p.valid_to_revision IS NULL ORDER BY p.uuid"
        )
    )
    definition_event = (
        active_identity,
        "absent" if proposed_identity is None else "present",
        None if proposed_identity is None else str(proposed_identity),
    )
    resulting_state_identity = _captured_state_identity(connection)
    empty_summary = (0, "0" * 64)
    event_identity = semantic_identity(
        (
            "canonicalEvents",
            "initial",
            base_graph,
            empty_summary,
            empty_summary,
            empty_summary,
            definition_event,
        )
    )
    content_identity = semantic_identity(
        ("canonicalRecordContent", event_identity, resulting_state_identity)
    )
    record_identity = semantic_identity(
        (
            ledger_identity,
            None,
            revision,
            "initial",
            recorded_at,
            "snapshot-import",
            None,
            f"initialized from captured record {captured_identity}",
            content_identity,
        )
    )
    connection.execute("DELETE FROM canonical_record")
    connection.execute("DELETE FROM ledger")
    connection.execute("DELETE FROM canonical_graph_event")
    connection.execute("DELETE FROM canonical_proposal_event")
    connection.execute("DELETE FROM canonical_definition_proposal_event")
    connection.execute("DELETE FROM canonical_definition_event")
    connection.execute("DELETE FROM activity_record")
    connection.execute("DELETE FROM current_assessment")
    connection.execute("DELETE FROM validation_finding_definition")
    connection.execute("DELETE FROM validation_finding_object")
    connection.execute("DELETE FROM validation_finding")
    connection.execute("DELETE FROM validation_assessment")
    connection.execute("DELETE FROM graph_presence_interval WHERE valid_to_revision IS NOT NULL")
    connection.execute("UPDATE graph_presence_interval SET valid_from_revision = ?", (revision,))
    connection.execute("INSERT INTO ledger VALUES (0, ?)", (ledger_identity,))
    connection.execute(
        "INSERT INTO canonical_record VALUES (?, 0, 'initial', ?, 'snapshot-import',"
        " NULL, ?, NULL, ?, NULL, ?, ?, ?)",
        (
            revision,
            recorded_at,
            f"initialized from captured record {captured_identity}",
            record_identity,
            content_identity,
            resulting_state_identity,
            event_identity,
        ),
    )
    connection.execute("UPDATE state_head SET established_by = ? WHERE id = 0", (revision,))
    connection.execute(
        "INSERT INTO canonical_definition_event VALUES (?, ?, ?, ?)",
        (
            revision,
            active_identity,
            "absent" if proposed_identity is None else "present",
            proposed_identity,
        ),
    )
