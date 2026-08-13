"""Evidence for ``VellisVerification::ownerControl`` and ``::observableFailure``.

Every capability these workflows use already has evidence of its own. What is not yet
shown is the whole: that the owner-facing use cases in ``Vellis`` — obtaining and
retaining context, reviewing memory and both histories, correcting and forgetting,
governing vocabulary, assessing conformance, exploring what memory used to be, preserving
it, checking that it can be recovered, and restoring it — compose into one system the
owner governs, and that a refusal or a failure anywhere in them reaches whoever asked
while every non-effect it promised still holds.

The agent-facing use cases go through the selected MCP boundary, because that is the
contract an external agent actually reaches. Four of the use cases the model gives the
system as its own RTG client — retention, snapshot, recovery check, and restoration —
are deliberately absent from that surface, and the model selects no owner transport for
them, so they are exercised at the boundary that realizes them. Correcting and forgetting
is the fifth such use case, but it is one the agent-facing surface does carry, so it is
exercised there; the owner-boundary path for the same operation is evidence for
``RTGSystem::'Apply graph change'`` and lives with it.

Approval is the load-bearing thing Vellis does not implement. The model is explicit that
the tools neither establish the agent's scope nor decide whether the owner approved a
proposal: a declined proposal is one that never becomes a call. So the evidence that
declined context is not retained cannot be a rejection — it has to be that looking at
memory is incapable of retaining anything, and that memory after a declined proposal is
indistinguishable from memory that was never asked.

Each check compares a whole state-effect vector rather than the one value under test:
graph, active definitions, delta, and revision, together with the canonical ledger, and
with the activity ledger read separately because an observation is the one thing allowed
to move it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from tests.vellis.evolution_support import activate_clean_delta, stage_complete_fixture
from vellis.activity import ActivityRecord, HistoryKind, HistoryQuery, RetentionDecision
from vellis.canonical import (
    CanonicalState,
    CanonicalTransitionRecord,
    Provenance,
    canonical_state_equal,
    now,
)
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkTypeDefinition,
    definition_set_equal,
)
from vellis.everyday_life import everyday_life_starter
from vellis.graph import Anchor, graph_equal
from vellis.history import RevisionSelection
from vellis.mcp import build_server
from vellis.outcomes import OperationStatus
from vellis.replay import ReplayRequest
from vellis.setup import FreshVocabularyChoice, prepare_local_system
from vellis.system import RTGSystem

OWNER = Provenance(initiator="owner")


def _starting_vocabulary() -> GraphDefinitionSet:
    """The vocabulary this owner already has.

    Deliberately small and anchor-and-link only, so a complete proposal can be written
    out here without a rendering layer that could quietly drop part of one. The families
    it leaves out are guarded in :func:`_proposal`.
    """
    return GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition(type_key="person", description="Someone the owner knows."),
            AnchorTypeDefinition(type_key="project", description="A piece of work."),
        ),
        link_types=(
            LinkTypeDefinition(
                type_key="worksOn",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("person",),
                    permitted_target_type_keys=("project",),
                    description="Who works on what.",
                ),
                description="A working relationship.",
            ),
        ),
    )


# --- One established personal memory --------------------------------------------------


@pytest.fixture
def store_file(tmp_path: Path) -> Path:
    return tmp_path / "vellis.sqlite3"


@pytest.fixture
def memory(store_file: Path):
    """One Vellis system the owner already began, holding two anchors at revision 1."""
    system = RTGSystem.open(store_file)
    assert system.initialize_fresh(
        _starting_vocabulary(),
        provenance=OWNER,
        initialization_summary="a fresh start",
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=(
                Anchor(uuid="a-1", type_key="person", display_name="Ada"),
                Anchor(uuid="a-2", type_key="project", display_name="Orbit"),
            )
        ),
        provenance=OWNER,
    ).accepted
    try:
        yield system
    finally:
        system.close()


@pytest.fixture
def agent(memory: RTGSystem) -> Client:
    """The one trusted owner-configured agent, reaching memory through the ten tools."""
    return Client(build_server(memory))


# --- Reading the whole state-effect vector --------------------------------------------


@dataclass(frozen=True, slots=True)
class _Everything:
    """Every governed state one operation could move."""

    state: CanonicalState
    transitions: tuple[CanonicalTransitionRecord, ...]
    activity: tuple[ActivityRecord, ...]


def _everything(system: RTGSystem) -> _Everything:
    return _Everything(
        state=system.current_state(),
        transitions=system.store.transitions(),
        activity=system.store.activity_records(),
    )


def _canonically_unchanged(before: _Everything, after: _Everything) -> bool:
    """Whether graph, definitions, delta, revision, and canonical history all held."""
    return canonical_state_equal(before.state, after.state) and (
        before.transitions == after.transitions
    )


async def _call(client: Client, name: str, arguments: dict[str, Any] | None = None) -> dict:
    """Invoke one tool and return the structured meaning it answered with."""
    result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    assert result.structured_content is not None, name
    return result.structured_content


# --- The shapes these workflows ask in ------------------------------------------------


def _people_query(*, maximum_rows: int = 10, revision: int | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {
        "anchor_groups": [{"name": "who", "anchor_type": "person"}],
        "return_shape": {
            "projections": [{"name": "person", "anchor_group": "who", "type": "AnchorProjection"}]
        },
        "maximum_rows": maximum_rows,
    }
    if revision is not None:
        query["historical_selection"] = {"revision": revision}
    return query


def _names(payload: dict) -> set[str]:
    return {
        binding["anchor"]["display_name"] for row in payload["rows"] for binding in row["anchors"]
    }


def _anchor_upsert(uuid: str, type_key: str, display_name: str) -> dict[str, Any]:
    return {
        "change": {
            "anchor_upserts": [{"uuid": uuid, "type_key": type_key, "display_name": display_name}]
        }
    }


def _proposal(definitions: GraphDefinitionSet) -> dict[str, Any]:
    """Render one complete proposed definition set the way the boundary takes it.

    A definition delta replaces the whole vocabulary, so an incomplete rendering would
    silently propose deleting what it failed to mention. This refuses to render a set
    carrying a family it does not write out.
    """
    assert not definitions.associated_data_types
    assert not definitions.relationship_constraints
    return {
        "anchor_types": [
            {"type_key": each.type_key, "description": each.description}
            for each in definitions.anchor_types
        ],
        "link_types": [
            {
                "type_key": each.type_key,
                "description": each.description,
                "endpoint_constraint": {
                    "permitted_source_type_keys": list(
                        each.endpoint_constraint.permitted_source_type_keys
                    ),
                    "permitted_target_type_keys": list(
                        each.endpoint_constraint.permitted_target_type_keys
                    ),
                    "description": each.endpoint_constraint.description,
                },
            }
            for each in definitions.link_types
        ],
    }


def _plus_team(base: GraphDefinitionSet, *, description: str | None) -> GraphDefinitionSet:
    """The owner's next vocabulary: the one they have, plus one more anchor type."""
    return GraphDefinitionSet(
        anchor_types=(
            *base.anchor_types,
            AnchorTypeDefinition(type_key="team", description=description),
        ),
        associated_data_types=base.associated_data_types,
        link_types=base.link_types,
        relationship_constraints=base.relationship_constraints,
    )


