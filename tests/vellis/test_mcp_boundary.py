"""Concise evidence for the accepted ten-tool MCP contract."""

import json
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastmcp import Client

from vellis.canonical import Provenance
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    PropertyConstraint,
)
from vellis.json_value import JsonKind
from vellis.mcp import TOOL_NAMES, build_server
from vellis.system import RTGSystem


@pytest.fixture
def system(tmp_path: Path) -> Iterator[RTGSystem]:
    value = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert value.initialize_fresh(
        GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
        provenance=Provenance("owner"),
        initialization_summary="fresh",
    ).accepted
    yield value
    value.close()


@pytest.fixture
def client(system: RTGSystem) -> Client:
    return Client(build_server(system))


@pytest.mark.anyio
async def test_exactly_the_ten_selected_tools_are_exposed(client: Client) -> None:
    async with client:
        tools = await client.list_tools()
        names = tuple(tool.name for tool in tools)
    assert names == TOOL_NAMES
    assert all(
        tool.output_schema is not None and tool.output_schema["type"] == "object" for tool in tools
    )


def _references(node: object) -> bool:
    """Report whether one schema fragment defers meaning to a reference."""
    if isinstance(node, dict):
        return "$ref" in node or any(_references(member) for member in node.values())
    if isinstance(node, list):
        return any(_references(member) for member in node)
    return False


@pytest.mark.anyio
async def test_published_input_schemas_carry_their_whole_meaning(client: Client) -> None:
    """A caller reading discovery must learn what a request looks like.

    The other tests here hand ``call_tool`` a dictionary, so they never consult a schema
    and cannot notice one that says nothing. A client that resolves no references sees
    exactly what this asserts: a request type, or an untyped blank it can only guess at.
    Resolving references is an additional capability the contract does not permit
    requiring, and a tool whose semantic input arrives blank is a tool nobody can call.
    """
    async with client:
        tools = await client.list_tools()
    for tool in tools:
        schema = tool.input_schema
        assert "$defs" not in schema, f"{tool.name} publishes a separate definitions block"
        assert not _references(schema), f"{tool.name} publishes an unresolved reference"
        for parameter, declared in schema.get("properties", {}).items():
            assert declared.get("type") == "object", (
                f"{tool.name} declares no object meaning for {parameter}"
            )
            assert declared.get("properties"), f"{tool.name} declares no members for {parameter}"


@pytest.mark.anyio
async def test_query_discovery_explains_identity_counts_and_multi_type_grounding(
    client: Client,
) -> None:
    async with client:
        tools = await client.list_tools()
    query = next(tool for tool in tools if tool.name == "rtg_query")
    description = " ".join((query.description or "").split())

    assert "identity-bearing anchor" in description
    assert "exact object count" in description
    assert "permits every anchor type" in description
    assert "query each type separately" in description


@pytest.fixture
def valued_client(tmp_path: Path) -> Iterator[Client]:
    value = RTGSystem.open(tmp_path / "valued.sqlite3")
    assert value.initialize_fresh(
        GraphDefinitionSet(
            anchor_types=(AnchorTypeDefinition("person", "A person."),),
            associated_data_types=(
                AssociatedDataTypeDefinition(
                    "person.stats",
                    ("person",),
                    (
                        PropertyConstraint("count", False, JsonKind.NUMBER, "A count."),
                        PropertyConstraint("flag", False, JsonKind.BOOLEAN, "A flag."),
                        PropertyConstraint("blob", False, JsonKind.OBJECT, "An object."),
                        PropertyConstraint("list", False, JsonKind.ARRAY, "An array."),
                    ),
                    "Stats.",
                ),
            ),
        ),
        provenance=Provenance("owner"),
        initialization_summary="fresh",
    ).accepted
    yield Client(build_server(value))
    value.close()


