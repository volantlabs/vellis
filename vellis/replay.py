"""Capturing canonical state, and rebuilding it from a base and a tail.

Realizes ``RTG::'Canonical Snapshot'``, ``RTG::'Ledger Tail'``, ``RTG::'Replay Request'``
and ``RTGSystem::'Create canonical snapshot'`` and ``'Reconstruct canonical state'``,
carrying ``VellisRequirements::canonicalSnapshotCompleteness`` and
``VellisRequirements::replayEquivalence``.

A snapshot is a complete capture, not a summary: graph, active definitions, any in-flight
delta, and the revision, bound to the exact record that established it. Anything less and
rebuilding from it would need the history it was meant to replace.

The binding is the delicate part. A tail says which record it follows and a snapshot says
which record it captures, and both say it by identity rather than by revision number.
Two different ledgers can both have a revision 7; joining one's tail onto the other's
snapshot would produce a state that never existed and no bound could detect.

Identity is a digest chained over everything before it, rooted in the ledger's own
identity. Content alone is not enough: two systems seeded from the same snapshot hold
byte-identical records, so a per-record digest would call them the same history. Rooting
the chain in a value only one ledger holds makes lineage part of what a record *is*, and
the chain then carries it forward to every record that follows.

Reconstruction is read-only in both directions: it touches no live state, and no live
state decides its answer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC

from vellis.canonical import (
    CanonicalState,
    CanonicalTransitionRecord,
    InitialStateRecord,
    transition_findings,
)
from vellis.changes import change_findings
from vellis.definitions import validate_definition_set
from vellis.json_value import JsonValue
from vellis.outcomes import OperationStatus, ValidationFinding
from vellis.serialization import (
    encode_canonical_change,
    encode_canonical_state,
    encode_text,
)
from vellis.validation import assess_graph_conformance

__all__ = [
    "CanonicalSnapshot",
    "LedgerTail",
    "ReconstructionResult",
    "ReplayRequest",
    "SnapshotResult",
    "reconstruct",
    "record_identity",
]


def record_identity(record: InitialStateRecord | CanonicalTransitionRecord, *, follows: str) -> str:
    """Return the identity of one canonical record within its lineage.

    ``follows`` is the identity of the record before it, or the ledger's own identity for
    a history base. Every field that distinguishes one record from another participates,
    so a record cannot be altered, reordered, or lifted into another history without its
    identity changing — which is what a tail relies on when it says what it follows.

    The time is normalized the way the store normalizes it, so a record read back has the
    identity it was written with.
    """
    if isinstance(record, InitialStateRecord):
        material: dict[str, JsonValue] = {
            "kind": "initial",
            "state": encode_canonical_state(record.canonical_state),
            "summary": record.initialization_summary,
        }
    else:
        material = {
            "kind": "transition",
            "prior": str(record.prior_revision),
            "resulting": str(record.resulting_revision),
            "transition": record.kind.value,
            "change": encode_canonical_change(record.change),
        }
    material["follows"] = follows
    material["initiator"] = record.provenance.initiator
    material["source"] = record.provenance.source
    material["recordedAt"] = record.recorded_at.astimezone(UTC).isoformat()
    return hashlib.sha256(encode_text(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalSnapshot:
    """A complete capture of canonical state at one revision.

    ``captured_through`` is the identity of the record that established this revision,
    so a later tail can prove it belongs to the same history rather than merely
    continuing from the same number.
    """

    canonical_state: CanonicalState
    captured_through: str

    @property
    def revision(self) -> int:
        return self.canonical_state.revision


@dataclass(frozen=True, slots=True)
class LedgerTail:
    """A contiguous run of transitions, and the exact records it runs between.

    Naming both ends is what makes the run itself contiguous rather than only its seam.
    Checking the first record alone would let a record in the middle be swapped for one
    from another history with the same revision numbers — the very substitution numbers
    cannot detect.
    """

    preceding_record: str
    transitions: tuple[CanonicalTransitionRecord, ...]
    final_record: str


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    """Exactly one base, and optionally a tail that advances it."""

    initial: InitialStateRecord | None = None
    snapshot: CanonicalSnapshot | None = None
    tail: LedgerTail | None = None
    base_identity: str | None = None
    """The identity of the initial record, when the base is one.

    A snapshot already carries the identity it captured; an initial record is a domain
    object with no lineage of its own, so a caller supplying one supplies its identity
    too. Both come from the ledger that owns them.
    """


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    """The outcome of one reconstruction.

    A rejected result carries no state at all: a partially applied tail is not a smaller
    reconstruction, it is a state the ledger never held.
    """

    status: OperationStatus
    summary: str
    findings: tuple[ValidationFinding, ...] = ()
    canonical_state: CanonicalState | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


def reconstruct(request: ReplayRequest) -> ReconstructionResult:
    """Rebuild canonical state from one base and an optional contiguous tail."""
    findings = _base_findings(request)
    if findings:
        return _refused(findings)

    if request.snapshot is not None:
        state = request.snapshot.canonical_state
        base_identity = request.snapshot.captured_through
    else:
        assert request.initial is not None
        state = request.initial.canonical_state
        base_identity = request.base_identity or ""

    unsound = _state_findings(state)
    if unsound:
        return _refused(unsound)

    tail = request.tail
    if tail is None:
        return ReconstructionResult(
            status=OperationStatus.ACCEPTED,
            summary=f"reconstructed revision {state.revision} from its base alone",
            canonical_state=state,
        )

    if tail.preceding_record != base_identity:
        return _refused(
            (
                ValidationFinding(
                    summary=(
                        "the tail follows a different record than the base; equal revision "
                        "numbers do not make two ledgers one"
                    )
                ),
            )
        )

    for index, record in enumerate(tail.transitions):
        invalid = transition_findings(record)
        if invalid:
            return _refused(invalid)
        if record.prior_revision != state.revision:
            return _refused(
                (
                    ValidationFinding(
                        summary=(
                            f"tail transition {index} follows revision {record.prior_revision} "
                            f"but reconstruction is at {state.revision}"
                        )
                    ),
                )
            )
        if record.change.graph_change is not None:
            structural = change_findings(record.change.graph_change, state.graph)
            if structural:
                return _refused(structural)
        state = _advance(state, record)
        # Every intermediate state, not only the last. The commit path validates what each
        # change would produce, so a tail that passes through a state no commit could have
        # written is not a smaller reconstruction — it is one of a history that never was.
        unsound = _state_findings(state)
        if unsound:
            return _refused(unsound)
        base_identity = record_identity(record, follows=base_identity)

    if base_identity != tail.final_record:
        return _refused(
            (
                ValidationFinding(
                    summary=(
                        "the tail does not end at the record it names; a run whose interior "
                        "came from elsewhere is not this history"
                    )
                ),
            )
        )
    return ReconstructionResult(
        status=OperationStatus.ACCEPTED,
        summary=(
            f"reconstructed revision {state.revision} from its base and "
            f"{len(tail.transitions)} transitions"
        ),
        canonical_state=state,
    )


def _base_findings(request: ReplayRequest) -> tuple[ValidationFinding, ...]:
    """Exactly one base: two would leave which history was rebuilt ambiguous."""
    bases = [each for each in (request.initial, request.snapshot) if each is not None]
    if not bases:
        return (
            ValidationFinding(summary="a replay request needs an initial record or a snapshot"),
        )
    if request.initial is not None and request.tail is not None and not request.base_identity:
        return (
            ValidationFinding(
                summary="an initial record used as a base must say what identity it has"
            ),
        )
    if len(bases) > 1:
        return (
            ValidationFinding(
                summary="a replay request uses exactly one base, not an initial record and a "
                "snapshot"
            ),
        )
    if request.tail is not None and not request.tail.transitions:
        return (ValidationFinding(summary="a tail carries at least one transition"),)
    return ()


def _state_findings(state: CanonicalState) -> tuple[ValidationFinding, ...]:
    """Return every reason ``state`` is not one this system could have committed.

    The same two questions the write paths ask: is the vocabulary internally valid, and
    does the graph conform under it. Asking less here would let a reconstruction seed a
    system with definitions ``initialize_fresh`` itself would refuse.
    """
    return (
        *validate_definition_set(state.active_definitions, require_descriptions=True),
        *assess_graph_conformance(state.graph, state.active_definitions),
    )


def _refused(findings: tuple[ValidationFinding, ...]) -> ReconstructionResult:
    return ReconstructionResult(
        status=OperationStatus.REJECTED,
        summary=f"the state was not reconstructed ({len(findings)} findings)",
        findings=findings,
    )


def _advance(state: CanonicalState, record: CanonicalTransitionRecord) -> CanonicalState:
    """Apply one transition the same way the commit that wrote it did."""
    from vellis.canonical import replay

    return replay(
        InitialStateRecord(
            canonical_state=state,
            initialization_summary="",
            provenance=record.provenance,
            recorded_at=record.recorded_at,
        ),
        (record,),
    )


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    """The outcome of one capture. A refusal carries no snapshot."""

    status: OperationStatus
    summary: str
    findings: tuple[ValidationFinding, ...] = ()
    snapshot: CanonicalSnapshot | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED
