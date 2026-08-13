"""The one cohesive RTG semantic and transactional boundary.

Realizes ``RTGSystem::'RTG System'`` as far as this slice reaches:
``RTGSystem::'Initialize fresh RTG'``, ``RTGSystem::'Apply graph change'``,
``RTGSystem::'Assess graph conformance'``, the current-state half of
``RTGSystem::'Discover evaluated graph definitions'``, and the four definition-delta
operations — ``'Create or edit definition delta'``, ``'Review definition delta'``,
``'Activate definition delta'``, and ``'Discard definition delta'`` — carrying
``VellisRequirements::freshInitialization``,
``VellisRequirements::atomicCanonicalRevision``,
``VellisRequirements::explicitGraphChangeSet``,
``VellisRequirements::definitionCardinality``, and the current-state projection that
``VellisRequirements::historyIndependentCurrentWork`` constrains.

An accepted change is validated whole before it is committed: the resulting graph must
conform, not merely the objects the change touched, because a change can break an
invariant between objects it never mentions.

Reads, validation, and refused operations leave an observation in the activity ledger.
Accepted changes do not: they are already in the canonical ledger, and that one is
authority. Observing sits outside every canonical transaction, so a ledger the owner may
empty can never decide whether a change happened.

Query, validation, history, and recovery are capabilities of this one boundary rather
than independently existing subsystems, so they are methods here rather than injected
collaborators.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vellis.activity import (
    ActivityHistoryEntry,
    ActivityRecord,
    CanonicalHistoryEntry,
    HistoryKind,
    HistoryQuery,
    HistoryResult,
    RetentionDecision,
    history_query_findings,
    retention_findings,
)
from vellis.canonical import (
    CanonicalChange,
    CanonicalState,
    CanonicalTransitionRecord,
    DefinitionDelta,
    DefinitionDeltaDisposition,
    InitialStateRecord,
    Provenance,
    ReplayError,
    TransitionKind,
    now,
    replay,
    transition_findings,
)
from vellis.changes import GraphChange, apply_change, change_findings
from vellis.definitions import (
    GraphDefinitionSet,
    definition_set_equal,
)
from vellis.discovery import (
    AnchorDefinitionDetail,
    DefinitionInspectionRequest,
    DefinitionInspectionResult,
    DefinitionSummaryResult,
    anchor_neighborhood,
    inspection_findings,
    summarize_anchor_types,
)
from vellis.governance import DefinitionDeltaResult, assess_proposal
from vellis.graph import Graph, graph_equal
from vellis.history import (
    MAXIMUM_REVISION,
    EvaluatedDefinitions,
    HistoricalSelection,
    RevisionSelection,
    definitions_through,
    selection_findings,
)
from vellis.json_value import unencodable_reason
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.query import GraphQuery, GraphQueryResult, evaluate_query
from vellis.replay import (
    CanonicalSnapshot,
    LedgerTail,
    ReconstructionResult,
    ReplayRequest,
    SnapshotResult,
    reconstruct,
    record_identity,
    state_findings,
)
from vellis.serialization import unreadable_reason
from vellis.store import (
    AlreadyInitializedError,
    CanonicalStore,
    ConcurrentRevisionError,
    NotInitializedError,
    StoreError,
)
from vellis.validation import assess_graph_conformance

__all__ = ["UNATTRIBUTED", "RTGSystem"]

# The model attributes reads to an agent and retention to the owner, so a library that
# cannot see its caller must not name one. This says plainly that nobody was identified;
# a boundary that knows who is asking passes real provenance and this is never recorded.
UNATTRIBUTED = Provenance(initiator="unattributed")


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

    def _working_state(self) -> CanonicalState:
        """Materialize the durable SQLite projection for graph-bearing domain work."""
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
        return self._establish(
            CanonicalState(
                graph=Graph(),
                active_definitions=initial_definitions,
                revision=0,
                definition_delta=None,
            ),
            provenance=provenance,
            initialization_summary=initialization_summary,
        )

    def _establish(
        self,
        state: CanonicalState,
        *,
        provenance: Provenance,
        initialization_summary: str,
    ) -> RevisionedOutcome:
        """Write one initial record and its projection, or establish nothing.

        Shared by both ways of starting, because what it means to have a history base is
        the same either way: one record containing the whole of it, and no claim about
        anything before.
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
        if not 0 <= state.revision <= MAXIMUM_REVISION:
            # A base outside what a revision can be would be a history nothing could
            # name: below zero no selector reaches it, and above the ledger's range the
            # next transition could never be written.
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"revision {state.revision} is not one a ledger can hold; no canonical "
                    "state was established"
                ),
                findings=(
                    ValidationFinding(
                        summary=f"a history base names a committed revision, not {state.revision}"
                    ),
                ),
            )
        unsound = state_findings(state)
        if unsound:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the state is not one this system could have committed "
                    f"({len(unsound)} findings); no canonical state was established"
                ),
                findings=unsound,
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
        except StoreError as error:
            if not isinstance(error, AlreadyInitializedError):
                return RevisionedOutcome(
                    status=OperationStatus.FAILED,
                    summary=f"no canonical state was established: {error}",
                    findings=(ValidationFinding(summary=str(error)),),
                )
            # The store decides "already established" inside its own transaction, so this
            # is the only check on the path; a pre-check here would be a second, racier one.
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
            summary=(
                f"established revision {state.revision} with "
                f"{_vocabulary_summary(state.active_definitions)}"
            ),
            resulting_revision=state.revision,
        )

    def initialize_from_snapshot(
        self,
        request: ReplayRequest,
        *,
        provenance: Provenance,
        initialization_summary: str,
    ) -> RevisionedOutcome:
        """Begin a new lineage from a state that already existed somewhere else.

        The reconstructed state becomes this system's history base at the revision it
        reached, not at zero. Renumbering it would claim the transitions that produced it,
        and this ledger does not have them; keeping the revision says plainly that the
        history starts partway through.

        No starting vocabulary is offered or overlaid. A snapshot already carries one, and
        a fresh-start choice on top of it would be answering a question the owner already
        answered.
        """
        result = reconstruct(request)
        if result.canonical_state is None:
            return RevisionedOutcome(
                status=result.status,
                summary=result.summary,
                findings=result.findings,
            )
        return self._establish(
            result.canonical_state,
            provenance=provenance,
            initialization_summary=initialization_summary,
        )

    def initialize_from_recovery(
        self,
        graph: Graph,
        active_definitions: GraphDefinitionSet,
        *,
        provenance: Provenance,
        initialization_summary: str,
    ) -> RevisionedOutcome:
        """Begin at revision 0 from content recovered somewhere Vellis cannot replay.

        Unlike a snapshot of this system's own kind, a recovery candidate carries no
        history to inherit: what came before it happened in a system whose ledger this one
        never had and could not read. So the lineage starts at zero — not because the
        content is new, but because this is the first thing that ever happened here.

        The graph arrives unchanged. Whether it can be held at all was settled while the
        candidate was formed, and is asked again here for the same reason every other
        write asks: what establishes state decides whether it may.
        """
        return self._establish(
            CanonicalState(
                graph=graph,
                active_definitions=active_definitions,
                revision=0,
                definition_delta=None,
            ),
            provenance=provenance,
            initialization_summary=initialization_summary,
        )

    # --- Change -----------------------------------------------------------------------

    def apply_graph_change(
        self, change: GraphChange, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Validate a change whole, then commit it as one revision."""
        outcome = self._apply_graph_change(change, provenance=provenance)
        self._observe_outcome(
            "graphChange",
            outcome.status,
            scope=_change_scope(change),
            summary=outcome.summary,
            provenance=provenance,
            evaluated_revision=outcome.resulting_revision,
        )
        return outcome

    def _apply_graph_change(
        self, change: GraphChange, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Validate a change whole, then commit it as one revision.

        An effective no-op is accepted and advances nothing. A refusal changes no
        canonical state or revision, and leaves active definitions and the delta alone
        either way.
        """
        try:
            state = self._working_state()
        except NotInitializedError as error:
            # A determinate precondition, like initializing an established RTG: the caller
            # can act on it. A damaged store cannot be acted on, only reported.
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="no canonical state is established; initialize this RTG first",
                findings=(ValidationFinding(summary=str(error)),),
            )
        except StoreError as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the change could not be applied: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
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
        return self._commit(
            state,
            TransitionKind.GRAPH_MUTATION,
            CanonicalChange(graph_change=change),
            active_definitions=state.active_definitions,
            graph=resulting_graph,
            delta=state.definition_delta,
            provenance=provenance,
        )

    # --- Discovery --------------------------------------------------------------------

    def definition_summary(
        self,
        *,
        selection: HistoricalSelection | None = None,
        provenance: Provenance = UNATTRIBUTED,
    ) -> DefinitionSummaryResult:
        """Return every anchor type active at the current or a selected state.

        A caller reads this first and an inspection second; both carry the revision they
        were evaluated at, which is how a caller notices that the definitions moved
        between the two reads.
        """
        if selection is not None:
            result = self._historical_summary(selection)
            self._observe(
                "definitionSummary",
                result.status,
                scope="every active anchor type at a selected state",
                summary=result.summary,
                provenance=provenance,
                evaluated_revision=result.evaluated_revision,
            )
            return result
        try:
            revision, definitions, delta = self._store.current_definitions()
        except StoreError as error:
            failed = DefinitionSummaryResult(
                status=OperationStatus.FAILED,
                summary=f"the definition summary could not be returned completely: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
            self._observe(
                "definitionSummary",
                failed.status,
                scope="every active anchor type",
                summary=failed.summary,
                provenance=provenance,
            )
            return failed
        result = DefinitionSummaryResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{len(definitions.anchor_types)} active anchor types",
            anchor_types=summarize_anchor_types(definitions),
            evaluated_revision=revision,
            delta_present=delta is not None,
        )
        self._observe(
            "definitionSummary",
            result.status,
            scope="every active anchor type",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    def inspect_definitions(
        self,
        request: DefinitionInspectionRequest,
        *,
        selection: HistoricalSelection | None = None,
        provenance: Provenance = UNATTRIBUTED,
    ) -> DefinitionInspectionResult:
        """Return the complete neighborhood of each selected anchor type, then or now.

        An unknown or duplicated selection yields findings and nothing else — not the
        details that happened to resolve — because a partial answer would read as a
        complete one.
        """
        result = self._inspect(request, selection or request.historical_selection)
        self._observe(
            "definitionInspection",
            result.status,
            scope=f"{len(request.anchor_type_keys)} selected anchor types",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    def _inspect(
        self, request: DefinitionInspectionRequest, selection: HistoricalSelection | None = None
    ) -> DefinitionInspectionResult:
        if selection is not None:
            return self._historical_inspection(request, selection)
        try:
            revision, definitions, _ = self._store.current_definitions()
        except StoreError as error:
            return DefinitionInspectionResult(
                status=OperationStatus.FAILED,
                summary=f"the selection could not be answered completely: {error}",
                request=request,
                findings=(ValidationFinding(summary=str(error)),),
            )
        findings = inspection_findings(request, definitions)
        if findings:
            return DefinitionInspectionResult(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the selection could not be answered ({len(findings)} findings); no "
                    "details were returned"
                ),
                request=request,
                findings=findings,
            )
        details: tuple[AnchorDefinitionDetail, ...] = tuple(
            anchor_neighborhood(type_key, definitions) for type_key in request.anchor_type_keys
        )
        return DefinitionInspectionResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{len(details)} anchor neighborhoods",
            request=request,
            anchor_details=details,
            evaluated_revision=revision,
        )

    # --- The sole proposal ------------------------------------------------------------

    def definition_delta(self, *, provenance: Provenance = UNATTRIBUTED) -> DefinitionDeltaResult:
        """Return the sole proposal with a current assessment, or normal absence."""
        try:
            state = self._working_state()
        except StoreError as error:
            result = DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be retrieved: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        else:
            result = _delta_result(state, "the current proposal")
        self._observe(
            "definitionDelta",
            result.status,
            scope="the sole prospective definition set",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    def set_definition_delta(
        self, proposed: GraphDefinitionSet, *, provenance: Provenance
    ) -> DefinitionDeltaResult:
        """Create or replace the sole proposal."""
        result = self._set_definition_delta(proposed, provenance=provenance)
        self._observe_outcome(
            "definitionDeltaChange",
            result.status,
            scope="the sole prospective definition set",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    def _set_definition_delta(
        self, proposed: GraphDefinitionSet, *, provenance: Provenance
    ) -> DefinitionDeltaResult:
        """Create or replace the sole proposal.

        A proposal that already says what the current one says, or what the active set
        says when there is no proposal, changes nothing and advances nothing. Offering
        the active set while a different proposal stands is refused rather than read as
        a discard: clearing a proposal is its own operation, and guessing here would
        throw away work the owner did not ask to lose.
        """
        try:
            state = self._working_state()
        except StoreError as error:
            return DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be staged: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        current = state.definition_delta

        if current is not None and definition_set_equal(proposed, current.proposed_definitions):
            return _delta_result(state, "the proposal is unchanged; no revision was created")
        if current is None and definition_set_equal(proposed, state.active_definitions):
            return _delta_result(
                state,
                "the proposal matches the active definitions; nothing was staged",
                absent_summary="the proposal matches the active definitions; nothing was staged",
            )
        if current is not None and definition_set_equal(proposed, state.active_definitions):
            return DefinitionDeltaResult(
                status=OperationStatus.REJECTED,
                summary=(
                    "staging the active definitions would discard the current proposal; use "
                    "the discard operation to do that deliberately"
                ),
                findings=(
                    ValidationFinding(
                        summary="a proposal equal to the active set cannot implicitly discard"
                    ),
                ),
            )

        delta = DefinitionDelta(proposed_definitions=proposed)
        outcome = self._commit(
            state,
            TransitionKind.DEFINITION_DELTA_CHANGE,
            CanonicalChange(
                delta_disposition=DefinitionDeltaDisposition.PRESENT, definition_delta=delta
            ),
            active_definitions=state.active_definitions,
            graph=state.graph,
            delta=delta,
            provenance=provenance,
        )
        if not outcome.accepted:
            return DefinitionDeltaResult(
                status=outcome.status, summary=outcome.summary, findings=outcome.findings
            )
        return _delta_result(
            CanonicalState(
                graph=state.graph,
                active_definitions=state.active_definitions,
                revision=state.revision + 1,
                definition_delta=delta,
            ),
            f"staged the proposal at revision {outcome.resulting_revision}",
            resulting_revision=outcome.resulting_revision,
        )

    def activate_definition_delta(self, *, provenance: Provenance) -> RevisionedOutcome:
        """Activate the sole proposal, or preserve everything."""
        outcome = self._activate_definition_delta(provenance=provenance)
        self._observe_outcome(
            "definitionActivation",
            outcome.status,
            scope="the active definition set",
            summary=outcome.summary,
            provenance=provenance,
            evaluated_revision=outcome.resulting_revision,
        )
        return outcome

    def _activate_definition_delta(self, *, provenance: Provenance) -> RevisionedOutcome:
        """Activate the sole proposal, or preserve everything.

        Activation is the gate the working proposal was allowed to skip: every
        description present, the proposal internally valid, and the graph already
        conforming under it.
        """
        try:
            state = self._working_state()
        except StoreError as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be activated: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        if state.definition_delta is None:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="there is no proposal to activate",
            )
        proposed = state.definition_delta.proposed_definitions
        assessment = assess_proposal(proposed, state.graph, state.revision)
        if not assessment.conforms:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the proposal cannot be activated ({len(assessment.findings)} findings); "
                    "graph, active definitions, proposal, and revision are unchanged"
                ),
                findings=assessment.findings,
            )
        return self._commit(
            state,
            TransitionKind.DEFINITION_ACTIVATION,
            CanonicalChange(
                delta_disposition=DefinitionDeltaDisposition.ABSENT,
                active_definitions=proposed,
            ),
            active_definitions=proposed,
            graph=state.graph,
            delta=None,
            provenance=provenance,
        )

    def discard_definition_delta(self, *, provenance: Provenance) -> RevisionedOutcome:
        """Clear the sole proposal, or report that there is none."""
        outcome = self._discard_definition_delta(provenance=provenance)
        self._observe_outcome(
            "definitionDeltaDiscard",
            outcome.status,
            scope="the sole prospective definition set",
            summary=outcome.summary,
            provenance=provenance,
        )
        return outcome

    def _discard_definition_delta(self, *, provenance: Provenance) -> RevisionedOutcome:
        """Clear the sole proposal, or report that there is none."""
        try:
            state = self._working_state()
        except StoreError as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be discarded: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        if state.definition_delta is None:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="there is no proposal to discard",
            )
        return self._commit(
            state,
            TransitionKind.DEFINITION_DELTA_CHANGE,
            CanonicalChange(delta_disposition=DefinitionDeltaDisposition.ABSENT),
            active_definitions=state.active_definitions,
            graph=state.graph,
            delta=None,
            provenance=provenance,
        )

    def _commit(
        self,
        state: CanonicalState,
        kind: TransitionKind,
        change: CanonicalChange,
        *,
        active_definitions: GraphDefinitionSet,
        graph: Graph,
        delta: DefinitionDelta | None,
        provenance: Provenance,
    ) -> RevisionedOutcome:
        """Commit one canonical transition, or refuse without effect."""
        record_findings = _unstorable_record_text(provenance, None)
        if record_findings:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="the record's own text cannot be stored; nothing was committed",
                findings=record_findings,
            )
        resulting = CanonicalState(
            graph=graph,
            active_definitions=active_definitions,
            revision=state.revision + 1,
            definition_delta=delta,
        )
        record = CanonicalTransitionRecord(
            prior_revision=state.revision,
            resulting_revision=resulting.revision,
            kind=kind,
            change=change,
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
        try:
            self._store.append_transition(record, resulting)
        except ConcurrentRevisionError as error:
            # Another writer got there first. The request was well formed and nothing was
            # committed, so this is a refusal the caller can act on by reading and
            # retrying — not a report that something broke.
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="canonical state moved while this change was being committed",
                findings=(ValidationFinding(summary=str(error)),),
            )
        except StoreError as error:
            # The store rolls back before re-raising, so nothing was committed and the
            # status is safely reportable rather than an exception crossing the boundary.
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the transition could not be committed: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        return RevisionedOutcome(
            status=OperationStatus.ACCEPTED,
            summary=f"committed revision {resulting.revision}",
            resulting_revision=resulting.revision,
        )

    # --- Query ------------------------------------------------------------------------

    def query_graph(
        self,
        query: GraphQuery,
        *,
        selection: HistoricalSelection | None = None,
        provenance: Provenance = UNATTRIBUTED,
    ) -> GraphQueryResult:
        """Answer one bounded semantic query, or refuse it whole.

        A query changes no canonical state or revision. A current query reads no canonical
        record either; a historical one replays the transitions it needs, which is the
        cost the model permits reconstruction and denies current work.
        """
        chosen = selection or query.historical_selection
        if chosen is not None:
            result = self._historical_query(query, chosen)
            self._observe(
                "query",
                result.status,
                scope=_query_scope(query),
                summary=result.summary,
                provenance=provenance,
                evaluated_revision=result.evaluated_revision,
            )
            return result
        try:
            result = self._store.evaluate_current_query(query)
        except NotInitializedError as error:
            result = GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="no canonical state is established; initialize this RTG first",
                findings=(ValidationFinding(summary=str(error)),),
                query=query,
            )
        except StoreError as error:
            result = GraphQueryResult(
                status=OperationStatus.FAILED,
                summary=f"the query could not be evaluated: {error}",
                findings=(ValidationFinding(summary=str(error)),),
                query=query,
            )
        self._observe(
            "query",
            result.status,
            scope=_query_scope(query),
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    # --- Observation ------------------------------------------------------------------

    def _observe_outcome(
        self,
        capability: str,
        outcome: OperationStatus,
        *,
        scope: str,
        summary: str,
        provenance: Provenance,
        evaluated_revision: int | None = None,
    ) -> None:
        """Observe a mutation, which the ledger records only when it did not happen.

        An accepted mutation is already in the canonical ledger, and that ledger is
        authority. Copying it here would put half of an owner's state-change history
        behind a delete button meant for observations.
        """
        if outcome is OperationStatus.ACCEPTED:
            return
        self._observe(
            capability,
            outcome,
            scope=scope,
            summary=summary,
            provenance=provenance,
            evaluated_revision=evaluated_revision,
        )

    def _observe(
        self,
        capability: str,
        outcome: OperationStatus,
        *,
        scope: str,
        summary: str,
        provenance: Provenance,
        evaluated_revision: int | None = None,
    ) -> None:
        """Append one observation after an outcome has been determined.

        Deliberately outside every canonical transaction. Observing is not part of what
        an operation does to memory, and a ledger that could roll a commit back would
        make it so. A store that cannot record the observation has still done the work,
        so the outcome the caller already holds stands.
        """
        if _unstorable_record_text(provenance, summary) or _unstorable_record_text(
            provenance, scope
        ):
            # An operation refused for text it could not store must not then try to store
            # that same text in its own observation. The outcome the caller holds stands.
            return
        try:
            self._store.append_activity(
                ActivityRecord(
                    capability=capability,
                    outcome_category=outcome,
                    semantic_scope=scope,
                    summary=summary,
                    provenance=provenance,
                    recorded_at=now(),
                    evaluated_revision=evaluated_revision,
                )
            )
        except StoreError:
            return

    # --- Reading a state that has passed ------------------------------------------------

    def _resolve(self, selection: HistoricalSelection) -> tuple[int, tuple[ValidationFinding, ...]]:
        """Resolve a selector to the revision it names, or say why it does not name one."""
        findings = selection_findings(selection)
        if findings:
            return 0, findings
        if isinstance(selection, RevisionSelection):
            if not self._store.has_revision(selection.revision):
                return 0, (
                    ValidationFinding(
                        summary=(
                            f"no record in this ledger established revision {selection.revision}"
                        )
                    ),
                )
            return selection.revision, ()
        resolved = self._store.revision_at(selection.time)
        if resolved is None:
            return 0, (
                ValidationFinding(
                    summary=(
                        f"nothing had been committed at or before {selection.time.isoformat()}"
                    )
                ),
            )
        return resolved, ()

    def _definitions_at(self, revision: int) -> EvaluatedDefinitions:
        """Rebuild the vocabulary at one revision without replaying graph work."""
        return definitions_through(
            self._store.initial_record().canonical_state,
            self._store.definition_transitions_through(revision),
        )

    def _state_at(self, revision: int) -> CanonicalState:
        """Rebuild complete state at one revision. A graph needs its transitions."""
        base = self._store.initial_record()
        return replay(base, self._store.transitions_through(revision))

    def _historical_summary(self, selection: HistoricalSelection) -> DefinitionSummaryResult:
        try:
            return self._summary_at(selection)
        except StoreError as error:
            # A historical read answers the way a current one does. Letting a store fault
            # escape here would make the same fault an outcome on one path and a traceback
            # on the other, and would leave the observation unwritten.
            return DefinitionSummaryResult(
                status=OperationStatus.FAILED,
                summary=f"the selected state could not be read: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )

    def _summary_at(self, selection: HistoricalSelection) -> DefinitionSummaryResult:
        revision, findings = self._resolve(selection)
        if findings:
            return DefinitionSummaryResult(
                status=OperationStatus.REJECTED,
                summary=f"the selected state could not be resolved ({len(findings)} findings)",
                findings=findings,
            )
        evaluated = self._definitions_at(revision)
        return DefinitionSummaryResult(
            status=OperationStatus.ACCEPTED,
            summary=(
                f"{len(evaluated.active_definitions.anchor_types)} anchor types at "
                f"revision {revision}"
            ),
            anchor_types=summarize_anchor_types(evaluated.active_definitions),
            evaluated_revision=revision,
            delta_present=evaluated.delta_present,
        )

    def _historical_inspection(
        self, request: DefinitionInspectionRequest, selection: HistoricalSelection
    ) -> DefinitionInspectionResult:
        try:
            return self._inspection_at(request, selection)
        except StoreError as error:
            return DefinitionInspectionResult(
                status=OperationStatus.FAILED,
                summary=f"the selected state could not be read: {error}",
                request=request,
                findings=(ValidationFinding(summary=str(error)),),
            )

    def _inspection_at(
        self, request: DefinitionInspectionRequest, selection: HistoricalSelection
    ) -> DefinitionInspectionResult:
        revision, findings = self._resolve(selection)
        if findings:
            return DefinitionInspectionResult(
                status=OperationStatus.REJECTED,
                summary=f"the selected state could not be resolved ({len(findings)} findings)",
                request=request,
                findings=findings,
            )
        definitions = self._definitions_at(revision).active_definitions
        findings = inspection_findings(request, definitions)
        if findings:
            return DefinitionInspectionResult(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the selection could not be answered ({len(findings)} findings); "
                    "no details were returned"
                ),
                request=request,
                findings=findings,
            )
        return DefinitionInspectionResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{len(request.anchor_type_keys)} anchor neighborhoods at revision {revision}",
            request=request,
            anchor_details=tuple(
                anchor_neighborhood(type_key, definitions) for type_key in request.anchor_type_keys
            ),
            evaluated_revision=revision,
        )

    def _historical_query(
        self, query: GraphQuery, selection: HistoricalSelection
    ) -> GraphQueryResult:
        try:
            return self._query_at(query, selection)
        except (StoreError, ReplayError) as error:
            # A ledger that cannot be replayed is a failure to answer, not an answer.
            return GraphQueryResult(
                status=OperationStatus.FAILED,
                summary=f"the selected state could not be reconstructed: {error}",
                query=query,
                findings=(ValidationFinding(summary=str(error)),),
            )

    def _query_at(self, query: GraphQuery, selection: HistoricalSelection) -> GraphQueryResult:
        revision, findings = self._resolve(selection)
        if findings:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary=f"the selected state could not be resolved ({len(findings)} findings)",
                query=query,
                findings=findings,
            )
        state = self._state_at(revision)
        # The same evaluation as current state, against the definitions in force then.
        # A query means what it means; only the state it is asked of changes.
        return evaluate_query(query, state.active_definitions, state.graph, revision)

    # --- Capture and rebuild ------------------------------------------------------------

    def create_snapshot(self, *, provenance: Provenance = UNATTRIBUTED) -> SnapshotResult:
        """Capture complete canonical state, bound to the record that established it.

        Reads nothing it does not return and changes nothing at all: a capture that moved
        the revision would be capturing a state that no longer existed by the time it
        finished.
        """
        try:
            revision, establishing = self._store.establishing_record()
            state = self.current_state()
            if state.revision != revision:
                # Another writer committed between the two reads. A snapshot bound to a
                # record that established a different revision is not a smaller capture;
                # it is one of a state that never existed.
                raise ConcurrentRevisionError(
                    f"canonical state moved from revision {revision} to {state.revision} "
                    "while it was being captured"
                )
            captured = self._identity_through(establishing)
        except NotInitializedError as error:
            result = SnapshotResult(
                status=OperationStatus.REJECTED,
                summary="no canonical state is established; initialize this RTG first",
                findings=(ValidationFinding(summary=str(error)),),
            )
        except StoreError as error:
            result = SnapshotResult(
                status=OperationStatus.FAILED,
                summary=f"the snapshot could not be captured: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        else:
            result = SnapshotResult(
                status=OperationStatus.ACCEPTED,
                summary=f"captured revision {state.revision}",
                snapshot=CanonicalSnapshot(canonical_state=state, captured_through=captured),
            )
        self._observe(
            "snapshot",
            result.status,
            scope="complete canonical state",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=None if result.snapshot is None else result.snapshot.revision,
        )
        return result

    def base_identity(self) -> str:
        """Return the identity of this ledger's own history base."""
        return record_identity(self._store.initial_record(), follows=self._store.ledger_identity())

    def _identity_through(self, record: CanonicalTransitionRecord | None) -> str:
        """Walk the chain to the identity of ``record``, or of the base when it is None."""
        identity = self.base_identity()
        if record is None:
            return identity
        for each in self._store.transitions():
            identity = record_identity(each, follows=identity)
            if each.resulting_revision == record.resulting_revision:
                return identity
        raise StoreError("the record establishing the current revision is not in the ledger")

    def ledger_tail(self, *, after: int) -> LedgerTail:
        """Return the contiguous run of transitions following revision ``after``.

        The preceding record is named by its chained identity, so a tail taken from here
        cannot be joined onto another history that happens to sit at the same revision.
        An ``after`` no record established is refused rather than answered with a tail
        that says it follows something it does not.
        """
        base = self._store.initial_record()
        identity = self.base_identity()
        transitions = self._store.transitions()
        start: int | None = None
        preceding = identity
        if after == base.canonical_state.revision:
            start = 0
        for index, each in enumerate(transitions):
            identity = record_identity(each, follows=identity)
            if start is None and each.resulting_revision == after:
                start, preceding = index + 1, identity
        if start is None:
            raise ValueError(f"no record in this ledger established revision {after}")
        return LedgerTail(
            preceding_record=preceding,
            transitions=transitions[start:],
            final_record=identity,
        )

    def reconstruct_state(
        self, request: ReplayRequest, *, provenance: Provenance = UNATTRIBUTED
    ) -> ReconstructionResult:
        """Rebuild canonical state from a base and an optional tail.

        Live state is neither read nor moved: the answer comes entirely from what the
        caller supplied, which is what makes it a check of the ledger rather than of
        this system's memory.
        """
        result = reconstruct(request)
        self._observe(
            "reconstruction",
            result.status,
            scope="a supplied base and tail",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=(
                None if result.canonical_state is None else result.canonical_state.revision
            ),
        )
        return result

    # --- History ------------------------------------------------------------------------

    def history(
        self, query: HistoryQuery, *, provenance: Provenance = UNATTRIBUTED
    ) -> HistoryResult:
        """Read one ledger over an inclusive interval, or refuse the read whole.

        An activity read selects before its own observation is appended, so it never
        includes itself; that is why the append happens after the result is built.
        """
        findings = history_query_findings(query)
        if findings:
            result = HistoryResult(
                status=OperationStatus.REJECTED,
                summary=f"the history read was not evaluated ({len(findings)} findings)",
                query=query,
                findings=findings,
            )
        else:
            result = self._read_history(query)
        self._observe(
            "history",
            result.status,
            scope=query.kind.value,
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    def _read_history(self, query: HistoryQuery) -> HistoryResult:
        try:
            entries = (
                _canonical_entries(self, query)
                if query.kind is HistoryKind.CANONICAL
                else _activity_entries(self, query)
            )
            # After the entries, not before: a commit landing between the two reads would
            # otherwise produce a result claiming one revision while carrying records from
            # another, which is a state the ledger never held.
            revision = self._store.current_revision()
        except NotInitializedError as error:
            return HistoryResult(
                status=OperationStatus.REJECTED,
                summary="no canonical state is established; initialize this RTG first",
                query=query,
                findings=(ValidationFinding(summary=str(error)),),
            )
        except StoreError as error:
            return HistoryResult(
                status=OperationStatus.FAILED,
                summary=f"the history could not be read: {error}",
                query=query,
                findings=(ValidationFinding(summary=str(error)),),
            )
        canonical, activity = entries
        selected = len(canonical) + len(activity)
        if selected > query.maximum_records:
            return HistoryResult(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the interval holds more than {query.maximum_records} records; it is "
                    "refused whole rather than truncated"
                ),
                query=query,
                findings=(
                    ValidationFinding(
                        summary=(
                            f"the complete interval exceeds the maximum of {query.maximum_records}"
                        )
                    ),
                ),
            )
        return HistoryResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{selected} {query.kind.value} entries at revision {revision}",
            query=query,
            evaluated_revision=revision,
            canonical_entries=canonical,
            activity_entries=activity,
        )

    def manage_activity_retention(
        self, decision: RetentionDecision, *, provenance: Provenance = UNATTRIBUTED
    ) -> RevisionedOutcome:
        """Forget the observational records the owner chose to forget.

        Touches the activity ledger and nothing else: canonical state, definitions, the
        delta, the revision, and state-change history are all unaffected, which is what
        makes forgetting safe to offer at all.
        """
        refusals = retention_findings(decision)
        if refusals:
            outcome = RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=f"the retention decision was not applied ({len(refusals)} findings)",
                findings=refusals,
            )
            self._observe_outcome(
                "retention",
                outcome.status,
                scope="activity retention",
                summary=outcome.summary,
                provenance=provenance,
            )
            return outcome
        try:
            removed = self._store.remove_activity_before(decision.remove_before)
        except StoreError as error:
            outcome = RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the retention decision was not applied: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        else:
            outcome = RevisionedOutcome(
                status=OperationStatus.ACCEPTED,
                summary=f"removed {removed} activity records recorded before the boundary",
            )
        self._observe_outcome(
            "retention",
            outcome.status,
            scope=f"activity recorded before {decision.remove_before.isoformat()}",
            summary=outcome.summary,
            provenance=provenance,
        )
        return outcome

    # --- Going back ---------------------------------------------------------------------

    def restore_historical_state(
        self, selection: HistoricalSelection, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Make a past state current again, as one new revision.

        Restoration moves forward, not back. The selected state is committed as the next
        revision and everything already in the ledger stays exactly where it is — so
        going back is itself a thing that happened, and an owner can go back from it.

        A proposal in flight blocks it. The restored state carries no delta, so restoring
        over one would discard work the owner never asked to lose; refusing says so
        instead of deciding for them.
        """
        outcome = self._restore(selection, provenance=provenance)
        self._observe_outcome(
            "restoration",
            outcome.status,
            scope=_selection_scope(selection),
            summary=outcome.summary,
            provenance=provenance,
            evaluated_revision=outcome.resulting_revision,
        )
        return outcome

    def _restore(
        self, selection: HistoricalSelection, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Commit a past state as the next revision, or refuse without touching anything.

        The delta check comes first because it is decidable from state already in hand:
        refusing for a reason already known should not cost a replay of the whole tail.
        """
        try:
            state = self._working_state()
        except NotInitializedError as error:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="no canonical state is established; initialize this RTG first",
                findings=(ValidationFinding(summary=str(error)),),
            )
        except StoreError as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the current state could not be read: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )

        if state.definition_delta is not None:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    "a proposal is in flight; restoring would discard it, so activate or "
                    "discard it first"
                ),
                findings=(
                    ValidationFinding(summary="restoration requires no in-flight definition delta"),
                ),
            )

        revision, findings = self._resolve(selection)
        if findings:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=f"the selected state could not be resolved ({len(findings)} findings)",
                findings=findings,
            )
        try:
            historical = self._state_at(revision)
        except (StoreError, ReplayError) as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the selected state could not be reconstructed: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )

        if graph_equal(historical.graph, state.graph) and definition_set_equal(
            historical.active_definitions, state.active_definitions
        ):
            # Already there. Every other family treats a change that changes nothing as an
            # accepted no-op, and a revision recording that nothing happened is a record
            # of nothing.
            return RevisionedOutcome(
                status=OperationStatus.ACCEPTED,
                summary=f"revision {revision} is already the current state; nothing was restored",
            )
        return self._commit(
            state,
            TransitionKind.HISTORICAL_RESTORATION,
            CanonicalChange(
                replacement_graph=historical.graph,
                active_definitions=historical.active_definitions,
                delta_disposition=DefinitionDeltaDisposition.ABSENT,
            ),
            active_definitions=historical.active_definitions,
            graph=historical.graph,
            delta=None,
            provenance=provenance,
        )

    # --- Assessment -------------------------------------------------------------------

    def check(self, *, provenance: Provenance = UNATTRIBUTED) -> ValidationReport:
        """Assess the current graph against the current active definitions.

        The assessment changes no canonical state or revision and reads no canonical
        record; a false ``conforms`` describes the graph, it does not report a failure.
        """
        try:
            state = self._working_state()
        except StoreError as error:
            self._observe(
                "check",
                (
                    OperationStatus.REJECTED
                    if isinstance(error, NotInitializedError)
                    else OperationStatus.FAILED
                ),
                scope="the current graph against its active definitions",
                summary=f"the graph could not be assessed: {error}",
                provenance=provenance,
            )
            raise
        findings = assess_graph_conformance(state.graph, state.active_definitions)
        report = ValidationReport(
            scope=ValidationScope.GRAPH_CONFORMANCE,
            conforms=not findings,
            evaluated_revision=state.revision,
            findings=findings,
        )
        # A report has no status of its own: it succeeded, and says whether the graph
        # conforms. The observation records that the assessment ran and what it found.
        self._observe(
            "check",
            OperationStatus.ACCEPTED,
            scope="the current graph against its active definitions",
            summary=(
                "the graph conforms"
                if report.conforms
                else f"the graph does not conform ({len(findings)} findings)"
            ),
            provenance=provenance,
            evaluated_revision=report.evaluated_revision,
        )
        return report


