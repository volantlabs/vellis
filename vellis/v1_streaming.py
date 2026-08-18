"""Incremental Vellis v1 JSON import through normalized temporary SQLite."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator, Mapping, MutableMapping, MutableSequence, MutableSet
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, cast, overload

import ijson

from vellis.canonical import Provenance, now
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DefinitionEntry,
    GraphDefinitionSet,
    LinkTypeDefinition,
    RelationshipConstraint,
    relationship_identity,
)
from vellis.graph import GraphObject
from vellis.json_value import JsonKind, JsonValue
from vellis.normalized import (
    insert_associated_data_value,
    insert_definition_entries,
    insert_definition_entry,
    insert_object_value,
    load_definition_set,
    semantic_identity,
)
from vellis.outcomes import ValidationScope
from vellis.store import CanonicalStore, StoreError, prepare_private_directory
from vellis.v1 import (
    RecoveryDisposition,
    RecoveryFacts,
    RecoveryFinding,
    SnapshotError,
    _is_live,
    _recovered_anchor,
    _recovered_data_object,
    _recovered_link,
    _translate_constraint,
    _translate_definition,
    _translated_vocabulary_entries,
    _Translation,
)

__all__ = ["V1StreamPreview", "import_v1_stream", "preview_v1_stream"]


@dataclass(frozen=True, slots=True)
class V1StreamPreview:
    """Bounded summary and complete disposition report for one exact v1 file."""

    path: Path
    source_identity: str
    findings: tuple[RecoveryFinding, ...]
    anchor_count: int
    data_count: int
    link_count: int
    anchor_type_count: int
    data_type_count: int
    link_type_count: int

    @property
    def is_acceptable(self) -> bool:
        return not any(
            finding.disposition is RecoveryDisposition.BLOCKING for finding in self.findings
        )

    @property
    def summary(self) -> str:
        return (
            f"first-use recovery from a Vellis v1 snapshot ({self.source_identity[:12]}) "
            f"with {self.anchor_count} anchors, {self.data_count} associated-data objects, "
            f"{self.link_count} links, {self.anchor_type_count} anchor types, "
            f"{self.data_type_count} associated-data types, and {self.link_type_count} link types"
        )


class _SQLiteRecoveryFacts(RecoveryFacts):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def data_type_used(self, type_key: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM recovery_object AS r JOIN object_value AS v"
                " ON v.id = r.object_value_id WHERE v.object_kind = 'associatedData'"
                " AND v.type_key = ? LIMIT 1",
                (type_key,),
            ).fetchone()
            is not None
        )

    def grounding_types(self, type_key: str) -> set[str]:
        return {
            str(row[0])
            for row in self._connection.execute(
                "SELECT DISTINCT av.type_key FROM recovery_object AS dr"
                " JOIN object_value AS dv ON dv.id = dr.object_value_id"
                " JOIN object_anchor AS oa ON oa.object_value_id = dv.id"
                " JOIN recovery_object AS ar ON ar.uuid = oa.anchor_uuid"
                " JOIN object_value AS av ON av.id = ar.object_value_id"
                " WHERE dv.object_kind = 'associatedData' AND dv.type_key = ?",
                (type_key,),
            )
        }

    def stored_kinds(self, type_key: str, name: str) -> set[JsonKind]:
        return {
            JsonKind(str(row[0]))
            for row in self._connection.execute(
                "SELECT DISTINCT p.json_kind FROM recovery_object AS r"
                " JOIN object_value AS v ON v.id = r.object_value_id"
                " JOIN object_property AS p ON p.object_value_id = v.id"
                " WHERE v.object_kind = 'associatedData' AND v.type_key = ? AND p.name = ?",
                (type_key, name),
            )
        }


T = TypeVar("T")


class _DefinitionSequence:
    """List-like normalized temporary definitions loaded one entry at a time."""

    def __init__(self, connection: sqlite3.Connection, bucket: str) -> None:
        self.connection = connection
        self.bucket = bucket

    def __len__(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM recovery_translation_entry WHERE bucket = ?",
                (self.bucket,),
            ).fetchone()[0]
        )

    def __iter__(self) -> Iterator[object]:
        order = "natural_key, ordinal" if self.bucket == "relationship" else "ordinal"
        for (set_id,) in self.connection.execute(
            "SELECT value_set_id FROM recovery_translation_entry"
            f" WHERE bucket = ? ORDER BY {order}",  # noqa: S608
            (self.bucket,),
        ):
            definitions = load_definition_set(self.connection, str(set_id), one_entry=True)
            yield self._value(definitions)

    def __getitem__(self, index: int) -> object:
        size = len(self)
        resolved = index if index >= 0 else size + index
        row = self.connection.execute(
            "SELECT value_set_id FROM recovery_translation_entry"
            " WHERE bucket = ? ORDER BY ordinal LIMIT 1 OFFSET ?",
            (self.bucket, resolved),
        ).fetchone()
        if row is None:
            raise IndexError(index)
        return self._value(load_definition_set(self.connection, str(row[0]), one_entry=True))

    def append(self, value: object) -> None:
        definitions = _one_definition(value)
        set_id = insert_definition_entry(self.connection, definitions)
        natural_key = (
            semantic_identity(relationship_identity(cast(RelationshipConstraint, value)))
            if self.bucket == "relationship"
            else None
        )
        self.connection.execute(
            "INSERT INTO recovery_translation_entry VALUES (?, ?, ?, ?)",
            (self.bucket, len(self), natural_key, set_id),
        )

    def _value(self, definitions: GraphDefinitionSet) -> object:
        if self.bucket == "anchor":
            return definitions.anchor_types[0]
        if self.bucket == "link":
            return definitions.link_types[0]
        return definitions.relationship_constraints[0]


class _DataDefinitionMap:
    """Natural-key mapping backed by normalized one-entry definition sets."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __len__(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM recovery_translation_entry WHERE bucket = 'data'"
            ).fetchone()[0]
        )

    def __iter__(self) -> Iterator[str]:
        yield from (
            str(row[0])
            for row in self.connection.execute(
                "SELECT natural_key FROM recovery_translation_entry"
                " WHERE bucket = 'data' ORDER BY ordinal"
            )
        )

    def values(self) -> Iterator[AssociatedDataTypeDefinition]:
        for key in self:
            yield self[key]

    def __getitem__(self, key: str) -> AssociatedDataTypeDefinition:
        row = self.connection.execute(
            "SELECT value_set_id FROM recovery_translation_entry"
            " WHERE bucket = 'data' AND natural_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return load_definition_set(
            self.connection, str(row[0]), one_entry=True
        ).associated_data_types[0]

    def __setitem__(self, key: str, value: AssociatedDataTypeDefinition) -> None:
        set_id = insert_definition_entry(
            self.connection, GraphDefinitionSet(associated_data_types=(value,))
        )
        row = self.connection.execute(
            "SELECT ordinal FROM recovery_translation_entry"
            " WHERE bucket = 'data' AND natural_key = ?",
            (key,),
        ).fetchone()
        ordinal = len(self) if row is None else int(row[0])
        self.connection.execute(
            "INSERT OR REPLACE INTO recovery_translation_entry VALUES ('data', ?, ?, ?)",
            (ordinal, key, set_id),
        )

    def __delitem__(self, key: str) -> None:
        cursor = self.connection.execute(
            "DELETE FROM recovery_translation_entry WHERE bucket = 'data' AND natural_key = ?",
            (key,),
        )
        if cursor.rowcount == 0:
            raise KeyError(key)


