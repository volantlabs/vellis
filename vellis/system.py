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

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TextIO

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
    CanonicalTransitionRecord,
    DefinitionDeltaDisposition,
    Provenance,
    TransitionKind,
    now,
    transition_findings,
)
from vellis.changes import GraphChange, GraphChangeRequest, GraphChangeTarget
from vellis.definitions import DefinitionEntry
from vellis.discovery import (
    AnchorDefinitionDetail,
    AnchorTypeSummary,
    DefinitionInspectionRequest,
    DefinitionInspectionResult,
    DefinitionSummaryRequest,
    DefinitionSummaryResult,
    anchor_neighborhood,
    inspection_findings,
)
from vellis.governance import (
    ActivateDefinitionDeltaRequest,
    DefinitionChange,
    DefinitionDeltaResult,
)
from vellis.history import (
    MAXIMUM_REVISION,
    HistoricalSelection,
    RevisionSelection,
    selection_findings,
)
from vellis.json_value import unencodable_reason
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationRequest,
    ValidationRequestKind,
    ValidationScope,
)
from vellis.query import EvaluatedStateScope, GraphQuery, GraphQueryResult
from vellis.store import (
    AlreadyInitializedError,
    CanonicalStore,
    ConcurrentRevisionError,
    InvalidInitialDefinitionsError,
    NotInitializedError,
    ProposalState,
    StoreError,
)
from vellis.streaming import SnapshotMetadata, export_ndjson

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

    # --- Initialization -------------------------------------------------------------

    def initialize_fresh(
        self,
        initial_definitions: Iterable[DefinitionEntry],
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
                    "the initial definitions were not established "
                    f"({len(record_findings)} findings)"
                ),
                findings=record_findings,
            )
        try:
            self._store.initialize_empty(
                iter(initial_definitions),
                provenance=provenance,
                initialization_summary=initialization_summary,
                recorded_at=now(),
            )
        except AlreadyInitializedError:
            return RevisionedOutcome(
                OperationStatus.REJECTED,
                "canonical state is already established; initialization applies only to an RTG"
                " with no established state",
                findings=(
                    ValidationFinding(
                        summary="this RTG already has an established canonical state"
                    ),
                ),
            )
        except InvalidInitialDefinitionsError as error:
            return RevisionedOutcome(
                OperationStatus.REJECTED,
                f"the initial definitions were not established ({len(error.findings)} findings)",
                findings=error.findings,
            )
        except (StoreError, OSError) as error:
            return RevisionedOutcome(
                OperationStatus.FAILED,
                f"no canonical state was established: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        return RevisionedOutcome(
            OperationStatus.ACCEPTED,
            "established revision 0 with the streamed initial definitions",
            resulting_revision=0,
        )

    # --- Change -----------------------------------------------------------------------

    def apply_graph_change(
        self, request: GraphChangeRequest | GraphChange, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Validate a change whole, then commit it as one revision."""
        if isinstance(request, GraphChange):
            request = GraphChangeRequest(GraphChangeTarget.ACTIVE, request)
        if request.target is GraphChangeTarget.DEFINITION_DELTA:
            try:
                outcome = self._store.stage_proposal_graph(request, provenance=provenance)
            except StoreError as error:
                outcome = RevisionedOutcome(
                    status=(
                        OperationStatus.REJECTED
                        if isinstance(error, NotInitializedError)
                        else OperationStatus.FAILED
                    ),
                    summary=f"the prospective graph edit could not be staged: {error}",
                    findings=(ValidationFinding(summary=str(error)),),
                )
            self._observe_outcome(
                "graphChange",
                outcome.status,
                scope="the sole prospective graph overlay",
                summary=outcome.summary,
                provenance=provenance,
                evaluated_revision=outcome.resulting_revision,
            )
            return outcome
        if request.unstaging():
            outcome = RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="active graph changes cannot unstage prospective entries",
                findings=(
                    ValidationFinding(summary="unstaging requires a definition-delta target"),
                ),
            )
            self._observe_outcome(
                "graphChange",
                outcome.status,
                scope="the active graph",
                summary=outcome.summary,
                provenance=provenance,
            )
            return outcome
        change = request.change
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
            revision, structural, conformance, no_op = self._store.prepare_active_graph_change(
                change
            )
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
        if structural:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the change was not applied ({len(structural)} findings); no canonical "
                    "state or revision changed"
                ),
                findings=structural,
            )
        if conformance:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the resulting graph would not conform ({len(conformance)} findings); no "
                    "canonical state or revision changed"
                ),
                findings=conformance,
            )
        if no_op:
            return RevisionedOutcome(
                status=OperationStatus.ACCEPTED,
                summary="the change is an effective no-op; no revision was created",
            )
        return self._commit(
            revision,
            TransitionKind.GRAPH_MUTATION,
            CanonicalChange(graph_change=change),
            provenance=provenance,
        )

    # --- Discovery --------------------------------------------------------------------

    def definition_summary(
        self,
        request: DefinitionSummaryRequest | None = None,
        *,
        provenance: Provenance = UNATTRIBUTED,
    ) -> DefinitionSummaryResult:
        """Return every anchor type active at the current or a selected state.

        A caller reads this first and an inspection second; both carry the revision they
        were evaluated at, which is how a caller notices that the definitions moved
        between the two reads.
        """
        selected_request = DefinitionSummaryRequest() if request is None else request
        selection = selected_request.historical_selection
        state_scope = selected_request.state_scope
        if state_scope is EvaluatedStateScope.PROSPECTIVE:
            if selection is not None:
                result = DefinitionSummaryResult(
                    OperationStatus.REJECTED,
                    "prospective definition discovery forbids historical selection",
                    findings=(ValidationFinding(summary="state selection is inconsistent"),),
                )
                self._observe(
                    "definitionSummary",
                    result.status,
                    scope="every prospective anchor type",
                    summary=result.summary,
                    provenance=provenance,
                )
                return result
            try:
                revision, rows, _ = self._store.definition_summary_rows(prospective=True)
            except StoreError as error:
                result = DefinitionSummaryResult(
                    OperationStatus.REJECTED,
                    f"the prospective definitions could not be selected: {error}",
                    findings=(ValidationFinding(summary=str(error)),),
                )
                self._observe(
                    "definitionSummary",
                    result.status,
                    scope="every prospective anchor type",
                    summary=result.summary,
                    provenance=provenance,
                )
                return result
            result = DefinitionSummaryResult(
                OperationStatus.ACCEPTED,
                f"{len(rows)} prospective anchor types",
                anchor_types=tuple(AnchorTypeSummary(*row) for row in rows),
                evaluated_revision=revision,
                delta_present=True,
            )
            self._observe(
                "definitionSummary",
                result.status,
                scope="every prospective anchor type",
                summary=result.summary,
                provenance=provenance,
                evaluated_revision=revision,
            )
            return result
        if state_scope is EvaluatedStateScope.HISTORICAL:
            if selection is None:
                result = DefinitionSummaryResult(
                    OperationStatus.REJECTED,
                    "historical definition discovery requires one historical selection",
                    findings=(ValidationFinding(summary="no historical selection was provided"),),
                )
                self._observe(
                    "definitionSummary",
                    result.status,
                    scope="every active anchor type at a selected state",
                    summary=result.summary,
                    provenance=provenance,
                )
                return result
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
        if selection is not None:
            result = DefinitionSummaryResult(
                OperationStatus.REJECTED,
                "current definition discovery forbids historical selection",
                findings=(ValidationFinding(summary="state selection is inconsistent"),),
            )
            self._observe(
                "definitionSummary",
                result.status,
                scope="every active anchor type",
                summary=result.summary,
                provenance=provenance,
            )
            return result
        try:
            revision, rows, delta_present = self._store.definition_summary_rows()
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
            summary=f"{len(rows)} active anchor types",
            anchor_types=tuple(AnchorTypeSummary(*row) for row in rows),
            evaluated_revision=revision,
            delta_present=delta_present,
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
        if selection is not None and request.historical_selection is not None:
            result = DefinitionInspectionResult(
                OperationStatus.REJECTED,
                "an inspection carries more than one historical selector",
                request,
                findings=(ValidationFinding(summary="state selection is inconsistent"),),
            )
        else:
            effective_request = (
                replace(request, state_scope=EvaluatedStateScope.HISTORICAL)
                if selection is not None
                else request
            )
            result = self._inspect(effective_request, selection or request.historical_selection)
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
        if request.state_scope is EvaluatedStateScope.PROSPECTIVE:
            if selection is not None:
                return DefinitionInspectionResult(
                    OperationStatus.REJECTED,
                    "prospective inspection forbids historical selection",
                    request,
                    findings=(ValidationFinding(summary="state selection is inconsistent"),),
                )
            try:
                revision, definitions, _ = self._store.definition_neighborhood(
                    request.anchor_type_keys, prospective=True
                )
            except StoreError as error:
                return DefinitionInspectionResult(
                    OperationStatus.REJECTED,
                    f"the prospective definitions could not be selected: {error}",
                    request,
                    findings=(ValidationFinding(summary=str(error)),),
                )
        elif selection is not None:
            if request.state_scope is not EvaluatedStateScope.HISTORICAL:
                return DefinitionInspectionResult(
                    OperationStatus.REJECTED,
                    "historical selection requires historical state scope",
                    request,
                    findings=(ValidationFinding(summary="state selection is inconsistent"),),
                )
            return self._historical_inspection(request, selection)
        else:
            if request.state_scope is EvaluatedStateScope.HISTORICAL:
                return DefinitionInspectionResult(
                    OperationStatus.REJECTED,
                    "historical inspection requires one historical selection",
                    request,
                    findings=(ValidationFinding(summary="no historical selection was provided"),),
                )
            try:
                revision, definitions, _ = self._store.definition_neighborhood(
                    request.anchor_type_keys
                )
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
            result = _proposal_result(self._store.proposal_state(), "the current proposal")
        except StoreError as error:
            result = DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be retrieved: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
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
        self, change: DefinitionChange, *, provenance: Provenance
    ) -> DefinitionDeltaResult:
        """Create or edit the sole proposal through one bounded natural-keyed change."""
        result = self._set_definition_delta(change, provenance=provenance)
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
        self, change: DefinitionChange, *, provenance: Provenance
    ) -> DefinitionDeltaResult:
        """Create or replace the sole proposal.

        A proposal that already says what the current one says, or what the active set
        says when there is no proposal, changes nothing and advances nothing. Offering
        the active set while a different proposal stands is refused rather than read as
        a discard: clearing a proposal is its own operation, and guessing here would
        throw away work the owner did not ask to lose.
        """
        record_findings = _unstorable_record_text(provenance, None)
        if record_findings:
            return DefinitionDeltaResult(
                status=OperationStatus.REJECTED,
                summary="the record's own text cannot be stored; nothing was staged",
                findings=record_findings,
            )
        try:
            outcome = self._store.stage_definition_change(change, provenance=provenance)
        except StoreError as error:
            return DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be staged: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        if not outcome.accepted:
            return DefinitionDeltaResult(
                status=outcome.status, summary=outcome.summary, findings=outcome.findings
            )
        if outcome.resulting_revision is None:
            state = self._store.proposal_state()
            if state.proposed_definition_identity is None:
                return DefinitionDeltaResult(
                    OperationStatus.ACCEPTED,
                    outcome.summary,
                    evaluated_revision=state.revision,
                )
            return _proposal_result(state, outcome.summary)
        return _proposal_result(
            self._store.proposal_state(),
            f"staged the proposal at revision {outcome.resulting_revision}",
            resulting_revision=outcome.resulting_revision,
        )

    def activate_definition_delta(
        self, request: ActivateDefinitionDeltaRequest, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Activate the sole proposal, or preserve everything."""
        try:
            outcome = self._store.activate_proposal(request.assessment_id, provenance=provenance)
        except StoreError as error:
            outcome = RevisionedOutcome(
                status=(
                    OperationStatus.REJECTED
                    if isinstance(error, NotInitializedError)
                    else OperationStatus.FAILED
                ),
                summary=f"the proposal could not be activated: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        self._observe_outcome(
            "definitionActivation",
            outcome.status,
            scope="the active definition set",
            summary=outcome.summary,
            provenance=provenance,
            evaluated_revision=outcome.resulting_revision,
        )
        return outcome

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
            proposal = self._store.proposal_state()
        except StoreError as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be discarded: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        if proposal.proposed_definition_identity is None:
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="there is no proposal to discard",
            )
        return self._commit(
            proposal.revision,
            TransitionKind.DEFINITION_DELTA_CHANGE,
            CanonicalChange(delta_disposition=DefinitionDeltaDisposition.ABSENT),
            provenance=provenance,
        )

    def _commit(
        self,
        prior_revision: int,
        kind: TransitionKind,
        change: CanonicalChange,
        *,
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
        record = CanonicalTransitionRecord(
            prior_revision=prior_revision,
            resulting_revision=prior_revision + 1,
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
        try:
            self._store._append_transition(record)  # noqa: SLF001 - system owns store commits
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
            summary=f"committed revision {record.resulting_revision}",
            resulting_revision=record.resulting_revision,
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
        if selection is not None and query.historical_selection is not None:
            result = GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="a query carries more than one historical selector",
                query=query,
                findings=(ValidationFinding(summary="state selection is inconsistent"),),
            )
            self._observe(
                "query",
                result.status,
                scope=_query_scope(query),
                summary=result.summary,
                provenance=provenance,
            )
            return result
        if selection is not None:
            query = replace(query, state_scope=EvaluatedStateScope.HISTORICAL)
        chosen = selection or query.historical_selection
        if query.state_scope is EvaluatedStateScope.PROSPECTIVE:
            if chosen is not None:
                result = GraphQueryResult(
                    status=OperationStatus.REJECTED,
                    summary="prospective queries cannot carry a historical selection",
                    query=query,
                    findings=(ValidationFinding(summary="state selection is inconsistent"),),
                )
            else:
                try:
                    result = self._store.evaluate_prospective_query(query)
                except StoreError as error:
                    result = GraphQueryResult(
                        status=OperationStatus.FAILED,
                        summary=f"the prospective query could not be evaluated: {error}",
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
        if chosen is not None:
            if query.state_scope is not EvaluatedStateScope.HISTORICAL:
                result = GraphQueryResult(
                    status=OperationStatus.REJECTED,
                    summary="a historical selection requires historical state scope",
                    query=query,
                    findings=(ValidationFinding(summary="state selection is inconsistent"),),
                )
                self._observe(
                    "query",
                    result.status,
                    scope=_query_scope(query),
                    summary=result.summary,
                    provenance=provenance,
                )
                return result
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
        if query.state_scope is EvaluatedStateScope.HISTORICAL:
            result = GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="historical state scope requires one historical selection",
                query=query,
                findings=(ValidationFinding(summary="no historical selection was provided"),),
            )
            self._observe(
                "query",
                result.status,
                scope=_query_scope(query),
                summary=result.summary,
                provenance=provenance,
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
        _, rows, delta_present = self._store.definition_summary_rows(revision=revision)
        return DefinitionSummaryResult(
            status=OperationStatus.ACCEPTED,
            summary=(f"{len(rows)} anchor types at revision {revision}"),
            anchor_types=tuple(AnchorTypeSummary(*row) for row in rows),
            evaluated_revision=revision,
            delta_present=delta_present,
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
        _, definitions, _ = self._store.definition_neighborhood(
            request.anchor_type_keys, revision=revision
        )
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
        except StoreError as error:
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
        return self._store.evaluate_query_at_revision(query, revision)

    # --- Capture and rebuild ------------------------------------------------------------

    def export_snapshot(
        self, output: TextIO, *, batch_size: int = 256, provenance: Provenance = UNATTRIBUTED
    ) -> SnapshotMetadata:
        """Stream one complete normalized snapshot without constructing canonical state."""
        try:
            metadata = export_ndjson(self._store.path, output, batch_size=batch_size)
        except (StoreError, OSError) as error:
            self._observe(
                "snapshot",
                OperationStatus.FAILED,
                scope="complete canonical state",
                summary=f"the snapshot could not be streamed: {error}",
                provenance=provenance,
            )
            raise
        self._observe(
            "snapshot",
            OperationStatus.ACCEPTED,
            scope="complete canonical state",
            summary=f"streamed revision {metadata.revision}",
            provenance=provenance,
            evaluated_revision=metadata.revision,
        )
        return metadata

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
            with self._store.read_snapshot():
                entries = (
                    _canonical_entries(self, query)
                    if query.kind is HistoryKind.CANONICAL
                    else _activity_entries(self, query)
                )
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
            proposal = self._store.proposal_state()
        except StoreError as error:
            return RevisionedOutcome(
                (
                    OperationStatus.REJECTED
                    if isinstance(error, NotInitializedError)
                    else OperationStatus.FAILED
                ),
                f"the current proposal state could not be read: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )
        if proposal.proposed_definition_identity is not None:
            return RevisionedOutcome(
                OperationStatus.REJECTED,
                "an in-flight definition delta blocks restoration",
                findings=(
                    ValidationFinding(
                        summary="activate or discard the in-flight definition delta first"
                    ),
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
            return self._store.restore_revision(revision, provenance=provenance)
        except StoreError as error:
            return RevisionedOutcome(
                status=OperationStatus.FAILED,
                summary=f"the selected state could not be restored: {error}",
                findings=(ValidationFinding(summary=str(error)),),
            )

    # --- Assessment -------------------------------------------------------------------

    def check(
        self,
        request: ValidationRequest | None = None,
        *,
        provenance: Provenance = UNATTRIBUTED,
    ) -> ValidationReport:
        """Publish a complete stored assessment or read one bounded finding page."""
        request = request or ValidationRequest(
            ValidationRequestKind.ASSESS, ValidationScope.GRAPH_CONFORMANCE, 100
        )
        scope_text = (
            "the prospective graph against its proposed definitions"
            if request.scope is ValidationScope.DEFINITION_DELTA
            else "the current graph against its active definitions"
        )

        def finish(report: ValidationReport) -> ValidationReport:
            self._observe(
                "check",
                report.status,
                scope=scope_text,
                summary=report.summary,
                provenance=provenance,
                evaluated_revision=report.evaluated_revision,
            )
            return report

        if request.maximum_findings < 1:
            return finish(
                ValidationReport(
                    scope=request.scope,
                    status=OperationStatus.REJECTED,
                    summary="maximum findings must be positive",
                )
            )
        if request.kind is ValidationRequestKind.READ_FINDINGS:
            if request.assessment_id is None or request.start_ordinal is None:
                return finish(
                    ValidationReport(
                        scope=request.scope,
                        status=OperationStatus.REJECTED,
                        summary="finding retrieval requires assessment ID and start ordinal",
                    )
                )
            try:
                report = self._store.assessment_page(
                    request.assessment_id,
                    request.start_ordinal,
                    request.maximum_findings,
                )
            except StoreError as error:
                return finish(
                    ValidationReport(
                        scope=request.scope,
                        status=OperationStatus.FAILED,
                        summary=f"the assessment page could not be read: {error}",
                    )
                )
            if report is None or report.scope is not request.scope:
                return finish(
                    ValidationReport(
                        scope=request.scope,
                        status=OperationStatus.REJECTED,
                        summary=(
                            "the assessment page selection is unknown, expired, or out of range"
                        ),
                    )
                )
            return finish(report)
        if request.assessment_id is not None or request.start_ordinal is not None:
            return finish(
                ValidationReport(
                    scope=request.scope,
                    status=OperationStatus.REJECTED,
                    summary="a new assessment forbids prior assessment selectors",
                )
            )
        try:
            report = self._store.assess_and_publish(
                request.scope, maximum_findings=request.maximum_findings
            )
        except StoreError as error:
            return finish(
                ValidationReport(
                    scope=request.scope,
                    status=(
                        OperationStatus.REJECTED
                        if isinstance(error, NotInitializedError)
                        or "no definition delta" in str(error)
                        else OperationStatus.FAILED
                    ),
                    summary=f"the graph could not be assessed: {error}",
                )
            )
        # A report has no status of its own: it succeeded, and says whether the graph
        # conforms. The observation records that the assessment ran and what it found.
        return finish(report)


def _transition_summary(kind: str | None, revision: int) -> str:
    """Say what a transition was, for an owner reading their own history.

    Only what the ledger row already holds. Saying which objects moved would mean reading
    the replay-sufficient change, and a review response that reads it becomes a second
    replay authority — so this names the kind of change and its revision, in the words the
    model uses for them, and stops there.
    """
    said = {
        TransitionKind.GRAPH_MUTATION.value: "the graph changed",
        TransitionKind.DEFINITION_DELTA_CHANGE.value: "the definition proposal changed",
        TransitionKind.DEFINITION_ACTIVATION.value: "the definition proposal became active",
        TransitionKind.HISTORICAL_RESTORATION.value: "earlier state was restored",
    }.get(kind or "")
    return f"{said}, reaching revision {revision}" if said else f"reached revision {revision}"


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


def _proposal_result(
    state: ProposalState,
    summary: str,
    resulting_revision: int | None = None,
    *,
    absent_summary: str = "there is no proposal",
) -> DefinitionDeltaResult:
    """Return the proposal, or its absence, as the model shapes that answer."""
    if state.proposed_definition_identity is None:
        return DefinitionDeltaResult(
            status=OperationStatus.ACCEPTED,
            summary=absent_summary,
            evaluated_revision=state.revision,
            resulting_revision=resulting_revision,
        )
    return DefinitionDeltaResult(
        status=OperationStatus.ACCEPTED,
        summary=summary,
        proposed_definition_identity=state.proposed_definition_identity,
        graph_overlay_identity=state.graph_overlay_identity,
        staged_anchor_count=state.staged_anchor_count,
        staged_associated_data_count=state.staged_associated_data_count,
        staged_link_count=state.staged_link_count,
        staged_removal_count=state.staged_removal_count,
        assessment=state.assessment,
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
            summary=summary or _transition_summary(kind, revision),
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