@pytest.mark.anyio
async def test_a_stored_value_keeps_the_json_kind_the_caller_sent(valued_client: Client) -> None:
    """One and zero are numbers, and stay numbers wherever they sit.

    A Boolean read leniently accepts both, so a value arriving through a tool can have its
    kind decided by how it was parsed rather than by what it is. Where a declaration names
    the kind that surfaces as a refusal an owner can see; inside an array or an object no
    declaration reaches the member, and the substituted Boolean is committed silently. This
    sends every kind, including the two numbers that collide, and reads them back.
    """
    sent: dict[str, object] = {
        "count": 1,
        "flag": True,
        "blob": {"a": 1, "b": 0, "c": 2},
        "list": [0, 1, 2, True, False],
    }
    async with valued_client as client:
        changed = await client.call_tool(
            "rtg_change",
            {
                "request": {
                    "target": "active",
                    "change": {
                        "anchor_upserts": [
                            {"uuid": "p-1", "type_key": "person", "display_name": "Ada"}
                        ],
                        "associated_data_upserts": [
                            {
                                "uuid": "d-1",
                                "type_key": "person.stats",
                                "anchor_uuids": ["p-1"],
                                "properties": sent,
                            }
                        ],
                    },
                }
            },
        )
        queried = await client.call_tool(
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "people", "anchor_types": ["person"]}],
                    "data_conditions": [
                        {
                            "name": "stats",
                            "anchor_group": "people",
                            "associated_data_type": "person.stats",
                        }
                    ],
                    "return_shape": {
                        "projections": [
                            {"name": name, "data_condition": "stats", "property_name": name}
                            for name in sent
                        ]
                    },
                    "maximum_rows": 2,
                }
            },
        )
    assert changed.structured_content is not None
    assert changed.structured_content["status"] == "accepted", changed.structured_content
    assert queried.structured_content is not None
    returned = {
        each["projection"]: each["value"]
        for each in queried.structured_content["rows"][0]["properties"]
    }
    # Compared as JSON text so that True and 1 cannot pass for one another.
    assert json.dumps(returned, sort_keys=True) == json.dumps(sent, sort_keys=True)


def _raw_mcp_response(
    process: subprocess.Popen[str], request_id: int
) -> tuple[dict[str, object], str]:
    assert process.stdout is not None
    while line := process.stdout.readline():
        response = json.loads(line, parse_float=Decimal)
        if response.get("id") == request_id:
            return response, line
    raise AssertionError(f"the MCP server ended before answering request {request_id}")


