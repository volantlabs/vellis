"""Evidence for ``VellisVerification::simpleOperation`` as one whole.

Every capability this exercises already has evidence of its own, and the setup path and
the ten-tool surface each have theirs. What is not yet shown is the thing the verification
case actually asks for: that one owner, on one machine, can follow the documented setup
guidance, have a client launch the server, and reach a memory that is still there in a
later session — and that when any part of that fails, the failure says which stage failed,
what it did to established memory, and what to do about it.

The agent here connects the way a real client does: a subprocess running
``python -m vellis`` over local standard input and output, discovered and invoked through
core MCP alone. In-process evidence for the same tools lives with the boundary; what is
proved here is that the boundary an owner's client actually launches comes up, serves the
selected ten, and answers about the memory setup established. Nothing else would tell an
owner that the two commands they were given compose.

Three starts are exercised separately because the model names three starting inputs, and
a system that begins from one of them says nothing about the other two. The Everyday Life
start is the recommended one and is confirmed rather than assumed.

Each failure is checked against a whole state-effect vector — graph, active definitions,
delta, revision, canonical ledger — read before and after, because "established memory is
unchanged" is a claim about all of it and not only about the value under test.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from tests.vellis.evolution_support import stage_complete_fixture
from vellis.__main__ import EXIT_FAILED as SERVE_FAILED
from vellis.__main__ import main as serve_main
from vellis.canonical import (
    CanonicalState,
    CanonicalTransitionRecord,
    Provenance,
    canonical_state_equal,
)
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.everyday_life import everyday_life_starter
from vellis.graph import Anchor
from vellis.mcp import TOOL_NAMES
from vellis.paths import DATA_DIRECTORY_VARIABLE, store_path
from vellis.preserve import main as preserve_main
from vellis.setup import (
    EXIT_DECLINED,
    EXIT_FAILED,
    EXIT_SUCCESS,
    SetupStage,
)
from vellis.setup import (
    main as setup_main,
)
from vellis.snapshot_document import write_snapshot_document
from vellis.system import RTGSystem

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OWNER = Provenance(initiator="owner")

# The starter's own word for a person, which the queries below are written in. Pinned
# here rather than derived, because a cold agent learns this key by discovering it and
# the point of the discovery check is that the key it finds is the key that then works.
PERSON = "life.person"


# --- Running the two documented commands ----------------------------------------------


def _setup(argv: list[str], answer: str = "") -> tuple[int, str, str]:
    """Run the documented setup command exactly as an owner would."""
    out, err = io.StringIO(), io.StringIO()
    code = setup_main(argv, stdout=out, stderr=err, stdin=io.StringIO(answer))
    return code, out.getvalue(), err.getvalue()


def _serve(destination: Path) -> Client:
    """A client that launches the server the way an owner's client launches it.

    A subprocess over standard input and output, started from the repository so the
    module resolves the same way the documented invocation does. Nothing here reaches
    into the process; everything it learns, it learns through core MCP.
    """
    return Client(
        StdioTransport(
            command=sys.executable,
            args=["-m", "vellis", "--data-dir", str(destination)],
            cwd=str(REPOSITORY_ROOT),
            env={**os.environ},
        )
    )


async def _call(client: Client, name: str, arguments: dict[str, Any] | None = None) -> dict:
    result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    assert result.structured_content is not None, name
    return result.structured_content


def _people_query(maximum_rows: int = 10) -> dict[str, Any]:
    return {
        "query": {
            "anchor_groups": [{"name": "who", "anchor_type": PERSON}],
            "return_shape": {
                "projections": [
                    {"name": "person", "anchor_group": "who", "type": "AnchorProjection"}
                ]
            },
            "maximum_rows": maximum_rows,
        }
    }


def _names(payload: dict) -> set[str]:
    return {
        binding["anchor"]["display_name"] for row in payload["rows"] for binding in row["anchors"]
    }


# --- The whole governed state, before and after ----------------------------------------


@dataclass(frozen=True, slots=True)
class _Everything:
    """Every canonical state a failure promises not to move."""

    state: CanonicalState
    transitions: tuple[CanonicalTransitionRecord, ...]
    records: int


def _everything(destination: Path) -> _Everything:
    system = RTGSystem.open(store_path(destination.resolve()))
    try:
        return _Everything(
            state=system.current_state(),
            transitions=system.store.transitions(),
            records=system.store.canonical_record_count(),
        )
    finally:
        system.close()


def _unchanged(before: _Everything, after: _Everything) -> bool:
    return (
        canonical_state_equal(before.state, after.state)
        and before.transitions == after.transitions
        and before.records == after.records
    )


def _stage_a_proposal(destination: Path) -> None:
    """Leave one proposal in flight at ``destination``.

    The failures below promise to leave the current definition proposal where it was, and
    a system that never had one would compare absent with absent and pass whatever
    happened. Written through the owner boundary because the model selects no owner
    transport for staging beyond it.
    """
    system = RTGSystem.open(store_path(destination.resolve()))
    try:
        active = system.current_state().active_definitions
        proposed = GraphDefinitionSet(
            anchor_types=(
                *active.anchor_types,
                AnchorTypeDefinition(
                    type_key="life.hobby", description="Something done for its own sake."
                ),
            ),
            associated_data_types=active.associated_data_types,
            link_types=active.link_types,
            relationship_constraints=active.relationship_constraints,
        )
        assert stage_complete_fixture(system, proposed, provenance=OWNER).accepted
    finally:
        system.close()


# --- Three starting inputs, each confirmed ---------------------------------------------


def test_a_blank_start_establishes_one_empty_system(tmp_path: Path) -> None:
    destination = tmp_path / "blank"
    code, out, _ = _setup(["--data-dir", str(destination), "--vocabulary", "blank"], answer="y\n")

    assert code == EXIT_SUCCESS
    assert "current revision: 0" in out
    established = _everything(destination)
    assert established.state.revision == 0
    assert established.state.graph.is_empty
    assert not established.state.active_definitions.anchor_types


def test_the_recommended_everyday_life_start_is_offered_and_confirmed(tmp_path: Path) -> None:
    """The recommendation is what setup offers; the confirmation is what establishes it."""
    destination = tmp_path / "everyday"
    code, out, _ = _setup(["--data-dir", str(destination)], answer="y\n")

    assert code == EXIT_SUCCESS
    assert "Everyday Life (a starter vocabulary of everyday things) - recommended" in out
    established = _everything(destination)
    starter = everyday_life_starter()
    assert {each.type_key for each in established.state.active_definitions.anchor_types} == {
        each.type_key for each in starter.anchor_types
    }
    # The starter is a vocabulary, not a populated system: an owner who confirmed it has
    # been given words, not somebody else's people.
    assert established.state.graph.is_empty


def test_a_declined_start_establishes_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "declined"
    code, out, _ = _setup(["--data-dir", str(destination)], answer="n\n")

    assert code == EXIT_DECLINED
    assert "Declined" in out
    assert not store_path(destination.resolve()).exists()


@pytest.fixture
def snapshot_document(tmp_path: Path) -> Path:
    """A complete canonical snapshot plus the records committed after it was taken.

    Taken from a real system rather than assembled by hand, because the identities a tail
    is checked against are chained from that ledger's own and cannot be written out.
    """
    source = RTGSystem.open(tmp_path / "source.sqlite3")
    try:
        assert source.initialize_fresh(
            everyday_life_starter(), provenance=OWNER, initialization_summary="a fresh start"
        ).accepted
        assert source.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", PERSON, "Ada"),)), provenance=OWNER
        ).accepted
        captured = source.create_snapshot(provenance=OWNER)
        assert captured.accepted and captured.snapshot is not None
        assert source.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-2", PERSON, "Grace"),)), provenance=OWNER
        ).accepted
        document = tmp_path / "snapshot.json"
        write_snapshot_document(
            document, captured.snapshot, source.ledger_tail(after=captured.snapshot.revision)
        )
        return document
    finally:
        source.close()


def test_a_start_from_a_snapshot_and_later_records_establishes_that_state(
    tmp_path: Path, snapshot_document: Path
) -> None:
    destination = tmp_path / "restored"
    code, out, _ = _setup(
        ["--data-dir", str(destination), "--from-snapshot", str(snapshot_document)], answer="y\n"
    )

    assert code == EXIT_SUCCESS
    # What the owner is agreeing to is on the screen before they answer, including the
    # part that surprises: the new lineage does not begin at zero.
    assert "the new lineage begins at revision 2" in out
    assert "later transitions replayed: 1" in out
    established = _everything(destination)
    assert established.state.revision == 2
    assert {each.display_name for each in established.state.graph.anchors} == {"Ada", "Grace"}
    # Both records came across, but neither transition did: this ledger holds one base and
    # claims none of the history that produced it.
    assert established.records == 1
    assert established.transitions == ()


def test_a_start_from_a_snapshot_offers_no_starting_vocabulary(
    tmp_path: Path, snapshot_document: Path
) -> None:
    """Excludes overlaying a fresh choice on a state that already answered the question."""
    code, out, _ = _setup(
        [
            "--data-dir",
            str(tmp_path / "restored"),
            "--from-snapshot",
            str(snapshot_document),
            "--dry-run",
        ]
    )

    assert code == EXIT_SUCCESS
    assert "starting vocabulary:" not in out


def _v1_snapshot() -> dict[str, Any]:
    """One complete, compatible Vellis v1 system snapshot."""
    return {
        "graph": {
            "anchors": [
                {"uuid": "v1", "type": "person", "display_name": "Ada", "system": {"live": True}}
            ],
            "data_objects": [],
            "links": [],
            "anchor_data_index": {},
        },
        "schema": {
            "definitions": [
                {
                    "uuid": "s1",
                    "kind": "anchor",
                    "type_key": "person",
                    "description": "A person the owner knows.",
                    "payload": {},
                    "system": {"live": True},
                }
            ]
        },
        "constraints": {"constraints": []},
        "migration": {"migrations": []},
    }


def test_a_start_from_a_confirmed_v1_snapshot_begins_a_new_lineage(tmp_path: Path) -> None:
    document = tmp_path / "v1.json"
    document.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    destination = tmp_path / "recovered"

    code, _, _ = _setup(["--data-dir", str(destination), "--from-v1", str(document)], answer="y\n")

    assert code == EXIT_SUCCESS
    established = _everything(destination)
    # A v1 system's history happened somewhere this ledger never was, so the lineage
    # starts at zero even though the content is not new.
    assert established.state.revision == 0
    assert {each.display_name for each in established.state.graph.anchors} == {"Ada"}
    assert established.transitions == ()


# --- One cohesive system, reached the way a client reaches it ---------------------------


@pytest.fixture
def established(tmp_path: Path) -> Path:
    """One system the owner began by confirming the recommended start."""
    destination = tmp_path / "memory"
    assert _setup(["--data-dir", str(destination)], answer="y\n")[0] == EXIT_SUCCESS
    return destination


@pytest.mark.anyio
async def test_a_client_launched_server_serves_exactly_the_selected_ten_tools(
    established: Path,
) -> None:
    """Core MCP discovery alone, against the process a client actually starts."""
    async with _serve(established) as agent:
        discovered = await agent.list_tools()

    assert sorted(each.name for each in discovered) == sorted(TOOL_NAMES)


@pytest.mark.anyio
async def test_the_command_an_owner_registers_is_the_one_that_launches(
    established: Path,
    tmp_path: Path,
) -> None:
    """The documented client entry, run as the owner's client would run it.

    The other tests here launch the module with this interpreter from the repository,
    which proves the server but not the string an owner is told to register. That string
    is different in every part that can break: ``uv`` rather than a Python already chosen,
    ``--directory`` rather than an inherited working directory, and a client whose cwd is
    somewhere else entirely. If it drifts — a renamed entry point, a dropped flag, a
    project ``uv`` can no longer resolve — nothing else in the suite would notice, and the
    owner would find out from a client that fails to start.
    """
    documented = Client(
        StdioTransport(
            command="uv",
            args=[
                "--directory",
                str(REPOSITORY_ROOT),
                "run",
                "python",
                "-m",
                "vellis",
                "--data-dir",
                str(established),
            ],
            cwd=str(tmp_path),
            env={**os.environ},
        )
    )
    async with documented as agent:
        discovered = await agent.list_tools()
        people = await _call(agent, "rtg_query", _people_query())

    assert sorted(each.name for each in discovered) == sorted(TOOL_NAMES)
    # Not merely up: serving the memory setup established, from a cwd that is not the clone.
    assert people["status"] == "accepted"


@pytest.mark.anyio
async def test_approved_context_outlives_the_session_and_the_process(
    established: Path,
) -> None:
    """The whole of the use case, in the order an owner lives it.

    A cold agent learns the vocabulary, asks a bounded question, and writes one change the
    owner approved. Then the process ends. A second launch — a different process, a
    different session — finds the same memory at the same revision.
    """
    async with _serve(established) as first:
        vocabulary = await _call(first, "rtg_definition_summary")
        assert vocabulary["status"] == "accepted"
        assert PERSON in {each["type_key"] for each in vocabulary["anchor_types"]}

        before = await _call(first, "rtg_query", _people_query())
        assert before["status"] == "accepted"
        assert _names(before) == set()

        retained = await _call(
            first,
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [{"uuid": "a-1", "type_key": PERSON, "display_name": "Ada"}]
                }
            },
        )
        assert retained["status"] == "accepted"
        assert retained["resulting_revision"] == 1

    after_first_session = _everything(established)

    async with _serve(established) as later:
        recovered = await _call(later, "rtg_query", _people_query())

    assert recovered["status"] == "accepted"
    assert _names(recovered) == {"Ada"}
    assert recovered["evaluated_revision"] == 1
    # Identically recovered, not merely present: the state a restart reaches is the state
    # replay reconstructs from the ledger alone.
    reopened = _everything(established)
    assert canonical_state_equal(reopened.state, after_first_session.state)
    system = RTGSystem.open(store_path(established.resolve()))
    try:
        assert canonical_state_equal(system.replay(), reopened.state)
    finally:
        system.close()


@pytest.mark.anyio
async def test_a_second_proposal_the_owner_declines_is_not_retained(
    established: Path,
) -> None:
    """Approval is the owner's, and a declined proposal never becomes a call.

    So the evidence cannot be a refusal. It has to be that the exact context the agent
    prepared is absent afterwards and memory is indistinguishable from memory that was
    never asked — which is the whole of what declining does, because no tool retains a
    proposal and none is called.

    The declined one is a second proposal, after an approved first: a decline that only
    ever happened on an untouched system would not show that declining leaves an existing
    memory alone.
    """
    async with _serve(established) as agent:
        approved = await _call(
            agent,
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [{"uuid": "a-1", "type_key": PERSON, "display_name": "Ada"}]
                }
            },
        )
        assert approved["status"] == "accepted"

    after_the_approved_one = _everything(established)

    async with _serve(established) as agent:
        # Everything the agent does to prepare the second proposal: it rereads the
        # vocabulary and rechecks the facts, then puts the change to the owner.
        assert (await _call(agent, "rtg_definition_summary"))["status"] == "accepted"
        current = await _call(agent, "rtg_query", _people_query())
        assert current["status"] == "accepted"
        assert _names(current) == {"Ada"}
        declined = {"uuid": "a-2", "type_key": PERSON, "display_name": "Grace"}
        # The owner says no, so nothing is submitted. This is the last thing that happens.

    assert _unchanged(after_the_approved_one, _everything(established))
    async with _serve(established) as later:
        afterwards = await _call(later, "rtg_query", _people_query())
    assert declined["display_name"] not in _names(afterwards)


@pytest.fixture
def blank_memory(tmp_path: Path) -> Path:
    """One system the owner began blank.

    A definition delta replaces the whole vocabulary, so governing one means writing a
    complete set out. Starting blank keeps that set small enough to write here honestly
    rather than rendering the starter through a layer that could quietly drop part of it.
    """
    destination = tmp_path / "blank-memory"
    assert (
        _setup(["--data-dir", str(destination), "--vocabulary", "blank"], answer="y\n")[0]
        == EXIT_SUCCESS
    )
    return destination


@pytest.mark.anyio
async def test_the_owner_governs_the_sole_proposal_through_the_launched_client(
    blank_memory: Path,
) -> None:
    """A vocabulary change, staged and then activated, through the process a client starts.

    Governing the sole delta is named in the same clause as querying and preserving, and
    a system whose delta tools were never reached through the boundary an owner actually
    connects to would leave that clause unevidenced. Staging and activating are separated
    by the end of a process, because the model says a proposal survives other work and
    restarts and is gated at activation rather than at staging.
    """
    hobby = {"type_key": "hobby", "description": "Something done for its own sake."}
    proposed = {"proposed_definitions": {"anchor_types": [hobby]}}

    async with _serve(blank_memory) as agent:
        staged = await _call(agent, "rtg_set_definition_delta", {"request": proposed})
        assert staged["status"] == "accepted"

    # Staged, not activated, and still there after the process that staged it ended.
    with_delta = _everything(blank_memory)
    assert with_delta.state.definition_delta is not None
    assert not with_delta.state.active_definitions.anchor_types

    async with _serve(blank_memory) as later:
        held = await _call(later, "rtg_definition_delta")
        assert held["status"] == "accepted"
        activated = await _call(later, "rtg_activate_definition_delta")
        assert activated["status"] == "accepted"

    governed = _everything(blank_memory)
    assert governed.state.definition_delta is None
    assert {each.type_key for each in governed.state.active_definitions.anchor_types} == {"hobby"}


# --- Failures, and what they leave behind ------------------------------------------------


def test_a_setup_failure_before_initialization_establishes_nothing(tmp_path: Path) -> None:
    """A destination that cannot be prepared, named at the stage that found out."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory\n", encoding="utf-8")

    code, _, err = _setup(["--data-dir", str(blocker / "vellis"), "--yes"])

    assert code == EXIT_FAILED
    assert f"stage: {SetupStage.PREPARE_DESTINATION}" in err
    assert "established memory: unchanged" in err
    assert "what to do next:" in err
    assert not (blocker / "vellis").exists()


