"""The transportable form of a canonical snapshot and its later ledger tail.

``Vellis::'Begin using one personal Vellis system'`` takes, as one of its three starting
inputs, "a complete canonical snapshot with an optional later ledger tail". A snapshot
that exists only as a value inside one running process is not an input anybody can bring
to a new machine, so this is the document form that carries one there.

``RTG::'Canonical Snapshot'`` and ``RTG::'Ledger Tail'`` are semantic artifacts and the
model leaves their serialized form open. This is that selected form, and it is chosen to
be the same shape the store already uses: the state, change, and definition encoders are
the store's own, so a snapshot document says exactly what a ledger says and cannot drift
into a second dialect of canonical meaning.

What a document must carry is fixed by what reconstruction checks. A snapshot names the
record it was captured through, and a tail names the record it follows and the record it
ends at, because identity — not the revision number — is what proves a tail belongs to
this history. Dropping either end would produce documents that reconstruct happily and
sometimes reconstruct a history that never existed.

Decoding is strict and total: a document that is truncated, reordered into a different
meaning, or missing a member raises rather than reconstructing something plausible. The
caller that reads a file the owner supplied needs "this is not a snapshot document" to be
a distinguishable answer, not a partially populated request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from vellis.canonical import (
    CanonicalState,
    CanonicalTransitionRecord,
    Provenance,
    TransitionKind,
)
from vellis.history import MAXIMUM_REVISION
from vellis.json_value import JsonValue, dumps, normalize
from vellis.outcomes import OperationStatus, ValidationFinding
from vellis.replay import (
    CanonicalSnapshot,
    LedgerTail,
    ReconstructionResult,
    ReplayRequest,
    reconstruct,
)
from vellis.serialization import (
    DecodeError,
    decode_canonical_change,
    decode_canonical_state,
    decode_text,
    encode_canonical_change,
    encode_canonical_state,
    encode_text,
)

__all__ = [
    "DOCUMENT_VERSION",
    "SnapshotStart",
    "analyze_snapshot_document",
    "decode_snapshot_document",
    "document_identity",
    "encode_snapshot_document",
    "read_snapshot_document",
    "start_summary",
    "write_snapshot_document",
]

DOCUMENT_VERSION = "1"
"""The document form this build writes and the only one it reads.

