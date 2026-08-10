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
    TransitionKind,
    now,
    transition_findings,
)
from vellis.changes import GraphChange, apply_change, change_findings
from vellis.definitions import (
    GraphDefinitionSet,
    definition_set_equal,
    validate_definition_set,
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
from vellis.json_value import unencodable_reason
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.query import GraphQuery, GraphQueryResult, evaluate_query
from vellis.serialization import unreadable_reason
from vellis.store import (
    AlreadyInitializedError,
    CanonicalStore,
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
            state = self.current_state()
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
        self, *, provenance: Provenance = UNATTRIBUTED
    ) -> DefinitionSummaryResult:
        """Return every anchor type active at the current state.

        A caller reads this first and an inspection second; both carry the revision they
        were evaluated at, which is how a caller notices that the definitions moved
        between the two reads.
        """
        try:
            state = self.current_state()
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
            summary=f"{len(state.active_definitions.anchor_types)} active anchor types",
            anchor_types=summarize_anchor_types(state.active_definitions),
            evaluated_revision=state.revision,
            delta_present=state.definition_delta is not None,
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
        self, request: DefinitionInspectionRequest, *, provenance: Provenance = UNATTRIBUTED
    ) -> DefinitionInspectionResult:
        """Return the complete active neighborhood of each selected anchor type.

        An unknown or duplicated selection yields findings and nothing else — not the
        details that happened to resolve — because a partial answer would read as a
        complete one.
        """
        result = self._inspect(request)
        self._observe(
            "definitionInspection",
            result.status,
            scope=f"{len(request.anchor_type_keys)} selected anchor types",
            summary=result.summary,
            provenance=provenance,
            evaluated_revision=result.evaluated_revision,
        )
        return result

    def _inspect(self, request: DefinitionInspectionRequest) -> DefinitionInspectionResult:
        try:
            state = self.current_state()
        except StoreError as error:
            return DefinitionInspectionResult(
                status=OperationStatus.FAILED,
                summary=f"the selection could not be answered completely: {error}",
                request=request,
                findings=(ValidationFinding(summary=str(error)),),
            )
        findings = inspection_findings(request, state.active_definitions)
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
            anchor_neighborhood(type_key, state.active_definitions)
            for type_key in request.anchor_type_keys
        )
        return DefinitionInspectionResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{len(details)} anchor neighborhoods",
            request=request,
            anchor_details=details,
            evaluated_revision=state.revision,
        )

    # --- The sole proposal ------------------------------------------------------------

    def definition_delta(self, *, provenance: Provenance = UNATTRIBUTED) -> DefinitionDeltaResult:
        """Return the sole proposal with a current assessment, or normal absence."""
        try:
            state = self.current_state()
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
            state = self.current_state()
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
            state = self.current_state()
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
            state = self.current_state()
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
        self, query: GraphQuery, *, provenance: Provenance = UNATTRIBUTED
    ) -> GraphQueryResult:
        """Answer one bounded semantic query, or refuse it whole.

        A query changes no canonical state or revision and reads no canonical record.
        """
        try:
            state = self.current_state()
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
        else:
            result = evaluate_query(query, state.active_definitions, state.graph, state.revision)
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
            revision = self.current_state().revision
            entries = (
                _canonical_entries(self, query)
                if query.kind is HistoryKind.CANONICAL
                else _activity_entries(self, query)
            )
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

    # --- Assessment -------------------------------------------------------------------

    def check(self, *, provenance: Provenance = UNATTRIBUTED) -> ValidationReport:
        """Assess the current graph against the current active definitions.

        The assessment changes no canonical state or revision and reads no canonical
        record; a false ``conforms`` describes the graph, it does not report a failure.
        """
        try:
            state = self.current_state()
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
            system.store.canonical_summaries(start=query.start_time, end=query.end_time)
        )
    )
    return entries, ()


def _activity_entries(
    system: RTGSystem, query: HistoryQuery
) -> tuple[tuple[CanonicalHistoryEntry, ...], tuple[ActivityHistoryEntry, ...]]:
    records = system.store.activity_records(start=query.start_time, end=query.end_time)
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