def test_a_later_setup_attempt_is_actionable_and_moves_nothing(established: Path) -> None:
    _stage_a_proposal(established)
    before = _everything(established)
    assert before.state.definition_delta is not None

    code, _, err = _setup(["--data-dir", str(established), "--yes"])

    assert code == EXIT_FAILED
    assert f"stage: {SetupStage.PREVIEW}" in err
    assert "established memory: unchanged" in err
    assert "use this system as it is" in err
    assert _unchanged(before, _everything(established))


@pytest.mark.parametrize(
    ("directory", "expected"),
    [("absent", "no Vellis memory is established"), ("not-a-store", "could not be opened")],
)
def test_a_connection_failure_names_its_stage_state_effect_and_next_step(
    tmp_path: Path, established: Path, directory: str, expected: str
) -> None:
    """The client could not start the server, and says so the way setup does.

    A bare message would leave an owner unable to tell a mistyped destination from a
    memory that needs establishing from something that broke, so the minimum the model
    requires is checked here as literally as it is for setup.
    """
    wrong = tmp_path / directory
    wrong.mkdir()
    if directory == "not-a-store":
        store_path(wrong).write_text("this is not a database\n", encoding="utf-8")
    _stage_a_proposal(established)
    before = _everything(established)
    assert before.state.definition_delta is not None
    err = io.StringIO()

    code = serve_main(["--data-dir", str(wrong)], stderr=err)

    assert code == SERVE_FAILED
    reported = err.getvalue()
    assert "Stage: open-memory" in reported
    assert expected in reported
    assert "established memory: unchanged" in reported
    assert "what to do next:" in reported
    # The failure was somewhere else entirely, and the owner's real system is untouched.
    assert _unchanged(before, _everything(established))


