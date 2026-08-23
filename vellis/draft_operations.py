"""Operations for the one durable noncanonical draft and its validation backing."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import fields, is_dataclass
from pathlib import Path

from vellis.activity_repository import append_activity, canonical_activity_effect
from vellis.change_domain import (
    DraftChangeRequest,
    DraftChangeResult,
    ValidationPayload,
    ValidationRequest,
    ValidationResult,
    ValidationScope,
)
from vellis.change_operations import _request_findings
from vellis.database import connect_database, require_supported_database
from vellis.domain import (
    PUBLIC_ITEM_LIMIT,
    CurrentState,
    Finding,
    FindingCode,
    GraphChangeRequest,
    ObjectKind,
    OperationOutcome,
    OperationStatus,
    PropertyDefinition,
)
from vellis.draft_activation import prepare_activation_changes, publish_activation_revision
from vellis.draft_analysis import draft_counts
from vellis.draft_repository import (
    clear_draft,
    draft_fingerprint,
    draft_present,
    remove_draft_if_empty,
    stage_definition,
    stage_definition_removal,
    stage_object_removal,
    stage_object_upsert,
    unstage_definition,
    unstage_object,
)
from vellis.draft_sql_overlay import remove_draft_graph_overlay
from vellis.effective_validation import effective_findings
from vellis.public_wire import public_result
from vellis.state_repository import resolve_state
from vellis.wire import serialize_wire


def change_draft(
    database_path: Path,
    request: DraftChangeRequest,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> DraftChangeResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        state = resolve_state(connection, CurrentState())
        findings = _draft_request_findings(connection, request)
        if findings:
            result = DraftChangeResult(
                OperationOutcome(
                    OperationStatus.REJECTED,
                    "draft change was rejected",
                    findings,
                    state.evaluated_revision,
                )
            )
        else:
            _apply_draft_request(connection, request)
            remove_draft_if_empty(connection)
            counts = draft_counts(connection)
            result = DraftChangeResult(
                OperationOutcome(
                    OperationStatus.ACCEPTED,
                    "draft changed" if _has_commands(request) else "draft change had no effect",
                    (),
                    state.evaluated_revision,
                ),
                counts,
            )
        serialize_wire(result)
        append_activity(
            connection,
            capability="rtg_draft_change",
            outcome=result.outcome.status.value,
            initiator=initiator,
            source=source,
            evaluated_revision=state.evaluated_revision,
            resulting_revision=None,
            summary=result.outcome.summary,
            semantic_payload={
                "request": (
                    _wire(request) if result.outcome.status is OperationStatus.REJECTED else None
                ),
                "keys": _draft_request_keys(request),
                "rawEntryCount": (
                    None if result.payload is None else result.payload.raw_entry_count
                ),
                "effectiveChangeCount": (
                    None if result.payload is None else result.payload.effective_change_count
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


def validate_state(
    database_path: Path,
    request: ValidationRequest,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> ValidationResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        state = resolve_state(connection, CurrentState())
        if request.cursor is not None:
            result = _continue_validation(connection, request, state.evaluated_revision)
        else:
            result = _fresh_validation(connection, request, state.evaluated_revision)
        serialize_wire(result)
        append_activity(
            connection,
            capability="rtg_validate",
            outcome=result.outcome.status.value,
            initiator=initiator,
            source=source,
            evaluated_revision=state.evaluated_revision,
            resulting_revision=None,
            summary=result.outcome.summary,
            semantic_payload={
                "request": _wire(request),
                "totalFindings": None if result.payload is None else result.payload.total_findings,
                "findings": _validation_activity_findings(connection, request.scope.value, result),
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


def discard_draft(
    database_path: Path, *, initiator: str = "agent", source: str | None = None
) -> OperationOutcome:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        state = resolve_state(connection, CurrentState())
        was_present = draft_present(connection)
        if was_present:
            clear_draft(connection)
        result = OperationOutcome(
            OperationStatus.ACCEPTED,
            "draft discarded" if was_present else "no draft was present",
            (),
            state.evaluated_revision,
        )
        serialize_wire(result)
        append_activity(
            connection,
            capability="rtg_draft_discard",
            outcome="accepted",
            initiator=initiator,
            source=source,
            evaluated_revision=state.evaluated_revision,
            resulting_revision=None,
            summary=result.summary,
            semantic_payload={"draftWasPresent": was_present},
            verbose_payload={"request": {}, "response": public_result(result)},
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def activate_draft(
    database_path: Path,
    *,
    initiator: str = "agent",
    source: str | None = None,
    finding_limit: int = PUBLIC_ITEM_LIMIT,
) -> ValidationResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        state = resolve_state(connection, CurrentState())
        if not draft_present(connection):
            finding = Finding(FindingCode.MISSING, "draft does not exist", "/draft")
            result = ValidationResult(
                OperationOutcome(
                    OperationStatus.REJECTED,
                    "draft activation was rejected",
                    (finding,),
                    state.evaluated_revision,
                )
            )
            _append_activation(connection, result, initiator, source)
            connection.commit()
            return result
        counts = draft_counts(connection)
        payload = _publish_validation(
            connection,
            ValidationScope.DRAFT,
            state.evaluated_revision,
            effective_findings(connection, state, draft=True),
            finding_limit,
            counts.raw_entry_count,
            counts.effective_change_count,
        )
        remove_draft_graph_overlay(connection)
        if not payload.clean:
            result = ValidationResult(
                OperationOutcome(
                    OperationStatus.REJECTED,
                    "draft activation was rejected",
                    tuple(payload.findings),
                    state.evaluated_revision,
                ),
                payload,
            )
            serialize_wire(result)
            _append_activation(connection, result, initiator, source)
            connection.commit()
            return result
        change_count = prepare_activation_changes(connection, state)
        if change_count == 0:
            clear_draft(connection)
            result = ValidationResult(
                OperationOutcome(
                    OperationStatus.ACCEPTED,
                    "redundant draft cleared without a canonical revision",
                    (),
                    state.evaluated_revision,
                ),
                ValidationPayload(0, True, (), None, 0, 0),
            )
            serialize_wire(result)
            _append_activation(connection, result, initiator, source)
            connection.commit()
            return result
        revision = state.evaluated_revision + 1
        publish_activation_revision(
            connection,
            revision,
            state,
            initiator,
            source,
        )
        clear_draft(connection)
        result = ValidationResult(
            OperationOutcome(
                OperationStatus.ACCEPTED, "draft activated", (), state.evaluated_revision, revision
            ),
            ValidationPayload(0, True, (), None, 0, 0),
        )
        serialize_wire(result)
        _append_activation(connection, result, initiator, source)
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _fresh_validation(connection, request, revision):
    if request.limit is None or not 1 <= request.limit <= PUBLIC_ITEM_LIMIT:
        finding = Finding(
            FindingCode.INVALID_VALUE,
            f"fresh validation requires limit from 1 through {PUBLIC_ITEM_LIMIT}",
            "/limit",
        )
        return ValidationResult(
            OperationOutcome(
                OperationStatus.REJECTED, "validation request was rejected", (finding,), revision
            )
        )
    if request.scope is ValidationScope.DRAFT and not draft_present(connection):
        finding = Finding(FindingCode.MISSING, "draft does not exist", "/scope")
        return ValidationResult(
            OperationOutcome(
                OperationStatus.REJECTED, "validation request was rejected", (finding,), revision
            )
        )
    raw = effective = None
    if request.scope is ValidationScope.DRAFT:
        counts = draft_counts(connection)
        raw, effective = counts.raw_entry_count, counts.effective_change_count
    state = resolve_state(connection, CurrentState())
    payload = _publish_validation(
        connection,
        request.scope,
        revision,
        effective_findings(connection, state, draft=request.scope is ValidationScope.DRAFT),
        request.limit,
        raw,
        effective,
    )
    return ValidationResult(
        OperationOutcome(OperationStatus.ACCEPTED, "validation completed", (), revision), payload
    )


def _continue_validation(connection, request, revision):
    if request.limit is not None:
        finding = Finding(
            FindingCode.INVALID_VALUE, "validation continuation must omit limit", "/limit"
        )
        return ValidationResult(
            OperationOutcome(
                OperationStatus.REJECTED, "validation request was rejected", (finding,), revision
            )
        )
    digest = hashlib.sha256(request.cursor.encode("utf-8")).digest()
    row = connection.execute(
        "SELECT * FROM validation_run WHERE scope = ?", (request.scope.value,)
    ).fetchone()
    current_fingerprint = (
        draft_fingerprint(connection)
        if request.scope is ValidationScope.DRAFT and draft_present(connection)
        else None
    )
    if (
        row is None
        or row["cursor_hash"] is None
        or bytes(row["cursor_hash"]) != digest
        or int(row["evaluated_revision"]) != revision
        or (
            request.scope is ValidationScope.DRAFT
            and bytes(row["draft_fingerprint"] or b"") != bytes(current_fingerprint or b"")
        )
    ):
        finding = Finding(FindingCode.EXPIRED_CURSOR, "validation cursor expired", "/cursor")
        return ValidationResult(
            OperationOutcome(
                OperationStatus.REJECTED,
                "validation continuation was rejected",
                (finding,),
                revision,
            )
        )
    offset = int(row["next_offset"])
    page_limit = int(row["page_limit"])
    stored = connection.execute(
        """SELECT finding FROM validation_finding
           WHERE scope = ? AND ordinal >= ? ORDER BY ordinal LIMIT ?""",
        (request.scope.value, offset, page_limit),
    ).fetchall()
    findings = tuple(_finding_from_json(str(value[0])) for value in stored)
    next_offset = offset + len(findings)
    total = int(row["total_findings"])
    cursor = None
    if next_offset < total:
        cursor = request.cursor
        connection.execute(
            "UPDATE validation_run SET next_offset = ? WHERE scope = ?",
            (next_offset, request.scope.value),
        )
    else:
        connection.execute(
            """UPDATE validation_run SET cursor_hash = NULL, next_offset = NULL,
               page_limit = NULL WHERE scope = ?""",
            (request.scope.value,),
        )
    payload = ValidationPayload(
        total,
        total == 0,
        findings,
        cursor,
        row["raw_draft_entry_count"],
        row["effective_draft_change_count"],
    )
    return ValidationResult(
        OperationOutcome(OperationStatus.ACCEPTED, "validation continued", (), revision), payload
    )


def _publish_validation(connection, scope, revision, findings, limit, raw=None, effective=None):
    connection.execute("DELETE FROM validation_run WHERE scope = ?", (scope.value,))
    connection.execute("DROP TABLE IF EXISTS temp.validation_work")
    connection.execute(
        """CREATE TEMP TABLE validation_work(
           code TEXT NOT NULL, path TEXT NOT NULL, type_keys TEXT NOT NULL,
           uuids TEXT NOT NULL, summary TEXT NOT NULL, finding TEXT NOT NULL)"""
    )
    for finding in findings:
        encoded = json.dumps(_wire(finding), sort_keys=True, separators=(",", ":"))
        connection.execute(
            "INSERT INTO temp.validation_work VALUES (?, ?, ?, ?, ?, ?)",
            (
                finding.code.value,
                finding.path or "",
                json.dumps(finding.type_keys, separators=(",", ":")),
                json.dumps(finding.uuids, separators=(",", ":")),
                finding.summary,
                encoded,
            ),
        )
    total = int(connection.execute("SELECT count(*) FROM temp.validation_work").fetchone()[0])
    token = _token() if total > limit else None
    digest = None if token is None else hashlib.sha256(token.encode("utf-8")).digest()
    fingerprint = draft_fingerprint(connection) if scope is ValidationScope.DRAFT else None
    connection.execute(
        """INSERT INTO validation_run(
           scope, evaluated_revision, draft_fingerprint, total_findings,
           raw_draft_entry_count, effective_draft_change_count,
           cursor_hash, next_offset, page_limit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scope.value,
            revision,
            fingerprint,
            total,
            raw,
            effective,
            digest,
            limit if token else None,
            limit if token else None,
        ),
    )
    page = []
    rows = connection.execute(
        """SELECT finding FROM temp.validation_work
           ORDER BY code, path, type_keys, uuids, summary"""
    )
    for ordinal, row in enumerate(rows):
        encoded = str(row[0])
        connection.execute(
            "INSERT INTO validation_finding VALUES (?, ?, ?)",
            (scope.value, ordinal, encoded),
        )
        if ordinal < limit:
            page.append(_finding_from_json(encoded))
    connection.execute("DROP TABLE temp.validation_work")
    return ValidationPayload(total, total == 0, tuple(page), token, raw, effective)


