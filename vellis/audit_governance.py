"""Bounded integrity checks for draft, validation, and activity storage."""

from __future__ import annotations

import json
import math
import sqlite3

from vellis.change_domain import DraftCategory, DraftOperation
from vellis.domain import (
    PUBLIC_ITEM_LIMIT,
    AnchorUpsert,
    AssociatedDataUpsert,
    Finding,
    FindingCode,
    LinkUpsert,
    ObjectKind,
    canonical_uuid,
    parse_timestamp,
)
from vellis.draft_analysis import draft_counts
from vellis.draft_repository import (
    computed_draft_fingerprint,
    load_draft_definitions,
    raw_entry_count,
)
from vellis.history_domain import ActivityHistoryEntry, ActivityOutcome
from vellis.sqlite_values import property_from_row

DRAFT_RELATIONS = (
    "draft_definition_entry",
    "draft_definition_permitted_type",
    "draft_property_definition_entry",
    "draft_property_definition_allowed_value",
    "draft_graph_object_patch",
    "draft_association_operation",
    "draft_property_operation",
)


def check_governance(connection: sqlite3.Connection, findings: list[str]) -> None:
    _check_settings(connection, findings)
    _check_draft(connection, findings)
    _check_activity(connection, findings)
    _check_validation(connection, findings)


def _check_draft(connection, findings):
    metadata = connection.execute("SELECT * FROM draft_metadata WHERE singleton = 1").fetchone()
    child_count = sum(_count(connection, relation) for relation in DRAFT_RELATIONS)
    if metadata is None:
        if child_count:
            _add(findings, "draft rows exist without draft metadata")
        if _count_where(connection, "validation_run", "scope = 'draft'"):
            _add(findings, "draft validation exists without a draft")
        return
    if raw_entry_count(connection) == 0:
        _add(findings, "draft metadata exists without a raw draft entry")
    fingerprint = metadata["fingerprint"]
    if not isinstance(fingerprint, bytes) or len(fingerprint) != 32:
        _add(findings, "draft fingerprint is absent or malformed")
    elif fingerprint != computed_draft_fingerprint(connection):
        _add(findings, "draft fingerprint differs from normalized draft content")
    _check_inspect_cursor(connection, metadata, findings)
    _check_draft_parents(connection, findings)
    _check_definition_entries(connection, findings)
    _check_graph_patches(connection, findings)


def _check_inspect_cursor(connection, metadata, findings):
    digest = metadata["inspect_cursor_hash"]
    state_text = metadata["inspect_cursor_state"]
    if (digest is None) != (state_text is None):
        _add(findings, "draft inspection cursor fields are inconsistent")
        return
    if digest is None:
        return
    if not isinstance(digest, bytes) or len(digest) != 32:
        _add(findings, "draft inspection cursor hash is malformed")
    try:
        state = _safe_json(state_text)
        _validate_inspect_state(connection, state, bytes(metadata["fingerprint"]))
    except TypeError, ValueError, KeyError, json.JSONDecodeError:
        _add(findings, "draft inspection cursor state is malformed")


def _validate_inspect_state(connection, state, fingerprint):
    if not isinstance(state, dict) or set(state) != {
        "categories",
        "operations",
        "typeKeys",
        "uuids",
        "limit",
        "offset",
        "evaluatedRevision",
        "fingerprint",
    }:
        raise ValueError("inspect state shape")
    categories = state["categories"]
    operations = state["operations"]
    type_keys = state["typeKeys"]
    uuids = state["uuids"]
    if not isinstance(categories, list) or any(
        DraftCategory(value).value != value for value in categories
    ):
        raise ValueError("inspect categories")
    if not isinstance(operations, list) or any(
        DraftOperation(value).value != value for value in operations
    ):
        raise ValueError("inspect operations")
    if not isinstance(type_keys, list) or any(not isinstance(value, str) for value in type_keys):
        raise ValueError("inspect type keys")
    if not isinstance(uuids, list) or any(canonical_uuid(value) != value for value in uuids):
        raise ValueError("inspect UUIDs")
    limit, offset, revision = state["limit"], state["offset"], state["evaluatedRevision"]
    if type(limit) is not int or not 1 <= limit <= PUBLIC_ITEM_LIMIT:
        raise ValueError("inspect limit")
    if type(offset) is not int or offset < limit:
        raise ValueError("inspect offset")
    if type(revision) is not int or not _known_revision(connection, revision):
        raise ValueError("inspect revision")
    if state["fingerprint"] != fingerprint.hex():
        raise ValueError("inspect fingerprint")