def test_a_connection_to_an_unusable_destination_fails_at_the_destination_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Excludes a bare traceback where the model requires a stage and a next step."""
    monkeypatch.setenv(DATA_DIRECTORY_VARIABLE, "   ")
    err = io.StringIO()

    code = serve_main([], stderr=err)

    assert code == SERVE_FAILED
    reported = err.getvalue()
    assert "Stage: resolve-destination" in reported
    assert "established memory: unchanged" in reported
    assert "what to do next:" in reported


def test_setup_and_the_server_resolve_the_same_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Excludes the two commands disagreeing about where one owner's system lives.

    Setup honours the configured destination; a server that fell back to the platform
    default would refuse a memory the owner had just established, and the refusal would
    name a path they never chose.
    """
    destination = tmp_path / "configured"
    monkeypatch.setenv(DATA_DIRECTORY_VARIABLE, str(destination))
    assert _setup(["--yes", "--vocabulary", "blank"])[0] == EXIT_SUCCESS
    assert store_path(destination.resolve()).exists()

    err = io.StringIO()
    # Serving would block on standard input, so what is proved here is the negative it
    # depends on: this destination is not one the server reports as unestablished.
    monkeypatch.setenv(DATA_DIRECTORY_VARIABLE, str(tmp_path / "elsewhere"))
    assert serve_main([], stderr=err) == SERVE_FAILED
    assert str(tmp_path / "elsewhere") in err.getvalue()
    assert str(destination) not in err.getvalue()


