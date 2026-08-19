"""Compile one positive graph pattern into bounded SQLite answer identities.

The public query is a conjunction over named object and link variables.  This module
keeps that meaning small: variables that distinguish the answer are the outer relation;
connected groups of all other variables are correlated existence tests.  Relationship
witnesses are themselves existence predicates unless their link identity is projected.
No graph object is decoded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vellis.graph import ObjectKind
from vellis.json_value import JsonKind
from vellis.normalized import json_storage_fields
from vellis.query import (
    AggregateQueryOutput,
    AnalyzedGraphQuery,
    GraphQuery,
    PropertyComparison,
    RowQueryOutput,
)

__all__ = [
    "CompiledQuery",
    "CompiledStatement",
    "QueryRelations",
    "SelectorMember",
    "UuidValidation",
    "compile_query",
    "selector_members",
]


@dataclass(frozen=True, slots=True)
class QueryRelations:
    """The already-resolved evaluated-state relations used by one compilation."""

    graph: str
    association: str
    prefix: str = ""
    prefix_parameters: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorMember:
    member_kind: str
    selector_name: str
    value: str


@dataclass(frozen=True, slots=True)
class CompiledStatement:
    """One exact statement plus structural facts known without executing it."""

    sql: str
    parameters: tuple[object, ...] = ()
    selected_columns: int = 0
    maximum_tables_in_select: int = 0
    expression_depth: int = 0
    maximum_function_arguments: int = 0

    @property
    def utf8_bytes(self) -> int:
        return len(self.sql.encode("utf-8"))

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)


@dataclass(frozen=True, slots=True)
class UuidValidation:
    label: str
    object_kind: str
    statement: CompiledStatement


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    """The complete preparation surface for one bounded identity query."""

    reset_answer: CompiledStatement
    create_answer: CompiledStatement
    populate_answer: CompiledStatement
    read_answer: CompiledStatement
    uuid_validations: tuple[UuidValidation, ...]
    identity_kinds: tuple[str, ...]
    bound: int
    bound_kind: Literal["rows", "matches"]

    @property
    def statements(self) -> tuple[CompiledStatement, ...]:
        return (
            self.reset_answer,
            self.create_answer,
            *(validation.statement for validation in self.uuid_validations),
            self.populate_answer,
            self.read_answer,
        )


@dataclass(frozen=True, slots=True)
class _Predicate:
    variables: frozenset[str]
    sql: str
    parameters: tuple[object, ...] = ()
    subquery_tables: int = 0
    depth: int = 1


def selector_members(query: GraphQuery) -> tuple[SelectorMember, ...]:
    """Return all public collection members for the one indexed temp relation."""
    members: list[SelectorMember] = []
    for group in query.anchor_groups:
        members.extend(
            SelectorMember("anchorType", group.name, type_key) for type_key in group.anchor_types
        )
        if group.uuid_filter is not None:
            members.extend(
                SelectorMember("anchorUuid", group.name, uuid) for uuid in group.uuid_filter.uuids
            )
    for condition in query.data_conditions:
        if condition.uuid_filter is not None:
            members.extend(
                SelectorMember("associatedDataUuid", condition.name, uuid)
                for uuid in condition.uuid_filter.uuids
            )
    for required in query.required_links:
        if required.uuid_filter is not None:
            members.extend(
                SelectorMember("linkUuid", required.name, uuid)
                for uuid in required.uuid_filter.uuids
            )
    if isinstance(query.output, AggregateQueryOutput):
        members.extend(
            SelectorMember("aggregateProperty", query.output.data_condition, property_name)
            for property_name in dict.fromkeys(
                aggregation.property_name
                for aggregation in query.output.aggregations
                if aggregation.property_name is not None
            )
        )
    return tuple(members)


def compile_query(analysis: AnalyzedGraphQuery, relations: QueryRelations) -> CompiledQuery:
    """Compile the analyzed positive conjunction without enumerating hidden witnesses."""
    query = analysis.query
    aliases = _variable_aliases(query)
    answer = frozenset(analysis.answer_variables)
    hidden = frozenset(analysis.existential_variables)
    predicates = _predicates(query, relations, aliases, answer)

    outer_predicates = [predicate for predicate in predicates if predicate.variables <= answer]
    outer_predicates.extend(_data_candidate_semijoins(query, relations, aliases, answer))
    hidden_components = _hidden_components(
        tuple(variable for variable in _ordered_variables(query) if variable in hidden), predicates
    )
    for component in hidden_components:
        component_predicates = [
            predicate for predicate in predicates if predicate.variables & component
        ]
        tables = ", ".join(
            f"{relations.graph} AS {aliases[variable]}"
            for variable in _ordered_variables(query)
            if variable in component
        )
        condition_sql = " AND ".join(predicate.sql for predicate in component_predicates)
        parameters = tuple(
            parameter for predicate in component_predicates for parameter in predicate.parameters
        )
        outer_predicates.append(
            _Predicate(
                variables=frozenset(
                    variable
                    for variable in answer
                    if any(variable in predicate.variables for predicate in component_predicates)
                ),
                sql=f"EXISTS (SELECT 1 FROM {tables} WHERE {condition_sql})",
                parameters=parameters,
                subquery_tables=len(component),
                depth=2 + max((predicate.depth for predicate in component_predicates), default=0),
            )
        )

    ordered_answer = [variable for variable in _ordered_variables(query) if variable in answer]
    outer_tables = ", ".join(
        f"{relations.graph} AS {aliases[variable]}" for variable in ordered_answer
    )
    where_sql = " AND ".join(predicate.sql for predicate in outer_predicates)
    where_parameters = tuple(
        parameter for predicate in outer_predicates for parameter in predicate.parameters
    )
    selected = tuple(
        f"{aliases[column.variable]}.object_value_id" for column in analysis.identity_columns
    )
    columns = tuple(f"c{index}" for index in range(len(selected)))
    create_sql = (
        "CREATE TEMP TABLE query_answer ("
        + ", ".join(f"{column} INTEGER NOT NULL" for column in columns)
        + ", PRIMARY KEY ("
        + ", ".join(columns)
        + ")) WITHOUT ROWID"
    )
    output = query.output
    bound = output.maximum_rows if isinstance(output, RowQueryOutput) else output.maximum_matches
    limit = bound + 1
    insert_sql = (
        relations.prefix
        + "INSERT OR IGNORE INTO query_answer ("
        + ", ".join(columns)
        + ") SELECT "
        + ", ".join(selected)
        + " FROM "
        + outer_tables
        + (" WHERE " + where_sql if where_sql else "")
        + " LIMIT ?"
    )
    maximum_tables = max(
        [len(ordered_answer), *(predicate.subquery_tables for predicate in outer_predicates)]
    )
    maximum_function_arguments = (
        max(
            (
                8
                if comparison.comparison in {PropertyComparison.EQUAL, PropertyComparison.NOT_EQUAL}
                else 2
            )
            for condition in query.data_conditions
            for comparison in condition.property_conditions
        )
        if any(condition.property_conditions for condition in query.data_conditions)
        else 0
    )
    return CompiledQuery(
        reset_answer=CompiledStatement("DROP TABLE IF EXISTS query_answer"),
        create_answer=CompiledStatement(create_sql),
        populate_answer=CompiledStatement(
            insert_sql,
            (*relations.prefix_parameters, *where_parameters, limit),
            selected_columns=len(selected),
            maximum_tables_in_select=maximum_tables,
            expression_depth=max((predicate.depth for predicate in outer_predicates), default=0),
            maximum_function_arguments=maximum_function_arguments,
        ),
        read_answer=CompiledStatement(
            "SELECT " + ", ".join(columns) + " FROM query_answer ORDER BY " + ", ".join(columns),
            selected_columns=len(columns),
            maximum_tables_in_select=1,
        ),
        uuid_validations=_uuid_validations(query, relations, aliases),
        identity_kinds=tuple(column.kind for column in analysis.identity_columns),
        bound=bound,
        bound_kind="rows" if isinstance(output, RowQueryOutput) else "matches",
    )


def _variable_aliases(query: GraphQuery) -> dict[str, str]:
    aliases: dict[str, str] = {}
    aliases.update((group.name, f"a{index}") for index, group in enumerate(query.anchor_groups))
    aliases.update(
        (condition.name, f"d{index}") for index, condition in enumerate(query.data_conditions)
    )
    aliases.update(
        (required.name, f"l{index}") for index, required in enumerate(query.required_links)
    )
    return aliases


def _ordered_variables(query: GraphQuery) -> tuple[str, ...]:
    return (
        *(group.name for group in query.anchor_groups),
        *(condition.name for condition in query.data_conditions),
        *(required.name for required in query.required_links),
    )


def _predicates(
    query: GraphQuery,
    relations: QueryRelations,
    aliases: dict[str, str],
    answer: frozenset[str],
) -> tuple[_Predicate, ...]:
    predicates: list[_Predicate] = []
    for group in query.anchor_groups:
        alias = aliases[group.name]
        predicates.extend(
            (
                _Predicate(
                    frozenset({group.name}),
                    f"{alias}.object_kind = ?",
                    (ObjectKind.ANCHOR.value,),
                ),
                _Predicate(
                    frozenset({group.name}),
                    f"{alias}.type_key IN (SELECT qsm.value FROM query_selector_member AS qsm"
                    f" WHERE qsm.member_kind = 'anchorType' AND qsm.selector_name = ?"
                    ")",
                    (group.name,),
                    subquery_tables=1,
                    depth=2,
                ),
            )
        )
        if group.uuid_filter is not None:
            predicates.append(_member_predicate(group.name, "anchorUuid", alias))

    for condition in query.data_conditions:
        alias = aliases[condition.name]
        predicates.extend(
            (
                _Predicate(
                    frozenset({condition.name}),
                    f"{alias}.object_kind = ? AND {alias}.type_key = ?",
                    (ObjectKind.ASSOCIATED_DATA.value, condition.associated_data_type),
                ),
                _Predicate(
                    frozenset({condition.anchor_group, condition.name}),
                    "EXISTS (SELECT 1 FROM "
                    + relations.association
                    + " AS qa WHERE qa.data_uuid = "
                    + alias
                    + ".uuid AND qa.anchor_uuid = "
                    + aliases[condition.anchor_group]
                    + ".uuid)",
                    subquery_tables=1,
                    depth=2,
                ),
            )
        )
        if condition.uuid_filter is not None:
            predicates.append(_member_predicate(condition.name, "associatedDataUuid", alias))
        for index, comparison in enumerate(condition.property_conditions):
            property_alias = f"p{aliases[condition.name][1:]}_{index}"
            comparison_sql, parameters = _property_comparison(
                property_alias, comparison.comparison, comparison.expected_value
            )
            predicates.append(
                _Predicate(
                    frozenset({condition.name}),
                    "EXISTS (SELECT 1 FROM object_property AS "
                    + property_alias
                    + " WHERE "
                    + property_alias
                    + ".object_value_id = "
                    + alias
                    + ".object_value_id AND "
                    + property_alias
                    + ".name = ? AND "
                    + comparison_sql
                    + ")",
                    (comparison.property_name, *parameters),
                    subquery_tables=1,
                    depth=2,
                )
            )

    for required in query.required_links:
        alias = aliases[required.name]
        if required.name not in answer:
            uuid_sql = ""
            parameters: tuple[object, ...] = (
                ObjectKind.LINK.value,
                required.link_type,
            )
            if required.uuid_filter is not None:
                uuid_sql = (
                    f" AND {alias}.uuid IN (SELECT qsm.value FROM query_selector_member AS qsm"
                    " WHERE qsm.member_kind = ? AND qsm.selector_name = ?)"
                )
                parameters = (*parameters, "linkUuid", required.name)
            predicates.append(
                _Predicate(
                    frozenset({required.source_group, required.target_group}),
                    "EXISTS (SELECT 1 FROM "
                    + relations.graph
                    + " AS "
                    + alias
                    + f" WHERE {alias}.object_kind = ? AND {alias}.type_key = ?"
                    + f" AND {alias}.source_uuid = {aliases[required.source_group]}.uuid"
                    + f" AND {alias}.target_uuid = {aliases[required.target_group]}.uuid"
                    + uuid_sql
                    + ")",
                    parameters,
                    subquery_tables=1,
                    depth=3,
                )
            )
            continue
        predicates.append(
            _Predicate(
                frozenset({required.name}),
                f"{alias}.object_kind = ? AND {alias}.type_key = ?",
                (ObjectKind.LINK.value, required.link_type),
            )
        )
        if required.uuid_filter is not None:
            predicates.append(_member_predicate(required.name, "linkUuid", alias))
        predicates.append(
            _Predicate(
                frozenset({required.name, required.source_group, required.target_group}),
                f"{alias}.source_uuid = {aliases[required.source_group]}.uuid"
                f" AND {alias}.target_uuid = {aliases[required.target_group]}.uuid",
            )
        )
    return tuple(predicates)


def _data_candidate_semijoins(
    query: GraphQuery,
    relations: QueryRelations,
    aliases: dict[str, str],
    answer: frozenset[str],
) -> tuple[_Predicate, ...]:
    """Drive visible data identities from a hidden grounding anchor when possible.

    A property predicate is intentionally non-sargable.  This indexed membership relation
    keeps it downstream of the data UUIDs reachable from the hidden anchor selector instead
    of scanning every same-type property before testing association.
    """
    groups = {group.name: group for group in query.anchor_groups}
    predicates: list[_Predicate] = []
    for index, condition in enumerate(query.data_conditions):
        if condition.name not in answer or condition.anchor_group in answer:
            continue
        group = groups[condition.anchor_group]
        anchor_alias = f"ca{index}"
        association_alias = f"cda{index}"
        sql = (
            f"{aliases[condition.name]}.uuid IN (SELECT {association_alias}.data_uuid FROM "
            f"{relations.graph} AS {anchor_alias} JOIN {relations.association} AS"
            f" {association_alias} ON {association_alias}.anchor_uuid = {anchor_alias}.uuid"
            f" WHERE {anchor_alias}.object_kind = ? AND {anchor_alias}.type_key IN"
            " (SELECT qsm.value FROM query_selector_member AS qsm WHERE"
            " qsm.member_kind = 'anchorType' AND qsm.selector_name = ?)"
        )
        parameters: tuple[object, ...] = (ObjectKind.ANCHOR.value, group.name)
        if group.uuid_filter is not None:
            sql += (
                f" AND {anchor_alias}.uuid IN (SELECT qsm.value FROM query_selector_member AS qsm"
                " WHERE qsm.member_kind = 'anchorUuid' AND qsm.selector_name = ?)"
            )
            parameters = (*parameters, group.name)
        predicates.append(
            _Predicate(
                frozenset({condition.name}),
                sql + ")",
                parameters,
                subquery_tables=2,
                depth=3,
            )
        )
    return tuple(predicates)


def _member_predicate(selector: str, member_kind: str, alias: str) -> _Predicate:
    return _Predicate(
        frozenset({selector}),
        f"{alias}.uuid IN (SELECT qsm.value FROM query_selector_member AS qsm"
        " WHERE qsm.member_kind = ? AND qsm.selector_name = ?"
        ")",
        (member_kind, selector),
        subquery_tables=1,
        depth=2,
    )


def _property_comparison(
    alias: str, comparison: PropertyComparison, expected: object
) -> tuple[str, tuple[object, ...]]:
    kind, boolean, number, text = json_storage_fields(expected)  # type: ignore[arg-type]
    if comparison in {PropertyComparison.EQUAL, PropertyComparison.NOT_EQUAL}:
        predicate = (
            f"vellis_json_equal({alias}.json_kind, {alias}.boolean_value,"
            f" {alias}.number_value, {alias}.text_value, ?, ?, ?, ?)"
        )
        desired = 1 if comparison is PropertyComparison.EQUAL else 0
        return f"{predicate} = {desired}", (kind, boolean, number, text)
    if comparison is PropertyComparison.MATCHES_PATTERN:
        return (
            f"{alias}.json_kind = '{JsonKind.STRING.value}'"
            f" AND vellis_re2_full_match({alias}.text_value, ?) = 1",
            (text,),
        )
    operators = {
        PropertyComparison.LESS_THAN: "<",
        PropertyComparison.LESS_THAN_OR_EQUAL: "<=",
        PropertyComparison.GREATER_THAN: ">",
        PropertyComparison.GREATER_THAN_OR_EQUAL: ">=",
    }
    operator = operators[comparison]
    if kind == JsonKind.STRING.value:
        return (
            f"{alias}.json_kind = '{JsonKind.STRING.value}' AND {alias}.text_value {operator} ?",
            (text,),
        )
    return (
        f"{alias}.json_kind = '{JsonKind.NUMBER.value}'"
        f" AND vellis_decimal_cmp({alias}.number_value, ?) {operator} 0",
        (number,),
    )


def _hidden_components(
    hidden_in_order: tuple[str, ...], predicates: tuple[_Predicate, ...]
) -> tuple[frozenset[str], ...]:
    hidden = frozenset(hidden_in_order)
    remaining = set(hidden)
    components: list[frozenset[str]] = []
    for seed in hidden_in_order:
        if seed not in remaining:
            continue
        remaining.remove(seed)
        component = {seed}
        changed = True
        while changed:
            changed = False
            for predicate in predicates:
                touched = predicate.variables & hidden
                if touched & component and not touched <= component:
                    component.update(touched)
                    remaining.difference_update(touched)
                    changed = True
        components.append(frozenset(component))
    return tuple(components)


def _uuid_validations(
    query: GraphQuery, relations: QueryRelations, aliases: dict[str, str]
) -> tuple[UuidValidation, ...]:
    validations: list[UuidValidation] = []
    for group in query.anchor_groups:
        if group.uuid_filter is None:
            continue
        alias = aliases[group.name]
        sql = (
            relations.prefix + "SELECT qsm.value FROM query_selector_member AS qsm WHERE"
            " qsm.member_kind = 'anchorUuid' AND qsm.selector_name = ? AND NOT EXISTS"
            " (SELECT 1 FROM "
            + relations.graph
            + " AS "
            + alias
            + f" WHERE {alias}.uuid = qsm.value AND {alias}.object_kind = ?"
            " AND EXISTS (SELECT 1 FROM query_selector_member AS qat"
            " WHERE qat.member_kind = 'anchorType' AND qat.selector_name = ?"
            f" AND qat.value = {alias}.type_key)) ORDER BY qsm.value"
        )
        validations.append(
            UuidValidation(
                f"anchor group '{group.name}'",
                "anchor",
                CompiledStatement(
                    sql,
                    (*relations.prefix_parameters, group.name, ObjectKind.ANCHOR.value, group.name),
                    selected_columns=1,
                    maximum_tables_in_select=1,
                    expression_depth=3,
                ),
            )
        )
    for condition in query.data_conditions:
        if condition.uuid_filter is None:
            continue
        validations.append(
            _typed_uuid_validation(
                condition.name,
                "associatedDataUuid",
                "associated-data",
                ObjectKind.ASSOCIATED_DATA.value,
                condition.associated_data_type,
                relations,
                aliases[condition.name],
                label=f"data condition '{condition.name}'",
            )
        )
    for required in query.required_links:
        if required.uuid_filter is None:
            continue
        validations.append(
            _typed_uuid_validation(
                required.name,
                "linkUuid",
                "link",
                ObjectKind.LINK.value,
                required.link_type,
                relations,
                aliases[required.name],
                label=f"required link '{required.name}'",
            )
        )
    return tuple(validations)


def _typed_uuid_validation(
    selector: str,
    member_kind: str,
    object_kind_label: str,
    object_kind: str,
    type_key: str,
    relations: QueryRelations,
    alias: str,
    *,
    label: str,
) -> UuidValidation:
    sql = (
        relations.prefix + "SELECT qsm.value FROM query_selector_member AS qsm WHERE"
        " qsm.member_kind = ? AND qsm.selector_name = ? AND NOT EXISTS"
        " (SELECT 1 FROM "
        + relations.graph
        + " AS "
        + alias
        + f" WHERE {alias}.uuid = qsm.value AND {alias}.object_kind = ?"
        + f" AND {alias}.type_key = ?) ORDER BY qsm.value"
    )
    return UuidValidation(
        label,
        object_kind_label,
        CompiledStatement(
            sql,
            (*relations.prefix_parameters, member_kind, selector, object_kind, type_key),
            selected_columns=1,
            maximum_tables_in_select=1,
            expression_depth=2,
        ),
    )