class _SQLiteStringList(MutableSequence[str]):
    def __init__(self, connection: sqlite3.Connection, bucket: str, key: str) -> None:
        self.connection = connection
        self.bucket = bucket
        self.key = key

    def __len__(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM recovery_translation_value"
                " WHERE bucket = ? AND natural_key = ?",
                (self.bucket, self.key),
            ).fetchone()[0]
        )

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> MutableSequence[str]: ...

    def __getitem__(self, index: int | slice) -> str | MutableSequence[str]:
        if isinstance(index, slice):
            return [self[each] for each in range(*index.indices(len(self)))]
        resolved = index if index >= 0 else len(self) + index
        row = self.connection.execute(
            "SELECT text_value FROM recovery_translation_value"
            " WHERE bucket = ? AND natural_key = ? ORDER BY ordinal LIMIT 1 OFFSET ?",
            (self.bucket, self.key, resolved),
        ).fetchone()
        if row is None:
            raise IndexError(index)
        return str(row[0])

    @overload
    def __setitem__(self, index: int, value: str) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[str]) -> None: ...

    def __setitem__(self, index: int | slice, value: str | Iterable[str]) -> None:
        if isinstance(index, slice):
            raise TypeError("slice replacement is not used by recovery translation")
        if not isinstance(value, str):
            raise TypeError("one translated value must be a string")
        resolved = index if index >= 0 else len(self) + index
        cursor = self.connection.execute(
            "UPDATE recovery_translation_value SET text_value = ?"
            " WHERE bucket = ? AND natural_key = ? AND ordinal = ?",
            (value, self.bucket, self.key, resolved),
        )
        if cursor.rowcount == 0:
            raise IndexError(index)

    def __delitem__(self, index: int | slice) -> None:
        if isinstance(index, slice):
            raise TypeError("slice deletion is not used by recovery translation")
        resolved = index if index >= 0 else len(self) + index
        cursor = self.connection.execute(
            "DELETE FROM recovery_translation_value"
            " WHERE bucket = ? AND natural_key = ? AND ordinal = ?",
            (self.bucket, self.key, resolved),
        )
        if cursor.rowcount == 0:
            raise IndexError(index)
        self.connection.execute(
            "UPDATE recovery_translation_value SET ordinal = ordinal - 1"
            " WHERE bucket = ? AND natural_key = ? AND ordinal > ?",
            (self.bucket, self.key, resolved),
        )

    def insert(self, index: int, value: str) -> None:
        resolved = max(0, min(index, len(self)))
        self.connection.execute(
            "UPDATE recovery_translation_value SET ordinal = ordinal + 1"
            " WHERE bucket = ? AND natural_key = ? AND ordinal >= ?",
            (self.bucket, self.key, resolved),
        )
        self.connection.execute(
            "INSERT INTO recovery_translation_value VALUES (?, ?, ?, ?, NULL)",
            (self.bucket, self.key, resolved, value),
        )


