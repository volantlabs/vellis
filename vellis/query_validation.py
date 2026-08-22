"""Pure semantic validation for the deliberately flat VEL2 query boundary."""

from __future__ import annotations

import re2

from vellis.domain import (
    PUBLIC_ITEM_LIMIT,
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    Finding,
    FindingCode,
    LinkTypeDefinition,
    ScalarValue,
    TypeDefinition,
    ValueKind,
    canonical_number_text,
)
from vellis.query_domain import (
    DirectAssociation,
    DisplayNameField,
    GraphQuery,
    IdentitySelection,
    PatternLink,
    PatternNode,
    PatternNodeKind,
    PatternSelection,
    Predicate,
    PredicateOperator,
    PropertyField,
    PropertySelection,
)
from vellis.search_repository import structured_fts_expression

_NO_PAYLOAD = {
    PredicateOperator.PRESENT,
    PredicateOperator.MISSING,
    PredicateOperator.IS_NULL,
    PredicateOperator.IS_NOT_NULL,
}
_ORDER = {
    PredicateOperator.LESS_THAN,
    PredicateOperator.LESS_THAN_OR_EQUAL,
    PredicateOperator.GREATER_THAN,
    PredicateOperator.GREATER_THAN_OR_EQUAL,
}
_TEXT = {PredicateOperator.CONTAINS, PredicateOperator.PREFIX, PredicateOperator.REGEX}
_TERMS = {PredicateOperator.ALL_TERMS, PredicateOperator.ANY_TERMS}
_ORDERABLE = {
    ValueKind.INTEGER,
    ValueKind.NUMBER,
    ValueKind.TEXT,
    ValueKind.DATE,
    ValueKind.TIMESTAMP,
}


def query_findings(
    query: GraphQuery,
    definitions: tuple[TypeDefinition, ...],
    *,
    include_relationship_compatibility: bool = True,
) -> tuple[Finding, ...]:
    if isinstance(query.selection, IdentitySelection):
        return _identity_findings(query.selection)
    return _pattern_findings(query.selection, definitions, include_relationship_compatibility)


def relationship_compatibility_findings(
    selection: PatternSelection, definitions: tuple[TypeDefinition, ...]
) -> tuple[Finding, ...]:
    """Check only endpoint compatibility after request meaning is known valid."""
    definition_map = {definition.type_key: definition for definition in definitions}
    nodes = {node.name: node for node in selection.nodes}
    findings: list[Finding] = []
    for index, association in enumerate(selection.direct_associations):
        _association_compatibility(association, index, nodes, definition_map, findings)
    for index, link in enumerate(selection.links):
        _link_compatibility(link, index, nodes, definition_map, findings)
    return _ordered(findings)


def structured_predicate_findings(connection, selection: PatternSelection) -> tuple[Finding, ...]:
    searchable = {
        PredicateOperator.ALL_TERMS,
        PredicateOperator.ANY_TERMS,
        PredicateOperator.PHRASE,
    }
    for node in selection.nodes:
        for predicate in node.predicates:
            if predicate.operator not in searchable:
                continue
            try:
                structured_fts_expression(connection, predicate)
            except ValueError as error:
                return (_finding(FindingCode.INVALID_VALUE, "/selection", str(error)),)
    return ()


def _identity_findings(selection: IdentitySelection) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if not 1 <= len(selection.objects) <= PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                "/selection/objects",
                f"objects must contain between 1 and {PUBLIC_ITEM_LIMIT} selections",
            )
        )
    _duplicates(tuple(value.uuid for value in selection.objects), "/selection/objects", findings)
    for index, value in enumerate(selection.objects):
        if value.properties is not None:
            _property_selection_findings(
                value.properties, f"/selection/objects/{index}/properties", findings
            )
    return _ordered(findings)


