"""Restore one selected historical meaning as a new canonical transition."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from vellis.activity_repository import append_activity, canonical_activity_effect
from vellis.canonical_encoding import (
    CanonicalHeader,
    canonical_record_hash_members,
    descriptor_member,
)
from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import (
    close_definition_versions,
    insert_definition_versions,
    load_definitions,
)
from vellis.domain import (
    CurrentState,
    Finding,
    FindingCode,
    GraphObject,
    OperationOutcome,
    OperationStatus,
    RevisionState,
    StateSelection,
    SystemEnvelope,
    TimeState,
    TypeDefinition,
    parse_timestamp,
)
from vellis.draft_repository import draft_present
from vellis.graph_repository import (
    close_graph_versions,
    insert_graph_versions,
    load_graph_objects,
)
from vellis.public_wire import public_result
from vellis.search_repository import close_search_versions, insert_search_versions
from vellis.state_repository import StateNotFoundError, resolve_state
from vellis.state_validation_repository import first_state_finding
from vellis.wire import serialize_wire, wire_value


def restore_state(
    database_path: Path,
    selection: StateSelection,
    *,
    initiator: str = "owner",
    source: str | None = None,
) -> OperationOutcome:
    if not isinstance(selection, RevisionState | TimeState):
        raise ValueError("restore selection must identify a revision or time")
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        current_state = resolve_state(connection, CurrentState())
        if draft_present(connection):
            result = _rejected(
                "restore was rejected",
                current_state.evaluated_revision,
                Finding(FindingCode.CONFLICT, "restore requires no draft", "/draft"),
            )
            return _finish(connection, result, selection, initiator, source)
        try:
            selected_state = resolve_state(connection, selection)
        except StateNotFoundError as error:
            result = _rejected(
                "restore state was not found",
                current_state.evaluated_revision,
                Finding(FindingCode.MISSING, str(error), "/state"),
            )
            return _finish(connection, result, selection, initiator, source)
        finding = first_state_finding(connection, selected_state)
        if finding is not None:
            result = OperationOutcome(
                OperationStatus.REJECTED,
                "selected historical state is not conforming",
                (finding,),
                current_state.evaluated_revision,
            )
            return _finish(connection, result, selection, initiator, source)
        _stage_restore_changes(connection, current_state, selected_state)
        definition_count = _change_count(connection, "restore_definition_key")
        graph_count = _change_count(connection, "restore_graph_key")
        if not definition_count and not graph_count:
            result = OperationOutcome(
                OperationStatus.ACCEPTED,
                "restore already equals current state",
                (),
                current_state.evaluated_revision,
            )
            return _finish(connection, result, selection, initiator, source)
        revision = current_state.evaluated_revision + 1
        _publish_restore(
            connection,
            revision,
            selected_state,
            definition_count,
            graph_count,
            initiator,
            source,
        )
        result = OperationOutcome(
            OperationStatus.ACCEPTED,
            "historical state restored",
            (),
            current_state.evaluated_revision,
            revision,
        )
        return _finish(connection, result, selection, initiator, source)
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _finish(connection, result, selection, initiator, source):
    serialize_wire(result)
    semantic: dict[str, object] = {
        "selection": wire_value(selection),
        "findings": wire_value(result.findings),
    }
    if result.status is OperationStatus.ACCEPTED:
        semantic.update(canonical_activity_effect(connection, result.resulting_revision))
    append_activity(
        connection,
        capability="restore",
        outcome=result.status.value,
        initiator=initiator,
        source=source,
        evaluated_revision=result.evaluated_revision,
        resulting_revision=result.resulting_revision,
        summary=result.summary,
        semantic_payload=semantic,
        verbose_payload={"request": wire_value(selection), "response": public_result(result)},
    )
    connection.commit()
    return result


def _rejected(summary, revision, finding):
    return OperationOutcome(OperationStatus.REJECTED, summary, (finding,), revision)


def _stage_restore_changes(connection, current, selected):
    connection.execute(
        "CREATE TEMP TABLE restore_definition_key(type_key TEXT PRIMARY KEY) WITHOUT ROWID"
    )
    connection.execute("CREATE TEMP TABLE restore_graph_key(uuid TEXT PRIMARY KEY) WITHOUT ROWID")
    definition_keys = connection.execute(
        """SELECT type_key FROM definition_version
           WHERE valid_from_revision <= ? AND (valid_to_revision IS NULL OR valid_to_revision > ?)
           UNION SELECT type_key FROM definition_version
           WHERE valid_from_revision <= ? AND (valid_to_revision IS NULL OR valid_to_revision > ?)
           ORDER BY type_key""",
        (
            current.evaluated_revision,
            current.evaluated_revision,
            selected.evaluated_revision,
            selected.evaluated_revision,
        ),
    )
    for row in definition_keys:
        key = str(row[0])
        before = _one_definition(connection, current, key)
        after = _one_definition(connection, selected, key)
        if _definition_content(before) != _definition_content(after):
            connection.execute("INSERT INTO restore_definition_key VALUES (?)", (key,))
    graph_keys = connection.execute(
        """SELECT uuid FROM graph_object_version
           WHERE valid_from_revision <= ? AND (valid_to_revision IS NULL OR valid_to_revision > ?)
           UNION SELECT uuid FROM graph_object_version
           WHERE valid_from_revision <= ? AND (valid_to_revision IS NULL OR valid_to_revision > ?)
           ORDER BY uuid""",
        (
            current.evaluated_revision,
            current.evaluated_revision,
            selected.evaluated_revision,
            selected.evaluated_revision,
        ),
    )
    for row in graph_keys:
        key = str(row[0])
        before = _one_graph(connection, current, key)
        after = _one_graph(connection, selected, key)
        if _graph_content(before) != _graph_content(after):
            connection.execute("INSERT INTO restore_graph_key VALUES (?)", (key,))


def _one_definition(connection, state, key):
    values = load_definitions(connection, state, (key,))
    return values[0] if values else None


def _one_graph(connection, state, key):
    values = load_graph_objects(connection, state, (key,))
    return values[0] if values else None


def _change_count(connection, relation):
    return int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])


def _definition_content(value: TypeDefinition | None):
    return None if value is None else replace(value, system=None)


def _graph_content(value: GraphObject | None):
    return None if value is None else replace(value, system=None)


def _publish_restore(
    connection,
    revision,
    selected_state,
    definition_count,
    graph_count,
    initiator,
    source,
):
    previous = connection.execute(
        """SELECT c.*, m.lineage_uuid FROM canonical_record c
           JOIN metadata_setting m ON m.head_revision = c.revision WHERE m.singleton = 1"""
    ).fetchone()
    timestamp = _canonical_time(str(previous["recorded_at"]))
    summary = f"Restore: definitions={definition_count}, objects={graph_count}"
    previous_hash = bytes(previous["record_hash"])
    connection.execute(
        """INSERT INTO canonical_record(
           revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
           initiator, source, transition_kind, summary, affected_type_keys,
           affected_uuids, previous_hash, record_hash)
           SELECT ?, ?, ?, ?, ?, ?, 'restore', ?,
             (SELECT json_group_array(type_key) FROM
               (SELECT type_key FROM restore_definition_key ORDER BY type_key)),
             (SELECT json_group_array(uuid) FROM
               (SELECT uuid FROM restore_graph_key ORDER BY uuid)), ?, ?""",
        (
            revision,
            timestamp.canonical,
            timestamp.epoch_seconds,
            timestamp.nanosecond,
            initiator,
            source,
            summary,
            previous_hash,
            bytes(32),
        ),
    )
    _create_descriptor_work(connection)
    for row in connection.execute("SELECT type_key FROM restore_definition_key ORDER BY type_key"):
        key = str(row[0])
        target = _one_definition(connection, selected_state, key)
        _store_descriptors(
            connection, "retired", close_definition_versions(connection, (key,), revision)
        )
        if target is not None:
            value = _canonical_definition(target, revision)
            _store_descriptors(
                connection,
                "introduced",
                insert_definition_versions(connection, (value,), revision),
            )
    for row in connection.execute("SELECT uuid FROM restore_graph_key ORDER BY uuid"):
        uuid = str(row[0])
        target = _one_graph(connection, selected_state, uuid)
        _store_descriptors(
            connection, "retired", close_graph_versions(connection, (uuid,), revision)
        )
        close_search_versions(connection, (uuid,), revision)
        if target is not None:
            value = _canonical_graph(target, revision)
            definitions = load_definitions(connection, selected_state, (value.type_key,))
            _store_descriptors(
                connection,
                "introduced",
                insert_graph_versions(connection, (value,), definitions, revision),
            )
            insert_search_versions(connection, (value,), revision)
    header = CanonicalHeader(
        str(previous["lineage_uuid"]), revision, timestamp, initiator, source, "restore", summary
    )
    record_hash = _restore_hash(connection, previous_hash, header)
    connection.execute(
        "UPDATE canonical_record SET record_hash = ? WHERE revision = ?", (record_hash, revision)
    )
    connection.execute(
        "UPDATE metadata_setting SET head_revision = ? WHERE singleton = 1", (revision,)
    )


def _canonical_definition(value, revision, *, changed=True):
    assert value.system is not None
    last_changed = revision if changed else value.system.last_changed_revision
    return replace(
        value,
        system=SystemEnvelope(value.system.created_revision, last_changed, value.system.legacy_v1),
    )


def _canonical_graph(value, revision):
    assert value.system is not None
    return replace(
        value,
        system=SystemEnvelope(value.system.created_revision, revision, value.system.legacy_v1),
    )


def _create_descriptor_work(connection):
    connection.execute(
        """CREATE TEMP TABLE restore_descriptor(
           disposition TEXT NOT NULL, relation_name TEXT NOT NULL,
           identity BLOB NOT NULL, member BLOB NOT NULL,
           PRIMARY KEY(disposition, relation_name, identity)) WITHOUT ROWID"""
    )


def _store_descriptors(connection, disposition, descriptors):
    for descriptor in descriptors:
        identity, member = descriptor_member(descriptor)
        connection.execute(
            "INSERT INTO restore_descriptor VALUES (?, ?, ?, ?)",
            (disposition, descriptor.relation_name, identity, member),
        )


def _restore_hash(connection, previous_hash, header):
    def members(disposition):
        return (
            bytes(row[0])
            for row in connection.execute(
                """SELECT member FROM restore_descriptor WHERE disposition = ?
                   ORDER BY relation_name, identity""",
                (disposition,),
            )
        )

    def length(disposition):
        return int(
            connection.execute(
                """SELECT coalesce(sum(8 + length(member)), 0)
                   FROM restore_descriptor WHERE disposition = ?""",
                (disposition,),
            ).fetchone()[0]
        )

    return canonical_record_hash_members(
        previous_hash,
        header,
        length("introduced"),
        members("introduced"),
        length("retired"),
        members("retired"),
    )


def _canonical_time(previous_text):
    previous = parse_timestamp(previous_text)
    now = parse_timestamp(datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    if (now.epoch_seconds, now.nanosecond) < (previous.epoch_seconds, previous.nanosecond):
        return previous
    return now
