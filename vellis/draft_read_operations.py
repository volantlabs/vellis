"""Draft-overlay query evaluation over the mechanically composed graph."""

from __future__ import annotations

import json
from typing import Any

import re2

from vellis.domain import (
    Anchor,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Finding,
    FindingCode,
    GraphObject,
    Link,
    LinkTypeDefinition,
    ObjectKind,
    OperationStatus,
    ScalarValue,
    SystemEnvelope,
    TimestampValue,
)
from vellis.pattern_repository import select_pattern_bindings
from vellis.query_domain import (
    DefinitionNeighborhood,
    GraphQuery,
    HydratedObject,
    IdentityQueryPayload,
    IdentitySelection,
    PatternQueryPayload,
    PredicateOperator,
    PropertyField,
    QueryResult,
)
from vellis.query_repository import (
    ObjectHeader,
    hydration_requests_for_matches,
    load_hydrated_objects,
    pattern_execution_finding,
)
from vellis.search_repository import structured_fts_expression
from vellis.sqlite_values import property_from_row


def draft_effective_headers(connection, selection, requested, headers):
    """Overlay only request-selected headers without materializing draft values."""
    staged, patches, live_uuids, conflicts = _overlay_selected_headers(
        connection, requested, headers
    )
    findings = []
    _header_findings(selection, patches, live_uuids, conflicts, findings)
    return headers, staged, tuple(sorted(findings, key=lambda value: value.sort_key()))


def draft_identity_headers(connection, requested, headers):
    """Overlay request-selected identity headers without loading object values."""
    _overlay_selected_headers(connection, requested, headers)
    return headers


def _overlay_selected_headers(connection, requested, headers):
    staged = set()
    live_uuids = frozenset(headers)
    rows = connection.execute(
        """SELECT uuid, kind, tombstone, has_type_key, type_key
           FROM main.draft_graph_object_patch
           WHERE uuid IN (SELECT value FROM json_each(?))""",
        (json.dumps(requested, separators=(",", ":")),),
    )
    patches = {str(row["uuid"]): row for row in rows}
    conflicts = set()
    for uuid, row in patches.items():
        if bool(row["tombstone"]):
            headers.pop(uuid, None)
            continue
        staged.add(uuid)
        actual_kind = ObjectKind(str(row["kind"]))
        live = headers.get(uuid)
        if live is not None and live.kind is not actual_kind:
            headers.pop(uuid)
            conflicts.add(uuid)
            continue
        if bool(row["has_type_key"]):
            headers[uuid] = ObjectHeader(uuid, actual_kind, str(row["type_key"]))
    return frozenset(staged), patches, live_uuids, frozenset(conflicts)


def _header_findings(selection, patches, live_uuids, conflicts, findings):
    selectors = (
        *((node, node.kind.value, index, "nodes") for index, node in enumerate(selection.nodes)),
        *((link, "link", index, "links") for index, link in enumerate(selection.links)),
    )
    for selector, expected_kind, index, category in selectors:
        for position, uuid in enumerate(selector.uuids):
            row = patches.get(uuid)
            if row is None or bool(row["tombstone"]):
                continue
            path = f"/selection/{category}/{index}/uuids/{position}"
            if uuid in conflicts:
                findings.append(
                    _finding(
                        FindingCode.KIND_MISMATCH,
                        path,
                        "draft object kind conflicts with the live object kind",
                        uuids=(uuid,),
                    )
                )
            elif _partial_kind_mismatch(row, uuid, expected_kind, live_uuids):
                findings.append(
                    _finding(
                        FindingCode.KIND_MISMATCH,
                        path,
                        "UUID identifies another object kind",
                        uuids=(uuid,),
                    )
                )


def _partial_kind_mismatch(row, uuid, expected_kind, live_uuids):
    return (
        uuid not in live_uuids
        and str(row["kind"]) != expected_kind
        and not bool(row["has_type_key"])
    )


def query_draft_identity(state, query: GraphQuery, graph, unmaterializable):
    """Hydrate one already-validated keyed draft identity request."""
    assert isinstance(query.selection, IdentitySelection)
    return _identity_query(state, query.selection, graph, unmaterializable)


