"""One-relation unpublished SQLite staging for a v1 JSON snapshot."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path

import ijson

from vellis.json_pointer import append_pointer
from vellis.v1_import_domain import V1ImportError
from vellis.v1_json import canonical_legacy_json, decode_legacy_json

STAGE_RELATION = "v1_initialization_stage"

_ARRAY_FAMILIES = (
    ("sourceAnchor", "graph.anchors.item"),
    ("sourceData", "graph.data_objects.item"),
    ("sourceLink", "graph.links.item"),
    ("sourceDefinition", "schema.definitions.item"),
    ("sourceConstraint", "constraints.constraints.item"),
    ("sourceMigration", "migration.migrations.item"),
)


def create_stage(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""CREATE TABLE {STAGE_RELATION}(
            category TEXT NOT NULL,
            natural_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            source_pointer TEXT NOT NULL,
            payload TEXT,
            sort_key BLOB,
            member BLOB,
            PRIMARY KEY(category, natural_key, ordinal)
        ) STRICT"""
    )
    connection.execute(
        f"CREATE INDEX {STAGE_RELATION}_order_idx "
        f"ON {STAGE_RELATION}(category, source_pointer, natural_key, ordinal)"
    )


def stage_source(connection: sqlite3.Connection, path: Path) -> tuple[str, int]:
    before = source_identity(path)
    _require_shapes(path)
    for category, prefix in _ARRAY_FAMILIES:
        for ordinal, entry in enumerate(_items(path, prefix)):
            key = _entry_key(entry, ordinal)
            pointer = "/" + prefix.replace(".item", "").replace(".", "/") + f"/{ordinal}"
            _put(connection, category, key, ordinal, pointer, entry)
    for ordinal, (key, pointer, payload) in enumerate(_association_pairs(path)):
        _put(
            connection,
            "sourceAssociation",
            key,
            ordinal,
            pointer,
            payload,
        )
    after = source_identity(path)
    if after != before:
        raise V1ImportError("the v1 source changed while it was being staged")
    return before


def source_identity(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            total += len(block)
    return digest.hexdigest(), total


def iter_category(
    connection: sqlite3.Connection, category: str
) -> Iterator[tuple[str, str, object]]:
    rows = connection.execute(
        f"SELECT natural_key, source_pointer, payload FROM {STAGE_RELATION} "
        "WHERE category = ? ORDER BY ordinal",
        (category,),
    )
    for row in rows:
        yield str(row[0]), str(row[1]), decode_legacy_json(str(row[2]))


def put_payload(
    connection: sqlite3.Connection,
    category: str,
    natural_key: str,
    source_pointer: str,
    value: object,
    *,
    ordinal: int = 0,
) -> None:
    _put(connection, category, natural_key, ordinal, source_pointer, value)


def _put(connection, category, key, ordinal, pointer, value):
    connection.execute(
        f"INSERT INTO {STAGE_RELATION}(category,natural_key,ordinal,source_pointer,payload) "
        "VALUES(?,?,?,?,?)",
        (category, key, ordinal, pointer, canonical_legacy_json(value)),
    )


def _items(path: Path, prefix: str) -> Iterator[Mapping[str, object]]:
    with path.open("rb") as source:
        for value in ijson.items(source, prefix):
            if not isinstance(value, dict):
                raise V1ImportError(f"an entry in {prefix} is not an object")
            yield value


def _entry_key(entry: Mapping[str, object], ordinal: int) -> str:
    for name in ("uuid", "type_key"):
        value = entry.get(name)
        if isinstance(value, str):
            return value
    return f"ordinal:{ordinal}"


def _require_shapes(path: Path) -> None:
    expected = {
        "": "start_map",
        "graph": "start_map",
        "graph.anchors": "start_array",
        "graph.data_objects": "start_array",
        "graph.links": "start_array",
        "graph.anchor_data_index": "start_map",
        "schema": "start_map",
        "schema.definitions": "start_array",
        "constraints": "start_map",
        "constraints.constraints": "start_array",
        "migration": "start_map",
        "migration.migrations": "start_array",
    }
    observed: dict[str, str] = {}
    with path.open("rb") as source:
        for prefix, event, _value in ijson.parse(source):
            if prefix in expected and event in {"start_map", "start_array", "null"}:
                observed.setdefault(prefix, event)
    if any(observed.get(prefix) != event for prefix, event in expected.items()):
        raise V1ImportError("the source is not a complete Vellis v1 JSON snapshot")


def _association_pairs(path: Path) -> Iterator[tuple[str, str, object]]:
    current_anchor: str | None = None
    ordinal = 0
    in_array = False
    with path.open("rb") as source:
        for prefix, event, value in ijson.parse(source):
            if prefix == "graph.anchor_data_index" and event == "map_key":
                current_anchor = str(value)
                ordinal = 0
                in_array = False
                continue
            if current_anchor is None:
                continue
            base = f"graph.anchor_data_index.{current_anchor}"
            pointer_base = append_pointer("/graph/anchor_data_index", current_anchor)
            if prefix == base and event == "start_array":
                in_array = True
            elif prefix == base and event == "end_array":
                current_anchor = None
                in_array = False
            elif (
                prefix == base
                and not in_array
                and event
                in {
                    "null",
                    "boolean",
                    "integer",
                    "double",
                    "number",
                    "string",
                    "start_map",
                }
            ):
                yield (
                    f"malformed:{current_anchor}",
                    pointer_base,
                    {"shapeError": "association index value must be an array"},
                )
                current_anchor = None
            elif prefix == f"{base}.item" and event == "string":
                pointer = f"{pointer_base}/{ordinal}"
                yield (
                    str(value),
                    pointer,
                    {
                        "anchorUuid": current_anchor,
                        "dataUuid": str(value),
                    },
                )
                ordinal += 1
            elif prefix == f"{base}.item" and event in {
                "null",
                "boolean",
                "integer",
                "double",
                "number",
                "start_map",
                "start_array",
            }:
                pointer = f"{pointer_base}/{ordinal}"
                yield (
                    f"malformed:{current_anchor}:{ordinal}",
                    pointer,
                    {"shapeError": "association index member must be a UUID string"},
                )
                ordinal += 1