# --- Disclosure: looking at memory never changes it -----------------------------------


@pytest.mark.anyio
async def test_every_way_of_looking_at_memory_leaves_it_exactly_as_it_was(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a read path that retains, caches into, or advances canonical memory.

    This is what makes an owner's decision to decline a proposal mean anything: if any of
    the seven ways an agent can look at memory could write, declining would not be a
    decision the system is capable of respecting.
    """
    before = _everything(memory)

    async with agent:
        answers = [
            await _call(agent, "rtg_definition_summary"),
            await _call(
                agent, "rtg_definition_inspect", {"request": {"anchor_type_keys": ["person"]}}
            ),
            await _call(agent, "rtg_definition_delta"),
            await _call(agent, "rtg_query", {"query": _people_query()}),
            await _call(
                agent, "rtg_history", {"query": {"kind": "canonical", "maximum_records": 10}}
            ),
            await _call(
                agent, "rtg_history", {"query": {"kind": "activity", "maximum_records": 10}}
            ),
        ]
        assessed = await _call(agent, "rtg_check")

    # Each read answered, so this says the reads are harmless rather than that they are
    # inert: a surface that had started refusing everything would also move nothing.
    assert [answer["status"] for answer in answers] == ["accepted"] * 6
    assert assessed["conforms"] is True

    after = _everything(memory)
    assert _canonically_unchanged(before, after)
    assert len(after.activity) == len(before.activity) + 7


@pytest.mark.anyio
async def test_reviewing_both_histories_shows_what_happened_without_joining_it(
    agent: Client, memory: RTGSystem
) -> None:
    """Both ledgers are the owner's to read, and neither read appears in the other."""
    async with agent:
        canonical = await _call(
            agent, "rtg_history", {"query": {"kind": "canonical", "maximum_records": 10}}
        )
        activity = await _call(
            agent, "rtg_history", {"query": {"kind": "activity", "maximum_records": 10}}
        )

    assert canonical["status"] == "accepted"
    assert [entry["revision"] for entry in canonical["canonical_entries"]] == [0, 1]
    assert canonical["activity_entries"] == []

    assert activity["status"] == "accepted"
    # The activity read selected before its own record was appended, so it sees the
    # canonical read that came first and not itself.
    assert [entry["capability"] for entry in activity["activity_entries"]] == ["history"]
    assert activity["canonical_entries"] == []


@pytest.mark.anyio
async def test_a_cold_agent_reaches_a_query_from_discovery_alone(agent: Client) -> None:
    """Excludes a vocabulary an agent has to already know to use.

    Nothing here is written down in advance: the type the query asks about, the type the
    projection names, and the shape of the answer all come out of what discovery said.
    """
    async with agent:
        summary = await _call(agent, "rtg_definition_summary")
        discovered = sorted(entry["type_key"] for entry in summary["anchor_types"])
        detail = await _call(
            agent, "rtg_definition_inspect", {"request": {"anchor_type_keys": discovered}}
        )
        chosen = detail["anchor_details"][0]["anchor_type"]["type_key"]
        answered = await _call(
            agent,
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "found", "anchor_type": chosen}],
                    "return_shape": {
                        "projections": [
                            {"name": "it", "anchor_group": "found", "type": "AnchorProjection"}
                        ]
                    },
                    "maximum_rows": 10,
                }
            },
        )

    assert discovered == ["person", "project"]
    assert summary["evaluated_revision"] == 1
    assert answered["status"] == "accepted"
    assert answered["evaluated_revision"] == 1
    assert {
        binding["anchor"]["type_key"] for row in answered["rows"] for binding in row["anchors"]
    } == {chosen}


