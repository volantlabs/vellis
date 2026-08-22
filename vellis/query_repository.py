"""Targeted hydration and flat parameterized SQL for bounded VEL2 queries."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from vellis.domain import (
    Finding,
    FindingCode,
    ObjectKind,
    ResolvedState,
    ScalarValue,
    SystemEnvelope,
    TimestampValue,
    ValueKind,
)
from vellis.query_domain import (
    DisplayNameField,
    HydratedObject,
    PatternMatch,
    PatternNodeKind,
    PatternSelection,
    Predicate,
    PredicateOperator,
    PropertySelection,
)
from vellis.search_repository import structured_fts_expression
from vellis.sqlite_values import property_from_row
from vellis.state_repository import interval_parameters, interval_sql

_CHUNK = 500


@dataclass(frozen=True, slots=True)
class HydrationRequest:
    uuid: str
    properties: PropertySelection | None
    include_legacy_system: bool


@dataclass(frozen=True, slots=True)
class ObjectHeader:
    uuid: str
    kind: ObjectKind
    type_key: str


def pattern_execution_finding(error: ValueError) -> Finding:
    return Finding(FindingCode.INVALID_VALUE, str(error), "/selection")


def load_object_headers(
    connection: sqlite3.Connection,
    state: ResolvedState,
    uuids: tuple[str, ...],
) -> dict[str, ObjectHeader]:
    headers: dict[str, ObjectHeader] = {}
    for chunk in _chunks(uuids):
        rows = connection.execute(
            f"""
            SELECT v.uuid, v.kind, v.type_key
            FROM graph_object_version AS v
            WHERE {interval_sql("v")}
              AND v.uuid IN (SELECT value FROM json_each(?))
            """,
            (*interval_parameters(state), _json_list(chunk)),
        ).fetchall()
        for row in rows:
            uuid = str(row["uuid"])
            headers[uuid] = ObjectHeader(uuid, ObjectKind(str(row["kind"])), str(row["type_key"]))
    return headers


def pattern_identity_findings(
    headers: dict[str, ObjectHeader],
    selection: PatternSelection,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for index, node in enumerate(selection.nodes):
        expected = (
            ObjectKind.ANCHOR if node.kind is PatternNodeKind.ANCHOR else ObjectKind.ASSOCIATED_DATA
        )
        _filter_identity_findings(
            node.uuids,
            expected,
            node.type_keys,
            headers,
            f"/selection/nodes/{index}/uuids",
            findings,
        )
    for index, link in enumerate(selection.links):
        _filter_identity_findings(
            link.uuids,
            ObjectKind.LINK,
            link.type_keys,
            headers,
            f"/selection/links/{index}/uuids",
            findings,
        )
    return _ordered_findings(findings)


def hydration_requests_for_matches(
    selection: PatternSelection, matches: tuple[PatternMatch, ...]
) -> tuple[HydrationRequest, ...]:
    selectors = {
        node.name: (node.properties, node.include_legacy_system) for node in selection.nodes
    }
    selectors.update({link.name: (None, link.include_legacy_system) for link in selection.links})
    collected: dict[str, tuple[PropertySelection | None, bool]] = {}
    for match in matches:
        for name, uuid in match.bindings:
            properties, include_legacy = selectors[name]
            prior = collected.get(uuid)
            if prior is None:
                collected[uuid] = properties, include_legacy
            else:
                collected[uuid] = (
                    _merge_properties(prior[0], properties),
                    prior[1] or include_legacy,
                )
    return tuple(
        HydrationRequest(uuid, properties, legacy)
        for uuid, (properties, legacy) in sorted(collected.items())
    )


def load_hydrated_objects(
    connection: sqlite3.Connection,
    state: ResolvedState,
    requests: tuple[HydrationRequest, ...],
) -> tuple[HydratedObject, ...]:
    if not requests:
        return ()
    by_uuid = {request.uuid: request for request in requests}
    rows = _load_structure_rows(connection, state, tuple(by_uuid))
    data_uuids = tuple(
        uuid for uuid, row in rows.items() if str(row["kind"]) == ObjectKind.ASSOCIATED_DATA.value
    )
    associations = _load_associations(connection, state, data_uuids)
    properties = _load_requested_properties(connection, state, by_uuid, rows)
    legacy = _load_legacy(
        connection, tuple(request.uuid for request in requests if request.include_legacy_system)
    )
    return tuple(
        _hydrate(rows[request.uuid], associations, properties, legacy)
        for request in requests
        if request.uuid in rows
    )


def compile_predicate(
    connection: sqlite3.Connection,
    state: ResolvedState,
    object_alias: str,
    predicate: Predicate,
) -> tuple[str, list[object]]:
    if isinstance(predicate.field, DisplayNameField):
        return _text_predicate_sql(connection, state, object_alias, None, predicate)
    name = predicate.field.name
    if predicate.operator is PredicateOperator.MISSING:
        return _property_presence_sql(state, object_alias, name, exists=False)
    if predicate.operator in {
        PredicateOperator.PRESENT,
        PredicateOperator.IS_NULL,
        PredicateOperator.IS_NOT_NULL,
    }:
        return _property_presence_sql(
            state, object_alias, name, exists=True, operator=predicate.operator
        )
    if predicate.operator in {
        PredicateOperator.CONTAINS,
        PredicateOperator.PREFIX,
        PredicateOperator.REGEX,
        PredicateOperator.ALL_TERMS,
        PredicateOperator.ANY_TERMS,
        PredicateOperator.PHRASE,
    }:
        return _text_predicate_sql(connection, state, object_alias, name, predicate)
    return _scalar_predicate_sql(state, object_alias, name, predicate)


def _property_presence_sql(
    state: ResolvedState,
    object_alias: str,
    name: str,
    *,
    exists: bool,
    operator: PredicateOperator | None = None,
) -> tuple[str, list[object]]:
    condition = ""
    if operator is PredicateOperator.IS_NULL:
        condition = " AND p.is_null = 1"
    elif operator is PredicateOperator.IS_NOT_NULL:
        condition = " AND p.is_null = 0"
    sql = (
        ("EXISTS" if exists else "NOT EXISTS")
        + " (SELECT 1 FROM property_version AS p "
        + f"WHERE p.object_uuid = {object_alias}.uuid AND p.property_name = ? "
        + f"AND {interval_sql('p')}{condition})"
    )
    return sql, [name, *interval_parameters(state)]


def _scalar_predicate_sql(
    state: ResolvedState,
    object_alias: str,
    name: str,
    predicate: Predicate,
) -> tuple[str, list[object]]:
    operands = (
        predicate.values if predicate.operator is PredicateOperator.ANY_OF else (predicate.value,)
    )
    if predicate.operator is PredicateOperator.ANY_OF:
        return _scalar_any_of_sql(state, object_alias, name, operands)
    clauses: list[str] = []
    parameters: list[object] = [name, *interval_parameters(state)]
    for operand in operands:
        if operand is None:
            clauses.append("p.is_null = 1")
            continue
        expression, values = _scalar_comparison(predicate.operator, operand)
        clauses.append(f"(p.is_null = 0 AND p.value_kind = ? AND {expression})")
        parameters.append(operand.kind.value)
        parameters.extend(values)
    sql = (
        "EXISTS (SELECT 1 FROM property_version AS p "
        f"WHERE p.object_uuid = {object_alias}.uuid AND p.property_name = ? "
        f"AND {interval_sql('p')} AND ({' OR '.join(clauses)}))"
    )
    return sql, parameters


def _scalar_any_of_sql(
    state: ResolvedState,
    object_alias: str,
    name: str,
    operands: tuple[ScalarValue | None, ...],
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    parameters: list[object] = [name, *interval_parameters(state)]
    if any(value is None for value in operands):
        clauses.append("p.is_null = 1")
    values = tuple(value for value in operands if value is not None)
    if values:
        kind = values[0].kind
        column = {
            ValueKind.BOOLEAN: "boolean_value",
            ValueKind.INTEGER: "integer_value",
            ValueKind.NUMBER: "number_value",
            ValueKind.TEXT: "text_value",
            ValueKind.DATE: "date_value",
            ValueKind.TIMESTAMP: "timestamp_text",
        }[kind]
        encoded = json.dumps(
            tuple(value.wire_value() for value in values),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        clauses.append(
            f"(p.is_null = 0 AND p.value_kind = ? "
            f"AND p.{column} IN (SELECT value FROM json_each(?)))"
        )
        parameters.extend((kind.value, encoded))
    sql = (
        "EXISTS (SELECT 1 FROM property_version AS p "
        f"WHERE p.object_uuid = {object_alias}.uuid AND p.property_name = ? "
        f"AND {interval_sql('p')} AND ({' OR '.join(clauses)}))"
    )
    return sql, parameters


def _scalar_comparison(operator: PredicateOperator, value: ScalarValue) -> tuple[str, list[object]]:
    sql_operator = {
        PredicateOperator.EQUAL: "=",
        PredicateOperator.NOT_EQUAL: "<>",
        PredicateOperator.LESS_THAN: "<",
        PredicateOperator.LESS_THAN_OR_EQUAL: "<=",
        PredicateOperator.GREATER_THAN: ">",
        PredicateOperator.GREATER_THAN_OR_EQUAL: ">=",
        PredicateOperator.ANY_OF: "=",
    }[operator]
    if value.kind is ValueKind.TIMESTAMP:
        timestamp = value.value
        assert isinstance(timestamp, TimestampValue)
        comparison = f"(p.timestamp_epoch_seconds, p.timestamp_nanosecond) {sql_operator} (?, ?)"
        return comparison, [timestamp.epoch_seconds, timestamp.nanosecond]
    column = {
        ValueKind.BOOLEAN: "boolean_value",
        ValueKind.INTEGER: "integer_value",
        ValueKind.NUMBER: "number_value",
        ValueKind.TEXT: "text_value",
        ValueKind.DATE: "date_value",
    }[value.kind]
    return f"p.{column} {sql_operator} ?", [value.wire_value()]


def _text_predicate_sql(
    connection: sqlite3.Connection,
    state: ResolvedState,
    object_alias: str,
    property_name: str | None,
    predicate: Predicate,
) -> tuple[str, list[object]]:
    operator = predicate.operator
    field = "displayName" if property_name is None else property_name
    if operator in {
        PredicateOperator.ALL_TERMS,
        PredicateOperator.ANY_TERMS,
        PredicateOperator.PHRASE,
    }:
        expression = structured_fts_expression(connection, predicate)
        sql = (
            "EXISTS (SELECT 1 FROM search_document AS d JOIN search_fts "
            "ON search_fts.rowid = d.document_id "
            f"WHERE d.object_uuid = {object_alias}.uuid AND d.field_name = ? "
            f"AND {interval_sql('d')} AND search_fts MATCH ?)"
        )
        return sql, [field, *interval_parameters(state), expression]
    column = f"{object_alias}.display_name" if property_name is None else "p.text_value"
    if operator in {
        PredicateOperator.EQUAL,
        PredicateOperator.NOT_EQUAL,
        PredicateOperator.LESS_THAN,
        PredicateOperator.LESS_THAN_OR_EQUAL,
        PredicateOperator.GREATER_THAN,
        PredicateOperator.GREATER_THAN_OR_EQUAL,
    }:
        symbol = {
            PredicateOperator.EQUAL: "=",
            PredicateOperator.NOT_EQUAL: "<>",
            PredicateOperator.LESS_THAN: "<",
            PredicateOperator.LESS_THAN_OR_EQUAL: "<=",
            PredicateOperator.GREATER_THAN: ">",
            PredicateOperator.GREATER_THAN_OR_EQUAL: ">=",
        }[operator]
        comparison = f"{column} {symbol} ?"
        values: list[object] = [predicate.value.wire_value()]  # type: ignore[union-attr]
    elif operator is PredicateOperator.ANY_OF and property_name is not None:
        return _scalar_predicate_sql(state, object_alias, property_name, predicate)
    elif operator is PredicateOperator.ANY_OF:
        encoded = json.dumps(
            tuple(value.wire_value() for value in predicate.values if value is not None),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        comparison = f"{column} IN (SELECT value FROM json_each(?))"
        values = [encoded]
    elif operator is PredicateOperator.CONTAINS:
        function = "instr" if predicate.case_sensitive else "vellis_casefold_contains"
        comparison = f"{function}({column}, ?) > 0"
        values = [predicate.text]
    elif operator is PredicateOperator.PREFIX:
        if predicate.case_sensitive:
            comparison = f"substr({column}, 1, length(?)) = ?"
            values = [predicate.text, predicate.text]
        else:
            comparison = f"vellis_casefold_prefix({column}, ?) = 1"
            values = [predicate.text]
    else:
        comparison = f"vellis_re2_search({column}, ?, ?) = 1"
        values = [predicate.text, int(predicate.case_sensitive)]
    if property_name is None:
        return comparison, values
    sql = (
        "EXISTS (SELECT 1 FROM property_version AS p "
        f"WHERE p.object_uuid = {object_alias}.uuid AND p.property_name = ? "
        f"AND {interval_sql('p')} AND p.is_null = 0 AND p.value_kind = 'text' "
        f"AND {comparison})"
    )
    return sql, [property_name, *interval_parameters(state), *values]


def _load_structure_rows(
    connection: sqlite3.Connection,
    state: ResolvedState,
    uuids: tuple[str, ...],
) -> dict[str, sqlite3.Row]:
    collected: dict[str, sqlite3.Row] = {}
    for chunk in _chunks(uuids):
        rows = connection.execute(
            f"""
            SELECT v.*, i.created_revision
            FROM graph_object_version AS v
            JOIN graph_object_identity AS i USING (uuid)
            WHERE {interval_sql("v")} AND v.uuid IN (SELECT value FROM json_each(?))
            """,
            (*interval_parameters(state), _json_list(chunk)),
        ).fetchall()
        collected.update((str(row["uuid"]), row) for row in rows)
    return collected


def _load_associations(
    connection: sqlite3.Connection,
    state: ResolvedState,
    uuids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    collected: dict[str, list[str]] = defaultdict(list)
    for chunk in _chunks(uuids):
        rows = connection.execute(
            f"""
            SELECT object_uuid, anchor_uuid FROM direct_association_version AS a
            WHERE {interval_sql("a")} AND object_uuid IN (SELECT value FROM json_each(?))
            ORDER BY object_uuid, anchor_uuid
            """,
            (*interval_parameters(state), _json_list(chunk)),
        ).fetchall()
        for row in rows:
            collected[str(row["object_uuid"])].append(str(row["anchor_uuid"]))
    return {uuid: tuple(values) for uuid, values in collected.items()}


def _load_requested_properties(
    connection: sqlite3.Connection,
    state: ResolvedState,
    requests: dict[str, HydrationRequest],
    rows: dict[str, sqlite3.Row],
) -> dict[str, tuple[tuple[str, ScalarValue | None], ...]]:
    groups: dict[tuple[str, ...] | None, list[str]] = defaultdict(list)
    collected: dict[str, list[tuple[str, ScalarValue | None]]] = defaultdict(list)
    for uuid, request in requests.items():
        if uuid not in rows or request.properties is None:
            continue
        collected[uuid]
        key = None if request.properties.all else tuple(sorted(request.properties.names))
        groups[key].append(uuid)
    for names, uuids in groups.items():
        for chunk in _chunks(tuple(uuids)):
            conditions = [interval_sql("p"), "p.object_uuid IN (SELECT value FROM json_each(?))"]
            parameters: list[object] = [*interval_parameters(state), _json_list(chunk)]
            if names is not None:
                conditions.append("p.property_name IN (SELECT value FROM json_each(?))")
                parameters.append(_json_list(names))
            rows_found = connection.execute(
                f"SELECT * FROM property_version AS p WHERE {' AND '.join(conditions)} "
                "ORDER BY object_uuid, property_name",
                parameters,
            ).fetchall()
            for row in rows_found:
                collected[str(row["object_uuid"])].append(
                    (str(row["property_name"]), property_from_row(row))
                )
    return {uuid: tuple(values) for uuid, values in collected.items()}


def _load_legacy(connection: sqlite3.Connection, uuids: tuple[str, ...]) -> dict[str, str | None]:
    collected: dict[str, str | None] = {}
    for chunk in _chunks(uuids):
        rows = connection.execute(
            "SELECT uuid, legacy_v1 FROM graph_object_identity "
            "WHERE uuid IN (SELECT value FROM json_each(?))",
            (_json_list(chunk),),
        ).fetchall()
        for row in rows:
            collected[str(row["uuid"])] = (
                None if row["legacy_v1"] is None else str(row["legacy_v1"])
            )
    return collected


def _hydrate(
    row: sqlite3.Row,
    associations: dict[str, tuple[str, ...]],
    properties: dict[str, tuple[tuple[str, ScalarValue | None], ...]],
    legacy: dict[str, str | None],
) -> HydratedObject:
    uuid = str(row["uuid"])
    kind = ObjectKind(str(row["kind"]))
    return HydratedObject(
        uuid,
        kind,
        str(row["type_key"]),
        str(row["display_name"]) if kind is ObjectKind.ANCHOR else None,
        associations.get(uuid, ()) if kind is ObjectKind.ASSOCIATED_DATA else (),
        str(row["source_uuid"]) if kind is ObjectKind.LINK else None,
        str(row["target_uuid"]) if kind is ObjectKind.LINK else None,
        properties.get(uuid) if kind is ObjectKind.ASSOCIATED_DATA and uuid in properties else None,
        None
        if row["created_revision"] is None
        else SystemEnvelope(
            int(row["created_revision"]),
            int(row["last_changed_revision"]),
            legacy.get(uuid),
        ),
    )


def _filter_identity_findings(
    uuids: tuple[str, ...],
    expected_kind: ObjectKind,
    type_keys: tuple[str, ...],
    headers: dict[str, ObjectHeader],
    path: str,
    findings: list[Finding],
) -> None:
    for index, uuid in enumerate(uuids):
        header = headers.get(uuid)
        if header is None:
            findings.append(
                Finding(
                    FindingCode.UNKNOWN,
                    "UUID is absent from selected state",
                    f"{path}/{index}",
                    uuids=(uuid,),
                )
            )
        elif header.kind is not expected_kind:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "UUID has another object kind",
                    f"{path}/{index}",
                    uuids=(uuid,),
                )
            )
        elif type_keys and header.type_key not in type_keys:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "UUID type does not pass the intersected type filter",
                    f"{path}/{index}",
                    type_keys=(header.type_key,),
                    uuids=(uuid,),
                )
            )


def _merge_properties(
    left: PropertySelection | None, right: PropertySelection | None
) -> PropertySelection | None:
    if left is None:
        return right
    if right is None:
        return left
    if left.all or right.all:
        return PropertySelection(all=True)
    return PropertySelection(tuple(sorted({*left.names, *right.names})))


def _json_filter(
    conditions: list[str], parameters: list[object], column: str, values: tuple[str, ...]
) -> None:
    if values:
        conditions.append(f"{column} IN (SELECT value FROM json_each(?))")
        parameters.append(_json_list(values))


def _json_list(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _chunks(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(values[index : index + _CHUNK] for index in range(0, len(values), _CHUNK))


def _ordered_findings(values: list[Finding]) -> tuple[Finding, ...]:
    return tuple(
        sorted(
            values,
            key=lambda value: (
                value.code.value,
                value.path or "",
                value.type_keys,
                value.uuids,
                value.summary,
            ),
        )
    )