def _check_draft_parents(connection, findings):
    checks = (
        ("draft_definition_permitted_type", "type_key", "draft_definition_entry", "type_key"),
        ("draft_property_definition_entry", "type_key", "draft_definition_entry", "type_key"),
        (
            "draft_property_definition_allowed_value",
            "type_key || char(0) || property_name",
            "draft_property_definition_entry",
            "type_key || char(0) || property_name",
        ),
        ("draft_association_operation", "object_uuid", "draft_graph_object_patch", "uuid"),
        ("draft_property_operation", "object_uuid", "draft_graph_object_patch", "uuid"),
    )
    for child, child_key, parent, parent_key in checks:
        missing = connection.execute(
            f"""SELECT 1 FROM {child} c WHERE NOT EXISTS (
                SELECT 1 FROM {parent} p WHERE p.{parent_key} = c.{child_key}) LIMIT 1"""
        ).fetchone()
        if missing is not None:
            _add(findings, f"{child} contains rows without its draft parent")


def _check_definition_entries(connection, findings):
    cursor = connection.execute("SELECT * FROM draft_definition_entry ORDER BY type_key")
    for row in cursor:
        key = row["type_key"]
        try:
            if not isinstance(key, str) or key == "":
                raise ValueError("type key")
            operation = str(row["operation"])
            if operation == "remove":
                if _definition_child_count(connection, key):
                    raise ValueError("removal children")
                continue
            if operation != "replace":
                raise ValueError("definition operation")
            _require_reserved_kind(
                connection, "type_key_identity", "type_key", key, str(row["kind"])
            )
            values = load_draft_definitions(connection, (), (key,))
            if len(values) != 1 or values[0].system is not None:
                raise ValueError("replacement decode")
            if _definition_roles_invalid(connection, key, str(row["kind"])):
                raise ValueError("definition roles")
            if _allowed_value_rows_invalid(connection, key):
                raise ValueError("allowed values")
        except TypeError, ValueError, KeyError, OverflowError:
            _add(findings, "draft definition entry is not normalized domain content")


def _definition_child_count(connection, key):
    return sum(
        int(
            connection.execute(
                f"SELECT count(*) FROM {relation} WHERE type_key = ?", (key,)
            ).fetchone()[0]
        )
        for relation in (
            "draft_definition_permitted_type",
            "draft_property_definition_entry",
            "draft_property_definition_allowed_value",
        )
    )


def _definition_roles_invalid(connection, key, kind):
    roles = tuple(
        str(row[0])
        for row in connection.execute(
            """SELECT DISTINCT role FROM draft_definition_permitted_type
               WHERE type_key = ? ORDER BY role""",
            (key,),
        )
    )
    permitted = {"anchor": set(), "associatedData": {"anchor"}, "link": {"source", "target"}}
    property_count = _count_where(
        connection, "draft_property_definition_entry", "type_key = ?", (key,)
    )
    return (
        kind not in permitted
        or not set(roles) <= permitted[kind]
        or (kind != "associatedData" and property_count != 0)
    )


def _allowed_value_rows_invalid(connection, key):
    properties = connection.execute(
        """SELECT property_name, value_kind, required, nullable, allowed_values_present
           FROM draft_property_definition_entry
           WHERE type_key = ? ORDER BY property_name""",
        (key,),
    )
    for prop in properties:
        if prop["required"] not in (0, 1) or prop["nullable"] not in (0, 1):
            return True
        if prop["allowed_values_present"] not in (0, 1):
            return True
        ordinal = 0
        rows = connection.execute(
            """SELECT * FROM draft_property_definition_allowed_value
               WHERE type_key = ? AND property_name = ? ORDER BY ordinal""",
            (key, prop["property_name"]),
        ).fetchall()
        if not bool(prop["allowed_values_present"]) and rows:
            return True
        for row in rows:
            if int(row["ordinal"]) != ordinal:
                return True
            ordinal += 1
            if property_from_row({**dict(row), "is_null": 0}) is None:
                return True
    return False


