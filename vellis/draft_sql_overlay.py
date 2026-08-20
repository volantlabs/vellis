"""Connection-local SQL views of latest live state with the draft bucket applied."""

import json
import sqlite3


def install_draft_graph_overlay(connection: sqlite3.Connection, *, search_scopes=()) -> None:
    """Install derived temporary relations consumed by the existing query compiler."""
    _execute_without_commit(
        connection,
        """
        CREATE TEMP VIEW graph_object_identity AS
        SELECT i.uuid, i.kind, i.created_revision, i.legacy_v1
        FROM main.graph_object_identity AS i
        WHERE NOT EXISTS (
            SELECT 1 FROM main.draft_graph_object_patch AS p
            WHERE p.uuid = i.uuid AND p.tombstone = 0
              AND NOT EXISTS (
                  SELECT 1 FROM main.graph_object_version AS l
                  WHERE l.uuid = p.uuid AND l.valid_to_revision IS NULL
              )
        )
        UNION ALL
        SELECT p.uuid, p.kind, NULL, NULL
        FROM main.draft_graph_object_patch AS p
        WHERE p.tombstone = 0
          AND NOT EXISTS (
              SELECT 1 FROM main.graph_object_version AS l
              WHERE l.uuid = p.uuid AND l.valid_to_revision IS NULL
          );

        CREATE TEMP VIEW graph_object_version AS
        SELECT l.uuid, 0 AS valid_from_revision, NULL AS valid_to_revision, l.kind,
               CASE WHEN p.has_type_key = 1 THEN p.type_key ELSE l.type_key END AS type_key,
               CASE WHEN p.has_display_name = 1 THEN p.display_name ELSE l.display_name END
                   AS display_name,
               CASE WHEN p.has_source_uuid = 1 THEN p.source_uuid ELSE l.source_uuid END
                   AS source_uuid,
               CASE WHEN p.has_target_uuid = 1 THEN p.target_uuid ELSE l.target_uuid END
                   AS target_uuid,
               l.last_changed_revision, zeroblob(32) AS row_digest
        FROM main.graph_object_version AS l
        LEFT JOIN main.draft_graph_object_patch AS p ON p.uuid = l.uuid
        WHERE l.valid_to_revision IS NULL
          AND coalesce(p.tombstone, 0) = 0
          AND (p.uuid IS NULL OR p.kind = l.kind)
        UNION ALL
        SELECT p.uuid, 0, NULL, p.kind, p.type_key, p.display_name,
               p.source_uuid, p.target_uuid, 0, zeroblob(32)
        FROM main.draft_graph_object_patch AS p
        WHERE p.tombstone = 0
          AND NOT EXISTS (
              SELECT 1 FROM main.graph_object_version AS l
              WHERE l.uuid = p.uuid AND l.valid_to_revision IS NULL
          )
          AND p.has_type_key = 1
          AND (
              (p.kind = 'anchor' AND p.has_display_name = 1)
              OR (p.kind = 'link' AND p.has_source_uuid = 1 AND p.has_target_uuid = 1)
              OR (p.kind = 'associatedData' AND p.has_complete_anchor_set = 1 AND EXISTS (
                  SELECT 1 FROM main.draft_association_operation AS a
                  WHERE a.object_uuid = p.uuid AND a.operation = 'base'
              ))
          );

        CREATE TEMP VIEW direct_association_version AS
        SELECT a.object_uuid, a.anchor_uuid, 0 AS valid_from_revision,
               NULL AS valid_to_revision, zeroblob(32) AS row_digest
        FROM main.direct_association_version AS a
        JOIN temp.graph_object_version AS o ON o.uuid = a.object_uuid
        LEFT JOIN main.draft_graph_object_patch AS p ON p.uuid = a.object_uuid
        WHERE a.valid_to_revision IS NULL
          AND coalesce(p.has_complete_anchor_set, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM main.draft_association_operation AS d
              WHERE d.object_uuid = a.object_uuid AND d.anchor_uuid = a.anchor_uuid
          )
        UNION ALL
        SELECT d.object_uuid, d.anchor_uuid, 0, NULL, zeroblob(32)
        FROM main.draft_association_operation AS d
        JOIN temp.graph_object_version AS o ON o.uuid = d.object_uuid
        WHERE d.operation IN ('base', 'add');

        CREATE TEMP VIEW property_version AS
        SELECT p.object_uuid, p.property_name, 0 AS valid_from_revision,
               NULL AS valid_to_revision, p.value_kind, p.is_null,
               p.boolean_value, p.integer_value, p.number_value, p.text_value,
               p.date_value, p.timestamp_epoch_seconds, p.timestamp_nanosecond,
               p.timestamp_text, zeroblob(32) AS row_digest
        FROM main.property_version AS p
        JOIN temp.graph_object_version AS o ON o.uuid = p.object_uuid
        WHERE p.valid_to_revision IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM main.draft_property_operation AS d
              WHERE d.object_uuid = p.object_uuid AND d.property_name = p.property_name
          )
        UNION ALL
        SELECT d.object_uuid, d.property_name, 0, NULL, d.value_kind, d.is_null,
               d.boolean_value, d.integer_value, d.number_value, d.text_value,
               d.date_value, d.timestamp_epoch_seconds, d.timestamp_nanosecond,
               d.timestamp_text, zeroblob(32)
        FROM main.draft_property_operation AS d
        JOIN temp.graph_object_version AS o ON o.uuid = d.object_uuid
        WHERE d.operation = 'set';

        """,
    )
    if search_scopes:
        _install_search_overlay(connection, search_scopes)


