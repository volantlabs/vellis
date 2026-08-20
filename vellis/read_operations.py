"""Explicit connection-owning discovery and query operations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import load_definitions
from vellis.discovery_repository import load_anchor_summary, load_neighborhoods
from vellis.domain import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    Finding,
    FindingCode,
    LinkTypeDefinition,
    ObjectKind,
    OperationStatus,
    StateSelection,
    SystemEnvelope,
    TypeDefinition,
)
from vellis.draft_read_operations import (
    draft_effective_headers,
    draft_identity_headers,
    draft_neighborhoods,
    query_draft_identity,
    query_draft_pattern_sql,
)
from vellis.draft_repository import load_draft_definitions, load_draft_graph
from vellis.draft_sql_overlay import install_draft_graph_overlay
from vellis.graph_repository import load_graph_objects
from vellis.query_domain import (
    PUBLIC_ITEM_LIMIT,
    DefinitionNeighborhood,
    GraphQuery,
    IdentityObjectSelection,
    IdentityQueryPayload,
    IdentitySelection,
    PatternQueryPayload,
    PatternSelection,
    PredicateOperator,
    QueryResult,
    TypeInspectionResult,
    TypeSummaryResult,
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


def type_summary(
    database_path: Path, state_selection: StateSelection | None = None
) -> TypeSummaryResult:
    connection = connect_database(database_path, read_only=True)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN")
        try:
            state = resolve_state(connection, state_selection)
            over_limit = False
            if state.includes_draft:
                over_limit = _draft_anchor_type_count(connection) > PUBLIC_ITEM_LIMIT
                if over_limit:
                    values = ()
                else:
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
            else:
                values = tuple(
                    _definition_without_legacy(value)
                    for value in load_anchor_summary(connection, state, PUBLIC_ITEM_LIMIT + 1)
                )
            if over_limit or len(values) > PUBLIC_ITEM_LIMIT:
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
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def type_inspect(
    database_path: Path,
    anchor_type_keys: tuple[str, ...],
    *,
    state_selection: StateSelection | None = None,
    include_legacy_system: bool = False,
) -> TypeInspectionResult:
    request_findings = _inspection_request_findings(anchor_type_keys, include_legacy_system)
    if request_findings:
        return TypeInspectionResult(
            OperationStatus.REJECTED,
            "definition inspection was rejected",
            request_findings,
            None,
            None,
        )
    connection = connect_database(database_path, read_only=True)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN")
        try:
            state = resolve_state(connection, state_selection)
            if state.includes_draft:
                keys = _draft_neighborhood_type_keys(connection, anchor_type_keys)
                definitions = load_draft_definitions(
                    connection, load_definitions(connection, state, keys), keys
                )
            else:
                definitions = load_definitions(connection, state, anchor_type_keys)
            selected = tuple(value for value in definitions if value.type_key in anchor_type_keys)
            unknown = _unknown_anchor_findings(anchor_type_keys, selected)
            if unknown:
                result = TypeInspectionResult(
                    OperationStatus.REJECTED,
                    "definition inspection was rejected",
                    unknown,
                    state.evaluated_revision,
                    None,
                )
            else:
                neighborhoods = (
                    draft_neighborhoods(definitions, anchor_type_keys)
                    if state.includes_draft
                    else load_neighborhoods(connection, state, anchor_type_keys)
                )
                projected = tuple(
                    _neighborhood_legacy(value, include_legacy_system) for value in neighborhoods
                )
                result = TypeInspectionResult(
                    OperationStatus.ACCEPTED,
                    "definition neighborhoods selected",
                    (),
                    state.evaluated_revision,
                    projected,
                )
        except StateNotFoundError as error:
            result = TypeInspectionResult(
                OperationStatus.REJECTED,
                "state was not found",
                (_finding(FindingCode.MISSING, "/state", str(error)),),
                None,
                None,
            )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def query_graph(database_path: Path, query: GraphQuery) -> QueryResult:
    connection = connect_database(database_path, read_only=True)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN")
        try:
            state = resolve_state(connection, query.state)
            if state.includes_draft:
                result = _draft_query(connection, state, query)
                connection.commit()
                return result
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


def _inspection_request_findings(
    anchor_type_keys: tuple[str, ...], include_legacy_system: bool
) -> tuple[Finding, ...]:
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


def _unknown_anchor_findings(
    requested: tuple[str, ...], selected: tuple[TypeDefinition, ...]
) -> tuple[Finding, ...]:
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
    ).fetchall()
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
    ).fetchall()
    return tuple(
        dict.fromkeys((*anchor_type_keys, *data_keys, *(str(row[0]) for row in link_rows)))
    )


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


def _neighborhood_legacy(
    value: DefinitionNeighborhood, include_legacy_system: bool
) -> DefinitionNeighborhood:
    if include_legacy_system:
        return value
    return DefinitionNeighborhood(
        _definition_without_legacy(value.anchor_type),
        tuple(_definition_without_legacy(item) for item in value.associated_data_types),
        tuple(_definition_without_legacy(item) for item in value.link_types),
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