def _change_scope(change: GraphChange) -> str:
    """Count what a change touched without copying any of it."""
    counts = (
        (len(change.anchor_upserts) + len(change.anchor_removals), "anchors"),
        (len(change.associated_data_upserts) + len(change.associated_data_removals), "data"),
        (len(change.link_upserts) + len(change.link_removals), "links"),
    )
    named = ", ".join(f"{count} {label}" for count, label in counts if count)
    return named or "nothing"


def _selection_scope(selection: HistoricalSelection) -> str:
    """Name the state a restoration went back to, without copying it."""
    if isinstance(selection, RevisionSelection):
        return f"revision {selection.revision}"
    return f"the state at {selection.time.isoformat()}"


def _query_scope(query: GraphQuery) -> str:
    """Name what a query was about without copying what it returned.

    The group and projection names are the caller's own words for its subject; the rows
    are the answer, and the model keeps those out of the ledger.
    """
    groups = ", ".join(group.name for group in query.anchor_groups)
    return f"anchor groups {groups}" if groups else "no anchor groups"


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


def _delta_result(
    state: CanonicalState,
    summary: str,
    resulting_revision: int | None = None,
    *,
    absent_summary: str = "there is no proposal",
) -> DefinitionDeltaResult:
    """Return the proposal, or its absence, as the model shapes that answer."""
    if state.definition_delta is None:
        return DefinitionDeltaResult(
            status=OperationStatus.ACCEPTED,
            summary=absent_summary,
            evaluated_revision=state.revision,
            resulting_revision=resulting_revision,
        )
    return DefinitionDeltaResult(
        status=OperationStatus.ACCEPTED,
        summary=summary,
        definition_delta=state.definition_delta,
        assessment=assess_proposal(
            state.definition_delta.proposed_definitions, state.graph, state.revision
        ),
        evaluated_revision=state.revision,
        resulting_revision=resulting_revision,
    )


