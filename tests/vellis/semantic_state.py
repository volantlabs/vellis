"""Small complete-state values used only by independent test oracles."""

from dataclasses import dataclass

from vellis.changes import GraphChange
from vellis.definitions import GraphDefinitionSet, definition_set_equal
from vellis.graph import Graph, graph_equal
from vellis.normalized import object_identity


@dataclass(frozen=True, slots=True)
class DefinitionDelta:
    proposed_definitions: GraphDefinitionSet
    graph_overlay: GraphChange = GraphChange()


def definition_delta_equal(left: DefinitionDelta | None, right: DefinitionDelta | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return definition_set_equal(left.proposed_definitions, right.proposed_definitions) and (
        {
            (kind.value, value.uuid): object_identity(value)
            for kind, value in left.graph_overlay.upserts()
        }
        == {
            (kind.value, value.uuid): object_identity(value)
            for kind, value in right.graph_overlay.upserts()
        }
        and sorted(left.graph_overlay.removals()) == sorted(right.graph_overlay.removals())
    )


@dataclass(frozen=True, slots=True)
class SemanticState:
    graph: Graph
    active_definitions: GraphDefinitionSet
    revision: int
    definition_delta: DefinitionDelta | None = None


def semantic_state_equal(left: SemanticState, right: SemanticState) -> bool:
    return (
        left.revision == right.revision
        and graph_equal(left.graph, right.graph)
        and definition_set_equal(left.active_definitions, right.active_definitions)
        and definition_delta_equal(left.definition_delta, right.definition_delta)
    )
