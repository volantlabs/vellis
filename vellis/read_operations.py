"""Explicit connection-owning discovery and query operations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vellis.activity_repository import append_activity
from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import load_definitions
from vellis.domain import (
    AssociatedDataTypeDefinition,
    Finding,
    FindingCode,
    LinkTypeDefinition,
    ObjectKind,
    OperationStatus,
    TypeDefinition,
)
from vellis.draft_read_operations import (
    draft_effective_headers,
    draft_identity_headers,
    query_draft_identity,
    query_draft_pattern_sql,
)
from vellis.draft_repository import load_draft_definitions, load_draft_graph
from vellis.draft_sql_overlay import install_draft_graph_overlay
from vellis.graph_repository import load_graph_objects
from vellis.query_domain import (
    GraphQuery,
    IdentityObjectSelection,
    IdentityQueryPayload,
    IdentitySelection,
    PatternQueryPayload,
    PatternSelection,
    PredicateOperator,
    QueryResult,
)
from vellis.query_repository import (
    HydrationRequest,
    hydration_requests_for_matches,
    load_hydrated_objects,
    load_object_headers,
    pattern_execution_finding,
    pattern_identity_findings,
    select_pattern_bindings,
)
from vellis.query_validation import (
    query_findings,
    relationship_compatibility_findings,
    structured_predicate_findings,
)
from vellis.state_repository import (
    StateNotFoundError,
    interval_parameters,
    interval_sql,
    resolve_state,
)
from vellis.wire import serialize_wire, wire_value


def query_graph(
    database_path: Path,
    query: GraphQuery,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> QueryResult:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            state = resolve_state(connection, query.state)
            if state.includes_draft:
                result = _draft_query(connection, state, query)
            else:
                definitions = load_definitions(connection, state, _referenced_type_keys(query))
                if isinstance(query.selection, PatternSelection):
                    result = _pattern_query(connection, state, query.selection, definitions)
                else:
                    findings = query_findings(query, definitions)
                    result = (
                        _rejected_query(
                            "query meaning was rejected", findings, state.evaluated_revision
                        )
                        if findings
                        else _identity_query(connection, state, query.selection, definitions)
                    )
        except StateNotFoundError as error:
            result = _rejected_query(
                "state was not found", (_finding(FindingCode.MISSING, "/state", str(error)),), None
            )
        serialize_wire(result)
        shape = _query_activity_shape(result)
        _append_read_activity(
            connection,
            "rtg_query",
            result,
            {"query": wire_value(query)},
            shape,
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


def _identity_query(connection, state, selection: IdentitySelection, definitions) -> QueryResult:
    requested = tuple(value.uuid for value in selection.objects)
    headers = load_object_headers(connection, state, requested)
    found = tuple(uuid for uuid in requested if uuid in headers)
    missing = tuple(uuid for uuid in requested if uuid not in headers)
    needed_type_keys = tuple(
        sorted(
            {
                headers[value.uuid].type_key
                for value in selection.objects
                if value.uuid in headers and value.properties is not None
            }
        )
    )
    loaded = {value.type_key: value for value in definitions}
    if any(key not in loaded for key in needed_type_keys):
        for definition in load_definitions(connection, state, needed_type_keys):
            loaded[definition.type_key] = definition
    findings = _identity_property_findings(selection.objects, headers, loaded)
    if findings:
        return _rejected_query(
            "identity hydration was rejected", findings, state.evaluated_revision
        )
    requests = tuple(
        HydrationRequest(value.uuid, value.properties, value.include_legacy_system)
        for value in selection.objects
        if value.uuid in headers
    )
    objects = load_hydrated_objects(connection, state, requests)
    payload = IdentityQueryPayload(found, missing, objects)
    return QueryResult(
        OperationStatus.ACCEPTED, "identities selected", (), state.evaluated_revision, payload
    )


def _draft_query(connection, state, query: GraphQuery) -> QueryResult:
    if isinstance(query.selection, IdentitySelection):
        request_findings = query_findings(query, ())
        if request_findings:
            return _rejected_query(
                "query meaning was rejected", request_findings, state.evaluated_revision
            )
        uuids = tuple(value.uuid for value in query.selection.objects)
        headers = draft_identity_headers(
            connection, uuids, load_object_headers(connection, state, uuids)
        )
        type_keys = tuple(sorted({value.type_key for value in headers.values()}))
        definitions = load_draft_definitions(
            connection, load_definitions(connection, state, type_keys), type_keys
        )
        property_findings = _identity_property_findings(
            query.selection.objects,
            headers,
            {value.type_key: value for value in definitions},
        )
        if property_findings:
            return _rejected_query(
                "identity hydration was rejected",
                property_findings,
                state.evaluated_revision,
            )
        current = load_graph_objects(connection, state, uuids)
        graph, unmaterializable = load_draft_graph(connection, current, uuids)
    else:
        headers, staged_partial_uuids, header_findings = _pattern_headers(
            connection, state, query.selection
        )
        definition_keys = _draft_pattern_definition_keys(query, headers)
        definitions = load_draft_definitions(
            connection,
            load_definitions(connection, state, definition_keys),
            definition_keys,
        )
        findings = _pattern_preflight(
            connection,
            state,
            query.selection,
            definitions,
            headers=headers,
            staged_partial_uuids=staged_partial_uuids,
            header_findings=header_findings,
        )
        if findings:
            return _rejected_query(
                "pattern preflight was rejected", findings, state.evaluated_revision
            )
        install_draft_graph_overlay(connection, search_scopes=_full_text_scopes(query.selection))
        return query_draft_pattern_sql(connection, state, query.selection)
    return query_draft_identity(state, query, graph, unmaterializable)


def _pattern_query(connection, state, selection: PatternSelection, definitions) -> QueryResult:
    findings = _pattern_preflight(connection, state, selection, definitions)
    if findings:
        return _rejected_query("pattern preflight was rejected", findings, state.evaluated_revision)
    try:
        matches = select_pattern_bindings(connection, state, selection)
    except ValueError as error:
        finding = pattern_execution_finding(error)
        return _rejected_query(
            "pattern predicate was rejected", (finding,), state.evaluated_revision
        )
    if matches is None:
        finding = _finding(
            FindingCode.RESULT_LIMIT_EXCEEDED,
            "/selection/maximumMatches",
            "pattern has more matches than maximumMatches",
        )
        return _rejected_query(
            "pattern result limit was exceeded", (finding,), state.evaluated_revision
        )
    requests = hydration_requests_for_matches(selection, matches)
    objects = load_hydrated_objects(connection, state, requests)
    payload = PatternQueryPayload(matches, objects)
    return QueryResult(
        OperationStatus.ACCEPTED, "pattern selected", (), state.evaluated_revision, payload
    )


def _pattern_preflight(
    connection,
    state,
    selection,
    definitions,
    *,
    headers=None,
    staged_partial_uuids=frozenset(),
    header_findings=(),
):
    if headers is None:
        headers, staged_partial_uuids, header_findings = _pattern_headers(
            connection, state, selection
        )
    request_findings = query_findings(
        GraphQuery(selection),
        definitions,
        include_relationship_compatibility=False,
    )
    if request_findings:
        return request_findings
    runtime_findings = structured_predicate_findings(connection, selection)
    if runtime_findings:
        return runtime_findings
    identity_findings = pattern_identity_findings(headers, selection)
    identity_findings = tuple(
        finding
        for finding in identity_findings
        if not (
            finding.code is FindingCode.UNKNOWN and staged_partial_uuids.intersection(finding.uuids)
        )
    )
    identity_findings = _ordered_findings([*header_findings, *identity_findings])
    if identity_findings:
        return identity_findings
    compatibility_selection = _selection_with_identity_types(selection, headers)
    compatibility_keys = _referenced_type_keys(GraphQuery(compatibility_selection)) or ()
    loaded = {value.type_key: value for value in definitions}
    missing = tuple(key for key in compatibility_keys if key not in loaded)
    if missing:
        loaded.update(
            (value.type_key, value)
            for value in _load_effective_definitions(connection, state, missing)
        )
    compatibility_definitions = _query_definition_closure(
        connection, state, tuple(loaded.values()), compatibility_selection
    )
    return relationship_compatibility_findings(compatibility_selection, compatibility_definitions)


def _pattern_headers(connection, state, selection):
    requested = tuple(
        dict.fromkeys(
            uuid for selector in (*selection.nodes, *selection.links) for uuid in selector.uuids
        )
    )
    headers = load_object_headers(connection, state, requested)
    if not state.includes_draft:
        return headers, frozenset(), ()
    return draft_effective_headers(connection, selection, requested, headers)


def _load_effective_definitions(connection, state, keys):
    current = load_definitions(connection, state, keys)
    return load_draft_definitions(connection, current, keys) if state.includes_draft else current


def _identity_property_findings(
    selections: tuple[IdentityObjectSelection, ...],
    headers,
    definitions: dict[str, TypeDefinition],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for index, selection in enumerate(selections):
        if selection.properties is None or selection.uuid not in headers:
            continue
        header = headers[selection.uuid]
        path = f"/selection/objects/{index}/properties"
        if header.kind is not ObjectKind.ASSOCIATED_DATA:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH, path, "only associated-data objects have properties"
                )
            )
            continue
        definition = definitions.get(header.type_key)
        if not isinstance(definition, AssociatedDataTypeDefinition):
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    path,
                    "object type is unavailable in the selected state",
                    type_keys=(header.type_key,),
                )
            )
            continue
        known = {value.name for value in definition.properties}
        for position, name in enumerate(selection.properties.names):
            if name not in known:
                findings.append(
                    _finding(
                        FindingCode.UNKNOWN,
                        f"{path}/{position}",
                        "unknown property",
                        type_keys=(header.type_key,),
                    )
                )
    return _ordered_findings(findings)


def _referenced_type_keys(query: GraphQuery) -> tuple[str, ...] | None:
    if isinstance(query.selection, IdentitySelection):
        return ()
    return tuple(
        sorted(
            {
                key
                for selector in (*query.selection.nodes, *query.selection.links)
                for key in selector.type_keys
            }
        )
    )


def _query_definition_closure(
    connection, state, definitions, selection
) -> tuple[TypeDefinition, ...]:
    loaded = {value.type_key: value for value in definitions}
    if not isinstance(selection, PatternSelection):
        return tuple(loaded[key] for key in sorted(loaded))
    for value in _relationship_witnesses(connection, state, selection):
        loaded[value.type_key] = value
    endpoint_keys = {
        key
        for value in loaded.values()
        if isinstance(value, LinkTypeDefinition)
        for key in (*value.permitted_source_type_keys, *value.permitted_target_type_keys)
        if key not in loaded
    }
    if endpoint_keys:
        loaded.update(
            (value.type_key, value)
            for value in _load_effective_definitions(
                connection, state, tuple(sorted(endpoint_keys))
            )
        )
    anchor_keys = {
        key
        for value in loaded.values()
        if isinstance(value, AssociatedDataTypeDefinition)
        for key in value.permitted_anchor_type_keys
        if key not in loaded
    }
    if anchor_keys:
        loaded.update(
            (value.type_key, value)
            for value in _load_effective_definitions(connection, state, tuple(sorted(anchor_keys)))
        )
    return tuple(loaded[key] for key in sorted(loaded))


def _relationship_witnesses(connection, state, selection):
    nodes = {value.name: value for value in selection.nodes}
    for link in selection.links:
        if link.type_keys:
            continue
        source = nodes.get(link.source)
        target = nodes.get(link.target)
        source_keys = () if source is None else source.type_keys
        target_keys = () if target is None else target.type_keys
        if source_keys and target_keys:
            source_set, target_set = set(source_keys), set(target_keys)
            witness = _definition_witness(
                connection,
                state,
                "link",
                lambda value, source_set=source_set, target_set=target_set: (
                    isinstance(value, LinkTypeDefinition)
                    and bool(source_set.intersection(value.permitted_source_type_keys))
                    and bool(target_set.intersection(value.permitted_target_type_keys))
                ),
            )
            if witness is not None:
                yield witness
    for association in selection.direct_associations:
        anchor = nodes.get(association.anchor)
        data = nodes.get(association.associated_data)
        anchor_keys = () if anchor is None else anchor.type_keys
        if anchor_keys and data is not None and not data.type_keys:
            anchor_set = set(anchor_keys)
            witness = _definition_witness(
                connection,
                state,
                "associatedData",
                lambda value, anchor_set=anchor_set: (
                    isinstance(value, AssociatedDataTypeDefinition)
                    and bool(anchor_set.intersection(value.permitted_anchor_type_keys))
                ),
            )
            if witness is not None:
                yield witness


def _definition_witness(connection, state, kind, compatible):
    first = None
    parameters = interval_parameters(state)
    rows = connection.execute(
        f"""SELECT v.type_key FROM definition_version AS v
            WHERE {interval_sql("v")} AND v.kind = ? ORDER BY v.type_key""",
        (*parameters, kind),
    )
    for row in rows:
        key = str(row[0])
        current = load_definitions(connection, state, (key,))
        values = (
            load_draft_definitions(connection, current, (key,)) if state.includes_draft else current
        )
        if not values:
            continue
        value = values[0]
        first = value if first is None else first
        if compatible(value):
            return value
    if state.includes_draft:
        for row in connection.execute(
            """SELECT type_key FROM draft_definition_entry
               WHERE operation = 'replace' AND kind = ? ORDER BY type_key""",
            (kind,),
        ):
            key = str(row[0])
            values = load_draft_definitions(connection, (), (key,))
            if not values:
                continue
            value = values[0]
            first = value if first is None else first
            if compatible(value):
                return value
    return first


def _selection_with_identity_types(selection: PatternSelection, headers) -> PatternSelection:
    nodes = tuple(
        replace(node, type_keys=_identity_type_keys(node.uuids, node.type_keys, headers))
        if node.uuids and all(uuid in headers for uuid in node.uuids)
        else node
        for node in selection.nodes
    )
    links = tuple(
        replace(link, type_keys=_identity_type_keys(link.uuids, link.type_keys, headers))
        if link.uuids and all(uuid in headers for uuid in link.uuids)
        else link
        for link in selection.links
    )
    return replace(selection, nodes=nodes, links=links)


def _identity_type_keys(uuids, selected, headers) -> tuple[str, ...]:
    actual = {headers[uuid].type_key for uuid in uuids}
    if selected:
        actual.intersection_update(selected)
    return tuple(sorted(actual))


def _draft_pattern_definition_keys(query, headers):
    selection = query.selection
    keys = {value.type_key for value in headers.values()}
    for selector in (*selection.nodes, *selection.links):
        keys.update(selector.type_keys)
    return tuple(sorted(keys))


def _full_text_scopes(selection):
    operators = {
        PredicateOperator.ALL_TERMS,
        PredicateOperator.ANY_TERMS,
        PredicateOperator.PHRASE,
    }
    return tuple(
        (
            node.kind.value,
            node.type_keys,
            node.uuids,
            "displayName" if predicate.field.kind == "displayName" else predicate.field.name,
        )
        for node in selection.nodes
        for predicate in node.predicates
        if predicate.operator in operators
    )


def _rejected_query(
    summary: str, findings: tuple[Finding, ...], revision: int | None
) -> QueryResult:
    return QueryResult(OperationStatus.REJECTED, summary, findings, revision, None)


def _finding(
    code: FindingCode,
    path: str,
    summary: str,
    *,
    type_keys: tuple[str, ...] = (),
    uuids: tuple[str, ...] = (),
) -> Finding:
    return Finding(code, summary, path, type_keys, uuids)


def _ordered_findings(findings: list[Finding]) -> tuple[Finding, ...]:
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


def _append_read_activity(
    connection,
    capability,
    result,
    request_payload,
    result_shape,
    initiator,
    source,
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
        verbose_payload={"request": request_payload, "response": wire_value(result)},
    )


def _query_activity_shape(result):
    payload = result.payload
    if payload is None:
        return {"bindingCount": 0, "objectCount": 0, "bindings": []}
    if isinstance(payload, IdentityQueryPayload):
        bindings = [{"uuid": value} for value in payload.found_uuids[:100]]
        return {
            "bindingCount": len(payload.found_uuids),
            "missingCount": len(payload.missing_uuids),
            "objectCount": len(payload.objects),
            "bindings": bindings,
        }
    return {
        "bindingCount": len(payload.matches),
        "objectCount": len(payload.objects),
        "bindings": [wire_value(value.bindings) for value in payload.matches[:100]],
    }