class _SQLiteStringListMap(MutableMapping[str, MutableSequence[str]]):
    def __init__(self, connection: sqlite3.Connection, bucket: str) -> None:
        self.connection = connection
        self.bucket = bucket

    def __len__(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM recovery_translation_map_key WHERE bucket = ?",
                (self.bucket,),
            ).fetchone()[0]
        )

    def __iter__(self) -> Iterator[str]:
        yield from (
            str(row[0])
            for row in self.connection.execute(
                "SELECT natural_key FROM recovery_translation_map_key"
                " WHERE bucket = ? ORDER BY natural_key",
                (self.bucket,),
            )
        )

    def __getitem__(self, key: str) -> MutableSequence[str]:
        if (
            self.connection.execute(
                "SELECT 1 FROM recovery_translation_map_key WHERE bucket = ? AND natural_key = ?",
                (self.bucket, key),
            ).fetchone()
            is None
        ):
            raise KeyError(key)
        return _SQLiteStringList(self.connection, self.bucket, key)

    def __setitem__(self, key: str, values: MutableSequence[str]) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO recovery_translation_map_key VALUES (?, ?)",
            (self.bucket, key),
        )
        self.connection.execute(
            "DELETE FROM recovery_translation_value WHERE bucket = ? AND natural_key = ?",
            (self.bucket, key),
        )
        self.connection.executemany(
            "INSERT INTO recovery_translation_value VALUES (?, ?, ?, ?, NULL)",
            ((self.bucket, key, ordinal, value) for ordinal, value in enumerate(values)),
        )

    def __delitem__(self, key: str) -> None:
        cursor = self.connection.execute(
            "DELETE FROM recovery_translation_map_key WHERE bucket = ? AND natural_key = ?",
            (self.bucket, key),
        )
        if cursor.rowcount == 0:
            raise KeyError(key)
        self.connection.execute(
            "DELETE FROM recovery_translation_value WHERE bucket = ? AND natural_key = ?",
            (self.bucket, key),
        )

    def setdefault(
        self, key: str, default: MutableSequence[str] | None = None
    ) -> MutableSequence[str]:
        if key not in self:
            self[key] = [] if default is None else default
        return _SQLiteStringList(self.connection, self.bucket, key)


