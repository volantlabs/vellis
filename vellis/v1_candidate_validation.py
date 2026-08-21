"""Complete bounded-memory validation of one staged v1 candidate."""

from __future__ import annotations

from collections.abc import Iterator

from vellis.domain import AssociatedData, AssociatedDataTypeDefinition, Finding, Link
from vellis.domain_validation import graph_object_findings, type_definition_findings
from vellis.v1_candidate import (
    iter_definitions,
    iter_objects,
    load_candidate_definitions,
    load_objects,
)


def staged_candidate_findings(connection) -> Iterator[Finding]:
    """Yield every structural finding while retaining one local neighborhood."""
    for definition in iter_definitions(connection):
        yield from type_definition_findings(
            definition,
            load_candidate_definitions(connection, _definition_references(definition)),
            require_system=True,
        )
    for value in iter_objects(connection):
        referents = load_objects(connection, _object_references(value))
        type_keys = tuple(sorted({value.type_key, *(item.type_key for item in referents)}))
        yield from graph_object_findings(
            value,
            load_candidate_definitions(connection, type_keys),
            referents,
            require_system=True,
        )


def _definition_references(definition) -> tuple[str, ...]:
    if isinstance(definition, AssociatedDataTypeDefinition):
        return definition.permitted_anchor_type_keys
    source = getattr(definition, "permitted_source_type_keys", ())
    target = getattr(definition, "permitted_target_type_keys", ())
    return tuple(sorted(set(source) | set(target)))


def _object_references(value) -> tuple[str, ...]:
    if isinstance(value, AssociatedData):
        return value.anchor_uuids
    if isinstance(value, Link):
        return tuple(sorted({value.source_uuid, value.target_uuid}))
    return ()