def test_raw_stdio_preserves_a_high_precision_fraction_in_both_directions(tmp_path: Path) -> None:
    """The transport must not round a JSON number before Vellis can read its meaning."""
    directory = tmp_path / "memory"
    directory.mkdir()
    memory = directory / "vellis.sqlite3"
    system = RTGSystem.open(memory)
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(AnchorTypeDefinition("person", "A person."),),
                associated_data_types=(
                    AssociatedDataTypeDefinition(
                        "person.stats",
                        ("person",),
                        (PropertyConstraint("ratio", False, JsonKind.NUMBER, "A ratio."),),
                        "Stats.",
                    ),
                ),
            ),
            provenance=Provenance("owner"),
            initialization_summary="fresh",
        ).accepted
    finally:
        system.close()

    process = subprocess.Popen(
        [sys.executable, "-m", "vellis", "--data-dir", str(directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    exact = Decimal("0.12345678901234567890123456789")
    try:
        assert process.stdin is not None

        def send(message: dict[str, object]) -> None:
            assert process.stdin is not None
            process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            process.stdin.flush()

        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "exact-number-evidence", "version": "1"},
                },
            }
        )
        initialized, _ = _raw_mcp_response(process, 1)
        assert "result" in initialized
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        # Written as raw text on purpose: constructing this request through Python's
        # ordinary JSON encoder would round it before the transport test even began.
        process.stdin.write(
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"rtg_change",'
            '"arguments":{"request":{"target":"active","change":{"anchor_upserts":['
            '{"uuid":"p-1","type_key":"person","display_name":"Ada"}],'
            '"associated_data_upserts":[{"uuid":"d-1","type_key":"person.stats",'
            '"anchor_uuids":["p-1"],"properties":{"ratio":' + str(exact) + "}}]}}}}}\n"
        )
        process.stdin.flush()
        changed, _ = _raw_mcp_response(process, 2)
        changed_result = changed["result"]
        assert isinstance(changed_result, dict)
        changed_content = changed_result["structuredContent"]
        assert isinstance(changed_content, dict)
        assert changed_content["status"] == "accepted"

        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "rtg_query",
                    "arguments": {
                        "query": {
                            "anchor_groups": [{"name": "people", "anchor_types": ["person"]}],
                            "data_conditions": [
                                {
                                    "name": "stats",
                                    "anchor_group": "people",
                                    "associated_data_type": "person.stats",
                                }
                            ],
                            "return_shape": {
                                "projections": [
                                    {
                                        "name": "ratio",
                                        "data_condition": "stats",
                                        "property_name": "ratio",
                                    }
                                ]
                            },
                            "maximum_rows": 2,
                        }
                    },
                },
            }
        )
        queried, raw_query = _raw_mcp_response(process, 3)
        query_result = queried["result"]
        assert isinstance(query_result, dict)
        structured = query_result["structuredContent"]
        assert isinstance(structured, dict)
        rows = structured["rows"]
        assert isinstance(rows, list)
        assert structured["status"] == "accepted"
        assert rows[0]["properties"][0]["value"] == exact, raw_query
        assert f'"value":{exact}' in raw_query
        content = query_result["content"]
        assert isinstance(content, list)
        text = content[0]["text"]
        assert isinstance(text, str)
        assert json.loads(text, parse_float=Decimal) == structured

        process.stdin.close()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


@pytest.mark.anyio
async def test_typed_current_change_and_bounded_query_round_trip(client: Client) -> None:
    async with client:
        changed = await client.call_tool(
            "rtg_change",
            {
                "request": {
                    "target": "active",
                    "change": {
                        "anchor_upserts": [
                            {"uuid": "a-1", "type_key": "person", "display_name": "Ada"}
                        ]
                    },
                }
            },
        )
        queried = await client.call_tool(
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "people", "anchor_types": ["person"]}],
                    "return_shape": {
                        "projections": [
                            {
                                "name": "person",
                                "anchor_group": "people",
                            }
                        ]
                    },
                    "maximum_rows": 2,
                }
            },
        )
    assert changed.structured_content is not None
    assert changed.structured_content["status"] == "accepted"
    assert queried.structured_content is not None
    assert queried.structured_content["status"] == "accepted"
    assert queried.structured_content["rows"][0]["anchors"][0]["anchor"]["uuid"] == "a-1"


@pytest.mark.anyio
async def test_the_former_single_anchor_type_spelling_remains_callable(client: Client) -> None:
    """A multi-type extension must not invalidate already accepted singleton requests."""
    async with client:
        queried = await client.call_tool(
            "rtg_query",
            {
                "query": {
                    "anchor_groups": [{"name": "people", "anchor_type": "person"}],
                    "return_shape": {"projections": [{"name": "person", "anchor_group": "people"}]},
                    "maximum_rows": 2,
                }
            },
            raise_on_error=False,
        )
    assert not queried.is_error
    assert queried.structured_content is not None
    assert queried.structured_content["status"] == "accepted"
    returned_query = queried.structured_content["query"]
    assert returned_query["anchor_groups"][0]["anchor_types"] == ["person"]
    assert "anchor_type" not in returned_query["anchor_groups"][0]