def _apply_draft_request(connection, request):
    for definition in request.definition_upserts:
        stage_definition(connection, definition)
    for key in request.definition_removals:
        stage_definition_removal(connection, key)
    for key in request.unstage_definition_keys:
        unstage_definition(connection, key)
    for upsert in request.object_upserts:
        stage_object_upsert(connection, upsert)
    for uuid in request.object_removals:
        row = connection.execute(
            "SELECT kind FROM graph_object_identity WHERE uuid = ?", (uuid,)
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT kind FROM draft_graph_object_patch WHERE uuid = ?", (uuid,)
            ).fetchone()
        if row is not None:
            stage_object_removal(connection, uuid, ObjectKind(str(row[0])))
    for uuid in request.unstage_object_uuids:
        unstage_object(connection, uuid)
    if draft_present(connection):
        draft_fingerprint(connection)
        connection.execute(
            """UPDATE draft_metadata
               SET inspect_cursor_hash = NULL, inspect_cursor_state = NULL
               WHERE singleton = 1"""
        )


def _draft_request_findings(connection, request):
    findings = []
    definition_commands = [
        (value.type_key, f"/definitionUpserts/{index}/typeKey")
        for index, value in enumerate(request.definition_upserts)
    ]
    definition_commands.extend(
        (key, f"/definitionRemovals/{index}")
        for index, key in enumerate(request.definition_removals)
    )
    definition_commands.extend(
        (key, f"/unstageDefinitionKeys/{index}")
        for index, key in enumerate(request.unstage_definition_keys)
    )
    object_commands = [
        (value.uuid, f"/objectUpserts/{index}/uuid")
        for index, value in enumerate(request.object_upserts)
    ]
    object_commands.extend(
        (uuid, f"/objectRemovals/{index}") for index, uuid in enumerate(request.object_removals)
    )
    object_commands.extend(
        (uuid, f"/unstageObjectUuids/{index}")
        for index, uuid in enumerate(request.unstage_object_uuids)
    )
    _duplicate_command_paths(
        definition_commands,
        "type key occurs in more than one command",
        findings,
    )
    _duplicate_command_paths(object_commands, "UUID occurs in more than one command", findings)
    if len(definition_commands) + len(object_commands) > PUBLIC_ITEM_LIMIT:
        findings.append(
            Finding(
                FindingCode.INVALID_VALUE,
                f"draft change exceeds {PUBLIC_ITEM_LIMIT} commands",
                "",
            )
        )
    for index, definition in enumerate(request.definition_upserts):
        if definition.system is not None:
            findings.append(
                Finding(
                    FindingCode.INVALID_VALUE,
                    "draft definition cannot supply system metadata",
                    # The boundary carries no system member on a definition
                    # upsert, so name the entry the caller did send.
                    f"/definitionUpserts/{index}",
                )
            )
        reservation = connection.execute(
            "SELECT kind FROM type_key_identity WHERE type_key = ?", (definition.type_key,)
        ).fetchone()
        if reservation is not None and str(reservation[0]) != definition.kind.value:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "type key is reserved to another definition kind",
                    f"/definitionUpserts/{index}/typeKey",
                    type_keys=(definition.type_key,),
                )
            )
    graph_request = GraphChangeRequest(0, request.object_upserts, request.object_removals)
    findings.extend(
        _request_findings(
            graph_request,
            upserts_path="/objectUpserts",
            removals_path="/objectRemovals",
            check_command_duplicates=False,
        )
    )
    for index, upsert in enumerate(request.object_upserts):
        reservation = connection.execute(
            "SELECT kind FROM graph_object_identity WHERE uuid = ?", (upsert.uuid,)
        ).fetchone()
        staged = connection.execute(
            "SELECT kind, tombstone FROM draft_graph_object_patch WHERE uuid = ?",
            (upsert.uuid,),
        ).fetchone()
        reserved_kind = None if reservation is None else str(reservation[0])
        staged_kind = None if staged is None or bool(staged["tombstone"]) else str(staged["kind"])
        if reserved_kind is not None and reserved_kind != upsert.kind.value:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "UUID is permanently reserved to another object kind",
                    f"/objectUpserts/{index}/uuid",
                    uuids=(upsert.uuid,),
                )
            )
        elif staged_kind is not None and staged_kind != upsert.kind.value:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "staged object kind cannot change",
                    f"/objectUpserts/{index}/kind",
                    uuids=(upsert.uuid,),
                )
            )
    return _ordered(findings)