def _pattern_findings(
    selection: PatternSelection,
    definitions: tuple[TypeDefinition, ...],
    include_relationship_compatibility: bool,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if not 1 <= selection.maximum_matches <= PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                "/selection/maxMatches",
                f"maxMatches must be between 1 and {PUBLIC_ITEM_LIMIT}",
            )
        )
    total = len(selection.nodes) + len(selection.direct_associations) + len(selection.links)
    total += sum(len(node.predicates) for node in selection.nodes)
    if not selection.nodes:
        findings.append(
            _finding(
                FindingCode.MISSING, "/selection/nodes", "at least one pattern node is required"
            )
        )
    if total > PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                "/selection",
                f"combined pattern items exceed {PUBLIC_ITEM_LIMIT}",
            )
        )
    names = tuple(node.name for node in selection.nodes) + tuple(
        link.name for link in selection.links
    )
    _duplicates(names, "/selection", findings)
    _duplicate_values(selection.direct_associations, "/selection/directAssociations", findings)
    findings.extend(_empty_selector_name_findings(selection))
    definition_map = {definition.type_key: definition for definition in definitions}
    nodes = {node.name: node for node in selection.nodes}
    for index, node in enumerate(selection.nodes):
        _node_findings(node, index, definition_map, findings)
    for index, association in enumerate(selection.direct_associations):
        _association_findings(association, index, nodes, definition_map, findings)
    for index, link in enumerate(selection.links):
        _link_findings(link, index, nodes, definition_map, findings)
    findings.extend(
        _optional_relationship_findings(selection, definitions, include_relationship_compatibility)
    )
    if len(nodes) > 1 and not _connected(selection):
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                "/selection",
                "pattern nodes must form one connected component",
            )
        )
    return _ordered(findings)


def _optional_relationship_findings(selection, definitions, include):
    return relationship_compatibility_findings(selection, definitions) if include else ()


def _node_findings(
    node: PatternNode,
    index: int,
    definitions: dict[str, TypeDefinition],
    findings: list[Finding],
) -> None:
    path = f"/selection/nodes/{index}"
    _duplicates(node.type_keys, f"{path}/typeKeys", findings)
    _duplicates(node.uuids, f"{path}/uuids", findings)
    _duplicate_values(node.predicates, f"{path}/predicates", findings)
    if len(node.type_keys) > PUBLIC_ITEM_LIMIT or len(node.uuids) > PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                path,
                f"node filter exceeds {PUBLIC_ITEM_LIMIT} items",
            )
        )
    selected: list[TypeDefinition] = []
    for position, key in enumerate(node.type_keys):
        definition = definitions.get(key)
        expected = (
            AnchorTypeDefinition
            if node.kind is PatternNodeKind.ANCHOR
            else AssociatedDataTypeDefinition
        )
        if definition is None:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    f"{path}/typeKeys/{position}",
                    "unknown type key",
                    type_keys=(key,),
                )
            )
        elif not isinstance(definition, expected):
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/typeKeys/{position}",
                    "type key has another node kind",
                    type_keys=(key,),
                )
            )
        else:
            selected.append(definition)
    if node.properties is not None:
        _property_selection_findings(node.properties, f"{path}/properties", findings)
        if node.kind is not PatternNodeKind.ASSOCIATED_DATA:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/properties",
                    "only associated-data nodes have properties",
                )
            )
        elif not node.type_keys:
            findings.append(
                _finding(
                    FindingCode.MISSING,
                    f"{path}/typeKeys",
                    "property hydration requires explicit typeKeys",
                )
            )
        else:
            _selected_property_findings(node.properties, selected, f"{path}/properties", findings)
    for position, predicate in enumerate(node.predicates):
        _predicate_findings(
            predicate,
            selected,
            node,
            path,
            f"{path}/predicates/{position}",
            findings,
        )


def _predicate_findings(
    predicate: Predicate,
    definitions: list[TypeDefinition],
    node: PatternNode,
    node_path: str,
    path: str,
    findings: list[Finding],
) -> None:
    if isinstance(predicate.field, DisplayNameField):
        if node.kind is not PatternNodeKind.ANCHOR:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/field",
                    "displayName requires an anchor node",
                )
            )
        value_kind = ValueKind.TEXT
        nullable = False
    else:
        if node.kind is not PatternNodeKind.ASSOCIATED_DATA:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/field",
                    "property predicates require associated data",
                )
            )
            return
        if not node.type_keys:
            findings.append(
                _finding(
                    FindingCode.MISSING,
                    f"{node_path}/typeKeys",
                    "property predicates require explicit typeKeys",
                )
            )
            return
        rules = []
        for definition in definitions:
            assert isinstance(definition, AssociatedDataTypeDefinition)
            rule = next(
                (item for item in definition.properties if item.name == predicate.field.name), None
            )
            if rule is None:
                findings.append(
                    _finding(
                        FindingCode.UNKNOWN,
                        f"{path}/field/name",
                        "property is not defined by every candidate type",
                        type_keys=(definition.type_key,),
                    )
                )
            else:
                rules.append(rule)
        if not rules:
            return
        value_kind = rules[0].value_kind
        nullable = all(rule.nullable for rule in rules)
        if any(rule.value_kind is not value_kind for rule in rules):
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/field/name",
                    "candidate types define the property with different kinds",
                )
            )
            return
    _predicate_payload_findings(predicate, value_kind, nullable, path, findings)


