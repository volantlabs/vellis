"""The one cohesive RTG semantic and transactional boundary.

Realizes ``RTGSystem::'RTG System'`` as far as this slice reaches:
``RTGSystem::'Initialize fresh RTG'``, carrying
``VellisRequirements::freshInitialization``,
``VellisRequirements::definitionCardinality``, and the current-state projection that
``VellisRequirements::historyIndependentCurrentWork`` constrains.

The public parameterless conformance operation and its typed report belong to the
typed-validation authority a later slice carries, so they are not exposed here.
Assessing a graph against a definition set is available as a function in
``vellis.validation``; wrapping it in an operation that also appends an observational
record is that later slice's work.

Query, validation, history, and recovery are capabilities of this one boundary rather
than independently existing subsystems, so they are methods here rather than injected
collaborators.
"""

from __future__ import annotations

from pathlib import Path

from vellis.canonical import CanonicalState, InitialStateRecord, Provenance, now
from vellis.definitions import GraphDefinitionSet, validate_definition_set
from vellis.graph import Graph
from vellis.json_value import unencodable_reason
from vellis.outcomes import OperationStatus, RevisionedOutcome, ValidationFinding
from vellis.serialization import unreadable_reason
from vellis.store import AlreadyInitializedError, CanonicalStore

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


def _unstorable_record_text(
    provenance: Provenance, initialization_summary: str
) -> tuple[ValidationFinding, ...]:
    """Report record text that cannot be encoded.

    The definition set is screened by its own validity check; the record carries text of
    its own, and it reaches the same store.
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
