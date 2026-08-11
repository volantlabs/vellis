"""Evidence for ``VellisVerification::mcpToolSurface`` and ``::mcpOutcomes``.

Two questions. Is the surface exactly the selected ten, typed, and reachable with nothing
but core discovery and invocation? And does what comes back through it still mean what
the system meant — a semantic refusal distinct from malformed input, distinct again from
a failure, with every non-effect the operation promised still holding on the far side?

Everything here goes through an in-memory client rather than the Python functions, so the
assertions are about the boundary rather than about what sits behind it.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from conftest import build_rich_definitions
from fastmcp import Client
from mcp_types import Tool

from vellis.canonical import Provenance, canonical_state_equal
from vellis.changes import GraphChange
from vellis.graph import Anchor, AssociatedDataObject
from vellis.json_value import normalize
from vellis.mcp import TOOL_NAMES, build_server
from vellis.system import RTGSystem


@pytest.fixture
def system(tmp_path: Path):
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(),
        provenance=Provenance(initiator="owner"),
        initialization_summary="a fresh start",
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
        provenance=Provenance(initiator="owner"),
    ).accepted
    try:
        yield system
    finally:
        system.close()


@pytest.fixture
def client(system: RTGSystem):
    return Client(build_server(system))


def _payload(result) -> dict:
    """The structured content one call returned."""
    assert result.structured_content is not None
    return result.structured_content


# --- The surface ----------------------------------------------------------------------


@pytest.mark.anyio
async def test_exactly_the_selected_ten_tools_are_discoverable(client: Client) -> None:
    """Excludes a surface that grew a helper or lost one."""
    async with client:
        tools = cast("list[Tool]", await client.list_tools())

    assert tuple(tool.name for tool in tools) == TOOL_NAMES


@pytest.mark.anyio
async def test_every_tool_returns_typed_object_meaning(client: Client) -> None:
    async with client:
        tools = cast("list[Tool]", await client.list_tools())

    for tool in tools:
        assert tool.output_schema is not None, tool.name
        assert tool.output_schema.get("type") == "object", tool.name


@pytest.mark.anyio
async def test_only_operations_with_semantic_input_take_a_typed_input(
    client: Client,
) -> None:
    """The parameterless tools introduce no empty domain request type."""
    async with client:
        tools = {tool.name: tool for tool in cast("list[Tool]", await client.list_tools())}

    for name in (
        "rtg_definition_delta",
        "rtg_activate_definition_delta",
        "rtg_discard_definition_delta",
        "rtg_check",
    ):
        assert (tools[name].input_schema.get("properties") or {}) == {}, name

    for name in (
        "rtg_definition_inspect",
        "rtg_query",
        "rtg_change",
        "rtg_set_definition_delta",
        "rtg_history",
    ):
        assert tools[name].input_schema.get("properties") or {}, name


@pytest.mark.anyio
async def test_the_summary_carries_its_optional_selector_directly(client: Client) -> None:
    """Excludes wrapping one optional selector in a request type of its own."""
    async with client:
        tools = {tool.name: tool for tool in cast("list[Tool]", await client.list_tools())}

    properties = tools["rtg_definition_summary"].input_schema.get("properties") or {}
    assert set(properties) == {"historical_selection"}
    assert tools["rtg_definition_summary"].input_schema.get("required", []) == []


@pytest.mark.anyio
async def test_every_tool_is_reachable_through_core_invocation_alone(
    client: Client, system: RTGSystem
) -> None:
    """Excludes a surface that needs a capability beyond discovery and calling."""
    calls = {
        "rtg_definition_summary": {},
        "rtg_definition_inspect": {"request": {"anchor_type_keys": ["person"]}},
        "rtg_definition_delta": {},
        "rtg_query": {
            "query": {
                "anchor_groups": [{"name": "who", "anchor_type": "person"}],
                "return_shape": {
                    "projections": [
                        {"name": "p", "anchor_group": "who", "type": "AnchorProjection"}
                    ]
                },
                "maximum_rows": 10,
            }
        },
        "rtg_change": {"change": {}},
        "rtg_set_definition_delta": {"request": {"proposed_definitions": {}}},
        "rtg_activate_definition_delta": {},
        "rtg_discard_definition_delta": {},
        "rtg_check": {},
        "rtg_history": {"query": {"kind": "canonical", "maximum_records": 100}},
    }
    assert set(calls) == set(TOOL_NAMES)

    async with client:
        for name, arguments in calls.items():
            result = await client.call_tool(name, arguments, raise_on_error=False)
            assert result.structured_content is not None, name


# --- What comes back still means what the system meant --------------------------------


@pytest.mark.anyio
async def test_a_semantic_rejection_arrives_as_a_typed_result(client: Client) -> None:
    """Not an error: the memory answered, and the answer was no."""
    async with client:
        result = await client.call_tool(
            "rtg_definition_inspect",
            {"request": {"anchor_type_keys": ["unheard-of"]}},
            raise_on_error=False,
        )

    assert result.is_error is False
    payload = _payload(result)
    assert payload["status"] == "rejected"
    assert payload["findings"]
    assert payload["anchor_details"] == []
    assert payload["evaluated_revision"] is None


@pytest.mark.anyio
async def test_malformed_input_forms_no_domain_request(client: Client) -> None:
    """Excludes reporting a shape error as though the memory had considered it."""
    async with client:
        result = await client.call_tool(
            "rtg_definition_inspect",
            {"request": {"anchor_type_keys": "not a list"}},
            raise_on_error=False,
        )

    assert result.is_error is True
    assert result.structured_content is None


@pytest.mark.anyio
async def test_an_accepted_result_carries_its_complete_payload(client: Client) -> None:
    async with client:
        result = await client.call_tool("rtg_definition_summary", {})

    payload = _payload(result)
    assert payload["status"] == "accepted"
    assert {each["type_key"] for each in payload["anchor_types"]} == {"person", "project"}
    assert payload["evaluated_revision"] == 1
    assert payload["delta_present"] is False


@pytest.mark.anyio
async def test_a_rejected_mutation_preserves_its_promised_non_effect(
    client: Client, system: RTGSystem
) -> None:
    """The non-effect has to hold at the boundary, not only behind it."""
    before = system.current_state()
    records = system.store.canonical_record_count()

    async with client:
        result = await client.call_tool(
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [{"uuid": "x-1", "type_key": "ghost", "display_name": "X"}]
                }
            },
            raise_on_error=False,
        )

    payload = _payload(result)
    assert payload["status"] == "rejected"
    assert payload["resulting_revision"] is None
    assert canonical_state_equal(system.current_state(), before)
    assert system.store.canonical_record_count() == records


@pytest.mark.anyio
async def test_a_read_through_the_boundary_mutates_nothing(
    client: Client, system: RTGSystem
) -> None:
    before = system.current_state()
    records = system.store.canonical_record_count()

    async with client:
        for name in ("rtg_definition_summary", "rtg_definition_delta", "rtg_check"):
            assert (await client.call_tool(name, {})).structured_content is not None

    assert canonical_state_equal(system.current_state(), before)
    assert system.store.canonical_record_count() == records


@pytest.mark.anyio
async def test_structured_and_textual_representations_agree(client: Client) -> None:
    """Excludes a text rendering that says something the typed result does not."""
    async with client:
        result = await client.call_tool("rtg_check", {})

    structured = _payload(result)
    text = json.loads(result.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
    assert text == structured


@pytest.mark.anyio
async def test_an_accepted_mutation_commits_through_the_boundary(
    client: Client, system: RTGSystem
) -> None:
    async with client:
        result = await client.call_tool(
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [
                        {"uuid": "p-1", "type_key": "project", "display_name": "Orbit"}
                    ]
                }
            },
        )

    payload = _payload(result)
    assert payload["status"] == "accepted"
    assert payload["resulting_revision"] == 2
    assert system.current_state().graph.anchor("p-1") is not None


@pytest.mark.anyio
async def test_a_tool_call_is_attributed_to_the_agent_not_the_owner(
    client: Client, system: RTGSystem
) -> None:
    """The boundary records what it knows: something reached it through the client."""
    from vellis.activity import HistoryKind, HistoryQuery

    async with client:
        assert (await client.call_tool("rtg_check", {})).structured_content is not None

    entries = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100)
    ).activity_entries
    recorded = next(entry for entry in entries if entry.capability == "check")
    assert recorded.provenance.initiator == "agent"
    assert recorded.provenance.source == "mcp"


@pytest.mark.anyio
async def test_a_stored_number_arrives_as_a_number(client: Client, system: RTGSystem) -> None:
    """Excludes handing numbers back as text.

    The model permits only complete-object upserts, so an agent reads an object and
    writes it back whole. If a number came back as a string, that write would rewrite
    its owner's numbers into text — and nested values are not kind-checked, so it would
    commit.
    """
    assert system.apply_graph_change(
        GraphChange(
            associated_data_upserts=(
                AssociatedDataObject(
                    uuid="d-1",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={
                        "title": normalize("First"),
                        "rating": normalize(4),
                        "details": normalize({"attendees": [1, 2]}),
                    },
                ),
            )
        ),
        provenance=Provenance(initiator="owner"),
    ).accepted

    async with client:
        result = await client.call_tool(
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "who", "anchor_type": "person"}],
                    "data_conditions": [
                        {"name": "n", "anchor_group": "who", "associated_data_type": "note"}
                    ],
                    "return_shape": {
                        "projections": [
                            {
                                "name": "d",
                                "data_condition": "n",
                                "type": "AssociatedDataProjection",
                            }
                        ]
                    },
                    "maximum_rows": 10,
                }
            },
        )

    properties = _payload(result)["rows"][0]["associated_data"][0]["associated_data"]["properties"]
    assert properties["rating"] == 4
    assert properties["details"]["attendees"] == [1, 2]


@pytest.mark.anyio
async def test_an_object_read_through_the_boundary_can_be_written_back_whole(
    client: Client, system: RTGSystem
) -> None:
    """The complete-object workflow the model prescribes, end to end."""
    assert system.apply_graph_change(
        GraphChange(
            associated_data_upserts=(
                AssociatedDataObject(
                    uuid="d-1",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={"title": normalize("First"), "rating": normalize(4)},
                ),
            )
        ),
        provenance=Provenance(initiator="owner"),
    ).accepted

    async with client:
        read = await client.call_tool(
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "who", "anchor_type": "person"}],
                    "data_conditions": [
                        {"name": "n", "anchor_group": "who", "associated_data_type": "note"}
                    ],
                    "return_shape": {
                        "projections": [
                            {
                                "name": "d",
                                "data_condition": "n",
                                "type": "AssociatedDataProjection",
                            }
                        ]
                    },
                    "maximum_rows": 10,
                }
            },
        )
        obj = _payload(read)["rows"][0]["associated_data"][0]["associated_data"]
        obj["properties"]["title"] = "Second"

        written = await client.call_tool(
            "rtg_change", {"change": {"associated_data_upserts": [obj]}}, raise_on_error=False
        )

    assert _payload(written)["status"] == "accepted"
    stored = system.current_state().graph.associated_data_object("d-1")
    assert stored is not None
    assert stored.properties["rating"] == normalize(4)
    assert stored.properties["title"] == normalize("Second")


@pytest.mark.anyio
async def test_a_historical_selector_inside_the_query_reaches_that_state(
    client: Client, system: RTGSystem
) -> None:
    """The selector the model puts inside the query, exercised through the boundary."""
    query = {
        "anchor_groups": [{"name": "who", "anchor_type": "person"}],
        "return_shape": {
            "projections": [{"name": "p", "anchor_group": "who", "type": "AnchorProjection"}]
        },
        "maximum_rows": 10,
    }

    async with client:
        at_base = await client.call_tool(
            "rtg_query", {"query": {**query, "historical_selection": {"revision": 0}}}
        )
        now = await client.call_tool("rtg_query", {"query": query})

    assert _payload(at_base)["evaluated_revision"] == 0
    assert _payload(at_base)["rows"] == []
    assert _payload(now)["evaluated_revision"] == 1
    assert len(_payload(now)["rows"]) == 1


@pytest.mark.anyio
async def test_no_tool_gates_on_an_approval_it_invented(client: Client) -> None:
    """Excludes a per-call authorization the boundary made up.

    Checking the schema for suspicious parameter names would not catch a gate keyed on
    anything else, so this asks the question behaviourally: every tool answers with
    nothing supplied that could be read as approval.
    """
    async with client:
        for name in ("rtg_check", "rtg_definition_summary", "rtg_definition_delta"):
            assert (await client.call_tool(name, {})).structured_content is not None
        committed = await client.call_tool(
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [
                        {"uuid": "p-9", "type_key": "project", "display_name": "Orbit"}
                    ]
                }
            },
        )

    assert _payload(committed)["status"] == "accepted"


@pytest.mark.anyio
async def test_an_unexpected_failure_produces_no_completed_domain_result(
    client: Client, system: RTGSystem
) -> None:
    """The third outcome shape, distinct from a rejection and from malformed input."""
    system.store.close()

    async with client:
        result = await client.call_tool(
            "rtg_history",
            {"query": {"kind": "canonical", "maximum_records": 10}},
            raise_on_error=False,
        )

    payload = result.structured_content
    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["canonical_entries"] == []
    assert payload["evaluated_revision"] is None


# --- What the wire form promises ------------------------------------------------------


@pytest.mark.anyio
async def test_a_large_integer_arrives_exactly(client: Client, system: RTGSystem) -> None:
    """Excludes rendering integers through a float, which rounds past 2**53."""
    exact = normalize(Decimal("10000000000000000000000001"))
    assert system.apply_graph_change(
        GraphChange(
            associated_data_upserts=(
                AssociatedDataObject(
                    uuid="d-1",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={"title": normalize("First"), "details": {"n": exact}},
                ),
            )
        ),
        provenance=Provenance(initiator="owner"),
    ).accepted

    async with client:
        result = await client.call_tool("rtg_query", {"query": _note_query()})

    returned = _note_properties(result)["details"]["n"]
    assert isinstance(returned, int)
    assert returned == 10000000000000000000000001


@pytest.mark.anyio
async def test_a_number_the_wire_cannot_carry_is_a_typed_refusal(
    client: Client, system: RTGSystem
) -> None:
    """Excludes crashing on a value the system itself accepted.

    A number beyond what JSON can carry exactly makes the answer unreturnable, and the
    model calls that a refusal. Raising would leave the object permanently unreadable
    through the only surface an agent has.
    """
    assert system.apply_graph_change(
        GraphChange(
            associated_data_upserts=(
                AssociatedDataObject(
                    uuid="d-1",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={
                        "title": normalize("First"),
                        "details": {"n": Decimal("0.1234567890123456789")},
                    },
                ),
            )
        ),
        provenance=Provenance(initiator="owner"),
    ).accepted

    async with client:
        result = await client.call_tool("rtg_query", {"query": _note_query()}, raise_on_error=False)

    assert result.is_error is False
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["rows"] == []
    assert payload["evaluated_revision"] is None


@pytest.mark.anyio
async def test_a_timestamp_and_an_enum_arrive_as_text(client: Client) -> None:
    """Excludes handing back a Python object the wire has no form for."""
    async with client:
        result = await client.call_tool(
            "rtg_history", {"query": {"kind": "canonical", "maximum_records": 100}}
        )

    entry = _payload(result)["canonical_entries"][0]
    assert isinstance(entry["recorded_at"], str)
    assert entry["recorded_at"].endswith("+00:00")
    later = _payload(result)["canonical_entries"][1]
    assert later["transition_kind"] == "graphMutation"


def _note_query() -> dict:
    return {
        "anchor_groups": [{"name": "who", "anchor_type": "person"}],
        "data_conditions": [{"name": "n", "anchor_group": "who", "associated_data_type": "note"}],
        "return_shape": {
            "projections": [{"name": "d", "data_condition": "n"}],
        },
        "maximum_rows": 10,
    }


def _note_properties(result) -> dict:
    row = _payload(result)["rows"][0]
    return row["associated_data"][0]["associated_data"]["properties"]


@pytest.mark.anyio
async def test_structured_and_textual_agree_on_a_payload_that_could_disagree(
    client: Client, system: RTGSystem
) -> None:
    """Numbers and timestamps are where the two renderings could part company."""
    async with client:
        result = await client.call_tool(
            "rtg_history", {"query": {"kind": "canonical", "maximum_records": 100}}
        )

    assert json.loads(result.content[0].text) == _payload(result)  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.anyio
async def test_every_tool_records_the_agent_that_called_it(
    client: Client, system: RTGSystem
) -> None:
    """Excludes attributing part of the surface and not the rest."""
    from vellis.activity import HistoryKind, HistoryQuery

    async with client:
        for name, arguments in (
            ("rtg_definition_summary", {}),
            ("rtg_definition_inspect", {"request": {"anchor_type_keys": ["person"]}}),
            ("rtg_definition_delta", {}),
            ("rtg_query", {"query": _note_query()}),
            ("rtg_check", {}),
            ("rtg_set_definition_delta", {"request": {"proposed_definitions": {}}}),
            ("rtg_activate_definition_delta", {}),
            ("rtg_discard_definition_delta", {}),
            ("rtg_change", {"change": {"anchor_removals": ["nope"]}}),
        ):
            await client.call_tool(name, arguments, raise_on_error=False)

    entries = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=200)
    ).activity_entries
    assert entries
    assert {entry.provenance.initiator for entry in entries} == {"agent"}
    assert {entry.provenance.source for entry in entries} == {"mcp"}

    # An accepted change is canonical authority rather than an observation, so its
    # attribution lives in the other ledger.
    from vellis.canonical import TransitionKind

    committed = system.history(
        HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=200)
    ).canonical_entries
    staged = [
        entry.provenance
        for entry in committed
        if entry.transition_kind is TransitionKind.DEFINITION_DELTA_CHANGE
    ]
    assert len(staged) == 2  # the proposal, and the discard that cleared it
    assert set(staged) == {Provenance(initiator="agent", source="mcp")}


@pytest.mark.anyio
async def test_an_inspection_selector_inside_the_request_reaches_that_state(
    client: Client, system: RTGSystem
) -> None:
    async with client:
        result = await client.call_tool(
            "rtg_definition_inspect",
            {
                "request": {
                    "anchor_type_keys": ["person"],
                    "historical_selection": {"revision": 0},
                }
            },
        )

    assert _payload(result)["evaluated_revision"] == 0


@pytest.mark.anyio
async def test_a_revision_beyond_any_ledger_is_refused_not_raised(client: Client) -> None:
    async with client:
        result = await client.call_tool(
            "rtg_definition_summary",
            {"historical_selection": {"revision": 2**63}},
            raise_on_error=False,
        )

    assert result.is_error is False
    assert _payload(result)["status"] == "rejected"


@pytest.mark.anyio
async def test_two_writers_racing_leave_one_rejection_and_no_lost_change(
    system: RTGSystem,
) -> None:
    """Excludes reporting a lost race as a broken store, and excludes losing the update."""
    import anyio

    server = build_server(system)
    accepted: list[dict] = []
    rejected: list[dict] = []

    async def write(index: int) -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "rtg_change",
                {
                    "change": {
                        "anchor_upserts": [
                            {
                                "uuid": f"p-{index}",
                                "type_key": "project",
                                "display_name": f"P{index}",
                            }
                        ]
                    }
                },
                raise_on_error=False,
            )
        payload = result.structured_content
        assert payload is not None
        (accepted if payload["status"] == "accepted" else rejected).append(payload)

    async with anyio.create_task_group() as group:
        for index in range(8):
            group.start_soon(write, index)

    assert accepted
    assert all(each["status"] == "rejected" for each in rejected)
    assert system.current_state().revision == 1 + len(accepted)
