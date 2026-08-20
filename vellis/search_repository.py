"""Connection-local Unicode text predicates and version-aware FTS projection."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Any

import re2

from vellis.domain import Anchor, AssociatedData, GraphObject, ValueKind
from vellis.query_domain import Predicate, PredicateOperator


def register_query_functions(connection: sqlite3.Connection) -> None:
    connection.create_function("vellis_casefold_contains", 2, _folded_contains, deterministic=True)
    connection.create_function("vellis_casefold_prefix", 2, _folded_prefix, deterministic=True)
    connection.create_function("vellis_re2_search", 3, _regex_search, deterministic=True)


def structured_fts_expression(connection: sqlite3.Connection, predicate: Predicate) -> str:
    _ensure_tokenizer(connection)
    if predicate.operator in {PredicateOperator.ALL_TERMS, PredicateOperator.ANY_TERMS}:
        tokens = []
        for value in predicate.terms:
            parsed = _tokenize(connection, value)
            if len(parsed) != 1:
                raise ValueError("each full-text term must tokenize to exactly one token")
            tokens.append(_quote(parsed[0]))
        separator = " AND " if predicate.operator is PredicateOperator.ALL_TERMS else " OR "
        return separator.join(tokens)
    assert predicate.operator is PredicateOperator.PHRASE
    assert predicate.text is not None
    tokens = _tokenize(connection, predicate.text)
    if not tokens:
        raise ValueError("full-text phrase must tokenize to at least one token")
    return _quote(" ".join(tokens))


def insert_search_versions(
    connection: sqlite3.Connection, objects: tuple[GraphObject, ...], revision: int
) -> None:
    for value in objects:
        for field_name, content in _searchable_values(value):
            cursor = connection.execute(
                """
                INSERT INTO search_document(
                    object_uuid, kind, type_key, field_name, content, valid_from_revision
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (value.uuid, value.kind.value, value.type_key, field_name, content, revision),
            )
            if cursor.lastrowid is None:
                raise ValueError("search document insertion returned no identity")
            document_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO search_fts(rowid, content) VALUES (?, ?)",
                (document_id, content),
            )


def close_search_versions(
    connection: sqlite3.Connection, object_uuids: tuple[str, ...], revision: int
) -> None:
    if not object_uuids:
        return
    placeholders = ", ".join("?" for _ in object_uuids)
    connection.execute(
        f"""
        UPDATE search_document SET valid_to_revision = ?
        WHERE object_uuid IN ({placeholders}) AND valid_to_revision IS NULL
        """,
        (revision, *object_uuids),
    )


def _searchable_values(value: GraphObject) -> tuple[tuple[str, str], ...]:
    if isinstance(value, Anchor):
        return (("displayName", value.display_name),)
    if isinstance(value, AssociatedData):
        return tuple(
            (name, scalar.value)
            for name, scalar in value.properties
            if scalar is not None
            and scalar.kind is ValueKind.TEXT
            and isinstance(scalar.value, str)
        )
    return ()


def _ensure_tokenizer(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS temp.vellis_query_tokens "
        "USING fts5(content, tokenize='unicode61 remove_diacritics 2')"
    )
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS temp.vellis_query_vocab "
        "USING fts5vocab(vellis_query_tokens, instance)"
    )


def _tokenize(connection: sqlite3.Connection, value: str) -> tuple[str, ...]:
    connection.execute("DELETE FROM temp.vellis_query_tokens")
    connection.execute(
        "INSERT INTO temp.vellis_query_tokens(rowid, content) VALUES (1, ?)", (value,)
    )
    rows = connection.execute(
        "SELECT term FROM temp.vellis_query_vocab WHERE doc = 1 ORDER BY offset"
    ).fetchall()
    return tuple(str(row["term"]) for row in rows)


def _quote(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _folded_contains(content: str, expected: str) -> int:
    return int(expected.casefold() in content.casefold())


def _folded_prefix(content: str, expected: str) -> int:
    return int(content.casefold().startswith(expected.casefold()))


def _regex_search(content: str, pattern: str, case_sensitive: int) -> int:
    expression = _compiled_regex(pattern, bool(case_sensitive))
    return int(expression.search(content) is not None)


@lru_cache(maxsize=256)
def _compiled_regex(pattern: str, case_sensitive: bool) -> Any:
    prefix = "" if case_sensitive else "(?i)"
    return re2.compile(prefix + pattern)
