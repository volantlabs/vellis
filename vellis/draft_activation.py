"""Bounded publication of a validated effective draft."""

from dataclasses import replace
from datetime import UTC, datetime

from vellis.canonical_encoding import (
    CanonicalHeader,
    canonical_record_hash_members,
    descriptor_member,
)
from vellis.change_operations import _canonical_object, _content
from vellis.definition_repository import (
    close_definition_versions,
    insert_definition_versions,
    load_definitions,
)
from vellis.domain import SystemEnvelope, parse_timestamp
from vellis.draft_repository import (
    load_draft_definitions,
    load_draft_graph,
)
from vellis.graph_repository import (
    close_graph_versions,
    insert_graph_versions,
    load_graph_objects,
)
from vellis.search_repository import close_search_versions, insert_search_versions


def prepare_activation_changes(connection, state):
    """Record only effective staged keys in connection-local working state."""
    connection.execute("DROP TABLE IF EXISTS temp.activation_change")
    connection.execute(
        """CREATE TEMP TABLE activation_change(
           category TEXT NOT NULL, key TEXT NOT NULL, operation TEXT NOT NULL,
           PRIMARY KEY(category, key)) WITHOUT ROWID"""
    )
    for row in connection.execute("SELECT type_key FROM draft_definition_entry ORDER BY type_key"):
        _prepare_definition(connection, state, str(row[0]))
    for row in connection.execute("SELECT uuid FROM draft_graph_object_patch ORDER BY uuid"):
        _prepare_object(connection, state, str(row[0]))
    return int(connection.execute("SELECT count(*) FROM temp.activation_change").fetchone()[0])