def query_draft_pattern_sql(connection, state, selection):
    """Evaluate draft pattern bindings in SQL before bounded hydration."""
    try:
        if _unmaterializable_selector_match(connection, selection):
            finding = _finding(
                FindingCode.MISSING,
                "/selection/nodes",
                "staged partial object has no live base",
            )
            return _rejected(
                "draft object cannot be materialized", (finding,), state.evaluated_revision
            )
        matches = select_pattern_bindings(connection, state, selection)
    except ValueError as error:
        return _rejected(
            "pattern predicate was rejected",
            (pattern_execution_finding(error),),
            state.evaluated_revision,
        )
    if matches is None:
        finding = _finding(
            FindingCode.RESULT_LIMIT_EXCEEDED,
            "/selection/maximumMatches",
            "pattern has more matches than maximumMatches",
        )
        return _rejected("pattern result limit was exceeded", (finding,), state.evaluated_revision)
    objects = load_hydrated_objects(
        connection, state, hydration_requests_for_matches(selection, matches)
    )
    return QueryResult(
        OperationStatus.ACCEPTED,
        "pattern selected",
        (),
        state.evaluated_revision,
        PatternQueryPayload(matches, objects),
    )


def draft_neighborhoods(definitions, anchor_type_keys):
    """Build focused definition neighborhoods from the effective draft definitions."""
    by_key = {value.type_key: value for value in definitions}
    result = []
    for key in anchor_type_keys:
        data = tuple(
            value
            for value in definitions
            if isinstance(value, AssociatedDataTypeDefinition)
            and key in value.permitted_anchor_type_keys
        )
        participating = {key, *(value.type_key for value in data)}
        links = tuple(
            value
            for value in definitions
            if isinstance(value, LinkTypeDefinition)
            and participating.intersection(
                {*value.permitted_source_type_keys, *value.permitted_target_type_keys}
            )
        )
        result.append(DefinitionNeighborhood(by_key[key], data, links))
    return tuple(result)


def _identity_query(state, selection, graph, unmaterializable):
    requested = tuple(value.uuid for value in selection.objects)
    required = set(requested) & set(unmaterializable)
    if required:
        finding = _finding(
            FindingCode.MISSING,
            "/selection/objects",
            "staged partial object has no live base",
            uuids=tuple(required),
        )
        return _rejected(
            "draft object cannot be materialized", (finding,), state.evaluated_revision
        )
    by_uuid = {value.uuid: value for value in graph}
    found = tuple(uuid for uuid in requested if uuid in by_uuid)
    missing = tuple(uuid for uuid in requested if uuid not in by_uuid)
    objects = tuple(
        _hydrate(by_uuid[value.uuid], value) for value in selection.objects if value.uuid in by_uuid
    )
    return QueryResult(
        OperationStatus.ACCEPTED,
        "identities selected",
        (),
        state.evaluated_revision,
        IdentityQueryPayload(found, missing, objects),
    )


def _hydrate(value: GraphObject, selection) -> HydratedObject:
    properties = None
    if isinstance(value, AssociatedData) and selection.properties is not None:
        selected = dict(value.properties)
        properties = (
            tuple(sorted(selected.items()))
            if selection.properties.all
            else tuple(
                (name, selected[name]) for name in selection.properties.names if name in selected
            )
        )
    system = value.system
    if system is not None and not selection.include_legacy_system:
        system = SystemEnvelope(system.created_revision, system.last_changed_revision)
    return HydratedObject(
        value.uuid,
        value.kind,
        value.type_key,
        value.display_name if isinstance(value, Anchor) else None,
        value.anchor_uuids if isinstance(value, AssociatedData) else (),
        value.source_uuid if isinstance(value, Link) else None,
        value.target_uuid if isinstance(value, Link) else None,
        properties,
        system,
    )


def _unmaterializable_selector_match(connection, selection):
    rows = connection.execute(
        """SELECT p.* FROM main.draft_graph_object_patch AS p
           WHERE p.tombstone = 0 AND NOT EXISTS (
             SELECT 1 FROM temp.graph_object_version AS v WHERE v.uuid = p.uuid
           ) ORDER BY p.uuid"""
    )
    for row in rows:
        uuid, kind = str(row["uuid"]), str(row["kind"])
        selectors = (
            tuple(node for node in selection.nodes if node.kind.value == kind)
            if kind != "link"
            else selection.links
        )
        for selector in selectors:
            if selector.uuids and uuid not in selector.uuids:
                continue
            if (
                selector.type_keys
                and bool(row["has_type_key"])
                and str(row["type_key"]) not in selector.type_keys
            ):
                continue
            if hasattr(selector, "predicates") and any(
                _staged_predicate_result(connection, row, predicate) is False
                for predicate in selector.predicates
            ):
                continue
            return True
    return False