# --- What the owner never has to administer ---------------------------------------------


def _help_text(command: Any) -> str:
    """Everything one of the two documented commands offers an owner.

    Captured from the process's own streams rather than the command's, because argparse
    writes help to ``sys.stdout`` regardless of what a caller passed it.
    """
    captured = io.StringIO()
    with redirect_stdout(captured), redirect_stderr(captured), pytest.raises(SystemExit):
        command(["--help"])
    return captured.getvalue()


def test_the_documented_commands_ask_for_nothing_an_owner_would_have_to_administer(
    established: Path,
) -> None:
    """One owner, one directory, one process.

    The requirement names what must not be required by name. This holds every command an
    owner runs to exactly the options they document, so a later slice cannot quietly add a
    tenant, a role, or a server to configure to any of them.
    """
    documented = _help_text(setup_main) + _help_text(serve_main) + _help_text(preserve_main)

    for administered in ("tenant", "organization", "role", "cluster", "server", "database"):
        assert administered not in documented.lower(), administered
    assert store_path(established.resolve()).parent == established.resolve()


# --- Preserving one memory and beginning another from it ----------------------------------


def _preserve(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = preserve_main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.anyio
async def test_a_preserved_memory_begins_another_system_at_the_state_it_reached(
    tmp_path: Path, established: Path
) -> None:
    """The third starting input, produced and consumed by the documented commands.

    Without this the owner could begin from a snapshot document but had no way to make
    one, so the loop the model describes — preserve here, begin there — would close only
    for somebody willing to write Python.
    """
    async with _serve(established) as agent:
        retained = await _call(
            agent,
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [{"uuid": "a-1", "type_key": PERSON, "display_name": "Ada"}]
                }
            },
        )
        assert retained["status"] == "accepted"
    source = _everything(established)

    document = tmp_path / "preserved.json"
    code, out, _ = _preserve(["--data-dir", str(established), "--out", str(document)])
    assert code == EXIT_SUCCESS
    assert "canonical memory and its revision are unchanged." in out
    assert "the capture is recorded in this system's activity history." in out
    # Preserving is a read: the memory it captured is exactly where it was.
    assert _unchanged(source, _everything(established))

    elsewhere = tmp_path / "elsewhere"
    assert (
        _setup(["--data-dir", str(elsewhere), "--from-snapshot", str(document)], answer="y\n")[0]
        == EXIT_SUCCESS
    )

    begun = _everything(elsewhere)
    assert begun.state.revision == source.state.revision
    assert canonical_state_equal(begun.state, source.state)
    async with _serve(elsewhere) as agent:
        carried = await _call(agent, "rtg_query", _people_query())
    assert _names(carried) == {"Ada"}


