"""Read-only integrity checks for fresh VEL2 databases."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from vellis.audit_governance import check_governance
from vellis.audit_observability import check_observability
from vellis.canonical_encoding import (
    CanonicalHeader,
    Record,
    RowDescriptor,
    canonical_record_hash_members,
    descriptor_member,
)
from vellis.database import _SCHEMA, connect_database, require_supported_database
from vellis.definition_repository import definition_descriptors, load_definitions
from vellis.domain import (
    RevisionState,
    canonical_uuid,
    parse_timestamp,
)
from vellis.graph_repository import graph_descriptors, load_graph_objects
from vellis.state_repository import resolve_state
from vellis.state_validation_repository import first_state_finding


@dataclass(frozen=True, slots=True)
class AuditReport:
    findings: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.findings


class _FindingCategories(list[str]):
    """Retain each fixed audit category once while state-wide scans continue."""

    def append(self, finding: str) -> None:
        if finding not in self:
            super().append(finding)


def audit_database(path: Path, *, immutable: bool = False) -> AuditReport:
    connection = connect_database(path, read_only=True, immutable=immutable)
    try:
        return audit_connection(connection)
    finally:
        connection.close()


def audit_connection(connection: sqlite3.Connection) -> AuditReport:
    owns_snapshot = not connection.in_transaction
    if owns_snapshot:
        connection.execute("BEGIN")
    try:
        return _audit_snapshot(connection)
    finally:
        if owns_snapshot:
            connection.rollback()


def _expected_schema_objects() -> set[str]:
    """Object names the fresh schema creates, read from the schema itself.

    Deriving them keeps this from becoming a second inventory that drifts: a schema
    change updates the expectation in the same edit that makes it. Full-text virtual
    tables carry automatically created shadow objects, so those are derived from the
    virtual tables the schema declares rather than listed by name.
    """
    pattern = re.compile(
        r"CREATE\s+(?:UNIQUE\s+)?(?:VIRTUAL\s+)?(?:TABLE|INDEX|VIEW|TRIGGER)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    expected = set(pattern.findall(_SCHEMA))
    virtual = re.findall(
        r"CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        _SCHEMA,
        re.IGNORECASE,
    )
    for name in virtual:
        expected.update(f"{name}_{suffix}" for suffix in ("data", "idx", "docsize", "config"))
    return expected


def _check_schema_objects(connection: sqlite3.Connection, findings: list[str]) -> None:
    """A supported version does not prove the schema objects are the expected ones.

    Both directions matter. A missing object breaks a public operation; an unexpected
    one can change behavior the schema never selected, and backup publication trusts
    this verdict either way.
    """
    present = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    }
    expected = _expected_schema_objects()
    missing = sorted(expected - present)
    if missing:
        findings.append(f"database is missing required schema objects: {', '.join(missing)}")
    unexpected = sorted(present - expected)
    if unexpected:
        findings.append(f"database contains unexpected schema objects: {', '.join(unexpected)}")


def _audit_snapshot(connection: sqlite3.Connection) -> AuditReport:
    findings: list[str] = _FindingCategories()
    try:
        require_supported_database(connection)
        _check_schema_objects(connection, findings)
        _check_lineage_identity(connection, findings)
        _check_sqlite_integrity(connection, findings)
        _check_intervals(connection, findings)
        _check_child_boundaries(connection, findings)
        _check_reservations(connection, findings)
        _check_closed_storage_shapes(connection, findings)
        _check_version_metadata(connection, findings)
        _check_timestamp_representations(connection, findings)
        _check_revisions(connection, findings)
        check_observability(connection, findings)
        check_governance(connection, findings)
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, OverflowError) as error:
        findings.append(f"integrity inspection could not decode stored content: {error}")
    return AuditReport(tuple(sorted(findings)))


def _check_lineage_identity(connection: sqlite3.Connection, findings: list[str]) -> None:
    value = connection.execute(
        "SELECT lineage_uuid FROM metadata_setting WHERE singleton = 1"
    ).fetchone()[0]
    try:
        canonical = canonical_uuid(value)
    except ValueError:
        findings.append("database lineage is not a canonical hyphenated UUID")
        return
    if canonical != value:
        findings.append("database lineage is not a canonical hyphenated UUID")


def _check_version_metadata(connection: sqlite3.Connection, findings: list[str]) -> None:
    for relation in ("graph_object_version", "definition_version"):
        count = int(
            connection.execute(
                f"SELECT count(*) FROM {relation} "
                "WHERE last_changed_revision <> valid_from_revision"
            ).fetchone()[0]
        )
        if count:
            findings.append(f"{relation} contains {count} stale last-changed revisions")


def _check_closed_storage_shapes(connection: sqlite3.Connection, findings: list[str]) -> None:
    checks = (
        ("graph_object_version", _graph_version_shape),
        ("definition_version", _definition_version_shape),
        ("property_version", _property_version_shape),
        ("property_definition_version", _property_definition_shape),
        ("property_definition_allowed_value", _allowed_value_shape),
    )
    for relation, valid in checks:
        invalid = sum(not valid(row) for row in connection.execute(f"SELECT * FROM {relation}"))
        if invalid:
            findings.append(f"{relation} contains {invalid} rows with incompatible stored fields")


def _graph_version_shape(row: sqlite3.Row) -> bool:
    kind = row["kind"]
    populated = (
        row["display_name"] is not None,
        row["source_uuid"] is not None,
        row["target_uuid"] is not None,
    )
    return (kind, populated) in {
        ("anchor", (True, False, False)),
        ("associatedData", (False, False, False)),
        ("link", (False, True, True)),
    }


def _definition_version_shape(row: sqlite3.Row) -> bool:
    anchor_bounds = _bound_pair(row, "anchors_per_object", 1) and _bound_pair(
        row, "objects_per_anchor", 0
    )
    link_bounds = _bound_pair(row, "links_per_source", 0) and _bound_pair(
        row, "links_per_target", 0
    )
    no_anchor_bounds = _empty_bound_pair(row, "anchors_per_object") and _empty_bound_pair(
        row, "objects_per_anchor"
    )
    no_link_bounds = _empty_bound_pair(row, "links_per_source") and _empty_bound_pair(
        row, "links_per_target"
    )
    return (
        (row["kind"] == "anchor" and no_anchor_bounds and no_link_bounds)
        or (row["kind"] == "associatedData" and anchor_bounds and no_link_bounds)
        or (row["kind"] == "link" and no_anchor_bounds and link_bounds)
    )


def _bound_pair(row: sqlite3.Row, prefix: str, lower: int) -> bool:
    minimum = _stored_natural(row[f"{prefix}_minimum"])
    maximum_value = row[f"{prefix}_maximum"]
    maximum = None if maximum_value is None else _stored_natural(maximum_value)
    return (
        minimum is not None
        and minimum >= lower
        and (maximum_value is None or (maximum is not None and maximum >= minimum))
    )


def _empty_bound_pair(row: sqlite3.Row, prefix: str) -> bool:
    return row[f"{prefix}_minimum"] is None and row[f"{prefix}_maximum"] is None


def _property_version_shape(row: sqlite3.Row) -> bool:
    if row["is_null"] == 1:
        return _typed_columns_empty(row, "")
    return row["is_null"] == 0 and _typed_columns_match(row, "", str(row["value_kind"]))


def _property_definition_shape(row: sqlite3.Row) -> bool:
    minimum = _bound_columns_match(row, "minimum")
    maximum = _bound_columns_match(row, "maximum")
    lengths = _natural_range(row["minimum_length"], row["maximum_length"])
    return minimum and maximum and lengths


def _natural_range(minimum_value: object, maximum_value: object) -> bool:
    minimum = None if minimum_value is None else _stored_natural(minimum_value)
    maximum = None if maximum_value is None else _stored_natural(maximum_value)
    if minimum_value is not None and minimum is None:
        return False
    if maximum_value is not None and maximum is None:
        return False
    return minimum is None or maximum is None or maximum >= minimum


def _stored_natural(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    if value != "0" and (not value.isascii() or not value.isdigit() or value.startswith("0")):
        return None
    return int(value)


def _bound_columns_match(row: sqlite3.Row, prefix: str) -> bool:
    kind = row[f"{prefix}_kind"]
    if kind is None:
        return _typed_columns_empty(row, f"{prefix}_", include_boolean_text=False)
    return _typed_columns_match(row, f"{prefix}_", str(kind), include_boolean_text=False)


def _allowed_value_shape(row: sqlite3.Row) -> bool:
    return _typed_columns_match(row, "", str(row["value_kind"]))


def _typed_columns_match(
    row: sqlite3.Row, prefix: str, kind: str, *, include_boolean_text: bool = True
) -> bool:
    columns = _typed_column_names(prefix, include_boolean_text)
    expected = _expected_typed_columns(prefix, kind)
    return expected is not None and all(
        (row[column] is not None) == (column in expected) for column in columns
    )


def _typed_columns_empty(
    row: sqlite3.Row, prefix: str, *, include_boolean_text: bool = True
) -> bool:
    return all(row[column] is None for column in _typed_column_names(prefix, include_boolean_text))


def _typed_column_names(prefix: str, include_boolean_text: bool) -> tuple[str, ...]:
    scalar_names = ("boolean", "integer", "number", "text", "date")
    if not include_boolean_text:
        scalar_names = ("integer", "number", "date")
    return (
        *(f"{prefix}{name}_value" if prefix == "" else f"{prefix}{name}" for name in scalar_names),
        f"{prefix}timestamp_epoch_seconds",
        f"{prefix}timestamp_nanosecond",
        f"{prefix}timestamp_text",
    )


def _expected_typed_columns(prefix: str, kind: str) -> set[str] | None:
    if kind == "timestamp":
        return {
            f"{prefix}timestamp_epoch_seconds",
            f"{prefix}timestamp_nanosecond",
            f"{prefix}timestamp_text",
        }
    allowed = {"boolean", "integer", "number", "text", "date"}
    if prefix and kind not in {"integer", "number", "date"}:
        return None
    if kind not in allowed:
        return None
    suffix = f"{kind}_value" if prefix == "" else kind
    return {f"{prefix}{suffix}"}


def _check_sqlite_integrity(connection: sqlite3.Connection, findings: list[str]) -> None:
    integrity_ok = True
    for row in connection.execute("PRAGMA integrity_check"):
        integrity_ok = integrity_ok and str(row[0]) == "ok"
    if not integrity_ok:
        findings.append("SQLite integrity check reported corruption")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        findings.append("SQLite reports foreign-key violations")


def _check_intervals(connection: sqlite3.Connection, findings: list[str]) -> None:
    for relation, identity_columns in (
        ("graph_object_version", ("uuid",)),
        ("direct_association_version", ("object_uuid", "anchor_uuid")),
        ("property_version", ("object_uuid", "property_name")),
        ("definition_version", ("type_key",)),
        ("definition_permitted_type", ("type_key", "role", "permitted_type_key")),
        ("property_definition_version", ("type_key", "property_name")),
        (
            "property_definition_allowed_value",
            ("type_key", "property_name", "ordinal"),
        ),
    ):
        count = int(
            connection.execute(
                f"""
                SELECT count(*) FROM {relation}
                WHERE valid_to_revision IS NOT NULL
                  AND valid_to_revision <= valid_from_revision
                """
            ).fetchone()[0]
        )
        if count:
            findings.append(f"{relation} contains {count} invalid version intervals")
        overlaps = _overlapping_intervals(connection, relation, identity_columns)
        if overlaps:
            findings.append(f"{relation} contains {overlaps} overlapping version intervals")


def _overlapping_intervals(
    connection: sqlite3.Connection,
    relation: str,
    identity_columns: tuple[str, ...],
) -> int:
    identity = " AND ".join(f"earlier.{column} = later.{column}" for column in identity_columns)
    return int(
        connection.execute(
            f"""
            SELECT count(*) FROM {relation} AS earlier
            JOIN {relation} AS later
              ON {identity}
             AND earlier.valid_from_revision < later.valid_from_revision
             AND (earlier.valid_to_revision IS NULL
                  OR earlier.valid_to_revision > later.valid_from_revision)
            """
        ).fetchone()[0]
    )


def _check_child_boundaries(connection: sqlite3.Connection, findings: list[str]) -> None:
    checks = (
        ("direct_association_version", "object_uuid", "graph_object_version", "uuid"),
        ("property_version", "object_uuid", "graph_object_version", "uuid"),
        ("definition_permitted_type", "type_key", "definition_version", "type_key"),
        ("property_definition_version", "type_key", "definition_version", "type_key"),
    )
    for child, child_key, parent, parent_key in checks:
        invalid = _child_boundary_mismatches(connection, child, child_key, parent, parent_key)
        if invalid:
            findings.append(f"{child} contains {invalid} boundaries without a parent version")
    allowed_invalid = _allowed_value_boundary_mismatches(connection)
    if allowed_invalid:
        findings.append(
            "property_definition_allowed_value contains "
            f"{allowed_invalid} boundaries without a parent property version"
        )


def _child_boundary_mismatches(
    connection: sqlite3.Connection,
    child: str,
    child_key: str,
    parent: str,
    parent_key: str,
) -> int:
    return int(
        connection.execute(
            f"""
            SELECT count(*) FROM {child} AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM {parent} AS p
                WHERE p.{parent_key} = c.{child_key}
                  AND p.valid_from_revision = c.valid_from_revision
                  AND (p.valid_to_revision = c.valid_to_revision
                    OR (p.valid_to_revision IS NULL AND c.valid_to_revision IS NULL))
            )
            """
        ).fetchone()[0]
    )


def _allowed_value_boundary_mismatches(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            """
            SELECT count(*) FROM property_definition_allowed_value AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM property_definition_version AS p
                WHERE p.type_key = c.type_key AND p.property_name = c.property_name
                  AND p.valid_from_revision = c.valid_from_revision
                  AND (p.valid_to_revision = c.valid_to_revision
                    OR (p.valid_to_revision IS NULL AND c.valid_to_revision IS NULL))
            )
            """
        ).fetchone()[0]
    )


def _check_reservations(connection: sqlite3.Connection, findings: list[str]) -> None:
    graph_conflicts = int(
        connection.execute(
            """
            SELECT count(*)
            FROM graph_object_version AS v
            JOIN graph_object_identity AS i USING (uuid)
            WHERE v.kind <> i.kind
            """
        ).fetchone()[0]
    )
    type_conflicts = int(
        connection.execute(
            """
            SELECT count(*)
            FROM definition_version AS v
            JOIN type_key_identity AS i USING (type_key)
            WHERE v.kind <> i.kind
            """
        ).fetchone()[0]
    )
    graph_orphans = _reservation_mismatches(
        connection, "graph_object_identity", "graph_object_version", "uuid"
    )
    type_orphans = _reservation_mismatches(
        connection, "type_key_identity", "definition_version", "type_key"
    )
    if graph_conflicts:
        findings.append("graph object versions conflict with UUID kind reservations")
    if type_conflicts:
        findings.append("definition versions conflict with type-key kind reservations")
    if graph_orphans:
        findings.append("UUID reservations lack a matching earliest graph-object version")
    if type_orphans:
        findings.append("type-key reservations lack a matching earliest definition version")


def _reservation_mismatches(
    connection: sqlite3.Connection, identity: str, versions: str, key: str
) -> int:
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM {identity} AS i
            LEFT JOIN (
                SELECT {key}, min(valid_from_revision) AS first_revision
                FROM {versions}
                GROUP BY {key}
            ) AS v USING ({key})
            WHERE v.first_revision IS NULL OR i.created_revision <> v.first_revision
            """
        ).fetchone()[0]
    )


