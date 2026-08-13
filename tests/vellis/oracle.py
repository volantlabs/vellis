"""Small test-only semantic materializers independent of production interfaces.

Production Vellis deliberately has no API that constructs a complete Graph or
CanonicalState. Small conformance fixtures still benefit from an independent readable
oracle, so tests assemble those values directly from normalized SQLite rows here.
"""

from tests.vellis.semantic_state import DefinitionDelta, SemanticState
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    LinkTypeDefinition,
    RelationshipConstraint,
)
from vellis.everyday_life import everyday_life_entries
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link
from vellis.normalized import load_definition_set, load_object_value
from vellis.query import (
    AnchorGroup,
    GraphQuery,
    GraphQueryResult,
    RequiredLink,
    evaluate_indexed_query,
)
from vellis.store import CanonicalStore
from vellis.system import RTGSystem


class _TestGraphIndex:
    """Test-only hash index over an explicitly materialized semantic fixture."""

    def __init__(self, graph: Graph) -> None:
        self.anchors = {value.uuid: value for value in graph.anchors}
        self.links = {value.uuid: value for value in graph.links}
        self.data = graph.associated_data

    def known_anchor_uuids(self, anchor_type: str, uuids: tuple[str, ...]) -> set[str]:
        return {
            uuid
            for uuid in uuids
            if (value := self.anchors.get(uuid)) is not None and value.type_key == anchor_type
        }

    def known_link_uuids(self, link_type: str, uuids: tuple[str, ...]) -> set[str]:
        return {
            uuid
            for uuid in uuids
            if (value := self.links.get(uuid)) is not None and value.type_key == link_type
        }

    def anchor_candidates(
        self, group: AnchorGroup, allowed_uuids: frozenset[str] | None = None
    ) -> tuple[Anchor, ...]:
        requested = None if group.uuid_filter is None else frozenset(group.uuid_filter.uuids)
        permitted = (
            allowed_uuids
            if requested is None
            else requested
            if allowed_uuids is None
            else requested & allowed_uuids
        )
        return tuple(
            value
            for value in self.anchors.values()
            if value.type_key == group.anchor_type
            and (permitted is None or value.uuid in permitted)
        )

    def associated_data_candidates(
        self,
        associated_data_type: str,
        anchor_uuid: str,
        allowed_uuids: frozenset[str] | None = None,
    ) -> tuple[AssociatedDataObject, ...]:
        return tuple(
            value
            for value in self.data
            if value.type_key == associated_data_type
            and anchor_uuid in value.anchor_uuids
            and (allowed_uuids is None or value.uuid in allowed_uuids)
        )

    def link_candidates(
        self, required: RequiredLink, source_uuid: str, target_uuid: str
    ) -> tuple[Link, ...]:
        allowed = None if required.uuid_filter is None else frozenset(required.uuid_filter.uuids)
        return tuple(
            value
            for value in self.links.values()
            if value.type_key == required.link_type
            and value.source_uuid == source_uuid
            and value.target_uuid == target_uuid
            and (allowed is None or value.uuid in allowed)
        )

    def link_endpoint_pairs(self, required: RequiredLink) -> frozenset[tuple[str, str]]:
        allowed = None if required.uuid_filter is None else frozenset(required.uuid_filter.uuids)
        return frozenset(
            (value.source_uuid, value.target_uuid)
            for value in self.links.values()
            if value.type_key == required.link_type and (allowed is None or value.uuid in allowed)
        )


def evaluate_query(
    query: GraphQuery, definitions: GraphDefinitionSet, graph: Graph, revision: int
) -> GraphQueryResult:
    """Evaluate a small aggregate fixture independently of production storage."""
    return evaluate_indexed_query(query, definitions, _TestGraphIndex(graph), revision)


def materialize_everyday_life() -> GraphDefinitionSet:
    """Build the fixed starter aggregate only inside the independent test oracle."""
    entries = tuple(everyday_life_entries())
    return GraphDefinitionSet(
        tuple(value for value in entries if isinstance(value, AnchorTypeDefinition)),
        tuple(value for value in entries if isinstance(value, AssociatedDataTypeDefinition)),
        tuple(value for value in entries if isinstance(value, LinkTypeDefinition)),
        tuple(value for value in entries if isinstance(value, RelationshipConstraint)),
    )


def materialize_definitions(
    system: RTGSystem | CanonicalStore, *, prospective: bool = False
) -> GraphDefinitionSet:
    """Assemble complete definitions directly from normalized rows for tests only."""
    store = system if isinstance(system, CanonicalStore) else system.store
    connection = store._connection  # noqa: SLF001
    head = connection.execute(
        "SELECT active_definition_set_id, proposed_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    assert head is not None
    if not prospective:
        type_keys = {
            str(row[0])
            for row in connection.execute(
                "SELECT type_key FROM definition_type WHERE definition_set_id = ?", (str(head[0]),)
            )
        }
        relationship_keys = {
            str(row[0])
            for row in connection.execute(
                "SELECT natural_key FROM definition_multiplicity_rule WHERE definition_set_id = ?",
                (str(head[0]),),
            )
        }
        return load_definition_set(
            connection,
            str(head[0]),
            type_keys=type_keys,
            relationship_keys=relationship_keys,
        )
    assert head[1] is not None
    type_keys = {
        str(row[0])
        for row in connection.execute(
            "SELECT type_key FROM definition_type WHERE definition_set_id = ?"
            " UNION SELECT type_key FROM proposal_definition_type",
            (str(head[0]),),
        )
    }
    relationship_keys = {
        str(row[0])
        for row in connection.execute(
            "SELECT natural_key FROM definition_multiplicity_rule WHERE definition_set_id = ?"
            " UNION SELECT natural_key FROM proposal_definition_relationship",
            (str(head[0]),),
        )
    }
    return store._effective_proposed_definitions_unlocked(  # noqa: SLF001
        str(head[0]), type_keys=type_keys, relationship_keys=relationship_keys
    )


def materialize_state(system: RTGSystem | CanonicalStore) -> SemanticState:
    """Assemble one complete semantic state for a small test fixture only."""
    store = system if isinstance(system, CanonicalStore) else system.store
    connection = store._connection  # noqa: SLF001
    with store.read_snapshot():
        revision = store.current_revision()
        values = [
            load_object_value(connection, int(row[0]))
            for row in connection.execute(
                "SELECT object_value_id FROM current_graph_object ORDER BY object_kind, uuid"
            )
        ]
        graph = Graph(
            anchors=tuple(value for value in values if isinstance(value, Anchor)),
            associated_data=tuple(
                value for value in values if isinstance(value, AssociatedDataObject)
            ),
            links=tuple(value for value in values if isinstance(value, Link)),
        )
        active = materialize_definitions(store)
        proposal_present = connection.execute(
            "SELECT proposed_definition_set_id IS NOT NULL FROM state_head WHERE id = 0"
        ).fetchone()[0]
        delta = None
        if proposal_present:
            proposed = materialize_definitions(store, prospective=True)
            delta = DefinitionDelta(
                proposed_definitions=proposed,
                graph_overlay=store._proposal_graph_change_unlocked(),  # noqa: SLF001
            )
        return SemanticState(graph, active, revision, delta)


def materialize_replay(system: RTGSystem | CanonicalStore) -> SemanticState:
    """Require SQL ledger/projection agreement, then materialize the verified projection."""
    store = system if isinstance(system, CanonicalStore) else system.store
    findings = store.verify_projection_from_ledger()
    if findings:
        raise AssertionError(findings[0].summary)
    return materialize_state(system)