def _predicate_payload_findings(
    predicate: Predicate,
    value_kind: ValueKind,
    nullable: bool,
    path: str,
    findings: list[Finding],
) -> None:
    operator = predicate.operator
    if operator in _NO_PAYLOAD:
        if not isinstance(predicate.field, PropertyField):
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/operator",
                    "presence and null operators require a property",
                )
            )
        _reject_extra_payload(predicate, path, findings)
        return
    if operator in {PredicateOperator.EQUAL, PredicateOperator.NOT_EQUAL} | _ORDER:
        _single_value_findings(predicate, value_kind, path, findings)
        return
    if operator is PredicateOperator.ANY_OF:
        _any_of_findings(predicate, value_kind, nullable, path, findings)
        return
    if operator in _TEXT:
        _text_payload_findings(predicate, value_kind, path, findings)
        return
    if operator in _TERMS:
        _term_payload_findings(predicate, value_kind, path, findings)
        return
    assert operator is PredicateOperator.PHRASE
    _phrase_payload_findings(predicate, value_kind, path, findings)


def _single_value_findings(
    predicate: Predicate, value_kind: ValueKind, path: str, findings: list[Finding]
) -> None:
    _case_sensitive_finding(predicate, path, findings)
    if predicate.value is None or predicate.values or predicate.text is not None or predicate.terms:
        findings.append(
            _finding(FindingCode.INVALID_VALUE, path, "operator requires exactly one value")
        )
        return
    if predicate.value.kind is not value_kind:
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                f"{path}/value",
                "predicate value has another kind",
            )
        )
    if predicate.operator in _ORDER and value_kind not in _ORDERABLE:
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                f"{path}/operator",
                "property kind has no selected ordering",
            )
        )


def _any_of_findings(
    predicate: Predicate,
    value_kind: ValueKind,
    nullable: bool,
    path: str,
    findings: list[Finding],
) -> None:
    _case_sensitive_finding(predicate, path, findings)
    if (
        predicate.value is not None
        or predicate.text is not None
        or predicate.terms
        or not predicate.values
    ):
        findings.append(
            _finding(FindingCode.INVALID_VALUE, path, "anyOf requires one nonempty values list")
        )
        return
    if len(predicate.values) > PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                f"{path}/values",
                f"anyOf exceeds {PUBLIC_ITEM_LIMIT} values",
            )
        )
    _duplicates(
        tuple(_operand_key(value) for value in predicate.values), f"{path}/values", findings
    )
    for index, value in enumerate(predicate.values):
        if value is None and not nullable:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/values/{index}",
                    "null is not permitted by every candidate type",
                )
            )
        elif value is not None and value.kind is not value_kind:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/values/{index}",
                    "anyOf value has another kind",
                )
            )


def _text_payload_findings(
    predicate: Predicate, value_kind: ValueKind, path: str, findings: list[Finding]
) -> None:
    if predicate.value is not None or predicate.values or predicate.text is None or predicate.terms:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                path,
                "text operator requires exactly one text payload",
            )
        )
        return
    if value_kind is not ValueKind.TEXT:
        findings.append(
            _finding(FindingCode.KIND_MISMATCH, f"{path}/operator", "text operator requires text")
        )
    elif predicate.operator is PredicateOperator.REGEX:
        try:
            re2.compile(predicate.text)
        except re2.error:
            findings.append(
                _finding(
                    FindingCode.INVALID_VALUE,
                    f"{path}/value",
                    "regex is not a valid RE2 expression",
                )
            )


def _empty_selector_name_findings(selection: PatternSelection) -> tuple[Finding, ...]:
    """Point at the array the name actually lives in.

    Node and link names occupy separate request arrays, so an index into their
    concatenation identifies no member of the request.
    """
    findings: list[Finding] = []
    for collection, values in (("nodes", selection.nodes), ("links", selection.links)):
        for index, value in enumerate(values):
            if value.name == "":
                findings.append(
                    _finding(
                        FindingCode.MISSING,
                        f"/selection/{collection}/{index}/name",
                        "query name is empty",
                    )
                )
    return tuple(findings)


def _term_payload_findings(
    predicate: Predicate, value_kind: ValueKind, path: str, findings: list[Finding]
) -> None:
    _case_sensitive_finding(predicate, path, findings)
    if (
        predicate.value is not None
        or predicate.values
        or predicate.text is not None
        or not predicate.terms
    ):
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                path,
                "term operator requires a nonempty terms list",
            )
        )
    if len(predicate.terms) > PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                f"{path}/terms",
                f"term list exceeds {PUBLIC_ITEM_LIMIT} values",
            )
        )
    _full_text_kind_finding(value_kind, path, findings)
    _duplicates(predicate.terms, f"{path}/terms", findings)