def _check_timestamp_representations(connection: sqlite3.Connection, findings: list[str]) -> None:
    checks = (
        (
            "property_version",
            "value_kind = 'timestamp'",
            "timestamp_text",
            "timestamp_epoch_seconds",
            "timestamp_nanosecond",
        ),
        (
            "property_definition_allowed_value",
            "value_kind = 'timestamp'",
            "timestamp_text",
            "timestamp_epoch_seconds",
            "timestamp_nanosecond",
        ),
        (
            "property_definition_version",
            "minimum_kind = 'timestamp'",
            "minimum_timestamp_text",
            "minimum_timestamp_epoch_seconds",
            "minimum_timestamp_nanosecond",
        ),
        (
            "property_definition_version",
            "maximum_kind = 'timestamp'",
            "maximum_timestamp_text",
            "maximum_timestamp_epoch_seconds",
            "maximum_timestamp_nanosecond",
        ),
    )
    for relation, where, text_column, seconds_column, nanos_column in checks:
        rows = connection.execute(
            f"SELECT {text_column}, {seconds_column}, {nanos_column} FROM {relation} WHERE {where}"
        )
        if any(not _timestamp_matches(*row) for row in rows):
            findings.append(f"{relation} contains inconsistent timestamp representations")


def _check_transition_placement(revision: int, transition: str, findings: list[str]) -> None:
    """The hash chain attests a label was not altered, not that it may appear here.

    Revision zero carries the one initialization record, and initialization never recurs.
    """
    if revision == 0 and transition != "initialization":
        findings.append("canonical revision zero is not an initialization record")
    if revision != 0 and transition == "initialization":
        findings.append("canonical initialization appears after revision zero")