def _check_graph_patches(connection, findings):
    for row in connection.execute("SELECT * FROM draft_graph_object_patch ORDER BY uuid"):
        try:
            _decode_patch(connection, row)
        except TypeError, ValueError, KeyError, OverflowError:
            _add(findings, "draft graph patch is not normalized domain content")


def _decode_patch(connection, row):
    uuid = canonical_uuid(str(row["uuid"]))
    kind = ObjectKind(str(row["kind"]))
    _require_reserved_kind(connection, "graph_object_identity", "uuid", uuid, kind.value)
    if bool(row["tombstone"]):
        _check_tombstone(connection, row, uuid)
        return
    structural = _patch_structural_values(row)
    if kind is ObjectKind.ANCHOR:
        if structural["source_uuid"] or structural["target_uuid"] or row["has_complete_anchor_set"]:
            raise ValueError("anchor fields")
        AnchorUpsert(uuid, structural["type_key"], structural["display_name"])
        if _object_child_count(connection, uuid):
            raise ValueError("anchor children")
    elif kind is ObjectKind.LINK:
        if structural["display_name"] or row["has_complete_anchor_set"]:
            raise ValueError("link fields")
        LinkUpsert(
            uuid, structural["type_key"], structural["source_uuid"], structural["target_uuid"]
        )
        if _object_child_count(connection, uuid):
            raise ValueError("link children")
    else:
        if structural["display_name"] or structural["source_uuid"] or structural["target_uuid"]:
            raise ValueError("data fields")
        _decode_data_patch(
            connection, uuid, structural["type_key"], bool(row["has_complete_anchor_set"])
        )


def _check_tombstone(connection, row, uuid):
    flags = (
        row["has_type_key"],
        row["has_display_name"],
        row["has_source_uuid"],
        row["has_target_uuid"],
        row["has_complete_anchor_set"],
    )
    if any(value != 0 for value in flags):
        raise ValueError("tombstone fields")
    if _object_child_count(connection, uuid):
        raise ValueError("tombstone children")


def _patch_structural_values(row):
    result = {}
    for name in ("type_key", "display_name", "source_uuid", "target_uuid"):
        present = row[f"has_{name}"]
        value = row[name]
        if present not in (0, 1) or bool(present) != (value is not None):
            raise ValueError("patch presence flag")
        result[name] = None if value is None else str(value)
    return result


def _decode_data_patch(connection, uuid, type_key, complete):
    base, additions, removals = [], [], []
    for row in connection.execute(
        "SELECT anchor_uuid, operation FROM draft_association_operation WHERE object_uuid = ?",
        (uuid,),
    ):
        anchor = canonical_uuid(str(row["anchor_uuid"]))
        operation = str(row["operation"])
        if operation == "base":
            base.append(anchor)
        elif operation == "add":
            additions.append(anchor)
        elif operation == "remove":
            removals.append(anchor)
        else:
            raise ValueError("association operation")
    if bool(base) and not complete:
        raise ValueError("base without complete set")
    sets, removes = _decode_property_operations(connection, uuid)
    AssociatedDataUpsert(
        uuid,
        type_key,
        tuple(base) if complete else None,
        tuple(additions),
        tuple(removals),
        sets,
        removes,
    )


def _decode_property_operations(connection, uuid):
    sets, removes = [], []
    for row in connection.execute(
        "SELECT * FROM draft_property_operation WHERE object_uuid = ? ORDER BY property_name",
        (uuid,),
    ):
        name = str(row["property_name"])
        if not name:
            raise ValueError("property name")
        operation = str(row["operation"])
        if operation == "remove":
            if any(row[name] is not None for name in _PROPERTY_VALUE_COLUMNS):
                raise ValueError("remove payload")
            removes.append(name)
        elif operation == "set":
            sets.append((name, property_from_row(row)))
        else:
            raise ValueError("property operation")
    return tuple(sets), tuple(removes)


_PROPERTY_VALUE_COLUMNS = (
    "value_kind",
    "is_null",
    "boolean_value",
    "integer_value",
    "number_value",
    "text_value",
    "date_value",
    "timestamp_epoch_seconds",
    "timestamp_nanosecond",
    "timestamp_text",
)