@pytest.mark.anyio
async def test_assessing_memory_reports_on_the_current_revision_and_changes_nothing(
    agent: Client, memory: RTGSystem
) -> None:
    """Conformance is a report about a state, not an operation on one."""
    before = _everything(memory)

    async with agent:
        assessed = await _call(agent, "rtg_check")

    assert assessed["conforms"] is True
    assert assessed["scope"] == "graphConformance"
    assert assessed["evaluated_revision"] == before.state.revision
    assert _canonically_unchanged(before, _everything(memory))


# --- Retaining only what the owner approved -------------------------------------------


@pytest.mark.anyio
async def test_context_the_owner_declined_is_never_retained(
    agent: Client, memory: RTGSystem
) -> None:
    """The declined workflow, up to and not including the change.

    A declined proposal is one that never becomes a call, so what this excludes is not a
    boundary that keeps a submitted proposal — there is nothing submitted to keep. It
    excludes a preparation path that leaves a trace of its own: the agent does everything
    it would do to prepare the change, the owner declines, and memory afterwards is
    indistinguishable from memory that was never asked, down to the absence of the one
    anchor the prepared change would have written.
    """
    before = _everything(memory)

    async with agent:
        await _call(agent, "rtg_definition_summary")
        await _call(agent, "rtg_definition_inspect", {"request": {"anchor_type_keys": ["person"]}})
        # The owner declines here, so the prepared change is never submitted.
        answered = await _call(agent, "rtg_query", {"query": _people_query()})

    assert _names(answered) == {"Ada"}
    assert _canonically_unchanged(before, _everything(memory))
    assert memory.current_state().graph.anchor("a-3") is None


