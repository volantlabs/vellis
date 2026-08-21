"""Independent audit checks for the search and FTS projections."""

from __future__ import annotations

import sqlite3


def check_observability(connection: sqlite3.Connection, findings: list[str]) -> None:
    _check_search_projection(connection, findings)


def _check_search_projection(connection: sqlite3.Connection, findings: list[str]) -> None:
    expected = """
        SELECT uuid AS object_uuid, kind, type_key, 'displayName' AS field_name,
               display_name AS content, valid_from_revision, valid_to_revision
        FROM graph_object_version WHERE kind = 'anchor'
        UNION ALL
        SELECT g.uuid, g.kind, g.type_key, p.property_name, p.text_value,
               p.valid_from_revision, p.valid_to_revision
        FROM graph_object_version g
        JOIN property_version p
          ON p.object_uuid = g.uuid AND p.valid_from_revision = g.valid_from_revision
        WHERE g.kind = 'associatedData' AND p.value_kind = 'text' AND p.is_null = 0
    """
    actual = """
        SELECT object_uuid, kind, type_key, field_name, content,
               valid_from_revision, valid_to_revision FROM search_document
    """
    missing = connection.execute(
        f"SELECT count(*) FROM (SELECT * FROM ({expected}) EXCEPT SELECT * FROM ({actual}))"
    ).fetchone()[0]
    extra = connection.execute(
        f"SELECT count(*) FROM (SELECT * FROM ({actual}) EXCEPT SELECT * FROM ({expected}))"
    ).fetchone()[0]
    if missing or extra:
        findings.append("search documents differ from versioned searchable values")
    mismatch = int(
        connection.execute(
            """SELECT count(*) FROM search_document d
               LEFT JOIN search_fts f ON f.rowid = d.document_id
               WHERE f.rowid IS NULL OR f.content <> d.content"""
        ).fetchone()[0]
    )
    extra_fts = int(
        connection.execute(
            """SELECT count(*) FROM search_fts f
               LEFT JOIN search_document d ON d.document_id = f.rowid
               WHERE d.document_id IS NULL"""
        ).fetchone()[0]
    )
    if mismatch or extra_fts:
        findings.append("search FTS entries differ from search documents")
    if not _fts_terms_equivalent(connection):
        findings.append("search FTS terms differ from independently rebuilt terms")


def _fts_terms_equivalent(connection):
    connection.execute("DROP TABLE IF EXISTS temp.audit_expected_fts")
    connection.execute("DROP TABLE IF EXISTS temp.audit_expected_vocab")
    connection.execute("DROP TABLE IF EXISTS temp.audit_actual_vocab")
    connection.execute(
        """CREATE VIRTUAL TABLE temp.audit_expected_fts
           USING fts5(content, tokenize='unicode61 remove_diacritics 2')"""
    )
    connection.execute(
        """INSERT INTO temp.audit_expected_fts(rowid, content)
           SELECT document_id, content FROM search_document"""
    )
    connection.execute(
        """CREATE VIRTUAL TABLE temp.audit_expected_vocab
           USING fts5vocab(audit_expected_fts, row)"""
    )
    connection.execute(
        """CREATE VIRTUAL TABLE temp.audit_actual_vocab
           USING fts5vocab(main, search_fts, row)"""
    )
    missing = connection.execute(
        """SELECT count(*) FROM (
           SELECT term, doc, cnt FROM temp.audit_expected_vocab
           EXCEPT SELECT term, doc, cnt FROM temp.audit_actual_vocab)"""
    ).fetchone()[0]
    extra = connection.execute(
        """SELECT count(*) FROM (
           SELECT term, doc, cnt FROM temp.audit_actual_vocab
           EXCEPT SELECT term, doc, cnt FROM temp.audit_expected_vocab)"""
    ).fetchone()[0]
    return not missing and not extra