def _phrase_payload_findings(
    predicate: Predicate, value_kind: ValueKind, path: str, findings: list[Finding]
) -> None:
    _case_sensitive_finding(predicate, path, findings)
    if predicate.value is not None or predicate.values or predicate.text is None or predicate.terms:
        findings.append(
            _finding(FindingCode.INVALID_VALUE, path, "phrase requires exactly one text payload")
        )
    _full_text_kind_finding(value_kind, path, findings)


def _full_text_kind_finding(value_kind: ValueKind, path: str, findings: list[Finding]) -> None:
    if value_kind is not ValueKind.TEXT:
        findings.append(
            _finding(FindingCode.KIND_MISMATCH, f"{path}/operator", "full text requires text")
        )


def _reject_extra_payload(predicate: Predicate, path: str, findings: list[Finding]) -> None:
    _case_sensitive_finding(predicate, path, findings)
    if (
        predicate.value is not None
        or predicate.values
        or predicate.text is not None
        or predicate.terms
    ):
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE, path, "operator carries unsupported payload members"
            )
        )


def _case_sensitive_finding(predicate: Predicate, path: str, findings: list[Finding]) -> None:
    if predicate.case_sensitive:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                f"{path}/caseSensitive",
                "caseSensitive is supported only by contains, prefix, and regex",
            )
        )


def _property_selection_findings(
    selection: PropertySelection, path: str, findings: list[Finding]
) -> None:
    _duplicates(selection.names, path, findings)
    if len(selection.names) > PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                path,
                f"property selection exceeds {PUBLIC_ITEM_LIMIT} names",
            )
        )


def _selected_property_findings(
    selection: PropertySelection,
    definitions: list[TypeDefinition],
    path: str,
    findings: list[Finding],
) -> None:
    for position, name in enumerate(selection.names):
        missing = tuple(
            definition.type_key
            for definition in definitions
            if isinstance(definition, AssociatedDataTypeDefinition)
            and all(rule.name != name for rule in definition.properties)
        )
        if missing:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    f"{path}/{position}",
                    "property is not defined by every candidate type",
                    type_keys=missing,
                )
            )


def _association_findings(
    association: DirectAssociation,
    index: int,
    nodes: dict[str, PatternNode],
    definitions: dict[str, TypeDefinition],
    findings: list[Finding],
) -> None:
    path = f"/selection/directAssociations/{index}"
    anchor = nodes.get(association.anchor)
    data = nodes.get(association.associated_data)
    if anchor is None:
        findings.append(_finding(FindingCode.UNKNOWN, f"{path}/anchor", "unknown anchor node"))
    elif anchor.kind is not PatternNodeKind.ANCHOR:
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                f"{path}/anchor",
                "direct association requires an anchor node",
            )
        )
    if data is None:
        findings.append(
            _finding(FindingCode.UNKNOWN, f"{path}/associatedData", "unknown associated-data node")
        )
    elif data.kind is not PatternNodeKind.ASSOCIATED_DATA:
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                f"{path}/associatedData",
                "direct association requires an associated-data node",
            )
        )
    if anchor is None or data is None:
        return


def _association_compatibility(
    association: DirectAssociation,
    index: int,
    nodes: dict[str, PatternNode],
    definitions: dict[str, TypeDefinition],
    findings: list[Finding],
) -> None:
    path = f"/selection/directAssociations/{index}"
    anchor = nodes.get(association.anchor)
    data = nodes.get(association.associated_data)
    if anchor is None or data is None:
        return
    anchor_keys = _candidate_node_keys(anchor, definitions)
    data_definitions = tuple(
        value
        for value in _candidate_node_definitions(data, definitions)
        if isinstance(value, AssociatedDataTypeDefinition)
    )
    if (
        anchor_keys
        and data_definitions
        and not any(
            anchor_keys.intersection(value.permitted_anchor_type_keys) for value in data_definitions
        )
    ):
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                path,
                "direct-association candidate types have no compatible endpoint combination",
            )
        )