def _canonical_entries(
    system: RTGSystem, query: HistoryQuery
) -> tuple[tuple[CanonicalHistoryEntry, ...], tuple[ActivityHistoryEntry, ...]]:
    """Project the canonical ledger for review.

    The replay-sufficient change is deliberately left behind, and never even read. An
    owner reviewing what happened needs revision, kind, time, provenance and a summary;
    handing back the payload would make a review response a second replay authority.
    """
    entries = tuple(
        CanonicalHistoryEntry(
            recorded_at=recorded_at,
            provenance=Provenance(initiator=initiator, source=source),
            summary=summary or f"{kind} to revision {revision}",
            revision=revision,
            prior_revision=prior,
            transition_kind=None if kind is None else TransitionKind(kind),
        )
        for revision, prior, kind, initiator, source, summary, recorded_at in (
            system.store.canonical_summaries(
                start=query.start_time,
                end=query.end_time,
                limit=(
                    None if query.maximum_records >= MAXIMUM_REVISION else query.maximum_records + 1
                ),
            )
        )
    )
    return entries, ()


def _activity_entries(
    system: RTGSystem, query: HistoryQuery
) -> tuple[tuple[CanonicalHistoryEntry, ...], tuple[ActivityHistoryEntry, ...]]:
    records = system.store.activity_records(
        start=query.start_time,
        end=query.end_time,
        limit=(None if query.maximum_records >= MAXIMUM_REVISION else query.maximum_records + 1),
    )
    return (), tuple(
        ActivityHistoryEntry(
            recorded_at=record.recorded_at,
            provenance=record.provenance,
            summary=record.summary,
            capability=record.capability,
            outcome_category=record.outcome_category,
            semantic_scope=record.semantic_scope,
            evaluated_revision=record.evaluated_revision,
        )
        for record in records
    )


def _within(moment: datetime, query: HistoryQuery) -> bool:
    """Both bounds are inclusive, so a record recorded exactly at one is selected.

    Compared as instants, which is what the activity ledger's stored form also achieves,
    so one interval means the same thing whichever ledger it is asked of.
    """
    if query.start_time is not None and moment < query.start_time:
        return False
    return not (query.end_time is not None and moment > query.end_time)
