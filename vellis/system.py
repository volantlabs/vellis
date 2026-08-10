"""The one cohesive RTG semantic and transactional boundary.

Realizes ``RTGSystem::'RTG System'`` as far as this slice reaches:
``RTGSystem::'Initialize fresh RTG'``, ``RTGSystem::'Apply graph change'``, and
``RTGSystem::'Assess graph conformance'``, carrying
``VellisRequirements::freshInitialization``,
``VellisRequirements::atomicCanonicalRevision``,
``VellisRequirements::explicitGraphChangeSet``,
``VellisRequirements::definitionCardinality``, and the current-state projection that
``VellisRequirements::historyIndependentCurrentWork`` constrains.

An accepted change is validated whole before it is committed: the resulting graph must
conform, not merely the objects the change touched, because a change can break an
invariant between objects it never mentions. The observational activity record these
operations also owe is the work of the slice that establishes the activity ledger.

Query, validation, history, and recovery are capabilities of this one boundary rather
than independently existing subsystems, so they are methods here rather than injected
collaborators.
"""

from __future__ import annotations

from pathlib import Path

from vellis.canonical import (
    CanonicalChange,
    CanonicalState,
    CanonicalTransitionRecord,
    InitialStateRecord,
    Provenance,
    TransitionKind,
    now,
    transition_findings,
)
from vellis.changes import GraphChange, apply_change, change_findings
from vellis.definitions import GraphDefinitionSet, validate_definition_set
from vellis.graph import Graph, graph_equal
from vellis.json_value import unencodable_reason
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.serialization import unreadable_reason
from vellis.store import AlreadyInitializedError, CanonicalStore
from vellis.validation import assess_graph_conformance

__all__ = ["RTGSystem"]