def _append_activation(connection, result, initiator, source):
    serialize_wire(result)
    semantic: dict[str, object] = {
        "findings": _validation_activity_findings(connection, "draft", result)
    }
    if result.outcome.status is OperationStatus.ACCEPTED:
        semantic.update(canonical_activity_effect(connection, result.outcome.resulting_revision))
    append_activity(
        connection,
        capability="rtg_draft_activate",
        outcome=result.outcome.status.value,
        initiator=initiator,
        source=source,
        evaluated_revision=result.outcome.evaluated_revision,
        resulting_revision=result.outcome.resulting_revision,
        summary=result.outcome.summary,
        semantic_payload=semantic,
        verbose_payload={"request": {}, "response": public_result(result)},
    )


def _finding_from_json(value):
    item = json.loads(value)
    return Finding(
        FindingCode(item["code"]),
        item["summary"],
        item.get("path"),
        tuple(item.get("type_keys", ())),
        tuple(item.get("uuids", ())),
    )


def _token():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def _duplicates(values, path, summary, findings):
    seen = set()
    for index, value in enumerate(values):
        if value in seen:
            findings.append(Finding(FindingCode.DUPLICATE, summary, f"{path}/{index}"))
        seen.add(value)


def _duplicate_command_paths(commands, summary, findings):
    seen = set()
    for value, path in commands:
        if value in seen:
            findings.append(Finding(FindingCode.DUPLICATE, summary, path))
        seen.add(value)


def _ordered(findings):
    return tuple(
        sorted(
            findings, key=lambda v: (v.code.value, v.path or "", v.type_keys, v.uuids, v.summary)
        )
    )


def _has_commands(request):
    return any(getattr(request, field.name) for field in fields(request))


def _draft_request_keys(request):
    return {
        "typeKeys": sorted(
            [value.type_key for value in request.definition_upserts]
            + list(request.definition_removals)
            + list(request.unstage_definition_keys)
        ),
        "uuids": sorted(
            [value.uuid for value in request.object_upserts]
            + list(request.object_removals)
            + list(request.unstage_object_uuids)
        ),
    }


def _wire(value):
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _wire(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
            and not (
                isinstance(value, PropertyDefinition)
                and field.name == "allowed_values"
                and not value.allowed_values_present
            )
        }
    if hasattr(value, "wire_value"):
        return value.wire_value()
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def _validation_activity_findings(connection, scope, result):
    if result.payload is None:
        return _wire(result.outcome.findings)
    return [
        json.loads(str(row[0]))
        for row in connection.execute(
            "SELECT finding FROM validation_finding WHERE scope = ? ORDER BY ordinal", (scope,)
        )
    ]