def publish_activation_revision(connection, revision, state, initiator, source):
    """Publish prepared staged keys and stream their canonical descriptors."""
    previous = connection.execute(
        """SELECT c.*, m.lineage_uuid FROM canonical_record c
           JOIN metadata_setting m ON m.head_revision = c.revision
           WHERE m.singleton = 1"""
    ).fetchone()
    timestamp = _canonical_time(str(previous["recorded_at"]))
    definition_count = _activation_count(connection, "definition")
    object_count = _activation_count(connection, "object")
    summary = f"Draft activation: definitions={definition_count}, objects={object_count}"
    previous_hash = bytes(previous["record_hash"])
    connection.execute(
        """INSERT INTO canonical_record(
           revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
           initiator, source, transition_kind, summary, affected_type_keys,
           affected_uuids, previous_hash, record_hash)
           VALUES (?, ?, ?, ?, ?, ?, 'draftActivation', ?,
             (SELECT json_group_array(key) FROM (
                SELECT key FROM temp.activation_change
                WHERE category = 'definition' ORDER BY key)),
             (SELECT json_group_array(key) FROM (
                SELECT key FROM temp.activation_change
                WHERE category = 'object' ORDER BY key)),
             ?, ?)""",
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
    _publish_definition_changes(connection, state, revision)
    _publish_graph_changes(connection, state, revision)
    header = CanonicalHeader(
        str(previous["lineage_uuid"]),
        revision,
        timestamp,
        initiator,
        source,
        "draftActivation",
        summary,
    )
    connection.execute(
        "UPDATE canonical_record SET record_hash = ? WHERE revision = ?",
        (_activation_record_hash(connection, previous_hash, header), revision),
    )
    connection.execute(
        "UPDATE metadata_setting SET head_revision = ? WHERE singleton = 1", (revision,)
    )


def _prepare_definition(connection, state, key):
    current = load_definitions(connection, state, (key,))
    proposed = load_draft_definitions(connection, current, (key,))
    before = None if not current else current[0]
    after = None if not proposed else proposed[0]
    if _definition_content(before) != _definition_content(after):
        connection.execute(
            "INSERT INTO temp.activation_change VALUES ('definition', ?, ?)",
            (key, "remove" if after is None else "upsert"),
        )


def _prepare_object(connection, state, uuid):
    current = load_graph_objects(connection, state, (uuid,))
    proposed, _ = load_draft_graph(connection, current, (uuid,))
    before = None if not current else current[0]
    after = None if not proposed else proposed[0]
    if before is None and after is None:
        return
    if before is None or after is None or _content(before) != _content(after):
        connection.execute(
            "INSERT INTO temp.activation_change VALUES ('object', ?, ?)",
            (uuid, "remove" if after is None else "upsert"),
        )


def _publish_definition_changes(connection, state, revision):
    rows = connection.execute(
        """SELECT key, operation FROM temp.activation_change
           WHERE category = 'definition' ORDER BY key"""
    )
    for key, operation in rows:
        key = str(key)
        value = None
        if str(operation) != "remove":
            proposed = load_draft_definitions(
                connection, load_definitions(connection, state, (key,)), (key,)
            )
            value = _canonical_definition(connection, proposed[0], revision)
        _store_descriptors(
            connection, "retired", close_definition_versions(connection, (key,), revision)
        )
        if value is not None:
            _store_descriptors(
                connection,
                "introduced",
                insert_definition_versions(connection, (value,), revision),
            )


def _publish_graph_changes(connection, state, revision):
    rows = connection.execute(
        """SELECT key, operation FROM temp.activation_change
           WHERE category = 'object' ORDER BY key"""
    )
    for uuid, operation in rows:
        uuid = str(uuid)
        value = None
        definitions = ()
        if str(operation) != "remove":
            current = load_graph_objects(connection, state, (uuid,))
            proposed, _ = load_draft_graph(connection, current, (uuid,))
            value = _canonical_draft_object(connection, proposed[0], revision)
            definitions = load_draft_definitions(
                connection,
                load_definitions(connection, state, (value.type_key,)),
                (value.type_key,),
            )
        _store_descriptors(
            connection, "retired", close_graph_versions(connection, (uuid,), revision)
        )
        close_search_versions(connection, (uuid,), revision)
        if value is not None:
            _insert_graph_change(connection, value, definitions, revision)


def _insert_graph_change(connection, value, definitions, revision):
    _store_descriptors(
        connection,
        "introduced",
        insert_graph_versions(connection, (value,), definitions, revision),
    )
    insert_search_versions(connection, (value,), revision)


def _create_descriptor_work(connection):
    connection.execute("DROP TABLE IF EXISTS temp.activation_descriptor")
    connection.execute(
        """CREATE TEMP TABLE activation_descriptor(
           disposition TEXT NOT NULL, relation_name TEXT NOT NULL,
           identity BLOB NOT NULL, member BLOB NOT NULL,
           PRIMARY KEY(disposition, relation_name, identity)) WITHOUT ROWID"""
    )


def _store_descriptors(connection, disposition, descriptors):
    for descriptor in descriptors:
        identity, member = descriptor_member(descriptor)
        connection.execute(
            "INSERT INTO temp.activation_descriptor VALUES (?, ?, ?, ?)",
            (disposition, descriptor.relation_name, identity, member),
        )


def _activation_record_hash(connection, previous_hash, header):
    def values(disposition):
        return (
            bytes(row[0])
            for row in connection.execute(
                """SELECT member FROM temp.activation_descriptor
                   WHERE disposition = ? ORDER BY relation_name, identity""",
                (disposition,),
            )
        )

    def length(disposition):
        return int(
            connection.execute(
                """SELECT coalesce(sum(8 + length(member)), 0)
                   FROM temp.activation_descriptor WHERE disposition = ?""",
                (disposition,),
            ).fetchone()[0]
        )

    return canonical_record_hash_members(
        previous_hash,
        header,
        length("introduced"),
        values("introduced"),
        length("retired"),
        values("retired"),
    )


def _activation_count(connection, category):
    return int(
        connection.execute(
            "SELECT count(*) FROM temp.activation_change WHERE category = ?", (category,)
        ).fetchone()[0]
    )


def _canonical_definition(connection, value, revision):
    reservation = connection.execute(
        "SELECT created_revision, legacy_v1 FROM type_key_identity WHERE type_key = ?",
        (value.type_key,),
    ).fetchone()
    created = (
        int(reservation["created_revision"])
        if value.system is None and reservation is not None
        else (revision if value.system is None else value.system.created_revision)
    )
    legacy = (
        (None if reservation["legacy_v1"] is None else str(reservation["legacy_v1"]))
        if value.system is None and reservation is not None
        else (None if value.system is None else value.system.legacy_v1)
    )
    return replace(value, system=SystemEnvelope(created, revision, legacy))


def _canonical_draft_object(connection, value, revision):
    if value.system is not None:
        return _canonical_object(value, revision)
    reservation = connection.execute(
        "SELECT created_revision, legacy_v1 FROM graph_object_identity WHERE uuid = ?",
        (value.uuid,),
    ).fetchone()
    if reservation is None:
        return _canonical_object(value, revision)
    legacy = None if reservation["legacy_v1"] is None else str(reservation["legacy_v1"])
    return replace(
        value,
        system=SystemEnvelope(int(reservation["created_revision"]), revision, legacy),
    )


def _definition_content(value):
    return None if value is None else replace(value, system=None)


def _canonical_time(previous_text):
    previous = parse_timestamp(previous_text)
    now = parse_timestamp(datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    return (
        previous
        if (now.epoch_seconds, now.nanosecond) < (previous.epoch_seconds, previous.nanosecond)
        else now
    )