class RTGSystem:
    """One RTG boundary bound to one durable canonical store."""

    def __init__(self, store: CanonicalStore) -> None:
        self._store = store

    @classmethod
    def open(cls, path: Path) -> RTGSystem:
        """Open, creating the store file when it does not yet exist."""
        return cls(CanonicalStore(path))

    @property
    def store(self) -> CanonicalStore:
        return self._store

    def close(self) -> None:
        self._store.close()

    # --- State ----------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        return self._store.is_initialized()

    def current_state(self) -> CanonicalState:
        """Return the current canonical-state projection.

        This is one projection of replay through the final canonical record, never
        parallel authority, and it is read without traversing history.
        """
        return self._store.current_state()

    def replay(self) -> CanonicalState:
        """Reconstruct canonical state from the ledger itself."""
        return self._store.replay()

    def initial_record(self) -> InitialStateRecord:
        return self._store.initial_record()

    # --- Initialization -------------------------------------------------------------

    def initialize_fresh(
        self,
        initial_definitions: GraphDefinitionSet,
        *,
        provenance: Provenance,
        initialization_summary: str,
    ) -> RevisionedOutcome:
        """Establish revision 0 from one internally valid initial definition set.

        Success establishes an empty graph, exactly those active definitions, no
        definition delta, one initial-state record containing that state, no
        transitions, and an empty activity ledger. Refusal establishes no partial
        canonical or activity state.
        """
        record_findings = _unstorable_record_text(provenance, initialization_summary)
        if record_findings:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    "the record's own text cannot be stored; no canonical state was established"
                ),
                findings=record_findings,
            )
        findings = validate_definition_set(initial_definitions, require_descriptions=True)
        if findings:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the initial definition set is not internally valid "
                    f"({len(findings)} findings); no canonical state was established"
                ),
                findings=findings,
            )
        state = CanonicalState(
            graph=Graph(),
            active_definitions=initial_definitions,
            revision=0,
            definition_delta=None,
        )
        unreadable = unreadable_reason(state)
        if unreadable is not None:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    "this state could not be read back after storage, so it was not established"
                ),
                findings=(ValidationFinding(summary=unreadable),),
            )
        record = InitialStateRecord(
            canonical_state=state,
            initialization_summary=initialization_summary,
            provenance=provenance,
            recorded_at=now(),
        )
        try:
            self._store.initialize(record)
        except AlreadyInitializedError:
            # The store decides this inside its own transaction, so this is the only
            # check on the path; a pre-check here would be a second, racier one.
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    "canonical state is already established; initialization applies only to "
                    "an RTG with no established state"
                ),
                findings=(
                    ValidationFinding(
                        summary="this RTG already has an established canonical state"
                    ),
                ),
            )
        return RevisionedOutcome(
            status=OperationStatus.ACCEPTED,
            summary=f"established revision 0 with {_vocabulary_summary(initial_definitions)}",
            resulting_revision=0,
        )

    # --- Change -----------------------------------------------------------------------

    def apply_graph_change(
        self, change: GraphChange, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Validate a change whole, then commit it as one revision.

        An effective no-op is accepted and advances nothing. A refusal changes no
        canonical state or revision, and leaves active definitions and the delta alone
        either way.
        """
        record_findings = _unstorable_record_text(provenance, None)
        if record_findings:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="the record's own text cannot be stored; the change was not applied",
                findings=record_findings,
            )
        state = self.current_state()
        structural = change_findings(change, state.graph)
        if structural:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the change was not applied ({len(structural)} findings); no canonical "
                    "state or revision changed"
                ),
                findings=structural,
            )
        resulting_graph = apply_change(state.graph, change)
        conformance = assess_graph_conformance(resulting_graph, state.active_definitions)
        if conformance:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the resulting graph would not conform ({len(conformance)} findings); no "
                    "canonical state or revision changed"
                ),
                findings=conformance,
            )
        if graph_equal(resulting_graph, state.graph):
            return RevisionedOutcome(
                status=OperationStatus.ACCEPTED,
                summary="the change is an effective no-op; no revision was created",
            )

        resulting = CanonicalState(
            graph=resulting_graph,
            active_definitions=state.active_definitions,
            revision=state.revision + 1,
            definition_delta=state.definition_delta,
        )
        record = CanonicalTransitionRecord(
            prior_revision=state.revision,
            resulting_revision=resulting.revision,
            kind=TransitionKind.GRAPH_MUTATION,
            change=CanonicalChange(graph_change=change),
            provenance=provenance,
            recorded_at=now(),
        )
        invalid = transition_findings(record)
        if invalid:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="the resulting transition could not be replayed; nothing was committed",
                findings=invalid,
            )
        unreadable = unreadable_reason(resulting)
        if unreadable is not None:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    "the resulting state could not be read back after storage, so it was not "
                    "committed"
                ),
                findings=(ValidationFinding(summary=unreadable),),
            )
        self._store.append_transition(record, resulting)
        return RevisionedOutcome(
            status=OperationStatus.ACCEPTED,
            summary=f"committed revision {resulting.revision}",
            resulting_revision=resulting.revision,
        )

    # --- Assessment -------------------------------------------------------------------

    def check(self) -> ValidationReport:
        """Assess the current graph against the current active definitions.

        The assessment changes no canonical state or revision and reads no canonical
        record; a false ``conforms`` describes the graph, it does not report a failure.
        """
        state = self.current_state()
        findings = assess_graph_conformance(state.graph, state.active_definitions)
        return ValidationReport(
            scope=ValidationScope.GRAPH_CONFORMANCE,
            conforms=not findings,
            evaluated_revision=state.revision,
            findings=findings,
        )


def _unstorable_record_text(
    provenance: Provenance, initialization_summary: str | None
) -> tuple[ValidationFinding, ...]:
    """Report record text that cannot be encoded.

    The definition set and the canonical state are screened by their own checks; a
    record carries text of its own, and it reaches the same store. Every operation that
    writes a record screens it, not only the first one.
    """
    fields = (
        ("initialization summary", initialization_summary),
        ("provenance initiator", provenance.initiator),
        ("provenance source", provenance.source),
    )
    findings: list[ValidationFinding] = []
    for label, text in fields:
        if text is None:
            continue
        reason = unencodable_reason(text)
        if reason is not None:
            findings.append(ValidationFinding(summary=f"the {label} {reason}"))
    return tuple(findings)


def _vocabulary_summary(definitions: GraphDefinitionSet) -> str:
    return (
        f"{len(definitions.anchor_types)} anchor types, "
        f"{len(definitions.associated_data_types)} associated-data types, "
        f"{len(definitions.link_types)} link types, and "
        f"{len(definitions.relationship_constraints)} relationship constraints"
    )
