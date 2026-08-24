"""Small brute-force topology oracle independent of VEL2 SQL and repositories."""

from __future__ import annotations

import itertools
from collections.abc import Mapping

from vellis.domain import Anchor, AssociatedData, GraphObject, Link
from vellis.query_domain import PatternMatch, PatternNodeKind, PatternSelection


def evaluate_pattern(
    selection: PatternSelection, graph: tuple[GraphObject, ...]
) -> tuple[PatternMatch, ...]:
    nodes = tuple(_node_candidates(node, graph) for node in selection.nodes)
    links = tuple(_link_candidates(link, graph) for link in selection.links)
    matches: list[PatternMatch] = []
    node_names = tuple(node.name for node in selection.nodes)
    link_names = tuple(link.name for link in selection.links)
    for node_values in itertools.product(*nodes):
        if len({value.uuid for value in node_values}) != len(node_values):
            continue
        by_name = dict(zip(node_names, node_values, strict=True))
        if not _associations_hold(selection, by_name):
            continue
        for link_values in itertools.product(*links) if links else ((),):
            if len({value.uuid for value in link_values}) != len(link_values):
                continue
            if not _links_hold(selection, by_name, link_values):
                continue
            bindings = tuple(
                (name, value.uuid) for name, value in zip(node_names, node_values, strict=True)
            )
            bindings += tuple(
                (name, value.uuid) for name, value in zip(link_names, link_values, strict=True)
            )
            matches.append(PatternMatch(bindings))
    return tuple(sorted(set(matches), key=lambda match: tuple(uuid for _, uuid in match.bindings)))


def _node_candidates(node, graph: tuple[GraphObject, ...]):
    expected = Anchor if node.kind is PatternNodeKind.ANCHOR else AssociatedData
    return tuple(
        value
        for value in graph
        if isinstance(value, expected)
        and (not node.type_keys or value.type_key in node.type_keys)
        and (not node.uuids or value.uuid in node.uuids)
    )


def _link_candidates(selector, graph: tuple[GraphObject, ...]) -> tuple[Link, ...]:
    return tuple(
        value
        for value in graph
        if isinstance(value, Link)
        and (not selector.type_keys or value.type_key in selector.type_keys)
        and (not selector.uuids or value.uuid in selector.uuids)
    )


def _associations_hold(selection: PatternSelection, by_name: Mapping[str, GraphObject]) -> bool:
    for value in selection.direct_associations:
        data = by_name[value.associated_data]
        if (
            not isinstance(data, AssociatedData)
            or by_name[value.anchor].uuid not in data.anchor_uuids
        ):
            return False
    return True


def _links_hold(
    selection: PatternSelection,
    by_name: Mapping[str, GraphObject],
    links: tuple[Link, ...],
) -> bool:
    return all(
        value.source_uuid == by_name[selector.source].uuid
        and value.target_uuid == by_name[selector.target].uuid
        for selector, value in zip(selection.links, links, strict=True)
    )