class _SQLiteIntMap(MutableMapping[str, int]):
    def __init__(self, connection: sqlite3.Connection, bucket: str) -> None:
        self.connection = connection
        self.bucket = bucket

    def __len__(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM recovery_translation_value"
                " WHERE bucket = ? AND int_value IS NOT NULL",
                (self.bucket,),
            ).fetchone()[0]
        )

    def __iter__(self) -> Iterator[str]:
        yield from (
            str(row[0])
            for row in self.connection.execute(
                "SELECT natural_key FROM recovery_translation_value"
                " WHERE bucket = ? AND int_value IS NOT NULL ORDER BY natural_key",
                (self.bucket,),
            )
        )

    def __getitem__(self, key: str) -> int:
        row = self.connection.execute(
            "SELECT int_value FROM recovery_translation_value"
            " WHERE bucket = ? AND natural_key = ? AND int_value IS NOT NULL",
            (self.bucket, key),
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return int(row[0])

    def __setitem__(self, key: str, value: int) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO recovery_translation_value VALUES (?, ?, 0, NULL, ?)",
            (self.bucket, key, value),
        )

    def __delitem__(self, key: str) -> None:
        cursor = self.connection.execute(
            "DELETE FROM recovery_translation_value WHERE bucket = ? AND natural_key = ?",
            (self.bucket, key),
        )
        if cursor.rowcount == 0:
            raise KeyError(key)


class _SQLiteKeySet(MutableSet[str]):
    def __init__(self, connection: sqlite3.Connection, bucket: str) -> None:
        self.connection = connection
        self.bucket = bucket

    def __len__(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM recovery_translation_map_key WHERE bucket = ?",
                (self.bucket,),
            ).fetchone()[0]
        )

    def __iter__(self) -> Iterator[str]:
        yield from (
            str(row[0])
            for row in self.connection.execute(
                "SELECT natural_key FROM recovery_translation_map_key"
                " WHERE bucket = ? ORDER BY natural_key",
                (self.bucket,),
            )
        )

    def __contains__(self, value: object) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM recovery_translation_map_key WHERE bucket = ? AND natural_key = ?",
                (self.bucket, str(value)),
            ).fetchone()
            is not None
        )

    def add(self, value: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO recovery_translation_map_key VALUES (?, ?)",
            (self.bucket, value),
        )

    def discard(self, value: str) -> None:
        self.connection.execute(
            "DELETE FROM recovery_translation_map_key WHERE bucket = ? AND natural_key = ?",
            (self.bucket, value),
        )


def _one_definition(value: object) -> GraphDefinitionSet:
    if isinstance(value, AnchorTypeDefinition):
        return GraphDefinitionSet(anchor_types=(value,))
    if isinstance(value, LinkTypeDefinition):
        return GraphDefinitionSet(link_types=(value,))
    return GraphDefinitionSet(relationship_constraints=(cast(RelationshipConstraint, value),))


def _items(path: Path, prefix: str) -> Iterator[Mapping[str, JsonValue]]:
    with path.open("rb") as source:
        for value in ijson.items(source, prefix):
            if not isinstance(value, dict):
                raise SnapshotError(f"an entry in {prefix} is not an object")
            yield cast(Mapping[str, JsonValue], value)


def _association_pairs(path: Path) -> Iterator[tuple[str, str]]:
    """Stream v1 anchor/data associations without materializing any anchor's array."""
    current_anchor: str | None = None
    in_array = False
    with path.open("rb") as source:
        for prefix, event, value in ijson.parse(source):
            if prefix == "graph.anchor_data_index" and event == "map_key":
                current_anchor = str(value)
                in_array = False
                continue
            if current_anchor is None:
                continue
            value_prefix = f"graph.anchor_data_index.{current_anchor}"
            if prefix == value_prefix and event == "start_array":
                in_array = True
                continue
            if prefix == value_prefix and event == "end_array":
                current_anchor = None
                in_array = False
                continue
            if prefix == value_prefix and event not in {"start_array", "end_array"}:
                raise SnapshotError(
                    f"the associations recorded for anchor {current_anchor} are not a list"
                )
            if in_array and prefix == f"{value_prefix}.item":
                if event != "string":
                    raise SnapshotError(
                        f"an association recorded for anchor {current_anchor} is not a UUID"
                    )
                yield str(value), current_anchor