def _check_revisions(connection: sqlite3.Connection, findings: list[str]) -> None:
    _prepare_audit_descriptors(connection, findings)
    previous_hash = bytes(32)
    previous_time: tuple[int, int] | None = None
    expected_revision = 0
    semantic_invalid = False
    lineage_uuid = str(
        connection.execute(
            "SELECT lineage_uuid FROM metadata_setting WHERE singleton = 1"
        ).fetchone()[0]
    )
    records = connection.execute("SELECT * FROM canonical_record ORDER BY revision")
    for row in records:
        revision = int(row["revision"])
        if revision != expected_revision:
            findings.append("canonical revisions are not contiguous from zero")
        expected_revision = revision + 1
        _check_transition_placement(revision, str(row["transition_kind"]), findings)
        timestamp = (int(row["recorded_epoch_seconds"]), int(row["recorded_nanosecond"]))
        if previous_time is not None and timestamp < previous_time:
            findings.append("canonical recorded times decrease")
        previous_time = timestamp
        if not _timestamp_matches(
            row["recorded_at"], row["recorded_epoch_seconds"], row["recorded_nanosecond"]
        ):
            findings.append("canonical recorded time fields differ")
        state = resolve_state(connection, RevisionState(revision))
        semantic_invalid = semantic_invalid or first_state_finding(connection, state) is not None
        _check_affected_keys(connection, row, revision, findings)
        header = _header_from_row(row, lineage_uuid)
        computed_hash = _audit_record_hash(connection, previous_hash, header, revision)
        if bytes(row["previous_hash"]) != previous_hash:
            findings.append("previous canonical hashes differ")
        if bytes(row["record_hash"]) != computed_hash:
            findings.append("canonical record hashes differ")
        previous_hash = bytes(row["record_hash"])
    if expected_revision == 0:
        findings.append("canonical history is empty")
    head = int(
        connection.execute(
            "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
        ).fetchone()[0]
    )
    if head != expected_revision - 1:
        findings.append("metadata head does not identify the greatest canonical revision")
    if semantic_invalid:
        findings.append("a canonical revision is not graph-conforming")