Named in the document itself so a future form is a refusal an owner can act on rather
than a decode error somewhere inside a member that changed meaning.
"""

_MARKER = "vellisSnapshotDocument"


def _object(value: JsonValue, where: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise DecodeError(f"{where} is not a JSON object")
    return value


def _member(members: dict[str, JsonValue], name: str, where: str) -> JsonValue:
    if name not in members:
        raise DecodeError(f"{where} is missing {name}")
    return members[name]


def _string(value: JsonValue, where: str) -> str:
    if not isinstance(value, str):
        raise DecodeError(f"{where} is not a string")
    return value


def _identity(value: JsonValue, where: str) -> str:
    text = _string(value, where)
    if not text:
        # An empty identity would compare equal to the empty base identity reconstruction
        # uses when an initial record supplies none, which is exactly the seam a tail is
        # supposed to prove it belongs to.
        raise DecodeError(f"{where} is empty; a record identity names one record")
    return text


def _int(value: JsonValue, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise DecodeError(f"{where} is not a number")
    if value != value.to_integral_value():
        raise DecodeError(f"{where} is not a whole number")
    return int(value)


def _encode_transition(record: CanonicalTransitionRecord) -> JsonValue:
    """Encode one canonical transition whole.

    Every field ``record_identity`` digests participates, and nothing is defaulted on the
    way back in: a record whose provenance or time were reconstructed rather than read
    would digest to a different identity and fail the very check it was carried for.
    """
    return {
        "priorRevision": Decimal(record.prior_revision),
        "resultingRevision": Decimal(record.resulting_revision),
        "kind": record.kind.value,
        "change": encode_canonical_change(record.change),
        "initiator": record.provenance.initiator,
        "source": record.provenance.source,
        "recordedAt": record.recorded_at.isoformat(),
    }


def _decode_transition(value: JsonValue, where: str) -> CanonicalTransitionRecord:
    members = _object(value, where)
    raw_source = _member(members, "source", where)
    raw_kind = _string(_member(members, "kind", where), f"{where} kind")
    try:
        kind = TransitionKind(raw_kind)
    except ValueError as error:
        raise DecodeError(f"{where} kind {raw_kind!r} is not a canonical transition") from error
    raw_time = _string(_member(members, "recordedAt", where), f"{where} recordedAt")
    try:
        recorded_at = datetime.fromisoformat(raw_time)
    except ValueError as error:
        raise DecodeError(f"{where} recordedAt is not a time: {error}") from error
    return CanonicalTransitionRecord(
        prior_revision=_int(_member(members, "priorRevision", where), f"{where} priorRevision"),
        resulting_revision=_int(
            _member(members, "resultingRevision", where), f"{where} resultingRevision"
        ),
        kind=kind,
        change=decode_canonical_change(_member(members, "change", where)),
        provenance=Provenance(
            initiator=_string(_member(members, "initiator", where), f"{where} initiator"),
            source=None if raw_source is None else _string(raw_source, f"{where} source"),
        ),
        recorded_at=recorded_at,
    )


def encode_snapshot_document(
    snapshot: CanonicalSnapshot, tail: LedgerTail | None = None
) -> JsonValue:
    """Encode one snapshot, and optionally the tail that advances it, as one document.

    A tail carrying no transitions is written as no tail. The model makes the tail
    optional, and a capture taken at the head has nothing after it — but the obvious way
    to export one asks the ledger for everything since the captured revision and gets an
    empty run back. Writing that out as a present-but-empty tail would turn "nothing
    happened since" into a document reconstruction refuses, and no amount of retaking the
    snapshot would produce a different one.
    """
    encoded_tail: JsonValue = None
    if tail is not None and tail.transitions:
        encoded_tail = {
            "precedingRecord": tail.preceding_record,
            "transitions": [_encode_transition(each) for each in tail.transitions],
            "finalRecord": tail.final_record,
        }
    return {
        _MARKER: DOCUMENT_VERSION,
        "snapshot": {
            "canonicalState": encode_canonical_state(snapshot.canonical_state),
            "capturedThrough": snapshot.captured_through,
        },
        "tail": encoded_tail,
    }


def decode_snapshot_document(value: JsonValue) -> ReplayRequest:
    """Decode one document into the replay request that reconstructs its state.

    A request rather than a snapshot and a tail separately: the two are only meaningful
    joined, and handing back the joined form leaves no way for a caller to reconstruct
    the base while quietly dropping the records that came after it.
    """
    where = "snapshot document"
    members = _object(value, where)
    version = _string(_member(members, _MARKER, where), f"{where} version")
    if version != DOCUMENT_VERSION:
        raise DecodeError(
            f"{where} is version {version!r}; this build reads version {DOCUMENT_VERSION!r}"
        )
    snapshot_members = _object(_member(members, "snapshot", where), f"{where} snapshot")
    snapshot = CanonicalSnapshot(
        canonical_state=decode_canonical_state(
            _member(snapshot_members, "canonicalState", f"{where} snapshot")
        ),
        captured_through=_identity(
            _member(snapshot_members, "capturedThrough", f"{where} snapshot"),
            f"{where} capturedThrough",
        ),
    )
    raw_tail = _member(members, "tail", where)
    tail: LedgerTail | None = None
    if raw_tail is not None:
        tail_members = _object(raw_tail, f"{where} tail")
        raw_transitions = _member(tail_members, "transitions", f"{where} tail")
        if not isinstance(raw_transitions, list):
            raise DecodeError(f"{where} tail transitions is not an array")
        if not raw_transitions:
            # Refused here rather than left to reconstruction, so the answer is "this
            # document is malformed, omit the tail" instead of a finding about a state
            # that could never have been reconstructed from it.
            raise DecodeError(
                f"{where} tail carries no transitions; a document with nothing after its "
                "snapshot omits the tail"
            )
        tail = LedgerTail(
            preceding_record=_identity(
                _member(tail_members, "precedingRecord", f"{where} tail"),
                f"{where} tail precedingRecord",
            ),
            transitions=tuple(
                _decode_transition(each, f"{where} tail transition {index}")
                for index, each in enumerate(raw_transitions)
            ),
            final_record=_identity(
                _member(tail_members, "finalRecord", f"{where} tail"),
                f"{where} tail finalRecord",
            ),
        )
    return ReplayRequest(snapshot=snapshot, tail=tail)


def write_snapshot_document(
    path: Path, snapshot: CanonicalSnapshot, tail: LedgerTail | None = None
) -> None:
    """Write one snapshot document where an owner can carry it to a new system."""
    path.write_text(encode_text(encode_snapshot_document(snapshot, tail)) + "\n", encoding="utf-8")


def read_snapshot_document(text: str) -> ReplayRequest:
    """Read one snapshot document from its stored text."""
    return decode_snapshot_document(decode_text(text))


def document_identity(content: JsonValue) -> str:
    """Return a stable identity for the exact document content.

    Taken over the canonical serialization rather than the file's bytes, so reformatting
    is not treated as a changed document and a changed value always is.
    """
    return sha256(dumps(normalize(content)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SnapshotStart:
    """One reconstruction, bound to the exact document that produced it.

    The binding is what the confirmation is for. An owner agrees to begin from this
    state, not from "a snapshot", and a document that changed underneath describes a
    different state that nobody has seen.
    """

    source_identity: str
    request: ReplayRequest
    reconstruction: ReconstructionResult

    @property
    def is_acceptable(self) -> bool:
        """Whether this document reconstructs a state a system could be established at."""
        return self.reconstruction.accepted

    @property
    def canonical_state(self) -> CanonicalState | None:
        return self.reconstruction.canonical_state

    @property
    def tail_length(self) -> int:
        return 0 if self.request.tail is None else len(self.request.tail.transitions)


def analyze_snapshot_document(content: JsonValue) -> SnapshotStart:
    """Read one document and reconstruct it, without touching any system.

    Reconstruction happens here rather than at initialization so that everything an owner
    is agreeing to — the revision the new lineage would start at, the vocabulary it would
    carry, and every reason it cannot be used — is on the screen before they answer.
    """
    request = decode_snapshot_document(content)
    return SnapshotStart(
        source_identity=document_identity(content),
        request=request,
        reconstruction=_establishable(reconstruct(request)),
    )


def _establishable(result: ReconstructionResult) -> ReconstructionResult:
    """Refuse a reconstruction no ledger could be founded on.

    Reconstruction asks whether the state is one a system could have committed; founding a
    lineage asks one thing more, that the revision be one a ledger can name. A base below
    zero is unreachable by any selector and one above the range leaves no room for the
    next transition. Asked here rather than left to initialization, because the whole
    point of analyzing before confirming is that an owner is never asked to agree to a
    start that cannot happen — and the advice initialization would give at that point is
    about the destination, which is not where the fault is.
    """
    state = result.canonical_state
    if state is None or 0 <= state.revision <= MAXIMUM_REVISION:
        return result
    return ReconstructionResult(
        status=OperationStatus.REJECTED,
        summary="the state was not reconstructed (1 findings)",
        findings=(
            ValidationFinding(
                summary=(
                    f"revision {state.revision} is not one a ledger can hold, so no lineage "
                    "can begin from this state"
                )
            ),
        ),
    )


def start_summary(start: SnapshotStart) -> str:
    """Return the bounded sentence an accepted snapshot start records permanently."""
    state = start.canonical_state
    assert state is not None, "an acceptable start reconstructed a state"
    definitions = state.active_definitions
    # The delta is named because the start establishes it. A snapshot taken while a
    # proposal was in flight carries that proposal, and an owner who was told only about
    # the vocabulary would find a pending change to it they never agreed to inherit.
    delta = (
        "no definition proposal in flight"
        if state.definition_delta is None
        else "one definition proposal in flight"
    )
    return (
        f"first-use start from a Vellis canonical snapshot ({start.source_identity[:12]}) "
        f"at revision {state.revision} with {_counted(start.tail_length, 'later transition')}, "
        f"{_counted(len(state.graph.anchors), 'anchor')}, "
        f"{_counted(len(state.graph.associated_data), 'associated-data object')}, "
        f"{_counted(len(state.graph.links), 'link')}, "
        f"{_counted(len(definitions.anchor_types), 'anchor type')}, "
        f"{_counted(len(definitions.associated_data_types), 'associated-data type')}, "
        f"{_counted(len(definitions.link_types), 'link type')}, and {delta}"
    )


def _counted(total: int, noun: str) -> str:
    """Say how many of something there are, in the words that fit that many."""
    return f"{total} {noun}" if total == 1 else f"{total} {noun}s"