def _snapshot_shapes(path: Path) -> dict[str, str]:
    """Read only container events needed to recognize the v1 document shape."""
    wanted = {
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
            if prefix in wanted and event in {"start_map", "start_array", "null"}:
                observed.setdefault(prefix, event)
    return observed


def _source_identity(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _live(entry: Mapping[str, JsonValue], kind: str, findings: list[RecoveryFinding]) -> bool:
    try:
        live = _is_live(entry)
    except SnapshotError as error:
        findings.append(
            RecoveryFinding(RecoveryDisposition.BLOCKING, f"a v1 {kind} cannot be read: {error}")
        )
        return False
    if not live:
        identity = entry.get("type_key") or entry.get("uuid")
        findings.append(
            RecoveryFinding(
                RecoveryDisposition.OMITTED,
                f"the non-live {kind} {identity} is not imported; only live v1 content "
                "becomes memory",
            )
        )
    return live


def _stage_value(connection: sqlite3.Connection, value: GraphObject) -> None:
    value_id = insert_object_value(connection, value)
    connection.execute("INSERT INTO recovery_object VALUES (?, ?)", (value.uuid, value_id))


def _stage_data_value(
    connection: sqlite3.Connection,
    value: GraphObject,
    findings: list[RecoveryFinding],
) -> None:
    from vellis.graph import AssociatedDataObject

    assert isinstance(value, AssociatedDataObject)

    def live_anchors() -> Iterator[str]:
        yield from (
            str(row[0])
            for row in connection.execute(
                "SELECT a.anchor_uuid FROM recovery_association AS a"
                " LEFT JOIN recovery_anchor AS s ON s.uuid = a.anchor_uuid"
                " WHERE a.data_uuid = ? AND coalesce(s.live, 1) = 1 ORDER BY a.anchor_uuid",
                (value.uuid,),
            )
        )

    for (anchor_uuid,) in connection.execute(
        "SELECT a.anchor_uuid FROM recovery_association AS a"
        " JOIN recovery_anchor AS s ON s.uuid = a.anchor_uuid"
        " WHERE a.data_uuid = ? AND s.live = 0 ORDER BY a.anchor_uuid",
        (value.uuid,),
    ):
        findings.append(
            RecoveryFinding(
                RecoveryDisposition.OMITTED,
                f"associated-data object {value.uuid} was grounded by the anchor "
                f"{anchor_uuid} in v1, which is not live and does not become memory, so that "
                "grounding is left out with it",
            )
        )
    value_id = insert_associated_data_value(connection, value, live_anchors)
    connection.execute("INSERT INTO recovery_object VALUES (?, ?)", (value.uuid, value_id))


def _recover_entry(
    reader: object,
    entry: Mapping[str, JsonValue],
    findings: list[RecoveryFinding],
    *extra: object,
) -> GraphObject | None:
    try:
        return reader(entry, findings, *extra)  # type: ignore[operator]
    except SnapshotError as error:
        findings.append(
            RecoveryFinding(RecoveryDisposition.BLOCKING, f"a v1 record cannot be read: {error}")
        )
        return None


def _build(
    path: Path, database: Path, *, expected_source_identity: str | None = None
) -> V1StreamPreview:
    expected_shapes = {
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
    shapes = _snapshot_shapes(path)
    if any(shapes.get(prefix) != event for prefix, event in expected_shapes.items()):
        raise SnapshotError(
            "this is not a Vellis v1 system snapshot: required sections have invalid shapes"
        )
    source_identity = _source_identity(path)
    if expected_source_identity is not None and source_identity != expected_source_identity:
        raise SnapshotError("the v1 snapshot bytes do not match the confirmed input")
    findings: list[RecoveryFinding] = []
    store = CanonicalStore(database)
    connection = store._connection  # noqa: SLF001
    try:
        connection.execute(
            "CREATE TEMP TABLE recovery_object"
            " (uuid TEXT PRIMARY KEY, object_value_id INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE TEMP TABLE recovery_anchor (uuid TEXT PRIMARY KEY, live INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE TEMP TABLE recovery_association"
            " (data_uuid TEXT NOT NULL, anchor_uuid TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX recovery_association_data ON recovery_association(data_uuid)"
        )
        connection.execute(
            "CREATE TEMP TABLE recovery_translation_entry ("
            " bucket TEXT NOT NULL, ordinal INTEGER NOT NULL, natural_key TEXT,"
            " value_set_id TEXT NOT NULL, PRIMARY KEY (bucket, ordinal))"
        )
        connection.execute(
            "CREATE TEMP TABLE recovery_translation_map_key"
            " (bucket TEXT NOT NULL, natural_key TEXT NOT NULL,"
            " PRIMARY KEY (bucket, natural_key)) WITHOUT ROWID"
        )
        connection.execute(
            "CREATE TEMP TABLE recovery_translation_value"
            " (bucket TEXT NOT NULL, natural_key TEXT NOT NULL, ordinal INTEGER NOT NULL,"
            " text_value TEXT, int_value INTEGER,"
            " PRIMARY KEY (bucket, natural_key, ordinal)) WITHOUT ROWID"
        )

        connection.executemany(
            "INSERT INTO recovery_association VALUES (?, ?)", _association_pairs(path)
        )

        anchor_count = 0
        for entry in _items(path, "graph.anchors.item"):
            uuid = entry.get("uuid")
            if not isinstance(uuid, str):
                findings.append(
                    RecoveryFinding(RecoveryDisposition.BLOCKING, "a v1 anchor has no uuid")
                )
                continue
            live = _live(entry, "anchor", findings)
            connection.execute("INSERT INTO recovery_anchor VALUES (?, ?)", (uuid, int(live)))
            if not live:
                continue
            value = _recover_entry(_recovered_anchor, entry, findings)
            if value is not None:
                _stage_value(connection, value)
                anchor_count += 1

        data_count = 0
        for entry in _items(path, "graph.data_objects.item"):
            if not _live(entry, "associated-data object", findings):
                continue
            uuid = entry.get("uuid")
            if not isinstance(uuid, str):
                findings.append(
                    RecoveryFinding(
                        RecoveryDisposition.BLOCKING,
                        "a v1 associated-data object has no uuid",
                    )
                )
                continue
            value = _recover_entry(_recovered_data_object, entry, findings, {}, set())
            if value is not None:
                _stage_data_value(connection, value, findings)
                data_count += 1

        link_count = 0
        for entry in _items(path, "graph.links.item"):
            if not _live(entry, "link", findings):
                continue
            value = _recover_entry(_recovered_link, entry, findings)
            if value is not None:
                _stage_value(connection, value)
                link_count += 1

        facts = _SQLiteRecoveryFacts(connection)
        translation = _Translation(
            anchors=cast(
                MutableSequence[AnchorTypeDefinition],
                _DefinitionSequence(connection, "anchor"),
            ),
            data_types=cast(
                MutableMapping[str, AssociatedDataTypeDefinition],
                _DataDefinitionMap(connection),
            ),
            links=cast(
                MutableSequence[LinkTypeDefinition],
                _DefinitionSequence(connection, "link"),
            ),
            constraints=cast(
                MutableSequence[RelationshipConstraint],
                _DefinitionSequence(connection, "relationship"),
            ),
            guarantees=cast(
                MutableSequence[RelationshipConstraint],
                _DefinitionSequence(connection, "guarantee"),
            ),
            limited_floors=_SQLiteIntMap(connection, "floor"),
            carried_whole=_SQLiteStringListMap(connection, "carried"),
            permitted_anchors=_SQLiteStringListMap(connection, "permitted"),
            anchor_keys=_SQLiteKeySet(connection, "anchorKey"),
            data_keys=_SQLiteKeySet(connection, "dataKey"),
            link_keys=_SQLiteKeySet(connection, "linkKey"),
        )
        for entry in _items(path, "schema.definitions.item"):
            if not _live(entry, "definition", findings):
                continue
            try:
                _translate_definition(entry, facts, translation, findings)
            except SnapshotError as error:
                findings.append(
                    RecoveryFinding(
                        RecoveryDisposition.BLOCKING,
                        f"a v1 definition cannot be read: {error}",
                    )
                )
        for entry in _items(path, "constraints.constraints.item"):
            if _live(entry, "constraint", findings):
                _translate_constraint(entry, translation, findings)
        migration_count = sum(1 for _ in _items(path, "migration.migrations.item"))
        if migration_count:
            findings.append(
                RecoveryFinding(
                    RecoveryDisposition.OMITTED,
                    f"{migration_count} v1 migration records describe prior history and "
                    "are left out",
                )
            )
        anchor_type_count = data_type_count = link_type_count = 0

        def settled_entries() -> Iterator[DefinitionEntry]:
            nonlocal anchor_type_count, data_type_count, link_type_count
            for definitions in _translated_vocabulary_entries(translation, facts, findings):
                if definitions.anchor_types:
                    anchor_type_count += 1
                elif definitions.associated_data_types:
                    data_type_count += 1
                elif definitions.link_types:
                    link_type_count += 1
                yield from definitions.entries()

        definition_identity = insert_definition_entries(connection, settled_entries())
        if not any(f.disposition is RecoveryDisposition.BLOCKING for f in findings):
            summary = (
                f"first-use recovery from a Vellis v1 snapshot ({source_identity[:12]})"
                f" with {anchor_count} anchors, {data_count} associated-data objects,"
                f" {link_count} links, {anchor_type_count} anchor types,"
                f" {data_type_count} associated-data types, and"
                f" {link_type_count} link types"
            )
            store.initialize_staged_recovery_identity(
                definition_identity,
                provenance=Provenance("owner", "vellis setup: v1 recovery"),
                initialization_summary=summary,
                recorded_at=now(),
            )
            revision, relation, definition_id, _ = store.conformance_context(
                ValidationScope.GRAPH_CONFORMANCE
            )
            assert revision == 0 and definition_id is not None
            findings.extend(
                RecoveryFinding(
                    RecoveryDisposition.BLOCKING,
                    f"the v1 content does not form a system this can hold: {finding.summary}",
                )
                for finding in store.iter_conformance_findings(relation, definition_id)
            )
        if not findings or not any(
            finding.disposition is RecoveryDisposition.BLOCKING for finding in findings
        ):
            findings.insert(
                0,
                RecoveryFinding(
                    RecoveryDisposition.PRESERVED,
                    f"{anchor_count} anchors, {data_count} associated-data objects, and "
                    f"{link_count} links arrive exactly as v1 stored them",
                ),
            )
        if _source_identity(path) != source_identity:
            raise SnapshotError("the v1 snapshot changed while it was being imported")
        return V1StreamPreview(
            path,
            source_identity,
            tuple(findings),
            anchor_count,
            data_count,
            link_count,
            anchor_type_count,
            data_type_count,
            link_type_count,
        )
    finally:
        store.close()


def preview_v1_stream(path: Path) -> V1StreamPreview:
    """Incrementally verify one v1 file without retaining its graph in memory."""
    try:
        with tempfile.TemporaryDirectory(prefix="vellis-v1-preview-") as directory:
            return _build(path, Path(directory) / "preview.sqlite3")
    except (OSError, UnicodeError, ijson.JSONError, sqlite3.Error) as error:
        raise SnapshotError(f"could not incrementally read {path}: {error}") from error


def import_v1_stream(
    path: Path, destination: Path, *, expected_source_identity: str | None = None
) -> V1StreamPreview:
    """Verify in sibling temporary SQLite and publish only one accepted import."""
    if destination.exists():
        raise StoreError("v1 import requires an empty destination")
    prepare_private_directory(destination.parent)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".v1-import", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        preview = _build(path, temporary, expected_source_identity=expected_source_identity)
        if not preview.is_acceptable:
            raise StoreError("the v1 snapshot has blocking recovery findings")
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise StoreError("v1 destination was established concurrently") from error
        temporary.unlink()
        return preview
    finally:
        for candidate in (temporary, Path(str(temporary) + "-wal"), Path(str(temporary) + "-shm")):
            candidate.unlink(missing_ok=True)