def _check_affected_keys(
    connection: sqlite3.Connection,
    record: sqlite3.Row,
    revision: int,
    findings: list[str],
) -> None:
    checks = (
        ("definition_version", "type_key", "affected_type_keys"),
        ("graph_object_version", "uuid", "affected_uuids"),
    )
    for relation, key, column in checks:
        if _affected_keys_differ(connection, relation, key, revision, record[column]):
            findings.append(f"canonical {column} differ from version changes")


def _affected_keys_differ(connection, relation, key, revision, stored):
    if not isinstance(stored, str):
        return True
    valid = connection.execute("SELECT json_valid(?)", (stored,)).fetchone()
    if not bool(valid[0]):
        return True
    row = connection.execute(
        f"""WITH expected(value) AS (
               SELECT DISTINCT {key} FROM {relation}
               WHERE valid_from_revision = ? OR valid_to_revision = ?),
             supplied(value) AS (SELECT value FROM json_each(?))
             SELECT EXISTS(SELECT value FROM expected EXCEPT SELECT value FROM supplied)
                 OR EXISTS(SELECT value FROM supplied EXCEPT SELECT value FROM expected)
                 OR (SELECT count(*) FROM supplied) <> (SELECT count(*) FROM expected)
                 OR ? <> (SELECT json_group_array(value)
                           FROM (SELECT value FROM expected ORDER BY value))""",
        (revision, revision, stored, stored),
    ).fetchone()
    return bool(row[0])