def _object_child_count(connection, uuid):
    return sum(
        int(
            connection.execute(
                f"SELECT count(*) FROM {relation} WHERE object_uuid = ?", (uuid,)
            ).fetchone()[0]
        )
        for relation in ("draft_association_operation", "draft_property_operation")
    )


def _check_activity(connection, findings):
    metadata = connection.execute(
        """SELECT last_activity_sequence, last_activity_time
           FROM metadata_setting WHERE singleton = 1"""
    ).fetchone()
    expected_sequence = 1
    previous_time = None
    last_time = None
    for row in connection.execute(
        """SELECT h.*, p.semantic_payload, p.verbose_payload
           FROM activity_header h LEFT JOIN activity_payload p USING(sequence)
           ORDER BY h.sequence"""
    ):
        try:
            entry, recorded = _decode_activity_row(connection, row)
            if entry.sequence != expected_sequence:
                raise ValueError("activity sequence")
            if previous_time is not None and recorded < previous_time:
                raise ValueError("activity time order")
            expected_sequence += 1
            previous_time = recorded
            last_time = entry.recorded_at.canonical
        except TypeError, ValueError, KeyError, json.JSONDecodeError:
            _add(findings, "activity record is not normalized domain content")
    if metadata is None or (
        int(metadata["last_activity_sequence"]),
        metadata["last_activity_time"],
    ) != (expected_sequence - 1, last_time):
        _add(findings, "activity metadata differs from the activity ledger")
    missing = connection.execute(
        """SELECT 1 FROM activity_header h LEFT JOIN activity_payload p USING(sequence)
           WHERE p.sequence IS NULL LIMIT 1"""
    ).fetchone()
    orphan = connection.execute(
        """SELECT 1 FROM activity_payload p LEFT JOIN activity_header h USING(sequence)
           WHERE h.sequence IS NULL LIMIT 1"""
    ).fetchone()
    if missing is not None or orphan is not None:
        _add(findings, "activity header and payload correspondence differs")


def _decode_activity_row(connection, row):
    semantic = _safe_json(row["semantic_payload"])
    if not isinstance(semantic, dict):
        raise ValueError("semantic payload must be an object")
    verbose = None if row["verbose_payload"] is None else _safe_json(row["verbose_payload"])
    timestamp = parse_timestamp(str(row["recorded_at"]))
    recorded = (int(row["recorded_epoch_seconds"]), int(row["recorded_nanosecond"]))
    if recorded != (timestamp.epoch_seconds, timestamp.nanosecond):
        raise ValueError("activity time columns")
    evaluated = None if row["evaluated_revision"] is None else int(row["evaluated_revision"])
    resulting = None if row["resulting_revision"] is None else int(row["resulting_revision"])
    if any(
        value is not None and not _known_revision(connection, value)
        for value in (evaluated, resulting)
    ):
        raise ValueError("activity revision")
    return (
        ActivityHistoryEntry(
            int(row["sequence"]),
            timestamp,
            str(row["capability"]),
            ActivityOutcome(str(row["outcome"])),
            str(row["initiator"]),
            None if row["source"] is None else str(row["source"]),
            evaluated,
            resulting,
            str(row["summary"]),
            semantic,
            verbose,
        ),
        recorded,
    )


def _check_validation(connection, findings):
    for run in connection.execute("SELECT * FROM validation_run ORDER BY scope"):
        _check_validation_run(connection, run, findings)
    previous_scope = None
    expected_ordinal = 0
    for row in connection.execute(
        "SELECT scope, ordinal, finding FROM validation_finding ORDER BY scope, ordinal"
    ):
        scope = str(row["scope"])
        if scope != previous_scope:
            previous_scope, expected_ordinal = scope, 0
        if int(row["ordinal"]) != expected_ordinal:
            _add(findings, "validation finding ordinals are not contiguous from zero")
        expected_ordinal = int(row["ordinal"]) + 1
        try:
            _decode_finding(str(row["finding"]))
        except TypeError, ValueError, KeyError, json.JSONDecodeError:
            _add(findings, "validation finding is not normalized domain content")


