"""Connection-owning shallow and focused definition discovery operations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vellis.activity_repository import append_activity
from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import load_definitions
from vellis.discovery_repository import load_anchor_summary, load_neighborhoods
from vellis.domain import (
    AnchorTypeDefinition,
    Finding,
    FindingCode,
    OperationStatus,
    StateSelection,
    SystemEnvelope,
    TypeDefinition,
)
from vellis.draft_read_operations import draft_neighborhoods
from vellis.draft_repository import load_draft_definitions
from vellis.public_wire import public_result
from vellis.query_domain import (
    PUBLIC_ITEM_LIMIT,
    DefinitionNeighborhood,
    TypeInspectionResult,
    TypeSummaryResult,
)
from vellis.state_repository import StateNotFoundError, resolve_state
from vellis.wire import serialize_wire, wire_value


def type_summary(
    database_path: Path,
    state_selection: StateSelection | None = None,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> TypeSummaryResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            state = resolve_state(connection, state_selection)
            values, over_limit = _summary_values(connection, state)
            if over_limit:
                finding = _finding(
                    FindingCode.RESULT_LIMIT_EXCEEDED,
                    "/anchorTypes",
                    "complete anchor summary exceeds the public item limit",
                )
                result = TypeSummaryResult(
                    OperationStatus.REJECTED,
                    "anchor summary cannot be returned completely",
                    (finding,),
                    state.evaluated_revision,
                    None,
                )
            else:
                result = TypeSummaryResult(
                    OperationStatus.ACCEPTED,
                    "anchor types selected",
                    (),
                    state.evaluated_revision,
                    values,
                )
        except StateNotFoundError as error:
            result = TypeSummaryResult(
                OperationStatus.REJECTED,
                "state was not found",
                (_finding(FindingCode.MISSING, "/state", str(error)),),
                None,
                None,
            )
        serialize_wire(result)
        _append_discovery_activity(
            connection,
            "rtg_type_summary",
            result,
            {"state": wire_value(state_selection)},
            {"anchorTypeCount": 0 if result.anchor_types is None else len(result.anchor_types)},
            initiator,
            source,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _summary_values(connection, state):
    if state.includes_draft:
        if _draft_anchor_type_count(connection) > PUBLIC_ITEM_LIMIT:
            return (), True
        anchor_keys = _draft_anchor_type_keys(connection, PUBLIC_ITEM_LIMIT)
        definitions = load_draft_definitions(
            connection,
            load_definitions(connection, state, anchor_keys),
            anchor_keys,
        )
        values = tuple(
            _definition_without_legacy(value)
            for value in definitions
            if isinstance(value, AnchorTypeDefinition)
        )
        return values, False
    values = tuple(
        _definition_without_legacy(value)
        for value in load_anchor_summary(connection, state, PUBLIC_ITEM_LIMIT + 1)
    )
    return values, len(values) > PUBLIC_ITEM_LIMIT


def type_inspect(
    database_path: Path,
    anchor_type_keys: tuple[str, ...],
    *,
    state_selection: StateSelection | None = None,
    include_legacy_system: bool = False,
    initiator: str = "agent",
    source: str | None = None,
) -> TypeInspectionResult:
    request_findings = _inspection_request_findings(anchor_type_keys, include_legacy_system)
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        result = _inspect_result(
            connection,
            anchor_type_keys,
            state_selection,
            include_legacy_system,
            request_findings,
        )
        serialize_wire(result)
        _append_discovery_activity(
            connection,
            "rtg_type_inspect",
            result,
            {
                "state": wire_value(state_selection),
                "anchorTypeKeys": list(anchor_type_keys),
                "includeLegacySystem": include_legacy_system,
            },
            {"neighborhoodCount": 0 if result.neighborhoods is None else len(result.neighborhoods)},
            initiator,
            source,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _inspect_result(
    connection, anchor_type_keys, state_selection, include_legacy_system, request_findings
):
    if request_findings:
        head = int(
            connection.execute(
                "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
            ).fetchone()[0]
        )
        return TypeInspectionResult(
            OperationStatus.REJECTED,
            "definition inspection was rejected",
            request_findings,
            head,
            None,
        )
    try:
        state = resolve_state(connection, state_selection)
        definitions = _inspection_definitions(connection, state, anchor_type_keys)
        selected = tuple(value for value in definitions if value.type_key in anchor_type_keys)
        unknown = _unknown_anchor_findings(anchor_type_keys, selected)
        if unknown:
            return TypeInspectionResult(
                OperationStatus.REJECTED,
                "definition inspection was rejected",
                unknown,
                state.evaluated_revision,
                None,
            )
        neighborhoods = (
            draft_neighborhoods(definitions, anchor_type_keys)
            if state.includes_draft
            else load_neighborhoods(connection, state, anchor_type_keys)
        )
        projected = tuple(
            _neighborhood_legacy(value, include_legacy_system) for value in neighborhoods
        )
        return TypeInspectionResult(
            OperationStatus.ACCEPTED,
            "definition neighborhoods selected",
            (),
            state.evaluated_revision,
            projected,
        )
    except StateNotFoundError as error:
        return TypeInspectionResult(
            OperationStatus.REJECTED,
            "state was not found",
            (_finding(FindingCode.MISSING, "/state", str(error)),),
            None,
            None,
        )


def _inspection_definitions(connection, state, anchor_type_keys):
    if not state.includes_draft:
        return load_definitions(connection, state, anchor_type_keys)
    keys = _draft_neighborhood_type_keys(connection, anchor_type_keys)
    return load_draft_definitions(connection, load_definitions(connection, state, keys), keys)


def _inspection_request_findings(anchor_type_keys, include_legacy_system):
    findings: list[Finding] = []
    if not isinstance(anchor_type_keys, tuple) or any(
        not isinstance(value, str) for value in anchor_type_keys
    ):
        return (
            _finding(
                FindingCode.INVALID_VALUE,
                "/anchorTypeKeys",
                "anchorTypeKeys must be a tuple of text",
            ),
        )
    if not 1 <= len(anchor_type_keys) <= PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                "/anchorTypeKeys",
                "anchorTypeKeys must contain between 1 and 1000 keys",
            )
        )
    seen: set[str] = set()
    for index, key in enumerate(anchor_type_keys):
        if key in seen:
            findings.append(
                _finding(
                    FindingCode.DUPLICATE,
                    f"/anchorTypeKeys/{index}",
                    "duplicate anchor type key",
                    type_keys=(key,),
                )
            )
        seen.add(key)
    if type(include_legacy_system) is not bool:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                "/includeLegacySystem",
                "includeLegacySystem must be Boolean",
            )
        )
    return _ordered_findings(findings)


def _unknown_anchor_findings(requested, selected):
    by_key = {value.type_key: value for value in selected}
    findings = []
    for index, key in enumerate(requested):
        value = by_key.get(key)
        if value is None:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    f"/anchorTypeKeys/{index}",
                    "unknown anchor type key",
                    type_keys=(key,),
                )
            )
        elif not isinstance(value, AnchorTypeDefinition):
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"/anchorTypeKeys/{index}",
                    "type key is not an anchor type",
                    type_keys=(key,),
                )
            )
    return _ordered_findings(findings)


def _definition_without_legacy(value: TypeDefinition) -> TypeDefinition:
    if value.system is None or value.system.legacy_v1 is None:
        return value
    return replace(
        value,
        system=SystemEnvelope(value.system.created_revision, value.system.last_changed_revision),
    )


def _draft_anchor_type_keys(connection, maximum):
    rows = connection.execute(
        """SELECT type_key FROM definition_version
           WHERE valid_to_revision IS NULL AND kind = 'anchor'
             AND NOT EXISTS (
               SELECT 1 FROM draft_definition_entry AS d
               WHERE d.type_key = definition_version.type_key
             )
           UNION
           SELECT type_key FROM draft_definition_entry
           WHERE operation = 'replace' AND kind = 'anchor'
           ORDER BY type_key LIMIT ?""",
        (maximum,),
    )
    return tuple(str(row[0]) for row in rows)


def _draft_anchor_type_count(connection):
    return int(
        connection.execute(
            """SELECT count(*) FROM (
               SELECT v.type_key FROM definition_version AS v
               WHERE v.valid_to_revision IS NULL AND v.kind = 'anchor'
                 AND NOT EXISTS (
                   SELECT 1 FROM draft_definition_entry AS d
                   WHERE d.type_key = v.type_key
                 )
               UNION
               SELECT d.type_key FROM draft_definition_entry AS d
               WHERE d.operation = 'replace' AND d.kind = 'anchor')"""
        ).fetchone()[0]
    )


def _draft_neighborhood_type_keys(connection, anchor_type_keys):
    encoded = tuple(anchor_type_keys)
    placeholders = ",".join("?" for _ in encoded)
    data_rows = connection.execute(
        f"""SELECT DISTINCT p.type_key FROM definition_permitted_type AS p
            WHERE p.valid_to_revision IS NULL AND p.role = 'anchor'
              AND p.permitted_type_key IN ({placeholders})
              AND NOT EXISTS (
                SELECT 1 FROM draft_definition_entry AS d WHERE d.type_key = p.type_key)
            UNION
            SELECT DISTINCT p.type_key FROM draft_definition_permitted_type AS p
            JOIN draft_definition_entry AS d USING (type_key)
            WHERE d.operation = 'replace' AND d.kind = 'associatedData'
              AND p.role = 'anchor' AND p.permitted_type_key IN ({placeholders})""",
        (*encoded, *encoded),
    )
    data_keys = tuple(str(row[0]) for row in data_rows)
    participating = tuple(dict.fromkeys((*anchor_type_keys, *data_keys)))
    participant_placeholders = ",".join("?" for _ in participating)
    link_rows = connection.execute(
        f"""SELECT DISTINCT p.type_key FROM definition_permitted_type AS p
            WHERE p.valid_to_revision IS NULL AND p.role IN ('source', 'target')
              AND p.permitted_type_key IN ({participant_placeholders})
              AND NOT EXISTS (
                SELECT 1 FROM draft_definition_entry AS d WHERE d.type_key = p.type_key)
            UNION
            SELECT DISTINCT p.type_key FROM draft_definition_permitted_type AS p
            JOIN draft_definition_entry AS d USING (type_key)
            WHERE d.operation = 'replace' AND d.kind = 'link'
              AND p.role IN ('source', 'target')
              AND p.permitted_type_key IN ({participant_placeholders})""",
        (*participating, *participating),
    )
    return tuple(
        dict.fromkeys((*anchor_type_keys, *data_keys, *(str(row[0]) for row in link_rows)))
    )


def _neighborhood_legacy(value, include_legacy_system):
    if include_legacy_system:
        return value
    return DefinitionNeighborhood(
        _definition_without_legacy(value.anchor_type),
        tuple(_definition_without_legacy(item) for item in value.associated_data_types),
        tuple(_definition_without_legacy(item) for item in value.link_types),
    )


def _finding(code, path, summary, *, type_keys=(), uuids=()):
    return Finding(code, summary, path, type_keys, uuids)


def _ordered_findings(findings):
    return tuple(
        sorted(
            findings,
            key=lambda value: (
                value.code.value,
                value.path or "",
                value.type_keys,
                value.uuids,
                value.summary,
            ),
        )
    )


def _append_discovery_activity(
    connection, capability, result, request_payload, result_shape, initiator, source
):
    append_activity(
        connection,
        capability=capability,
        outcome=result.status.value,
        initiator=initiator,
        source=source,
        evaluated_revision=result.evaluated_revision,
        resulting_revision=None,
        summary=result.summary,
        semantic_payload={
            "request": request_payload,
            "resultShape": result_shape,
            "findings": wire_value(result.findings),
        },
        verbose_payload={"request": request_payload, "response": public_result(result)},
    )