def _prepare_audit_descriptors(connection, findings):
    connection.execute("DROP TABLE IF EXISTS temp.audit_descriptor")
    connection.execute(
        """CREATE TEMP TABLE audit_descriptor(
           relation_name TEXT NOT NULL, identity BLOB NOT NULL,
           valid_from_revision INTEGER NOT NULL, valid_to_revision INTEGER,
           expected_digest BLOB, expected_member BLOB,
           actual_digest BLOB, actual_member BLOB,
           PRIMARY KEY(relation_name, identity)) WITHOUT ROWID"""
    )
    _store_expected_descriptors(connection)
    _store_actual_descriptors(connection)
    missing = connection.execute(
        """SELECT 1 FROM audit_descriptor
           WHERE expected_digest IS NULL OR actual_digest IS NULL LIMIT 1"""
    ).fetchone()
    mismatch = connection.execute(
        """SELECT 1 FROM audit_descriptor
           WHERE expected_digest <> actual_digest LIMIT 1"""
    ).fetchone()
    if missing is not None:
        findings.append("introduced version identities differ from decoded state")
    if mismatch is not None:
        findings.append("introduced version row digests differ from decoded state")


def _store_expected_descriptors(connection):
    definition_rows = connection.execute(
        """SELECT type_key, valid_from_revision FROM definition_version
           ORDER BY type_key, valid_from_revision"""
    )
    for row in definition_rows:
        revision = int(row["valid_from_revision"])
        state = resolve_state(connection, RevisionState(revision))
        values = load_definitions(connection, state, (str(row["type_key"]),))
        for descriptor in definition_descriptors(values, revision):
            _put_expected_descriptor(connection, descriptor, revision)
    graph_rows = connection.execute(
        """SELECT uuid, valid_from_revision FROM graph_object_version
           ORDER BY uuid, valid_from_revision"""
    )
    for row in graph_rows:
        revision = int(row["valid_from_revision"])
        state = resolve_state(connection, RevisionState(revision))
        values = load_graph_objects(connection, state, (str(row["uuid"]),))
        definitions = (
            () if not values else load_definitions(connection, state, (values[0].type_key,))
        )
        for descriptor in graph_descriptors(values, definitions, revision):
            _put_expected_descriptor(connection, descriptor, revision)