@pytest.mark.anyio
async def test_context_the_owner_approved_is_recovered_by_a_later_session(
    agent: Client, memory: RTGSystem, store_file: Path
) -> None:
    """Approved context outlives the session that retained it.

    Excludes memory that is only as durable as the agent conversation that wrote it,
    which is the whole difference between retaining context and remembering it.
    """
    async with agent:
        retained = await _call(agent, "rtg_change", _anchor_upsert("a-3", "person", "Grace"))

    assert retained["status"] == "accepted"
    assert retained["resulting_revision"] == 2
    memory.close()

    later = RTGSystem.open(store_file)
    try:
        async with Client(build_server(later)) as session:
            recovered = await _call(session, "rtg_query", {"query": _people_query()})
    finally:
        later.close()

    assert _names(recovered) == {"Ada", "Grace"}


@pytest.mark.anyio
async def test_approved_context_that_does_not_conform_is_not_retained(
    agent: Client, memory: RTGSystem
) -> None:
    """Owner approval is not a conformance argument.

    Excludes retaining an approved change because it was approved. The owner said yes to
    a working relationship with something that is not there; memory says no, and says so.
    """
    before = _everything(memory)

    async with agent:
        refused = await _call(
            agent,
            "rtg_change",
            {
                "change": {
                    "link_upserts": [
                        {
                            "uuid": "l-1",
                            "type_key": "worksOn",
                            "source_uuid": "a-1",
                            "target_uuid": "a-missing",
                        }
                    ]
                }
            },
        )

    assert refused["status"] == "rejected"
    assert refused["findings"]
    assert refused["resulting_revision"] is None
    assert _canonically_unchanged(before, _everything(memory))


# --- Correcting and forgetting --------------------------------------------------------