def test_preserving_a_destination_that_holds_no_memory_is_actionable(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()

    code, _, err = _preserve(["--data-dir", str(empty), "--out", str(tmp_path / "out.json")])

    assert code == EXIT_FAILED
    assert "Stage: open-memory" in err
    assert "established memory: unchanged" in err
    assert "what to do next:" in err
    assert not (tmp_path / "out.json").exists()


def test_preserving_to_a_path_that_cannot_be_written_is_actionable(
    tmp_path: Path, established: Path
) -> None:
    before = _everything(established)

    code, _, err = _preserve(
        ["--data-dir", str(established), "--out", str(tmp_path / "missing" / "out.json")]
    )

    assert code == EXIT_FAILED
    assert "Stage: write" in err
    assert "established memory: unchanged" in err
    assert "what to do next:" in err
    assert _unchanged(before, _everything(established))


def test_preserving_says_both_halves_of_what_it_did(tmp_path: Path, established: Path) -> None:
    """Excludes a success line that promises nothing happened while an observation did.

    The model's state effect for preserving has two halves: canonical memory and revision
    do not change, and the attempt is recorded observationally. An owner told only the
    first would find the second in their own activity history and be right to distrust it.
    """
    system = RTGSystem.open(store_path(established.resolve()))
    try:
        before = system.store.activity_record_count()
    finally:
        system.close()

    code, out, _ = _preserve(["--data-dir", str(established), "--out", str(tmp_path / "out.json")])

    assert code == EXIT_SUCCESS
    system = RTGSystem.open(store_path(established.resolve()))
    try:
        assert system.store.activity_record_count() > before
    finally:
        system.close()
    assert "the capture is recorded in this system's activity history." in out


def test_preserving_a_memory_this_account_cannot_write_says_so(
    tmp_path: Path, established: Path
) -> None:
    """Opening a store writes, so read access alone is not enough — and the advice says so.

    Excludes a corrective action the owner has already satisfied: told to check that they
    can read the file, they would find that they can, and be left with no next step.
    """
    established.chmod(0o500)
    try:
        code, _, err = _preserve(
            ["--data-dir", str(established), "--out", str(tmp_path / "out.json")]
        )
    finally:
        established.chmod(0o700)

    assert code == EXIT_FAILED
    assert "Stage: open-memory" in err
    assert "established memory: unchanged" in err
    assert "read and write that file and the directory holding it" in err


def test_preserving_never_writes_over_something_already_there(
    tmp_path: Path, established: Path
) -> None:
    """Excludes the typo that replaces the memory this command exists to protect.

    ``--out`` pointing at the store it just read would overwrite it and report success,
    and the owner would be told their memory was preserved by the run that destroyed it.
    """
    memory = store_path(established.resolve())
    before = memory.read_bytes()

    code, _, err = _preserve(["--data-dir", str(established), "--out", str(memory)])

    assert code == EXIT_FAILED
    assert "Stage: write" in err
    assert "already exists" in err
    assert "what to do next:" in err
    assert memory.read_bytes() == before


@pytest.mark.parametrize("command", ["serve", "preserve"])
def test_the_way_out_of_an_unestablished_destination_names_that_destination(
    tmp_path: Path, command: str
) -> None:
    """Excludes advice that would establish a second system somewhere else.

    An owner who launched against an explicit destination and is told to run setup would,
    following that literally, begin a system at the platform default — and the next launch
    would fail exactly as this one did. Advice that leads back to the same failure is not
    an available corrective action.
    """
    wanted = tmp_path / "wanted"
    wanted.mkdir()
    err = io.StringIO()

    if command == "serve":
        assert serve_main(["--data-dir", str(wanted)], stderr=err) == SERVE_FAILED
        reported = err.getvalue()
    else:
        code, _, reported = _preserve(
            ["--data-dir", str(wanted), "--out", str(tmp_path / "out.json")]
        )
        assert code == EXIT_FAILED

    assert "no Vellis memory is established" in reported
    assert f"--data-dir {wanted}" in reported


def test_a_preserve_failure_after_the_capture_says_the_capture_happened(
    tmp_path: Path, established: Path
) -> None:
    """Excludes a failure report that reassures about the half it did not affect.

    The write fails, but the capture already observed the memory. An owner told only
    "established memory: unchanged" would find that observation in their own activity
    history and have been told, in the same breath, that nothing happened.
    """
    system = RTGSystem.open(store_path(established.resolve()))
    try:
        before = system.store.activity_record_count()
    finally:
        system.close()

    code, _, err = _preserve(
        ["--data-dir", str(established), "--out", str(tmp_path / "missing" / "out.json")]
    )

    assert code == EXIT_FAILED
    system = RTGSystem.open(store_path(established.resolve()))
    try:
        assert system.store.activity_record_count() > before
    finally:
        system.close()
    assert "established memory: unchanged" in err
    assert "the attempt is recorded in this system's activity history." in err


def test_a_failure_before_the_capture_claims_no_observation(tmp_path: Path) -> None:
    """The other side of the same line: nothing was read, so nothing is claimed."""
    empty = tmp_path / "nothing"
    empty.mkdir()

    code, _, err = _preserve(["--data-dir", str(empty), "--out", str(tmp_path / "out.json")])

    assert code == EXIT_FAILED
    assert "established memory: unchanged" in err
    assert "activity history" not in err