def _put_expected_descriptor(connection, descriptor, revision):
    identity, member = descriptor_member(descriptor)
    connection.execute(
        """INSERT INTO audit_descriptor(
             relation_name, identity, valid_from_revision, expected_digest, expected_member)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(relation_name, identity) DO UPDATE SET
             expected_digest = excluded.expected_digest,
             expected_member = excluded.expected_member""",
        (descriptor.relation_name, identity, revision, descriptor.row_digest, member),
    )


def _store_actual_descriptors(connection):
    specs = (
        ("definition_version", ("type_key",)),
        ("definition_permitted_type", ("type_key", "role", "permitted_type_key")),
        ("property_definition_version", ("type_key", "property_name")),
        (
            "property_definition_allowed_value",
            ("type_key", "property_name", "ordinal"),
        ),
        ("graph_object_version", ("uuid",)),
        ("direct_association_version", ("object_uuid", "anchor_uuid")),
        ("property_version", ("object_uuid", "property_name")),
    )
    for relation, keys in specs:
        for row in connection.execute(f"SELECT * FROM {relation}"):
            fields = tuple((_camel(key), row[key]) for key in keys)
            identity = Record((*fields, ("validFromRevision", int(row["valid_from_revision"]))))
            descriptor = RowDescriptor(relation, identity, bytes(row["row_digest"]))
            encoded_identity, member = descriptor_member(descriptor)
            connection.execute(
                """INSERT INTO audit_descriptor(
                     relation_name, identity, valid_from_revision, valid_to_revision,
                     actual_digest, actual_member)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(relation_name, identity) DO UPDATE SET
                     valid_to_revision = excluded.valid_to_revision,
                     actual_digest = excluded.actual_digest,
                     actual_member = excluded.actual_member""",
                (
                    relation,
                    encoded_identity,
                    int(row["valid_from_revision"]),
                    None if row["valid_to_revision"] is None else int(row["valid_to_revision"]),
                    descriptor.row_digest,
                    member,
                ),
            )