@pytest.mark.anyio
async def test_correcting_memory_leaves_what_it_corrected_in_history(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a correction that edits the past instead of adding to it.

    An owner correcting a name needs the correction to be what memory now says; an owner
    exploring prior memory needs what it used to say to still be there.
    """
    async with agent:
        corrected = await _call(
            agent, "rtg_change", _anchor_upsert("a-1", "person", "Ada Lovelace")
        )
        current = await _call(agent, "rtg_query", {"query": _people_query()})
        earlier = await _call(agent, "rtg_query", {"query": _people_query(revision=1)})

    assert corrected["status"] == "accepted"
    assert _names(current) == {"Ada Lovelace"}
    assert earlier["evaluated_revision"] == 1
    assert _names(earlier) == {"Ada"}
    assert canonical_state_equal(memory.current_state(), memory.replay())


@pytest.mark.anyio
async def test_forgetting_memory_removes_it_from_what_memory_now_says(
    agent: Client, memory: RTGSystem
) -> None:
    """Forgetting is a change like any other: current answers lose it, replay agrees."""
    async with agent:
        forgotten = await _call(agent, "rtg_change", {"change": {"anchor_removals": ["a-1"]}})
        current = await _call(agent, "rtg_query", {"query": _people_query()})
        earlier = await _call(agent, "rtg_query", {"query": _people_query(revision=1)})

    assert forgotten["status"] == "accepted"
    assert _names(current) == set()
    assert _names(earlier) == {"Ada"}
    assert canonical_state_equal(memory.current_state(), memory.replay())


# --- Governing the vocabulary ---------------------------------------------------------


@pytest.mark.anyio
async def test_a_proposal_the_owner_leaves_staged_is_still_there_afterwards(
    agent: Client, memory: RTGSystem, store_file: Path
) -> None:
    """Excludes a proposal lost to unrelated work or to a restart.

    Staging is the owner deciding not to decide yet. Ordinary graph work happens on top
    of it, the process ends, and the draft is still the draft — and still not the
    vocabulary in force.
    """
    proposed = _plus_team(_starting_vocabulary(), description="A group of people.")

    async with agent:
        staged = await _call(
            agent,
            "rtg_set_definition_delta",
            {"request": {"proposed_definitions": _proposal(proposed)}},
        )
        worked = await _call(agent, "rtg_change", _anchor_upsert("a-3", "person", "Grace"))

    assert staged["status"] == "accepted"
    assert worked["status"] == "accepted"
    memory.close()

    later = RTGSystem.open(store_file)
    try:
        async with Client(build_server(later)) as session:
            retrieved = await _call(session, "rtg_definition_delta")
            active = await _call(session, "rtg_definition_summary")
        standing = later.current_state()
    finally:
        later.close()

    assert retrieved["status"] == "accepted"
    assert standing.definition_delta is not None
    assert definition_set_equal(standing.definition_delta.proposed_definitions, proposed)
    assert "team" not in {entry["type_key"] for entry in active["anchor_types"]}


@pytest.mark.anyio
async def test_a_proposal_is_reviewed_for_readable_meaning_before_it_can_be_activated(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes activating a proposal the system itself found wanting.

    The owner stages a draft, reads the assessment, sees the type they left undescribed,
    fixes that one thing, and activates. Findings gate activation, not staging.
    """
    active = _starting_vocabulary()
    before = _everything(memory)

    async with agent:
        assessed = await _call(
            agent,
            "rtg_set_definition_delta",
            {"request": {"proposed_definitions": _proposal(_plus_team(active, description=None))}},
        )
        refused = await _call(agent, "rtg_activate_definition_delta")

    assert assessed["status"] == "accepted"
    assert assessed["assessment"]["conforms"] is False
    assert assessed["assessment"]["findings"]
    assert refused["status"] == "rejected"
    assert refused["findings"]
    # The refusal moved the vocabulary no more than it moved the graph, and it kept the
    # draft rather than discarding work the owner never asked to lose.
    assert graph_equal(memory.current_state().graph, before.state.graph)
    assert definition_set_equal(memory.current_state().active_definitions, active)
    assert memory.current_state().definition_delta is not None

    described = _plus_team(active, description="A group of people who work together.")
    async with agent:
        reassessed = await _call(
            agent,
            "rtg_set_definition_delta",
            {"request": {"proposed_definitions": _proposal(described)}},
        )
        activated = await _call(agent, "rtg_activate_definition_delta")
        summary = await _call(agent, "rtg_definition_summary")

    assert reassessed["assessment"]["conforms"] is True
    assert activated["status"] == "accepted"
    assert "team" in {entry["type_key"] for entry in summary["anchor_types"]}
    assert definition_set_equal(memory.current_state().active_definitions, described)
    assert memory.current_state().definition_delta is None


@pytest.mark.anyio
async def test_a_discarded_proposal_leaves_the_vocabulary_it_would_have_changed(
    agent: Client, memory: RTGSystem
) -> None:
    """The owner's other answer, and it costs the active set nothing."""
    proposed = _plus_team(_starting_vocabulary(), description="A group of people.")

    async with agent:
        await _call(
            agent,
            "rtg_set_definition_delta",
            {"request": {"proposed_definitions": _proposal(proposed)}},
        )
        discarded = await _call(agent, "rtg_discard_definition_delta")
        summary = await _call(agent, "rtg_definition_summary")

    assert discarded["status"] == "accepted"
    assert memory.current_state().definition_delta is None
    assert definition_set_equal(memory.current_state().active_definitions, _starting_vocabulary())
    assert "team" not in {entry["type_key"] for entry in summary["anchor_types"]}


@pytest.mark.anyio
async def test_exploring_prior_memory_uses_the_vocabulary_that_state_had(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes historical reads that answer with today's vocabulary.

    The owner retires a type they no longer use. What they recorded under it is still
    there in the state that had it, and a cold agent reaches it the same way it reaches
    anything: discover the vocabulary at the resolved revision, inspect it, then ask.
    """
    retained = GraphDefinitionSet(anchor_types=(_starting_vocabulary().anchor_types[0],))

    async with agent:
        assert (await _call(agent, "rtg_change", {"change": {"anchor_removals": ["a-2"]}}))[
            "status"
        ] == "accepted"
        assert (
            await _call(
                agent,
                "rtg_set_definition_delta",
                {"request": {"proposed_definitions": _proposal(retained)}},
            )
        )["status"] == "accepted"
        assert (await _call(agent, "rtg_activate_definition_delta"))["status"] == "accepted"

        current = await _call(agent, "rtg_definition_summary")
        was = await _call(
            agent, "rtg_definition_summary", {"historical_selection": {"revision": 1}}
        )
        inspected = await _call(
            agent,
            "rtg_definition_inspect",
            {"request": {"anchor_type_keys": ["project"], "historical_selection": {"revision": 1}}},
        )
        found = await _call(
            agent,
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "what", "anchor_type": "project"}],
                    "return_shape": {
                        "projections": [
                            {"name": "it", "anchor_group": "what", "type": "AnchorProjection"}
                        ]
                    },
                    "maximum_rows": 10,
                    "historical_selection": {"revision": 1},
                }
            },
        )
        # The same question about current state is refused: the type is not active now.
        refused = await _call(
            agent,
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "what", "anchor_type": "project"}],
                    "return_shape": {
                        "projections": [
                            {"name": "it", "anchor_group": "what", "type": "AnchorProjection"}
                        ]
                    },
                    "maximum_rows": 10,
                }
            },
        )

    assert {entry["type_key"] for entry in current["anchor_types"]} == {"person"}
    assert {entry["type_key"] for entry in was["anchor_types"]} == {"person", "project"}
    assert was["evaluated_revision"] == 1
    assert inspected["status"] == "accepted"
    assert inspected["anchor_details"][0]["anchor_type"]["type_key"] == "project"
    assert inspected["evaluated_revision"] == 1
    assert found["status"] == "accepted"
    assert found["evaluated_revision"] == 1
    assert _names(found) == {"Orbit"}
    assert refused["status"] == "rejected"
    assert canonical_state_equal(memory.current_state(), memory.replay())


def test_an_established_system_reaches_the_starter_only_through_ordinary_governance(
    tmp_path: Path,
) -> None:
    """Evidence that first use is the only place a starting vocabulary is offered.

    Excludes a second way into the Everyday Life vocabulary. Setup, asked for the starter
    at a destination that already holds memory, establishes nothing and changes nothing.
    The owner who wants it later reaches it the way they reach any other vocabulary:
    propose it, have it assessed against the memory they already have, and activate it.
    """
    directory = tmp_path / "memory"
    began = prepare_local_system(
        data_directory=directory, choice=FreshVocabularyChoice.BLANK, environ={}
    )
    assert began.succeeded
    assert began.store is not None

    asked_again = prepare_local_system(
        data_directory=directory,
        choice=FreshVocabularyChoice.EVERYDAY_LIFE_STARTER,
        environ={},
    )

    assert not asked_again.succeeded
    assert not asked_again.memory_changed
    assert asked_again.is_actionable_failure

    starter = everyday_life_starter()
    system = RTGSystem.open(began.store)
    try:
        assert not system.current_state().active_definitions.anchor_types
        assert stage_complete_fixture(system, starter, provenance=OWNER).accepted
        activated = activate_clean_delta(system, provenance=OWNER)
        adopted = system.current_state()
    finally:
        system.close()

    assert activated.accepted
    assert definition_set_equal(adopted.active_definitions, starter)
    assert adopted.definition_delta is None
    # Two ordinary transitions on the same lineage — a proposal and its activation —
    # rather than an installation, and the starter creates no graph objects.
    assert adopted.revision == 2
    assert not adopted.graph.anchors
    assert not adopted.graph.associated_data
    assert not adopted.graph.links


# --- Retention: forgetting activity moves nothing replay reads ------------------------


def test_forgetting_activity_history_leaves_canonical_memory_exactly_where_it_was(
    memory: RTGSystem,
) -> None:
    """Excludes a retention decision that reaches the canonical ledger.

    This asymmetry is why the two ledgers exist. The owner empties the record of what was
    asked, and what their memory *is* — down to the snapshot identity binding it to this
    lineage — is the same afterwards.
    """
    assert memory.history(HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=10)).accepted
    assert memory.check(provenance=OWNER).conforms
    captured = memory.create_snapshot(provenance=OWNER)
    assert captured.snapshot is not None
    before = _everything(memory)
    before_replay = memory.replay()
    assert len(before.activity) == 3

    forgotten = memory.manage_activity_retention(
        RetentionDecision(remove_before=now() + timedelta(seconds=1)), provenance=OWNER
    )

    after = _everything(memory)
    recaptured = memory.create_snapshot(provenance=OWNER)
    assert recaptured.snapshot is not None
    assert forgotten.accepted
    assert forgotten.resulting_revision is None
    assert _canonically_unchanged(before, after)
    assert canonical_state_equal(before_replay, memory.replay())
    assert recaptured.snapshot.captured_through == captured.snapshot.captured_through
    # Everything the owner asked to forget is gone, and an accepted decision leaves no
    # observation of its own: only a failed attempt appends one.
    assert after.activity == ()


# --- Preserving memory, and proving it can be recovered -------------------------------


def test_the_owner_can_prove_recovery_without_moving_live_memory(memory: RTGSystem) -> None:
    """Capture, keep working, then rebuild from the capture and the tail that followed.

    Excludes a recovery check answered out of live state, and one that quietly
    initializes or restores rather than reconstructing for inspection. The same capture
    is replayed twice — once with the tail that followed it and once without — so a
    reconstruction that reported live memory instead of what it was given would have to
    disagree with one of the two answers.
    """
    captured = memory.create_snapshot(provenance=OWNER)
    assert captured.snapshot is not None
    at_capture = memory.current_state()
    assert memory.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor(uuid="a-3", type_key="person", display_name="Grace"),)),
        provenance=OWNER,
    ).accepted
    before = _everything(memory)
    assert before.state.revision != at_capture.revision

    caught_up = memory.reconstruct_state(
        ReplayRequest(
            snapshot=captured.snapshot,
            tail=memory.ledger_tail(after=captured.snapshot.revision),
        ),
        provenance=OWNER,
    )
    as_captured = memory.reconstruct_state(
        ReplayRequest(snapshot=captured.snapshot), provenance=OWNER
    )

    assert caught_up.accepted
    assert caught_up.canonical_state is not None
    assert canonical_state_equal(caught_up.canonical_state, before.state)
    # The capture alone answers with the revision it captured, not with where memory has
    # since got to, so the answer came from the supplied base rather than from live state.
    assert as_captured.accepted
    assert as_captured.canonical_state is not None
    assert canonical_state_equal(as_captured.canonical_state, at_capture)
    assert as_captured.canonical_state.graph.anchor("a-3") is None
    assert _canonically_unchanged(before, _everything(memory))


def test_restoring_a_past_state_makes_it_current_without_rewriting_anything(
    memory: RTGSystem,
) -> None:
    """Excludes a restoration that truncates the ledger back to the selected revision.

    Going back is itself something that happened, so it is a new revision, the history it
    came from is untouched, and the owner can go back from it again.
    """
    original = memory.current_state()
    assert memory.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor(uuid="a-3", type_key="person", display_name="Grace"),)),
        provenance=OWNER,
    ).accepted
    before = _everything(memory)

    restored = memory.restore_historical_state(RevisionSelection(revision=1), provenance=OWNER)

    after = _everything(memory)
    assert restored.accepted
    assert restored.resulting_revision == 3
    assert after.state.revision == 3
    assert graph_equal(after.state.graph, original.graph)
    assert after.state.graph.anchor("a-3") is None
    assert after.transitions[: len(before.transitions)] == before.transitions
    assert canonical_state_equal(after.state, memory.replay())


# --- Observable failure ---------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("rtg_query", {"query": _people_query(maximum_rows=0)}),
        (
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "who", "anchor_type": "unknown"}],
                    "return_shape": {
                        "projections": [
                            {"name": "p", "anchor_group": "who", "type": "AnchorProjection"}
                        ]
                    },
                    "maximum_rows": 10,
                }
            },
        ),
        ("rtg_definition_inspect", {"request": {"anchor_type_keys": ["unknown"]}}),
        ("rtg_change", {"change": {"anchor_removals": ["a-missing"]}}),
        ("rtg_activate_definition_delta", {}),
        ("rtg_history", {"query": {"kind": "activity", "maximum_records": 0}}),
    ],
)
async def test_a_refusal_reaches_the_caller_and_moves_nothing(
    agent: Client, memory: RTGSystem, tool: str, arguments: dict[str, Any]
) -> None:
    """Every semantic refusal these workflows can meet, and its promised non-effects.

    Excludes a refusal reported as success, and one that leaves part of what it refused
    behind — in the payload as well as in memory, since each of these operations promises
    that a rejection carries no partial result and no evaluated revision. The activity
    ledger is checked as a prefix rather than for equality, because observing the refused
    attempt is the one effect it is allowed to have.
    """
    before = _everything(memory)

    async with agent:
        refused = await _call(agent, tool, arguments)

    after = _everything(memory)
    assert refused["status"] == "rejected", refused
    assert refused["summary"], refused
    for content in ("rows", "anchor_details", "canonical_entries", "activity_entries"):
        assert refused.get(content, []) == [], refused
    assert refused.get("evaluated_revision") is None, refused
    assert _canonically_unchanged(before, after)
    assert after.activity[: len(before.activity)] == before.activity


@pytest.mark.anyio
async def test_a_result_larger_than_the_owner_asked_for_is_refused_whole(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes truncating an over-broad answer to the bound.

    An owner reviewing their memory has to be able to tell that they saw all of it, so a
    result that would exceed the bound comes back as no result at all.
    """
    async with agent:
        assert (await _call(agent, "rtg_change", _anchor_upsert("a-3", "person", "Grace")))[
            "status"
        ] == "accepted"
        refused = await _call(agent, "rtg_query", {"query": _people_query(maximum_rows=1)})

    assert refused["status"] == "rejected"
    assert refused["rows"] == []
    assert refused["evaluated_revision"] is None
    assert refused["findings"]


def test_the_owner_only_operations_refuse_observably_too(memory: RTGSystem) -> None:
    """The operations the tool surface does not carry, refused and non-effecting.

    A refused retention has one non-effect the others do not: it must preserve every
    activity record that already existed, which is the one ledger this comparison
    otherwise allows to move.
    """
    assert memory.history(HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=10)).accepted
    before = _everything(memory)
    assert before.activity

    retention = memory.manage_activity_retention(
        RetentionDecision(remove_before=now().replace(tzinfo=None)), provenance=OWNER
    )
    unknown = memory.restore_historical_state(RevisionSelection(revision=99), provenance=OWNER)
    foreign = memory.reconstruct_state(
        ReplayRequest(
            initial=memory.initial_record(),
            base_identity="not this ledger's base",
            tail=memory.ledger_tail(after=0),
        ),
        provenance=OWNER,
    )

    after = _everything(memory)
    for outcome in (retention, unknown, foreign):
        assert outcome.status is OperationStatus.REJECTED, outcome
        assert outcome.findings, outcome
    assert foreign.canonical_state is None
    assert _canonically_unchanged(before, after)
    assert after.activity[: len(before.activity)] == before.activity


def test_a_restoration_refuses_rather_than_discarding_a_proposal_in_flight(
    memory: RTGSystem,
) -> None:
    """The owner's staged work is not collateral of going back."""
    proposed = _plus_team(_starting_vocabulary(), description="A group of people.")
    assert stage_complete_fixture(memory, proposed, provenance=OWNER).accepted
    before = _everything(memory)

    refused = memory.restore_historical_state(RevisionSelection(revision=1), provenance=OWNER)

    after = _everything(memory)
    assert refused.status is OperationStatus.REJECTED
    assert refused.findings
    assert _canonically_unchanged(before, after)
    assert after.state.definition_delta is not None


@pytest.mark.anyio
async def test_an_execution_failure_is_reported_and_leaves_memory_intact(
    agent: Client, memory: RTGSystem, store_file: Path
) -> None:
    """The third outcome shape, across the workflows rather than at one operation.

    Excludes a failure that is reported as a refusal or as an answer, and one that got
    half of a change written. An assessment has no failure status to return — a report
    says whether the graph conforms, never whether the assessment ran — so its failure
    reaches the caller as no completed result at all, which is the third outcome shape
    and not the same thing as a graph that does not conform. Memory is read back through
    a new system, so what is checked is what the store holds rather than a projection
    still in hand.
    """
    before = _everything(memory)
    memory.store.close()

    async with agent:
        queried = await _call(agent, "rtg_query", {"query": _people_query()})
        changed = await _call(agent, "rtg_change", _anchor_upsert("a-3", "person", "Grace"))
        read = await _call(
            agent, "rtg_history", {"query": {"kind": "canonical", "maximum_records": 5}}
        )
        assessed = await agent.call_tool("rtg_check", {}, raise_on_error=False)

    assert queried["status"] == "failed"
    assert queried["rows"] == []
    assert queried["evaluated_revision"] is None
    assert changed["status"] == "failed"
    assert changed["resulting_revision"] is None
    assert read["status"] == "failed"
    assert read["canonical_entries"] == []
    assert assessed.is_error
    assert assessed.structured_content is None

    reopened = RTGSystem.open(store_file)
    try:
        after = _everything(reopened)
        assert _canonically_unchanged(before, after)
        assert canonical_state_equal(after.state, reopened.replay())
    finally:
        reopened.close()