def _staged_predicate_result(connection, row, predicate):
    if isinstance(predicate.field, PropertyField):
        value_row = connection.execute(
            """SELECT * FROM draft_property_operation
               WHERE object_uuid = ? AND property_name = ?""",
            (row["uuid"], predicate.field.name),
        ).fetchone()
        if value_row is None:
            return None
        present = str(value_row["operation"]) == "set"
        content = property_from_row(value_row) if present else None
    else:
        if not bool(row["has_display_name"]):
            return None
        present, content = True, str(row["display_name"])
    return _known_predicate(connection, present, content, predicate)


def _known_predicate(connection, present, content, predicate):
    operator = predicate.operator
    if operator in {
        PredicateOperator.PRESENT,
        PredicateOperator.MISSING,
        PredicateOperator.IS_NULL,
        PredicateOperator.IS_NOT_NULL,
    }:
        return _known_presence(operator, present, content)
    if not present:
        return False
    if operator is PredicateOperator.ANY_OF:
        return _known_equality(operator, content, predicate)
    if content is None:
        return False
    if operator in {PredicateOperator.EQUAL, PredicateOperator.NOT_EQUAL}:
        return _known_equality(operator, content, predicate)
    actual: Any = _ordered_value(content)
    expected: Any = _ordered_value(predicate.value)
    if operator is PredicateOperator.LESS_THAN:
        return actual < expected
    if operator is PredicateOperator.LESS_THAN_OR_EQUAL:
        return actual <= expected
    if operator is PredicateOperator.GREATER_THAN:
        return actual > expected
    if operator is PredicateOperator.GREATER_THAN_OR_EQUAL:
        return actual >= expected
    assert isinstance(actual, str)
    return _known_text_predicate(connection, actual, predicate)


def _known_presence(operator, present, content):
    if operator is PredicateOperator.PRESENT:
        return present
    if operator is PredicateOperator.MISSING:
        return not present
    if operator is PredicateOperator.IS_NULL:
        return present and content is None
    return present and content is not None


def _known_equality(operator, content, predicate):
    actual = _ordered_value(content)
    if operator is PredicateOperator.ANY_OF:
        return actual in tuple(_ordered_value(value) for value in predicate.values)
    equal = actual == _ordered_value(predicate.value)
    return equal if operator is PredicateOperator.EQUAL else not equal


def _known_text_predicate(connection, actual, predicate):
    operator = predicate.operator
    if operator in {PredicateOperator.CONTAINS, PredicateOperator.PREFIX}:
        expected = predicate.text or ""
        if not predicate.case_sensitive:
            actual, expected = actual.casefold(), expected.casefold()
        return (
            expected in actual
            if operator is PredicateOperator.CONTAINS
            else actual.startswith(expected)
        )
    if operator is PredicateOperator.REGEX:
        prefix = "" if predicate.case_sensitive else "(?i)"
        return re2.search(prefix + (predicate.text or ""), actual) is not None
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS temp.draft_selector_fts "
        "USING fts5(content, tokenize='unicode61 remove_diacritics 2')"
    )
    connection.execute("DELETE FROM temp.draft_selector_fts")
    connection.execute("INSERT INTO temp.draft_selector_fts(content) VALUES (?)", (actual,))
    expression = structured_fts_expression(connection, predicate)
    return (
        connection.execute(
            "SELECT 1 FROM temp.draft_selector_fts WHERE content MATCH ?", (expression,)
        ).fetchone()
        is not None
    )


def _ordered_value(value):
    if isinstance(value, ScalarValue):
        if isinstance(value.value, TimestampValue):
            return value.value.epoch_seconds, value.value.nanosecond
        return value.value
    return value


def _rejected(summary, findings, revision):
    return QueryResult(OperationStatus.REJECTED, summary, tuple(findings), revision, None)


def _finding(code, path, summary, *, type_keys=(), uuids=()):
    return Finding(code, summary, path, tuple(sorted(type_keys)), tuple(sorted(uuids)))