def _link_findings(
    link: PatternLink,
    index: int,
    nodes: dict[str, PatternNode],
    definitions: dict[str, TypeDefinition],
    findings: list[Finding],
) -> None:
    path = f"/selection/links/{index}"
    _duplicates(link.type_keys, f"{path}/typeKeys", findings)
    _duplicates(link.uuids, f"{path}/uuids", findings)
    if len(link.type_keys) > PUBLIC_ITEM_LIMIT or len(link.uuids) > PUBLIC_ITEM_LIMIT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                path,
                f"link filter exceeds {PUBLIC_ITEM_LIMIT} items",
            )
        )
    source = nodes.get(link.source)
    target = nodes.get(link.target)
    if source is None:
        findings.append(_finding(FindingCode.UNKNOWN, f"{path}/source", "unknown source node"))
    if target is None:
        findings.append(_finding(FindingCode.UNKNOWN, f"{path}/target", "unknown target node"))
    for position, key in enumerate(link.type_keys):
        definition = definitions.get(key)
        if definition is None:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    f"{path}/typeKeys/{position}",
                    "unknown link type",
                    type_keys=(key,),
                )
            )
        elif not isinstance(definition, LinkTypeDefinition):
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    f"{path}/typeKeys/{position}",
                    "type is not a link type",
                    type_keys=(key,),
                )
            )


def _link_compatibility(
    link: PatternLink,
    index: int,
    nodes: dict[str, PatternNode],
    definitions: dict[str, TypeDefinition],
    findings: list[Finding],
) -> None:
    path = f"/selection/links/{index}"
    source = nodes.get(link.source)
    target = nodes.get(link.target)
    selected_links = (
        tuple(value for value in definitions.values() if isinstance(value, LinkTypeDefinition))
        if not link.type_keys
        else tuple(
            value
            for key in link.type_keys
            if isinstance((value := definitions.get(key)), LinkTypeDefinition)
        )
    )
    if source is None or target is None or not selected_links:
        return
    source_keys = _candidate_node_keys(source, definitions)
    target_keys = _candidate_node_keys(target, definitions)
    if (
        source_keys
        and target_keys
        and not any(
            source_keys.intersection(value.permitted_source_type_keys)
            and target_keys.intersection(value.permitted_target_type_keys)
            for value in selected_links
        )
    ):
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                path,
                "link candidate types have no compatible endpoint combination",
                type_keys=tuple(value.type_key for value in selected_links),
            )
        )


def _candidate_node_keys(node: PatternNode, definitions: dict[str, TypeDefinition]) -> set[str]:
    return {value.type_key for value in _candidate_node_definitions(node, definitions)}


def _candidate_node_definitions(
    node: PatternNode, definitions: dict[str, TypeDefinition]
) -> tuple[TypeDefinition, ...]:
    expected = (
        AnchorTypeDefinition
        if node.kind is PatternNodeKind.ANCHOR
        else AssociatedDataTypeDefinition
    )
    if node.type_keys:
        return tuple(
            value for key in node.type_keys if isinstance((value := definitions.get(key)), expected)
        )
    return tuple(value for value in definitions.values() if isinstance(value, expected))


def _connected(selection: PatternSelection) -> bool:
    neighbors = {node.name: set() for node in selection.nodes}
    for value in selection.direct_associations:
        if value.anchor in neighbors and value.associated_data in neighbors:
            neighbors[value.anchor].add(value.associated_data)
            neighbors[value.associated_data].add(value.anchor)
    for value in selection.links:
        if value.source in neighbors and value.target in neighbors:
            neighbors[value.source].add(value.target)
            neighbors[value.target].add(value.source)
    start = next(iter(neighbors))
    reached = {start}
    pending = [start]
    while pending:
        for neighbor in neighbors[pending.pop()]:
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    return len(reached) == len(neighbors)


def _operand_key(value: ScalarValue | None) -> str:
    if value is None:
        return "null"
    wire = value.wire_value()
    if value.kind is ValueKind.NUMBER:
        assert isinstance(wire, float)
        return f"number:{canonical_number_text(wire)}"
    return f"{value.kind.value}:{wire!r}"


def _duplicates(values: tuple[str, ...], path: str, findings: list[Finding]) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        if value in seen:
            findings.append(_finding(FindingCode.DUPLICATE, f"{path}/{index}", "duplicate value"))
        seen.add(value)


def _duplicate_values(values: tuple[object, ...], path: str, findings: list[Finding]) -> None:
    seen: set[object] = set()
    for index, value in enumerate(values):
        if value in seen:
            findings.append(_finding(FindingCode.DUPLICATE, f"{path}/{index}", "duplicate value"))
        seen.add(value)


def _finding(
    code: FindingCode,
    path: str,
    summary: str,
    *,
    type_keys: tuple[str, ...] = (),
) -> Finding:
    return Finding(code, summary, path, type_keys)


def _ordered(findings: list[Finding]) -> tuple[Finding, ...]:
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
