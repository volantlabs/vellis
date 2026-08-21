"""Connection-owning bounded history and activity-mode operations."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from vellis.activity_repository import append_activity
from vellis.database import connect_database, require_supported_database
from vellis.domain import Finding, FindingCode, OperationOutcome, OperationStatus
from vellis.history_domain import (
    ActivityHistoryEntry,
    ActivityHistoryPayload,
    ActivityMode,
    CanonicalHistoryEntry,
    CanonicalHistoryPayload,
    HistoryKind,
    HistoryRequest,
    HistoryResult,
    TimeHistoryRange,
)
from vellis.history_repository import history_head, select_history
from vellis.wire import serialize_wire, wire_value


def inspect_history(
    database_path: Path,
    request: HistoryRequest,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> HistoryResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        evaluated = int(
            connection.execute(
                "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
            ).fetchone()[0]
        )
        head = history_head(connection, request.kind)
        finding = _request_finding(request)
        entries = () if finding is not None else select_history(connection, request, head)
        if finding is not None:
            result = HistoryResult(
                OperationStatus.REJECTED,
                "history request was rejected",
                (finding,),
                evaluated,
            )
        elif len(entries) > request.maximum_records:
            result = HistoryResult(
                OperationStatus.REJECTED,
                "history interval exceeds maximumRecords",
                (
                    Finding(
                        FindingCode.RESULT_LIMIT_EXCEEDED,
                        "complete history interval exceeds maximumRecords",
                        "/maximumRecords",
                    ),
                ),
                evaluated,
            )
        else:
            payload = (
                CanonicalHistoryPayload(head, cast(tuple[CanonicalHistoryEntry, ...], entries))
                if request.kind is HistoryKind.CANONICAL
                else ActivityHistoryPayload(head, cast(tuple[ActivityHistoryEntry, ...], entries))
            )
            result = HistoryResult(
                OperationStatus.ACCEPTED,
                "history interval selected",
                (),
                evaluated,
                payload,
            )
        serialize_wire(result)
        activity_detail = _history_activity_detail(request, result, head)
        append_activity(
            connection,
            capability="rtg_history",
            outcome=result.status.value,
            initiator=initiator,
            source=source,
            evaluated_revision=evaluated,
            resulting_revision=None,
            summary=result.summary,
            semantic_payload=activity_detail,
            verbose_payload=activity_detail,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def configure_activity_mode(
    database_path: Path,
    mode: ActivityMode,
    *,
    initiator: str = "owner",
    source: str | None = None,
) -> OperationOutcome:
    if not isinstance(mode, ActivityMode):
        raise ValueError("activity mode is invalid")
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT head_revision, activity_mode FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
        evaluated = int(row["head_revision"])
        previous = str(row["activity_mode"])
        connection.execute(
            "UPDATE metadata_setting SET activity_mode = ? WHERE singleton = 1", (mode.value,)
        )
        result = OperationOutcome(
            OperationStatus.ACCEPTED,
            "activity detail mode changed"
            if previous != mode.value
            else "activity detail mode unchanged",
            (),
            evaluated,
        )
        serialize_wire(result)
        append_activity(
            connection,
            capability="configure.activityMode",
            outcome="accepted",
            initiator=initiator,
            source=source,
            evaluated_revision=evaluated,
            resulting_revision=None,
            summary=result.summary,
            semantic_payload={"previousMode": previous, "resultingMode": mode.value},
            verbose_payload={
                "request": {"activityMode": mode.value},
                "response": wire_value(result),
            },
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _request_finding(request: HistoryRequest) -> Finding | None:
    if request.include_verbose and request.kind is not HistoryKind.ACTIVITY:
        return Finding(
            FindingCode.INVALID_VALUE,
            "includeVerbose is valid only for activity history",
            "/includeVerbose",
        )
    value = request.range
    if isinstance(value, TimeHistoryRange) and value.start is not None and value.end is not None:
        if (value.start.epoch_seconds, value.start.nanosecond) > (
            value.end.epoch_seconds,
            value.end.nanosecond,
        ):
            return Finding(
                FindingCode.INVALID_VALUE,
                "history start time is after end time",
                "/range/start",
            )
    return None


def _history_activity_detail(request, result, head):
    return {
        "request": wire_value(request),
        "selectedLedger": request.kind.value,
        "headSequence": head,
        "status": result.status.value,
        "returnedCount": 0 if result.payload is None else len(result.payload.entries),
        "resultShape": None if result.payload is None else {"ledger": request.kind.value},
        "findings": wire_value(result.findings),
    }