def _audit_record_hash(connection, previous_hash, header, revision):
    def members(column, boundary):
        return (
            bytes(row[0])
            for row in connection.execute(
                f"""SELECT {column} FROM audit_descriptor WHERE {boundary} = ?
                    ORDER BY relation_name, identity""",
                (revision,),
            )
        )

    def length(column, boundary):
        return int(
            connection.execute(
                f"""SELECT coalesce(sum(8 + length({column})), 0)
                FROM audit_descriptor WHERE {boundary} = ?""",
                (revision,),
            ).fetchone()[0]
        )

    return canonical_record_hash_members(
        previous_hash,
        header,
        length("expected_member", "valid_from_revision"),
        members("expected_member", "valid_from_revision"),
        length("actual_member", "valid_to_revision"),
        members("actual_member", "valid_to_revision"),
    )


def _header_from_row(row: sqlite3.Row, lineage_uuid: str) -> CanonicalHeader:
    digest = row["v1_report_digest"]
    return CanonicalHeader(
        lineage_uuid=lineage_uuid,
        revision=int(row["revision"]),
        recorded_at=parse_timestamp(str(row["recorded_at"])),
        initiator=str(row["initiator"]),
        source=None if row["source"] is None else str(row["source"]),
        transition_kind=str(row["transition_kind"]),
        summary=str(row["summary"]),
        v1_report_digest=None if digest is None else bytes(digest),
    )


def _camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


def _timestamp_matches(text: object, seconds: object, nanosecond: object) -> bool:
    if not isinstance(text, str) or not isinstance(seconds, int) or not isinstance(nanosecond, int):
        return False
    try:
        parsed = parse_timestamp(text)
    except ValueError:
        return False
    return (parsed.canonical, parsed.epoch_seconds, parsed.nanosecond) == (
        text,
        seconds,
        nanosecond,
    )
