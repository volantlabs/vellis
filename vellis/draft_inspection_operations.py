"""Connection-owning raw inspection for the single draft bucket."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import fields, is_dataclass, replace
from pathlib import Path

from vellis.activity_repository import append_activity
from vellis.change_domain import (
    DraftCategory,
    DraftInspectionEntry,
    DraftInspectionPayload,
    DraftInspectionRequest,
    DraftInspectionResult,
    DraftOperation,
)
from vellis.change_operations import _content
from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import load_definitions
from vellis.domain import (
    PUBLIC_ITEM_LIMIT,
    CurrentState,
    Finding,
    FindingCode,
    OperationOutcome,
    OperationStatus,
)
from vellis.draft_analysis import draft_counts
from vellis.draft_repository import (
    draft_fingerprint,
    draft_present,
    ensure_draft,
    load_draft_definitions,
    load_draft_graph,
)
from vellis.graph_repository import load_graph_objects
from vellis.public_wire import public_result
from vellis.sqlite_values import property_from_row
from vellis.state_repository import resolve_state
from vellis.wire import serialize_wire


def inspect_draft(
    database_path: Path,
    request: DraftInspectionRequest,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> DraftInspectionResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        state = resolve_state(connection, CurrentState())
        request_finding = _request_finding(request)
        if request_finding is not None:
            result = DraftInspectionResult(
                OperationOutcome(
                    OperationStatus.REJECTED,
                    "draft inspection was rejected",
                    (request_finding,),
                    state.evaluated_revision,
                )
            )
        elif request.cursor is not None:
            result = _continue(connection, request.cursor, state.evaluated_revision)
        else:
            assert request.limit is not None
            result = _fresh(connection, request, state.evaluated_revision)
        serialize_wire(result)
        append_activity(
            connection,
            capability="rtg_draft_inspect",
            outcome=result.outcome.status.value,
            initiator=initiator,
            source=source,
            evaluated_revision=state.evaluated_revision,
            resulting_revision=None,
            summary=result.outcome.summary,
            semantic_payload={
                "request": _wire(request),
                "returnedCount": None if result.payload is None else result.payload.returned_count,
                "rawEntryCount": (
                    None if result.payload is None else result.payload.counts.raw_entry_count
                ),
                "effectiveChangeCount": (
                    None if result.payload is None else result.payload.counts.effective_change_count
                ),
                "findings": _wire(result.outcome.findings),
            },
            verbose_payload={"request": _wire(request), "response": public_result(result)},
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _fresh(connection, request, revision):
    entries = _entries(connection, request, 0, request.limit + 1)
    page = entries[: request.limit]
    cursor = None
    if len(entries) > request.limit:
        cursor = secrets.token_urlsafe(32)
        state = {
            "categories": [value.value for value in request.categories],
            "operations": [value.value for value in request.operations],
            "typeKeys": list(request.type_keys),
            "uuids": list(request.uuids),
            "limit": request.limit,
            "offset": request.limit,
            "evaluatedRevision": revision,
            "fingerprint": draft_fingerprint(connection).hex(),
        }
        ensure_draft(connection)
        connection.execute(
            """UPDATE draft_metadata
               SET inspect_cursor_hash = ?, inspect_cursor_state = ? WHERE singleton = 1""",
            (
                hashlib.sha256(cursor.encode("utf-8")).digest(),
                json.dumps(state, separators=(",", ":"), sort_keys=True),
            ),
        )
    elif draft_present(connection):
        connection.execute(
            """UPDATE draft_metadata SET inspect_cursor_hash = NULL,
               inspect_cursor_state = NULL WHERE singleton = 1"""
        )
    payload = DraftInspectionPayload(draft_counts(connection), len(page), tuple(page), cursor)
    return DraftInspectionResult(
        OperationOutcome(OperationStatus.ACCEPTED, "draft inspected", (), revision), payload
    )


def _continue(connection, cursor, revision):
    row = connection.execute(
        """SELECT fingerprint, inspect_cursor_hash, inspect_cursor_state
           FROM draft_metadata WHERE singleton = 1"""
    ).fetchone()
    digest = hashlib.sha256(cursor.encode("utf-8")).digest()
    if (
        row is None
        or row["inspect_cursor_hash"] is None
        or bytes(row["inspect_cursor_hash"]) != digest
    ):
        return _expired(revision)
    state = json.loads(str(row["inspect_cursor_state"]))
    if (
        state["evaluatedRevision"] != revision
        or state["fingerprint"] != draft_fingerprint(connection).hex()
    ):
        return _expired(revision)
    request = DraftInspectionRequest(
        tuple(DraftCategory(value) for value in state["categories"]),
        tuple(DraftOperation(value) for value in state["operations"]),
        tuple(state["typeKeys"]),
        tuple(state["uuids"]),
        int(state["limit"]),
    )
    offset = int(state["offset"])
    assert request.limit is not None
    entries = _entries(connection, request, offset, request.limit + 1)
    page = entries[: request.limit]
    next_offset = offset + len(page)
    next_cursor = cursor if len(entries) > request.limit else None
    if next_cursor is None:
        connection.execute(
            """UPDATE draft_metadata SET inspect_cursor_hash = NULL,
               inspect_cursor_state = NULL WHERE singleton = 1"""
        )
    else:
        state["offset"] = next_offset
        connection.execute(
            "UPDATE draft_metadata SET inspect_cursor_state = ? WHERE singleton = 1",
            (json.dumps(state, separators=(",", ":"), sort_keys=True),),
        )
    payload = DraftInspectionPayload(draft_counts(connection), len(page), tuple(page), next_cursor)
    return DraftInspectionResult(
        OperationOutcome(OperationStatus.ACCEPTED, "draft inspection continued", (), revision),
        payload,
    )


def _entries(connection, request, offset, limit):
    rows = _entry_rows(connection, request, offset, limit)
    state = resolve_state(connection, CurrentState())
    entries = []
    for category_text, key, operation_text in rows:
        category = DraftCategory(str(category_text))
        operation = DraftOperation(str(operation_text))
        if category is DraftCategory.DEFINITIONS:
            current_values = load_definitions(connection, state, (str(key),))
            proposed_values = load_draft_definitions(connection, current_values, (str(key),))
            current = None if not current_values else current_values[0]
            proposed = None if not proposed_values else proposed_values[0]
            row = connection.execute(
                "SELECT * FROM draft_definition_entry WHERE type_key = ?", (key,)
            ).fetchone()
            assert row is not None
            staged = (
                {"remove": True}
                if operation is DraftOperation.REMOVE
                else _definition_content(proposed)
            )
            entries.append(
                DraftInspectionEntry(
                    category,
                    str(key),
                    operation,
                    current,
                    staged,
                    proposed,
                    _definition_content(current) != _definition_content(proposed),
                )
            )
            continue
        current_values = load_graph_objects(connection, state, (str(key),))
        proposed_values, _ = load_draft_graph(connection, current_values, (str(key),))
        current = None if not current_values else current_values[0]
        proposed = None if not proposed_values else proposed_values[0]
        row = connection.execute(
            "SELECT * FROM draft_graph_object_patch WHERE uuid = ?", (key,)
        ).fetchone()
        assert row is not None
        staged = (
            {"remove": True}
            if operation is DraftOperation.REMOVE
            else _staged_operations(connection, row)
        )
        entries.append(
            DraftInspectionEntry(
                category,
                str(key),
                operation,
                current,
                staged,
                proposed,
                False
                if current is None and proposed is None
                else current is None or proposed is None or _content(current) != _content(proposed),
            )
        )
    return tuple(entries)


def _entry_rows(connection, request, offset, limit):
    categories = json.dumps([value.value for value in request.categories])
    operations = json.dumps([value.value for value in request.operations])
    type_keys = json.dumps(request.type_keys)
    uuids = json.dumps(request.uuids)
    return connection.execute(
        """WITH entries(category_order, category, key, operation) AS (
             SELECT 0, 'definitions', d.type_key,
                    CASE WHEN d.operation = 'remove' THEN 'remove'
                         WHEN EXISTS (SELECT 1 FROM definition_version v
                                      WHERE v.type_key = d.type_key
                                        AND v.valid_to_revision IS NULL)
                         THEN 'replace' ELSE 'add' END
             FROM draft_definition_entry d
             UNION ALL
             SELECT CASE p.kind WHEN 'anchor' THEN 1 WHEN 'associatedData' THEN 2 ELSE 3 END,
                    CASE p.kind WHEN 'anchor' THEN 'anchors'
                         WHEN 'associatedData' THEN 'associatedData' ELSE 'links' END,
                    p.uuid,
                    CASE WHEN p.tombstone = 1 THEN 'remove'
                         WHEN EXISTS (SELECT 1 FROM graph_object_version v
                                      WHERE v.uuid = p.uuid AND v.valid_to_revision IS NULL)
                         THEN 'patch' ELSE 'add' END
             FROM draft_graph_object_patch p
           )
           SELECT category, key, operation FROM entries
           WHERE (json_array_length(?) = 0 OR category IN (SELECT value FROM json_each(?)))
             AND (json_array_length(?) = 0 OR operation IN (SELECT value FROM json_each(?)))
             AND ((category = 'definitions' AND
                   (json_array_length(?) = 0 OR key IN (SELECT value FROM json_each(?))))
                  OR (category <> 'definitions' AND
                      (json_array_length(?) = 0 OR key IN (SELECT value FROM json_each(?)))))
           ORDER BY category_order, key LIMIT ? OFFSET ?""",
        (
            categories,
            categories,
            operations,
            operations,
            type_keys,
            type_keys,
            uuids,
            uuids,
            limit,
            offset,
        ),
    )


def _staged_operations(connection, row):
    if bool(row["tombstone"]):
        return {"remove": True}
    staged: dict[str, object] = {}
    field_names = {
        "type_key": "typeKey",
        "display_name": "displayName",
        "source_uuid": "sourceUuid",
        "target_uuid": "targetUuid",
    }
    for column, field_name in field_names.items():
        if bool(row[f"has_{column}"]):
            staged[field_name] = str(row[column])
    if bool(row["has_complete_anchor_set"]):
        staged["anchorUuids"] = [
            str(value[0])
            for value in connection.execute(
                """SELECT anchor_uuid FROM draft_association_operation
                   WHERE object_uuid = ? AND operation = 'base' ORDER BY anchor_uuid""",
                (row["uuid"],),
            )
        ]
    association_rows = connection.execute(
        """SELECT anchor_uuid, operation FROM draft_association_operation
           WHERE object_uuid = ? AND operation <> 'base' ORDER BY anchor_uuid""",
        (row["uuid"],),
    ).fetchall()
    additions = [
        str(value["anchor_uuid"]) for value in association_rows if value["operation"] == "add"
    ]
    removals = [
        str(value["anchor_uuid"]) for value in association_rows if value["operation"] == "remove"
    ]
    if additions:
        staged["addAnchorUuids"] = additions
    if removals:
        staged["removeAnchorUuids"] = removals
    property_rows = connection.execute(
        """SELECT * FROM draft_property_operation
           WHERE object_uuid = ? ORDER BY property_name""",
        (row["uuid"],),
    ).fetchall()
    sets = {
        str(value["property_name"]): property_from_row(value)
        for value in property_rows
        if value["operation"] == "set"
    }
    removes = [
        str(value["property_name"]) for value in property_rows if value["operation"] == "remove"
    ]
    if sets:
        staged["setProperties"] = sets
    if removes:
        staged["removeProperties"] = removes
    return staged


def _request_finding(request):
    if request.cursor is None:
        if request.limit is None or not 1 <= request.limit <= PUBLIC_ITEM_LIMIT:
            return Finding(
                FindingCode.INVALID_VALUE,
                f"fresh inspection requires limit from 1 through {PUBLIC_ITEM_LIMIT}",
                "/limit",
            )
    elif (
        any((request.categories, request.operations, request.type_keys, request.uuids))
        or request.limit is not None
    ):
        return Finding(
            FindingCode.INVALID_VALUE,
            "inspection continuation accepts only cursor",
            "/cursor",
        )
    for path, values in (
        ("/categories", request.categories),
        ("/operations", request.operations),
        ("/typeKeys", request.type_keys),
        ("/uuids", request.uuids),
    ):
        if len(set(values)) != len(values):
            return Finding(FindingCode.DUPLICATE, "duplicate inspection filter", path)
    return None


def _expired(revision):
    finding = Finding(FindingCode.EXPIRED_CURSOR, "draft inspection cursor expired", "/cursor")
    return DraftInspectionResult(
        OperationOutcome(
            OperationStatus.REJECTED,
            "draft inspection continuation was rejected",
            (finding,),
            revision,
        )
    )


def _definition_content(value):
    return None if value is None else replace(value, system=None)


def _wire(value):
    if is_dataclass(value):
        return {field.name: _wire(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if hasattr(value, "value"):
        return _wire(value.value)
    return value