def _install_search_overlay(connection, search_scopes):
    _execute_without_commit(
        connection,
        """
        CREATE TEMP TABLE search_document (
            document_id INTEGER PRIMARY KEY,
            object_uuid TEXT NOT NULL,
            kind TEXT NOT NULL,
            type_key TEXT NOT NULL,
            field_name TEXT NOT NULL,
            content TEXT NOT NULL,
            valid_from_revision INTEGER NOT NULL,
            valid_to_revision INTEGER
        );
        CREATE TEMP TABLE search_scope(
            kind TEXT NOT NULL, type_keys TEXT, uuids TEXT, field_name TEXT NOT NULL
        );
        """,
    )
    connection.executemany(
        "INSERT INTO temp.search_scope VALUES (?, ?, ?, ?)",
        (
            (
                kind,
                None if not type_keys else json.dumps(type_keys, separators=(",", ":")),
                None if not uuids else json.dumps(uuids, separators=(",", ":")),
                field_name,
            )
            for kind, type_keys, uuids, field_name in search_scopes
        ),
    )
    _execute_without_commit(
        connection,
        """
        INSERT INTO temp.search_document(
            object_uuid, kind, type_key, field_name, content,
            valid_from_revision, valid_to_revision
        )
        SELECT uuid, kind, type_key, 'displayName', display_name, 0, NULL
        FROM temp.graph_object_version AS o
        WHERE o.kind = 'anchor' AND EXISTS (
            SELECT 1 FROM temp.search_scope AS s
            WHERE s.kind = o.kind AND s.field_name = 'displayName'
              AND (s.type_keys IS NULL OR o.type_key IN (SELECT value FROM json_each(s.type_keys)))
              AND (s.uuids IS NULL OR o.uuid IN (SELECT value FROM json_each(s.uuids)))
        )
        UNION ALL
        SELECT o.uuid, o.kind, o.type_key, p.property_name, p.text_value, 0, NULL
        FROM temp.graph_object_version AS o
        JOIN temp.property_version AS p ON p.object_uuid = o.uuid
        WHERE p.is_null = 0 AND p.value_kind = 'text' AND EXISTS (
            SELECT 1 FROM temp.search_scope AS s
            WHERE s.kind = o.kind AND s.field_name = p.property_name
              AND (s.type_keys IS NULL OR o.type_key IN (SELECT value FROM json_each(s.type_keys)))
              AND (s.uuids IS NULL OR o.uuid IN (SELECT value FROM json_each(s.uuids)))
        );
        CREATE VIRTUAL TABLE temp.search_fts USING fts5(
            content,
            content='search_document',
            content_rowid='document_id',
            tokenize='unicode61 remove_diacritics 2'
        );
        INSERT INTO temp.search_fts(search_fts) VALUES ('rebuild');
        """,
    )


def remove_draft_graph_overlay(connection: sqlite3.Connection) -> None:
    """Remove the connection-local derived relations before canonical publication."""
    _execute_without_commit(
        connection,
        """
        DROP TABLE IF EXISTS temp.search_fts;
        DROP TABLE IF EXISTS temp.search_document;
        DROP TABLE IF EXISTS temp.search_scope;
        DROP VIEW IF EXISTS temp.property_version;
        DROP VIEW IF EXISTS temp.direct_association_version;
        DROP VIEW IF EXISTS temp.graph_object_version;
        DROP VIEW IF EXISTS temp.graph_object_identity;
        """,
    )


def _execute_without_commit(connection, script):
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)
