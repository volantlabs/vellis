"""Evidence for the document form of ``RTG::'Canonical Snapshot'`` and ``RTG::'Ledger Tail'``.

``Vellis::'Begin using one personal Vellis system'`` takes "a complete canonical snapshot
with an optional later ledger tail" as one of its three starting inputs. A snapshot that
only exists inside a running process is not an input anybody can bring anywhere, so this
is the form that carries one — and the questions asked of it are the ones reconstruction
will ask later.

Two of them are load-bearing. The document has to be complete: what comes back must
reconstruct the same canonical state the source system was in, delta and all. And it has
to be faithful in the fields nobody looks at directly — provenance and the recorded time
are digested into every record's identity, so a document that reconstructed them with
defaults would produce a tail that no longer proves it belongs to its history. Both are
exercised against a tampered document rather than only a well-formed one, because a
format that round-trips its own output is not yet a format that detects anything.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import build_rich_definitions

from vellis.canonical import Provenance, canonical_state_equal
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.graph import Anchor
from vellis.json_value import JsonValue, dumps, loads
from vellis.replay import CanonicalSnapshot, reconstruct
from vellis.serialization import DecodeError
from vellis.snapshot_document import (
    DOCUMENT_VERSION,
    analyze_snapshot_document,
    decode_snapshot_document,
    encode_snapshot_document,
    read_snapshot_document,
    start_summary,
    write_snapshot_document,
)
from vellis.system import RTGSystem

OWNER = Provenance(initiator="owner", source="a keyboard")


def _plus(base: GraphDefinitionSet, type_key: str, description: str) -> GraphDefinitionSet:
    """The same vocabulary with one more anchor type.

    Widening rather than narrowing, because a proposal that retired a type something in
    the graph still uses would be refused for a reason that has nothing to do with the
    document form under test.
    """
    return GraphDefinitionSet(
        anchor_types=(
            *base.anchor_types,
            AnchorTypeDefinition(type_key=type_key, description=description),
        ),
        associated_data_types=base.associated_data_types,
        link_types=base.link_types,
        relationship_constraints=base.relationship_constraints,
    )


def _wider() -> GraphDefinitionSet:
    return _plus(build_rich_definitions(), "team", "A group of people.")


@pytest.fixture
def source(tmp_path: Path):
    """A system with a history of more than one transition kind, and a live proposal.

    Both matter. A tail of graph mutations alone would not exercise the definition-change
    encoding, and a snapshot taken with no delta in flight would not show that an
    in-flight proposal travels with the state it belongs to.
    """
    system = RTGSystem.open(tmp_path / "source.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=OWNER, initialization_summary="a fresh start"
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)), provenance=OWNER
    ).accepted
    assert system.set_definition_delta(_wider(), provenance=OWNER).accepted
    assert system.activate_definition_delta(provenance=OWNER).accepted
    try:
        yield system
    finally:
        system.close()


def _capture(system: RTGSystem) -> CanonicalSnapshot:
    captured = system.create_snapshot(provenance=OWNER)
    assert captured.accepted and captured.snapshot is not None
    return captured.snapshot


def _captured(system: RTGSystem) -> JsonValue:
    """A document holding a capture of where ``system`` stands now, with no tail."""
    return encode_snapshot_document(_capture(system))


def _with_tail(system: RTGSystem, snapshot: CanonicalSnapshot) -> JsonValue:
    """A document holding an earlier capture plus every record committed since.

    The two halves are only meaningful together: a tail is checked against the identity
    of the record its base was captured through, so the snapshot has to be the one taken
    before the records the tail carries.
    """
    return encode_snapshot_document(snapshot, system.ledger_tail(after=snapshot.revision))


def _rewritten(document: JsonValue) -> dict[str, Any]:
    """A mutable copy of a document, read back the way a file would be."""
    copy = loads(dumps(document))
    assert isinstance(copy, dict)
    return copy


# --- A document says what the state said -------------------------------------------------


def test_a_document_reconstructs_the_state_it_captured(source: RTGSystem) -> None:
    request = decode_snapshot_document(_captured(source))

    result = reconstruct(request)

    assert result.accepted, result.findings
    assert result.canonical_state is not None
    assert canonical_state_equal(result.canonical_state, source.current_state())


def test_an_in_flight_proposal_travels_with_the_state(source: RTGSystem) -> None:
    """Excludes a document that reconstructs a state whose delta quietly went missing."""
    assert source.set_definition_delta(
        _plus(_wider(), "venue", "Somewhere things happen."), provenance=OWNER
    ).accepted
    expected = source.current_state()
    assert expected.definition_delta is not None

    result = reconstruct(decode_snapshot_document(_captured(source)))

    assert result.canonical_state is not None
    assert canonical_state_equal(result.canonical_state, expected)


def test_a_tail_of_several_transition_kinds_replays_to_the_same_state(
    source: RTGSystem,
) -> None:
    """The tail carries a graph mutation, a proposal, and an activation, and all replay."""
    snapshot = _capture(source)
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-2", "team", "Orbit"),)), provenance=OWNER
    ).accepted
    assert source.set_definition_delta(
        _plus(_wider(), "venue", "Somewhere things happen."), provenance=OWNER
    ).accepted
    assert source.activate_definition_delta(provenance=OWNER).accepted
    expected = source.current_state()

    result = reconstruct(decode_snapshot_document(_with_tail(source, snapshot)))

    assert result.accepted, result.findings
    assert result.canonical_state is not None
    assert canonical_state_equal(result.canonical_state, expected)


def test_a_written_document_reads_back_as_the_same_request(
    tmp_path: Path, source: RTGSystem
) -> None:
    snapshot = _capture(source)
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-3", "person", "Grace"),)), provenance=OWNER
    ).accepted
    expected_tail = source.ledger_tail(after=snapshot.revision)
    path = tmp_path / "snapshot.json"

    write_snapshot_document(path, snapshot, expected_tail)
    request = read_snapshot_document(path.read_text(encoding="utf-8"))

    assert request.tail is not None
    assert request.tail.transitions == expected_tail.transitions
    result = reconstruct(request)
    assert result.canonical_state is not None
    assert canonical_state_equal(result.canonical_state, source.current_state())


# --- What a document must not lose -------------------------------------------------------


@pytest.mark.parametrize("field", ["initiator", "source", "recordedAt"])
def test_a_record_field_the_identity_digests_is_carried_not_defaulted(
    source: RTGSystem, field: str
) -> None:
    """Excludes an encoding that drops provenance or time and reconstructs a default.

    None of these three changes what a transition *does*. All three change what it *is*:
    the identity chain digests them, so a document that lost one would hand back a tail
    that no longer ends where it says it ends.
    """
    snapshot = _capture(source)
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-4", "person", "Grace"),)), provenance=OWNER
    ).accepted

    altered = _rewritten(_with_tail(source, snapshot))
    tail: Any = altered["tail"]
    transition: Any = tail["transitions"][0]
    transition[field] = "somebody-else" if field != "recordedAt" else "2001-01-01T00:00:00+00:00"

    assert not reconstruct(decode_snapshot_document(altered)).accepted


def test_a_tail_that_does_not_end_where_it_says_is_refused(source: RTGSystem) -> None:
    snapshot = _capture(source)
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-5", "person", "Grace"),)), provenance=OWNER
    ).accepted
    document = _rewritten(_with_tail(source, snapshot))
    tail: Any = document["tail"]
    tail["finalRecord"] = "0" * 64

    result = reconstruct(decode_snapshot_document(document))

    assert not result.accepted


def test_a_tail_cannot_be_carried_onto_another_ledgers_snapshot(
    tmp_path: Path, source: RTGSystem
) -> None:
    """Two systems seeded identically hold identical records; identity is what parts them."""
    snapshot = _capture(source)
    stranger = RTGSystem.open(tmp_path / "stranger.sqlite3")
    try:
        assert stranger.initialize_fresh(
            build_rich_definitions(), provenance=OWNER, initialization_summary="a fresh start"
        ).accepted
        assert source.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-6", "person", "Grace"),)), provenance=OWNER
        ).accepted
        document = _rewritten(_with_tail(source, snapshot))
        document["snapshot"] = _rewritten(_captured(stranger))["snapshot"]

        assert not reconstruct(decode_snapshot_document(document)).accepted
    finally:
        stranger.close()


# --- What a document is not ---------------------------------------------------------------


def test_a_document_of_another_version_is_refused_by_name(source: RTGSystem) -> None:
    document = _rewritten(_captured(source))
    document["vellisSnapshotDocument"] = "99"

    with pytest.raises(DecodeError, match="version"):
        decode_snapshot_document(document)


@pytest.mark.parametrize("removed", ["vellisSnapshotDocument", "snapshot", "tail"])
def test_a_document_missing_a_member_is_refused(source: RTGSystem, removed: str) -> None:
    """Including ``tail``: absent and null are different, and only null means no tail."""
    document = _rewritten(_captured(source))
    del document[removed]

    with pytest.raises(DecodeError):
        decode_snapshot_document(document)


def test_an_empty_record_identity_is_refused(source: RTGSystem) -> None:
    """Excludes an identity that would compare equal to "no identity supplied"."""
    document = _rewritten(_captured(source))
    snapshot: Any = document["snapshot"]
    snapshot["capturedThrough"] = ""

    with pytest.raises(DecodeError, match="empty"):
        decode_snapshot_document(document)


def test_a_document_that_is_not_one_at_all_is_refused() -> None:
    for content in ({}, [], "a snapshot", None):
        with pytest.raises(DecodeError):
            decode_snapshot_document(content)  # type: ignore[arg-type]


def test_a_transition_kind_this_build_does_not_know_is_refused(source: RTGSystem) -> None:
    snapshot = _capture(source)
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-7", "person", "Grace"),)), provenance=OWNER
    ).accepted
    document = _rewritten(_with_tail(source, snapshot))
    tail: Any = document["tail"]
    tail["transitions"][0]["kind"] = "somethingElse"

    with pytest.raises(DecodeError, match="canonical transition"):
        decode_snapshot_document(document)


# --- Analyzing one before an owner is asked about it ----------------------------------------


def test_analysis_reports_what_a_start_would_establish(source: RTGSystem) -> None:
    snapshot = _capture(source)
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-8", "person", "Grace"),)), provenance=OWNER
    ).accepted

    start = analyze_snapshot_document(_with_tail(source, snapshot))

    assert start.is_acceptable
    assert start.tail_length == 1
    assert start.canonical_state is not None
    assert start.canonical_state.revision == source.current_state().revision


def test_the_same_content_is_the_same_document_however_it_is_written(
    source: RTGSystem,
) -> None:
    """Reformatting is not a changed document; a changed value always is."""
    document = _captured(source)
    reordered = _rewritten(document)
    rewritten = {name: reordered[name] for name in reversed(list(reordered))}

    assert (
        analyze_snapshot_document(rewritten).source_identity
        == analyze_snapshot_document(document).source_identity
    )


def test_a_changed_document_has_a_different_identity(source: RTGSystem) -> None:
    document = _captured(source)
    altered = _rewritten(document)
    captured_through: Any = altered["snapshot"]
    captured_through["capturedThrough"] = "f" * 64

    assert (
        analyze_snapshot_document(altered).source_identity
        != analyze_snapshot_document(document).source_identity
    )


def test_a_document_that_reconstructs_nothing_usable_is_a_start_with_findings(
    source: RTGSystem,
) -> None:
    """The wrong file and the right file with something wrong in it are different answers.

    A document that is not one raises; one that is, but cannot become a state, comes back
    carrying the reasons — which is what an owner can take back to the system it came from.
    """
    document = _rewritten(_captured(source))
    snapshot: Any = document["snapshot"]
    state: Any = snapshot["canonicalState"]
    state["activeDefinitions"]["anchorTypes"] = []

    start = analyze_snapshot_document(document)

    assert not start.is_acceptable
    assert start.reconstruction.findings
    assert start.canonical_state is None


def test_the_version_this_build_writes_is_the_one_it_reads(source: RTGSystem) -> None:
    document = _captured(source)
    assert isinstance(document, dict)
    assert document["vellisSnapshotDocument"] == DOCUMENT_VERSION


# --- A tail that is not there ----------------------------------------------------------


def test_a_capture_with_nothing_after_it_writes_no_tail(source: RTGSystem) -> None:
    """The obvious way to export a snapshot asks for everything since it, and gets none.

    A present-but-empty tail is a document reconstruction refuses, and retaking the
    snapshot produces the identical one — so the owner following the corrective action
    would loop. "Nothing happened since" is no tail.
    """
    snapshot = _capture(source)
    empty = source.ledger_tail(after=snapshot.revision)
    assert empty.transitions == ()

    document = encode_snapshot_document(snapshot, empty)

    assert _rewritten(document)["tail"] is None
    result = reconstruct(decode_snapshot_document(document))
    assert result.accepted, result.findings
    assert result.canonical_state is not None
    assert canonical_state_equal(result.canonical_state, source.current_state())


def test_a_written_capture_with_nothing_after_it_is_a_usable_start(
    tmp_path: Path, source: RTGSystem
) -> None:
    snapshot = _capture(source)
    path = tmp_path / "head.json"

    write_snapshot_document(path, snapshot, source.ledger_tail(after=snapshot.revision))

    assert analyze_snapshot_document(loads(path.read_text(encoding="utf-8"))).is_acceptable


def test_a_document_carrying_an_empty_tail_is_malformed_not_merely_unusable(
    source: RTGSystem,
) -> None:
    """Hand-written or produced by an older build: the answer names the fix, not a finding."""
    document = _rewritten(_captured(source))
    document["tail"] = {"precedingRecord": "a" * 64, "transitions": [], "finalRecord": "a" * 64}

    with pytest.raises(DecodeError, match="omits the tail"):
        decode_snapshot_document(document)


def test_a_revision_no_ledger_could_hold_is_refused_by_the_analysis(source: RTGSystem) -> None:
    """Excludes an owner confirming a start that initialization would then refuse.

    Reconstruction alone accepts it: the definitions are valid and the graph conforms. What
    it cannot be is the base of a lineage, and that has to be known before the question is
    put rather than after the destination has been created.
    """
    document = _rewritten(_captured(source))
    snapshot: Any = document["snapshot"]
    snapshot["canonicalState"]["revision"] = Decimal(-3)

    start = analyze_snapshot_document(document)

    assert not start.is_acceptable
    findings = start.reconstruction.findings
    assert any("not one a ledger can hold" in each.summary for each in findings)


def test_a_start_names_the_proposal_it_would_establish(source: RTGSystem) -> None:
    """Excludes a summary that inherits a pending vocabulary change without saying so.

    A snapshot taken while a proposal was in flight carries it, and the start establishes
    it. An owner told only about the active vocabulary would find a change to it they
    never agreed to inherit.
    """
    without = start_summary(analyze_snapshot_document(_captured(source)))
    assert "no definition proposal in flight" in without

    assert source.set_definition_delta(
        _plus(_wider(), "venue", "Somewhere things happen."), provenance=OWNER
    ).accepted

    with_delta = start_summary(analyze_snapshot_document(_captured(source)))

    assert "one definition proposal in flight" in with_delta
