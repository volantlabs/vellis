"""Explicit graph changes and how they become a new graph.

Realizes ``RTG::'Graph Change'`` and the change-facing obligations of
``VellisRequirements::explicitGraphChangeSet``.

A change says exactly what it does: complete-object upserts and UUID removals, per
object kind. Nothing is implied. Direct associations move only because an associated
data object was upserted carrying different anchor references, and a removal that would
leave something pointing at nothing is refused rather than quietly widened into a
cascade — the owner is told what else they would have to remove.

Applying a change is a pure function of a graph and the change, which is what makes a
transition record replay-sufficient: replay calls the same function this commit did.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from vellis.graph import Anchor, AssociatedDataObject, Graph, GraphObject, Link, ObjectKind
from vellis.outcomes import ValidationFinding

__all__ = ["GraphChange", "apply_change", "change_findings"]


@dataclass(frozen=True, slots=True)
class GraphChange:
    """Complete-object upserts and explicit UUID removals."""

    anchor_upserts: tuple[Anchor, ...] = ()
    associated_data_upserts: tuple[AssociatedDataObject, ...] = ()
    link_upserts: tuple[Link, ...] = ()
    anchor_removals: tuple[str, ...] = ()
    associated_data_removals: tuple[str, ...] = ()
    link_removals: tuple[str, ...] = ()

    def upserts(self) -> tuple[tuple[ObjectKind, GraphObject], ...]:
        return (
            *((ObjectKind.ANCHOR, each) for each in self.anchor_upserts),
            *((ObjectKind.ASSOCIATED_DATA, each) for each in self.associated_data_upserts),
            *((ObjectKind.LINK, each) for each in self.link_upserts),
        )

    def removals(self) -> tuple[tuple[ObjectKind, str], ...]:
        return (
            *((ObjectKind.ANCHOR, each) for each in self.anchor_removals),
            *((ObjectKind.ASSOCIATED_DATA, each) for each in self.associated_data_removals),
            *((ObjectKind.LINK, each) for each in self.link_removals),
        )


def apply_change(graph: Graph, change: GraphChange) -> Graph:
    """Return the graph this change produces.

    This assumes the change is structurally sound; :func:`change_findings` decides that.
    Kept pure so that committing a change and replaying its record run the same code.
    """
    anchors = _replace(graph.anchors, change.anchor_upserts, change.anchor_removals)
    associated = _replace(
        graph.associated_data, change.associated_data_upserts, change.associated_data_removals
    )
    links = _replace(graph.links, change.link_upserts, change.link_removals)
    return Graph(anchors=anchors, associated_data=associated, links=links)


def _replace[T: GraphObject](
    existing: tuple[T, ...], upserts: tuple[T, ...], removals: tuple[str, ...]
) -> tuple[T, ...]:
    removed = frozenset(removals)
    upserted = {each.uuid: each for each in upserts}
    kept: list[T] = []
    for each in existing:
        if each.uuid in upserted:
            kept.append(upserted.pop(each.uuid))
        elif each.uuid not in removed:
            kept.append(each)
    return (*kept, *upserted.values())


# --- Structural validity ------------------------------------------------------------


def change_findings(change: GraphChange, graph: Graph) -> tuple[ValidationFinding, ...]:
    """Return why this change cannot be applied to ``graph``, if it cannot.

    These are the faults that make the command itself incoherent, checked before any
    resulting graph exists. Conformance of the resulting graph is assessed separately.
    """
    findings: list[ValidationFinding] = []
    _check_duplicate_commands(change, findings)
    _check_upsert_removal_conflicts(change, findings)
    _check_removals_are_known(change, graph, findings)
    _check_object_kinds(change, graph, findings)
    _check_no_implicit_cascade(change, graph, findings)
    return tuple(findings)


def _check_duplicate_commands(change: GraphChange, findings: list[ValidationFinding]) -> None:
    _report_repeats(
        (graph_object.uuid for _, graph_object in change.upserts()), "upserted", findings
    )
    _report_repeats((uuid for _, uuid in change.removals()), "removed", findings)


def _report_repeats(uuids: Iterable[str], verb: str, findings: list[ValidationFinding]) -> None:
    seen: set[str] = set()
    for uuid in uuids:
        if uuid in seen:
            findings.append(
                ValidationFinding(
                    summary=f"{uuid!r} is {verb} more than once by one change",
                    implicated_objects=(uuid,),
                )
            )
        seen.add(uuid)


def _check_upsert_removal_conflicts(change: GraphChange, findings: list[ValidationFinding]) -> None:
    upserted = {graph_object.uuid for _, graph_object in change.upserts()}
    for _, uuid in change.removals():
        if uuid in upserted:
            findings.append(
                ValidationFinding(
                    summary=f"{uuid!r} is both upserted and removed by one change",
                    implicated_objects=(uuid,),
                )
            )


def _check_removals_are_known(
    change: GraphChange, graph: Graph, findings: list[ValidationFinding]
) -> None:
    for kind, uuid in change.removals():
        present = _existing_kind(graph, uuid)
        if present is None:
            findings.append(
                ValidationFinding(
                    summary=f"{uuid!r} is removed but no such object exists",
                    implicated_objects=(uuid,),
                )
            )
        elif present is not kind:
            findings.append(
                ValidationFinding(
                    summary=(f"{uuid!r} is removed as {kind.value} but exists as {present.value}"),
                    implicated_objects=(uuid,),
                )
            )


def _check_object_kinds(
    change: GraphChange, graph: Graph, findings: list[ValidationFinding]
) -> None:
    for kind, graph_object in change.upserts():
        present = _existing_kind(graph, graph_object.uuid)
        if present is not None and present is not kind:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{graph_object.uuid!r} already exists as {present.value} and cannot "
                        f"be upserted as {kind.value}; a type key never changes an object's kind"
                    ),
                    implicated_objects=(graph_object.uuid,),
                )
            )


def _existing_kind(graph: Graph, uuid: str) -> ObjectKind | None:
    if graph.anchor(uuid) is not None:
        return ObjectKind.ANCHOR
    if graph.associated_data_object(uuid) is not None:
        return ObjectKind.ASSOCIATED_DATA
    if graph.link(uuid) is not None:
        return ObjectKind.LINK
    return None


def _check_no_implicit_cascade(
    change: GraphChange, graph: Graph, findings: list[ValidationFinding]
) -> None:
    """Refuse a removal that something surviving the change still points at.

    The model forbids an implicit cascade, so this names what the owner would also have
    to remove rather than removing it for them.
    """
    removed = {uuid for _, uuid in change.removals()}
    if not removed:
        return
    upserted = {graph_object.uuid for _, graph_object in change.upserts()}
    resulting = apply_change(graph, change)
    for data in resulting.associated_data:
        for anchor_uuid in data.anchor_uuids:
            if anchor_uuid in removed and data.uuid not in upserted:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"removing {anchor_uuid!r} would leave associated data "
                            f"{data.uuid!r} grounded by it; remove or upsert that object too "
                            "rather than relying on a cascade"
                        ),
                        implicated_objects=(anchor_uuid, data.uuid),
                    )
                )
    for link in resulting.links:
        for role, endpoint in (("source", link.source_uuid), ("target", link.target_uuid)):
            if endpoint in removed and link.uuid not in upserted:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"removing {endpoint!r} would leave link {link.uuid!r} pointing at "
                            f"it as its {role}; remove or upsert that link too rather than "
                            "relying on a cascade"
                        ),
                        implicated_objects=(endpoint, link.uuid),
                    )
                )
