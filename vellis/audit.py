"""Read-only integrity checks for fresh VEL2 databases."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from vellis.canonical_encoding import (
    CanonicalHeader,
    Record,
    RowDescriptor,
    canonical_record_hash,
    encode,
)
from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import definition_descriptors, load_definitions
from vellis.domain import (
    GraphObject,
    RevisionState,
    TypeDefinition,
    canonical_uuid,
    parse_timestamp,
)
from vellis.domain_validation import definition_set_findings, graph_findings
from vellis.graph_repository import graph_descriptors, load_graph
from vellis.state_repository import resolve_state


@dataclass(frozen=True, slots=True)
class AuditReport:
    findings: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.findings


def audit_database(path: Path) -> AuditReport:
    connection = connect_database(path, read_only=True)
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


def _audit_snapshot(connection: sqlite3.Connection) -> AuditReport:
    findings: list[str] = []
    try:
        require_supported_database(connection)
        _check_lineage_identity(connection, findings)
        _check_sqlite_integrity(connection, findings)
        records = connection.execute("SELECT * FROM canonical_record ORDER BY revision").fetchall()
        _check_record_sequence(records, findings)
        _check_head(connection, records, findings)
        _check_intervals(connection, findings)
        _check_child_boundaries(connection, findings)
        _check_reservations(connection, findings)
        _check_closed_storage_shapes(connection, findings)
        _check_version_metadata(connection, findings)
        _check_timestamp_representations(connection, findings)
        _check_revisions(connection, records, findings)
        _check_search_projection(connection, findings)
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, OverflowError) as error:
        findings.append(f"integrity inspection could not decode stored content: {error}")
    return AuditReport(tuple(sorted(set(findings))))


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
        rows = connection.execute(f"SELECT * FROM {relation}").fetchall()
        invalid = sum(not valid(row) for row in rows)
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
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    messages = [str(row[0]) for row in rows]
    if messages != ["ok"]:
        findings.extend(f"SQLite integrity: {message}" for message in messages)
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        findings.append(f"SQLite reports {len(foreign_key_rows)} foreign-key violations")


def _check_record_sequence(records: list[sqlite3.Row], findings: list[str]) -> None:
    if not records:
        findings.append("canonical history is empty")
        return
    expected = list(range(len(records)))
    actual = [int(row["revision"]) for row in records]
    if actual != expected:
        findings.append("canonical revisions are not contiguous from zero")
    times = [
        (int(row["recorded_epoch_seconds"]), int(row["recorded_nanosecond"])) for row in records
    ]
    if times != sorted(times):
        findings.append("canonical recorded times decrease")
    for row in records:
        if not _timestamp_matches(
            row["recorded_at"], row["recorded_epoch_seconds"], row["recorded_nanosecond"]
        ):
            findings.append(f"revision {int(row['revision'])}: recorded time fields differ")


def _check_head(
    connection: sqlite3.Connection, records: list[sqlite3.Row], findings: list[str]
) -> None:
    if not records:
        return
    head = int(
        connection.execute(
            "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
        ).fetchone()[0]
    )
    if head != int(records[-1]["revision"]):
        findings.append("metadata head does not identify the greatest canonical revision")


def _check_intervals(connection: sqlite3.Connection, findings: list[str]) -> None:
    for relation in (
        "graph_object_version",
        "direct_association_version",
        "property_version",
        "definition_version",
        "definition_permitted_type",
        "property_definition_version",
        "property_definition_allowed_value",
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
        ).fetchall()
        if any(not _timestamp_matches(*row) for row in rows):
            findings.append(f"{relation} contains inconsistent timestamp representations")


def _check_revisions(
    connection: sqlite3.Connection,
    records: list[sqlite3.Row],
    findings: list[str],
) -> None:
    previous_hash = bytes(32)
    lineage_uuid = str(
        connection.execute(
            "SELECT lineage_uuid FROM metadata_setting WHERE singleton = 1"
        ).fetchone()[0]
    )
    for row in records:
        revision = int(row["revision"])
        state = resolve_state(connection, RevisionState(revision))
        definitions = load_definitions(connection, state)
        graph = load_graph(connection, state)
        findings.extend(
            f"revision {revision}: {finding.summary}"
            for finding in definition_set_findings(definitions, require_system=True)
        )
        findings.extend(
            f"revision {revision}: {finding.summary}"
            for finding in graph_findings(graph, definitions, require_system=True)
        )
        expected = _expected_introduced(connection, definitions, graph, revision)
        _check_affected_keys(connection, row, revision, findings)
        actual = _stored_descriptors(connection, revision, introduced=True)
        _compare_descriptors(expected, actual, revision, findings)
        retired = _stored_descriptors(connection, revision, introduced=False)
        header = _header_from_row(row, lineage_uuid)
        computed_hash = canonical_record_hash(previous_hash, header, expected, retired)
        if bytes(row["previous_hash"]) != previous_hash:
            findings.append(f"revision {revision}: previous canonical hash differs")
        if bytes(row["record_hash"]) != computed_hash:
            findings.append(f"revision {revision}: canonical record hash differs")
        previous_hash = bytes(row["record_hash"])


def _check_affected_keys(
    connection: sqlite3.Connection,
    record: sqlite3.Row,
    revision: int,
    findings: list[str],
) -> None:
    expected_types = _changed_keys(connection, "definition_version", "type_key", revision)
    expected_uuids = _changed_keys(connection, "graph_object_version", "uuid", revision)
    expected_type_text = json.dumps(expected_types, separators=(",", ":"))
    expected_uuid_text = json.dumps(expected_uuids, separators=(",", ":"))
    if record["affected_type_keys"] != expected_type_text:
        findings.append(f"revision {revision}: affected type keys differ from version changes")
    if record["affected_uuids"] != expected_uuid_text:
        findings.append(f"revision {revision}: affected UUIDs differ from version changes")


def _changed_keys(
    connection: sqlite3.Connection, relation: str, key: str, revision: int
) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            f"""
            SELECT DISTINCT {key}
            FROM {relation}
            WHERE valid_from_revision = ? OR valid_to_revision = ?
            ORDER BY {key}
            """,
            (revision, revision),
        )
    ]


def _expected_introduced(
    connection: sqlite3.Connection,
    definitions: tuple[TypeDefinition, ...],
    graph: tuple[GraphObject, ...],
    revision: int,
) -> tuple[RowDescriptor, ...]:
    type_keys = {
        str(row[0])
        for row in connection.execute(
            "SELECT type_key FROM definition_version WHERE valid_from_revision = ?", (revision,)
        )
    }
    uuids = {
        str(row[0])
        for row in connection.execute(
            "SELECT uuid FROM graph_object_version WHERE valid_from_revision = ?", (revision,)
        )
    }
    changed_definitions = tuple(value for value in definitions if value.type_key in type_keys)
    changed_graph = tuple(value for value in graph if value.uuid in uuids)
    return (
        *definition_descriptors(changed_definitions, revision),
        *graph_descriptors(changed_graph, definitions, revision),
    )


def _stored_descriptors(
    connection: sqlite3.Connection, revision: int, *, introduced: bool
) -> tuple[RowDescriptor, ...]:
    column = "valid_from_revision" if introduced else "valid_to_revision"
    descriptors: list[RowDescriptor] = []
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
        rows = connection.execute(
            f"SELECT * FROM {relation} WHERE {column} = ?", (revision,)
        ).fetchall()
        for row in rows:
            fields = tuple((_camel(key), row[key]) for key in keys)
            identity = Record((*fields, ("validFromRevision", int(row["valid_from_revision"]))))
            descriptors.append(RowDescriptor(relation, identity, bytes(row["row_digest"])))
    return tuple(descriptors)


def _compare_descriptors(
    expected: tuple[RowDescriptor, ...],
    actual: tuple[RowDescriptor, ...],
    revision: int,
    findings: list[str],
) -> None:
    expected_map = {_descriptor_key(value): value.row_digest for value in expected}
    actual_map = {_descriptor_key(value): value.row_digest for value in actual}
    if expected_map.keys() != actual_map.keys():
        findings.append(f"revision {revision}: introduced version identities differ")
        return
    if expected_map != actual_map:
        findings.append(f"revision {revision}: introduced version row digest differs")


def _descriptor_key(value: RowDescriptor) -> tuple[str, bytes]:
    return value.relation_name, encode(value.identity)


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


def _check_search_projection(connection: sqlite3.Connection, findings: list[str]) -> None:
    documents = int(connection.execute("SELECT count(*) FROM search_document").fetchone()[0])
    indexed = int(connection.execute("SELECT count(*) FROM search_fts").fetchone()[0])
    if documents != indexed:
        findings.append("search document and FTS row counts differ")


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