@pytest.mark.anyio
async def test_proposal_assessment_and_exact_activation_use_typed_requests(
    client: Client,
) -> None:
    async with client:
        staged = await client.call_tool(
            "rtg_set_definition_delta",
            {
                "request": {
                    "change": {
                        "anchor_type_upserts": [{"type_key": "team", "description": "A team."}]
                    }
                }
            },
        )
        assessed = await client.call_tool(
            "rtg_check",
            {
                "request": {
                    "kind": "assess",
                    "scope": "definitionDelta",
                    "maximum_findings": 10,
                }
            },
        )
        assert assessed.structured_content is not None
        activated = await client.call_tool(
            "rtg_activate_definition_delta",
            {"request": {"assessment_id": assessed.structured_content["assessment_id"]}},
        )
    assert staged.structured_content is not None
    assert staged.structured_content["status"] == "accepted"
    assert assessed.structured_content["conforms"] is True
    assert activated.structured_content is not None
    assert activated.structured_content["status"] == "accepted"


@pytest.mark.anyio
async def test_semantic_rejection_is_typed_but_malformed_input_is_not_a_domain_result(
    client: Client,
) -> None:
    async with client:
        refused = await client.call_tool(
            "rtg_change",
            {
                "request": {
                    "target": "active",
                    "change": {"anchor_removals": ["missing"]},
                }
            },
            raise_on_error=False,
        )
        malformed = await client.call_tool("rtg_change", {"change": {}}, raise_on_error=False)
    assert refused.structured_content is not None
    assert refused.structured_content["status"] == "rejected"
    assert malformed.structured_content is None
    assert malformed.is_error


@pytest.mark.anyio
async def test_every_remaining_selected_tool_invokes_one_typed_system_behavior(
    client: Client,
) -> None:
    async with client:
        summary = await client.call_tool("rtg_definition_summary", {"request": {}})
        inspected = await client.call_tool(
            "rtg_definition_inspect",
            {"request": {"anchor_type_keys": ["person"]}},
        )
        absent = await client.call_tool("rtg_definition_delta", {})
        discarded = await client.call_tool("rtg_discard_definition_delta", {})
        history = await client.call_tool(
            "rtg_history",
            {"query": {"kind": "activity", "maximum_records": 20}},
        )
    results = (summary, inspected, absent, discarded, history)
    assert all(result.structured_content is not None for result in results)
    summary_content = summary.structured_content
    inspected_content = inspected.structured_content
    absent_content = absent.structured_content
    discarded_content = discarded.structured_content
    history_content = history.structured_content
    assert summary_content is not None
    assert inspected_content is not None
    assert absent_content is not None
    assert discarded_content is not None
    assert history_content is not None
    assert summary_content["anchor_types"][0]["type_key"] == "person"
    assert inspected_content["anchor_details"][0]["anchor_type"]["type_key"] == "person"
    assert absent_content["status"] == "accepted"
    assert discarded_content["status"] == "rejected"
    assert history_content["status"] == "accepted"


@pytest.mark.anyio
async def test_an_unexpected_tool_failure_is_not_misreported_as_a_domain_result(
    client: Client, system: RTGSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_values: object) -> object:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(system, "definition_summary", fail)
    async with client:
        result = await client.call_tool("rtg_definition_summary", {}, raise_on_error=False)
    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
async def test_text_and_structured_results_agree_and_reads_change_no_canonical_state(
    client: Client, system: RTGSystem
) -> None:
    before_revision = system.store.current_revision()
    before_records = system.store.canonical_record_count()
    before_activity = system.store.activity_record_count()

    async with client:
        result = await client.call_tool("rtg_definition_summary", {"request": {}})

    assert result.structured_content is not None
    text_blocks = [block.text for block in result.content if block.type == "text"]
    assert len(text_blocks) == 1
    assert json.loads(text_blocks[0]) == result.structured_content
    assert system.store.current_revision() == before_revision
    assert system.store.canonical_record_count() == before_records
    assert system.store.activity_record_count() == before_activity + 1