def _check_validation_run(connection, run, findings):
    try:
        scope = str(run["scope"])
        if scope not in {"current", "draft"}:
            raise ValueError("scope")
        revision = int(run["evaluated_revision"])
        if not _known_revision(connection, revision):
            raise ValueError("revision")
        total = int(run["total_findings"])
        if total < 0 or total != _count_where(
            connection, "validation_finding", "scope = ?", (scope,)
        ):
            raise ValueError("count")
        _validate_validation_cursor(run, total)
        _validate_validation_scope(connection, run, scope)
    except TypeError, ValueError, KeyError, OverflowError:
        _add(findings, "validation run is not normalized domain content")


def _validate_validation_cursor(run, total):
    digest, offset, limit = run["cursor_hash"], run["next_offset"], run["page_limit"]
    if digest is None or offset is None or limit is None:
        if not (digest is None and offset is None and limit is None):
            raise ValueError("cursor fields")
        return
    if not isinstance(digest, bytes) or len(digest) != 32:
        raise ValueError("cursor digest")
    if type(offset) is not int or type(limit) is not int:
        raise ValueError("cursor numbers")
    if not 1 <= limit <= PUBLIC_ITEM_LIMIT or not limit <= offset < total:
        raise ValueError("cursor bounds")


def _validate_validation_scope(connection, run, scope):
    draft_fields = (
        run["draft_fingerprint"],
        run["raw_draft_entry_count"],
        run["effective_draft_change_count"],
    )
    if scope == "current":
        if any(value is not None for value in draft_fields):
            raise ValueError("current draft fields")
        return
    metadata = connection.execute(
        "SELECT fingerprint FROM draft_metadata WHERE singleton = 1"
    ).fetchone()
    if metadata is None or not isinstance(run["draft_fingerprint"], bytes):
        raise ValueError("draft backing")
    if len(run["draft_fingerprint"]) != 32:
        raise ValueError("draft validation fingerprint")
    if run["draft_fingerprint"] == metadata["fingerprint"]:
        counts = draft_counts(connection)
        if (run["raw_draft_entry_count"], run["effective_draft_change_count"]) != (
            counts.raw_entry_count,
            counts.effective_change_count,
        ):
            raise ValueError("draft validation counts")


def _decode_finding(encoded):
    item = _safe_json(encoded)
    if not isinstance(item, dict) or set(item) != {
        "code",
        "summary",
        "path",
        "type_keys",
        "uuids",
    }:
        raise ValueError("finding shape")
    finding = Finding(
        FindingCode(item["code"]),
        item["summary"],
        item["path"],
        tuple(item["type_keys"]),
        tuple(item["uuids"]),
    )
    normalized = json.dumps(_finding_wire(finding), sort_keys=True, separators=(",", ":"))
    if normalized != encoded:
        raise ValueError("finding normalization")
    return finding


def _finding_wire(finding):
    return {
        "code": finding.code.value,
        "path": finding.path,
        "summary": finding.summary,
        "type_keys": list(finding.type_keys),
        "uuids": list(finding.uuids),
    }


def _safe_json(value):
    if not isinstance(value, str):
        raise TypeError("JSON payload must be text")
    return json.loads(
        value,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        parse_float=_finite_float,
    )


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number is not finite binary64")
    return parsed


def _known_revision(connection, revision):
    return (
        type(revision) is int
        and revision >= 0
        and connection.execute(
            "SELECT 1 FROM canonical_record WHERE revision = ?", (revision,)
        ).fetchone()
        is not None
    )


def _require_reserved_kind(connection, relation, key_column, key, kind):
    row = connection.execute(
        f"SELECT kind FROM {relation} WHERE {key_column} = ?", (key,)
    ).fetchone()
    if row is not None and row["kind"] != kind:
        raise ValueError("draft kind conflicts with its identity reservation")


def _count(connection, relation):
    return int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])


def _count_where(connection, relation, where, parameters=()):
    return int(
        connection.execute(f"SELECT count(*) FROM {relation} WHERE {where}", parameters).fetchone()[
            0
        ]
    )


def _add(findings, finding):
    if finding not in findings:
        findings.append(finding)


def _check_settings(connection, findings):
    row = connection.execute(
        "SELECT activity_mode FROM metadata_setting WHERE singleton = 1"
    ).fetchone()
    if row is None or row["activity_mode"] not in {"semantic", "verbose"}:
        _add(findings, "activity detail mode is invalid")
