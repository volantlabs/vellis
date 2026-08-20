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
from vellis.query_domain import (
    PUBLIC_ITEM_LIMIT,
    DefinitionNeighborhood,
    GraphQuery,
    IdentityObjectSelection,
    IdentityQueryPayload,
    IdentitySelection,
    PatternQueryPayload,
    PatternSelection,
    QueryResult,
    TypeInspectionResult,
    TypeSummaryResult,
)
from vellis.query_repository import (
    HydrationRequest,
    hydration_requests_for_matches,
    load_hydrated_objects,
    load_object_headers,
    pattern_identity_findings,
    select_pattern_bindings,
)
from vellis.query_validation import query_findings
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
            _require_canonical_overlay(state.includes_draft)
            values = tuple(
                _definition_without_legacy(value)
                for value in load_anchor_summary(connection, state)
            )
            if len(values) > PUBLIC_ITEM_LIMIT:
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
            _require_canonical_overlay(state.includes_draft)
            selected = load_definitions(connection, state, anchor_type_keys)
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
                neighborhoods = load_neighborhoods(connection, state, anchor_type_keys)
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
            _require_canonical_overlay(state.includes_draft)
            definitions = load_definitions(connection, state, _referenced_type_keys(query))
            definitions = _query_definition_closure(connection, state, definitions, query.selection)
            findings = query_findings(query, definitions)
            if findings:
                result = _rejected_query(
                    "query meaning was rejected", findings, state.evaluated_revision
                )
            elif isinstance(query.selection, IdentitySelection):
                result = _identity_query(connection, state, query.selection, definitions)
            else:
                result = _pattern_query(connection, state, query.selection, definitions)
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


def _pattern_query(connection, state, selection: PatternSelection, definitions) -> QueryResult:
    requested = tuple(
        dict.fromkeys(
            uuid for selector in (*selection.nodes, *selection.links) for uuid in selector.uuids
        )
    )
    headers = load_object_headers(connection, state, requested)
    identity_findings = pattern_identity_findings(headers, selection)
    if identity_findings:
        return _rejected_query(
            "pattern identity filters were rejected", identity_findings, state.evaluated_revision
        )
    compatibility_selection = _selection_with_identity_types(selection, headers)
    compatibility_keys = _referenced_type_keys(GraphQuery(compatibility_selection)) or ()
    loaded = {value.type_key: value for value in definitions}
    missing = tuple(key for key in compatibility_keys if key not in loaded)
    if missing:
        loaded.update(
            (value.type_key, value) for value in load_definitions(connection, state, missing)
        )
    compatibility_definitions = _query_definition_closure(
        connection, state, tuple(loaded.values()), compatibility_selection
    )
    compatibility_findings = query_findings(
        GraphQuery(compatibility_selection), compatibility_definitions
    )
    if compatibility_findings:
        return _rejected_query(
            "pattern endpoints were rejected",
            compatibility_findings,
            state.evaluated_revision,
        )
    try:
        matches = select_pattern_bindings(connection, state, selection)
    except ValueError as error:
        finding = _finding(FindingCode.INVALID_VALUE, "/selection", str(error))
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
        definition = definitions[header.type_key]
        assert isinstance(definition, AssociatedDataTypeDefinition)
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
    if any(not link.type_keys for link in selection.links):
        missing_link_keys = tuple(
            key for key in _definition_keys(connection, state, "link") if key not in loaded
        )
        loaded.update(
            (value.type_key, value)
            for value in load_definitions(connection, state, missing_link_keys)
        )
    nodes = {value.name: value for value in selection.nodes}
    if any(
        (node := nodes.get(value.associated_data)) is not None and not node.type_keys
        for value in selection.direct_associations
    ):
        missing_data_keys = tuple(
            key
            for key in _definition_keys(connection, state, "associatedData")
            if key not in loaded
        )
        loaded.update(
            (value.type_key, value)
            for value in load_definitions(connection, state, missing_data_keys)
        )
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
            for value in load_definitions(connection, state, tuple(sorted(endpoint_keys)))
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
            for value in load_definitions(connection, state, tuple(sorted(anchor_keys)))
        )
    return tuple(loaded[key] for key in sorted(loaded))


def _definition_keys(connection, state, kind: str) -> tuple[str, ...]:
    rows = connection.execute(
        f"""
        SELECT type_key FROM definition_version AS v
        WHERE {interval_sql("v")} AND v.kind = ? ORDER BY type_key
        """,
        (*interval_parameters(state), kind),
    ).fetchall()
    return tuple(str(row["type_key"]) for row in rows)


def _selection_with_identity_types(selection: PatternSelection, headers) -> PatternSelection:
    nodes = tuple(
        replace(node, type_keys=_identity_type_keys(node.uuids, node.type_keys, headers))
        if node.uuids
        else node
        for node in selection.nodes
    )
    links = tuple(
        replace(link, type_keys=_identity_type_keys(link.uuids, link.type_keys, headers))
        if link.uuids
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


def _require_canonical_overlay(includes_draft: bool) -> None:
    if includes_draft:
        raise NotImplementedError("draft definition/query overlay is implemented in Phase 4")


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
) -> Finding:
    return Finding(code, summary, path, type_keys)


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
