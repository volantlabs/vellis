"""Disposable Phase 3 state builder; Phase 4 replaces it with public graph changes."""

from __future__ import annotations

import json
from pathlib import Path

from vellis.audit import audit_connection
from vellis.canonical_encoding import ZERO_HASH, CanonicalHeader, canonical_record_hash
from vellis.database import connect_database
from vellis.domain import GraphObject, SystemEnvelope, TypeDefinition, parse_timestamp
from vellis.graph_repository import insert_graph_versions
from vellis.operations import initialize_with_definitions
from vellis.search_repository import insert_search_versions


def initialized_query_database(
    database_path: Path,
    definitions: tuple[TypeDefinition, ...],
    objects: tuple[GraphObject, ...],
) -> Path:
    initialize_with_definitions(
        database_path,
        definitions,
        recorded_at="2026-01-01T00:00:00Z",
    )
    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        metadata = connection.execute(
            """
            SELECT m.lineage_uuid, c.record_hash
            FROM metadata_setting AS m
            JOIN canonical_record AS c ON c.revision = m.head_revision
            WHERE m.singleton = 1
            """
        ).fetchone()
        timestamp = parse_timestamp("2026-01-01T00:00:01Z")
        summary = f"Changed graph: objects={len(objects)}"
        uuids = tuple(sorted(value.uuid for value in objects))
        connection.execute(
            """
            INSERT INTO canonical_record(
                revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
                initiator, transition_kind, summary, affected_type_keys,
                affected_uuids, previous_hash, record_hash
            ) VALUES (1, ?, ?, ?, 'owner', 'graphChange', ?, '[]', ?, ?, ?)
            """,
            (
                timestamp.canonical,
                timestamp.epoch_seconds,
                timestamp.nanosecond,
                summary,
                json.dumps(uuids, separators=(",", ":")),
                bytes(metadata["record_hash"]),
                ZERO_HASH,
            ),
        )
        canonical_objects = tuple(_with_system(value) for value in objects)
        canonical_definitions = _current_definitions(connection)
        descriptors = insert_graph_versions(connection, canonical_objects, canonical_definitions, 1)
        insert_search_versions(connection, canonical_objects, 1)
        header = CanonicalHeader(
            str(metadata["lineage_uuid"]),
            1,
            timestamp,
            "owner",
            None,
            "graphChange",
            summary,
        )
        record_hash = canonical_record_hash(bytes(metadata["record_hash"]), header, descriptors, ())
        connection.execute(
            "UPDATE canonical_record SET record_hash = ? WHERE revision = 1", (record_hash,)
        )
        connection.execute("UPDATE metadata_setting SET head_revision = 1 WHERE singleton = 1")
        connection.commit()
        audit = audit_connection(connection)
        assert audit.clean, audit.findings
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    return database_path


def _with_system(value: GraphObject) -> GraphObject:
    from dataclasses import replace

    if value.system is not None:
        raise ValueError("fixture graph input must not carry canonical system metadata")
    return replace(value, system=SystemEnvelope(1, 1, '{"origin":"fixture"}'))


def _current_definitions(connection) -> tuple[TypeDefinition, ...]:
    from vellis.definition_repository import load_definitions
    from vellis.state_repository import resolve_state

    return load_definitions(connection, resolve_state(connection))
