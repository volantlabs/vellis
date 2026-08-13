"""Evidence for ``VellisVerification::improvementAnalysis``.

An owner's memory gets worse on its own. Reviews go stale, a vocabulary keeps a concept
nobody uses any more, and the same request keeps failing for the same reason. The model
asks Vellis to *support* an external agent noticing those things — not to notice them
itself. Everything here therefore runs the analysis outside Vellis, in this module, out
of nothing but the ten tools, and checks what Vellis had to provide for it to work.

Four properties carry that support, and each is a thing the analysis could not do
without:

Bounded intervals of both ledgers. What happened is in the canonical ledger; what was
asked and refused is in the activity ledger. An analysis reads explicit intervals of
each, with its own maximum, and a interval holding more than it asked for is refused
whole rather than truncated — a truncated interval would produce findings that read as
complete and are not.

Continuation. A scheduled run picks up where the last one stopped, so the second run
reads what happened since and not the whole history again. The place it stopped is the
agent's own state: Vellis stores no cursor, consumes no interval, and answers the same
bounded question the same way however many times it is asked.

Rediscovery. Findings are drawn at an evaluated revision, and memory moves on. Before
proposing anything the analysis reads current definitions again — a delta replaces the
whole vocabulary and would otherwise silently retire what the owner added since, and a
graph change is written in concepts that may have been retired since the run read them.
Current facts are rechecked with them, because the owner may already have fixed the
thing being cleaned up.

Approval. Nothing the analysis concludes reaches canonical memory. A proposal the owner
declines is one that never becomes a call, so declining is not a refusal to observe: it
is that memory afterwards is indistinguishable from memory that was never asked.

Traceability runs underneath all four. Every finding here cites the bounded observations
it came from and the exact revisions those observations were evaluated at, and a check
holds each citation to an observation the run actually made through the selected surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from tests.vellis.evolution_support import activate_clean_delta, stage_complete_fixture
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
    AssociatedDataTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkTypeDefinition,
    PropertyConstraint,
    ValueRange,
)
from vellis.graph import Anchor, AssociatedDataObject, Link
from vellis.json_value import JsonKind, normalize
from vellis.mcp import TOOL_NAMES, build_server
from vellis.system import RTGSystem

OWNER = Provenance(initiator="owner")
AGENT = Provenance(initiator="agent", source="mcp")

# The year the analysis in these tests treats a review as stale before. A parameter of
# the analysis, not of Vellis: what counts as stale is the agent's judgement, and the
# only thing Vellis contributes is answering a bounded ordered question about it.
FRESH_FROM = 2026


def _starting_vocabulary() -> GraphDefinitionSet:
    """The vocabulary this owner already has.

    ``fax`` is here because a real vocabulary accumulates concepts that stop being used;
    it is what the unused-vocabulary finding is about. ``reviewedYear`` is a number
    because an ordered comparison is defined on numbers, which is what lets staleness be
    a bounded query rather than a scan the agent filters afterwards.
    """
    return GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition(type_key="person", description="Someone the owner knows."),
            AnchorTypeDefinition(type_key="project", description="A piece of work."),
            AnchorTypeDefinition(type_key="fax", description="A fax machine the owner once had."),
        ),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="review",
                permitted_anchor_type_keys=("project",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="reviewedYear",
                        required=True,
                        json_kind=JsonKind.NUMBER,
                        description="The year this project was last looked at.",
                        value_range=ValueRange(
                            lower_bound=normalize(2000), upper_bound=normalize(2100)
                        ),
                    ),
                ),
                description="When a project was last looked at.",
            ),
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


# --- One memory with something worth noticing in it -----------------------------------


@pytest.fixture
def store_file(tmp_path: Path) -> Path:
    return tmp_path / "vellis.sqlite3"


@pytest.fixture
def memory(store_file: Path):
    """A memory that has been used for a while, and has drifted.

    Three revisions of ordinary use leave two projects reviewed long ago and one
    reviewed recently, an anchor type nothing was ever created under, and three
    identical failed attempts by an agent to store something under a type that does not
    exist. The failures are applied here rather than through the boundary because a
    refused tool call records exactly this — the boundary attributes the agent and hands
    the system the same change — and the attribution itself is evidence elsewhere.
    """
    system = RTGSystem.open(store_file)
    assert system.initialize_fresh(
        _starting_vocabulary(),
        provenance=OWNER,
        initialization_summary="a fresh start",
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=(
                Anchor(uuid="a-ada", type_key="person", display_name="Ada"),
                Anchor(uuid="p-orbit", type_key="project", display_name="Orbit"),
                Anchor(uuid="p-beacon", type_key="project", display_name="Beacon"),
                Anchor(uuid="p-kite", type_key="project", display_name="Kite"),
            )
        ),
        provenance=OWNER,
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            associated_data_upserts=(
                _review("d-orbit", "p-orbit", 2024),
                _review("d-beacon", "p-beacon", 2024),
                _review("d-kite", "p-kite", 2026),
            )
        ),
        provenance=OWNER,
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            link_upserts=(
                Link(uuid="l-1", type_key="worksOn", source_uuid="a-ada", target_uuid="p-orbit"),
            )
        ),
        provenance=OWNER,
    ).accepted
    for _ in range(3):
        assert not system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor(uuid="x-1", type_key="meeting", display_name="Standup"),)
            ),
            provenance=AGENT,
        ).accepted
    try:
        yield system
    finally:
        system.close()


@pytest.fixture
def agent(memory: RTGSystem) -> Client:
    """The owner-configured agent that runs the analysis, reaching memory through tools."""
    return Client(build_server(memory))


def _review(uuid: str, project: str, year: int) -> AssociatedDataObject:
    return AssociatedDataObject(
        uuid=uuid,
        type_key="review",
        anchor_uuids=(project,),
        properties={"reviewedYear": normalize(year)},
    )


# --- Reading the whole state-effect vector --------------------------------------------


@dataclass(frozen=True, slots=True)
class _Everything:
    """Every governed state one operation could move."""

    state: CanonicalState
    transitions: tuple[CanonicalTransitionRecord, ...]
    activity: tuple[Any, ...]


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


# --- The shapes the analysis asks in --------------------------------------------------


async def _call(client: Client, name: str, arguments: dict[str, Any] | None = None) -> dict:
    """Invoke one tool and return the structured meaning it answered with."""
    result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    assert result.structured_content is not None, name
    return result.structured_content


def _interval(
    kind: str,
    *,
    maximum_records: int,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {"kind": kind, "maximum_records": maximum_records}
    if since is not None:
        query["start_time"] = since.isoformat()
    if until is not None:
        query["end_time"] = until.isoformat()
    return {"query": query}


def _anchors_of_type(type_key: str, *, maximum_rows: int) -> dict[str, Any]:
    """A bounded question about whether anything of one type exists."""
    return {
        "query": {
            "anchor_groups": [{"name": "of_type", "anchor_type": type_key}],
            "return_shape": {
                "projections": [
                    {"name": "anchor", "anchor_group": "of_type", "type": "AnchorProjection"}
                ]
            },
            "maximum_rows": maximum_rows,
        }
    }


def _stale_reviews(*, maximum_rows: int, revision: int | None = None) -> dict[str, Any]:
    """A bounded ordered question: which projects were last reviewed before ``FRESH_FROM``."""
    query: dict[str, Any] = {
        "anchor_groups": [{"name": "projects", "anchor_type": "project"}],
        "data_conditions": [
            {
                "name": "reviews",
                "anchor_group": "projects",
                "associated_data_type": "review",
                "property_conditions": [
                    {
                        "property_name": "reviewedYear",
                        "comparison": "lessThan",
                        "expected_value": FRESH_FROM,
                    }
                ],
            }
        ],
        "return_shape": {
            "projections": [
                {"name": "project", "anchor_group": "projects", "type": "AnchorProjection"},
                {"name": "review", "data_condition": "reviews", "type": "AssociatedDataProjection"},
            ]
        },
        "maximum_rows": maximum_rows,
    }
    if revision is not None:
        query["historical_selection"] = {"revision": revision}
    return {"query": query}


def _stale_pairs(payload: dict) -> set[tuple[str, str]]:
    """The project and review identities one stale-review answer returned."""
    return {
        (
            row["anchors"][0]["anchor"]["uuid"],
            row["associated_data"][0]["associated_data"]["uuid"],
        )
        for row in payload["rows"]
    }


# --- The analysis, which runs outside Vellis ------------------------------------------


@dataclass(frozen=True, slots=True)
class _Observation:
    """One thing the analysis asked, and the state it was answered at.

    ``bound`` is the maximum the request carried, and is absent for discovery, which
    takes none: the vocabulary is bounded by being the vocabulary. It is recorded
    because a finding resting on an unbounded read of the ledger or the graph would not
    be an explanation an owner can check.
    """

    tool: str
    subject: str
    bound: int | None
    evaluated_revision: int | None


@dataclass(frozen=True, slots=True)
class _Finding:
    """One owner-visible thing the analysis noticed, and what it noticed it from."""

    kind: str
    subject: str
    drawn_from: tuple[_Observation, ...]


@dataclass(frozen=True, slots=True)
class _Run:
    """One scheduled pass, and the point a later pass would continue from."""

    observations: tuple[_Observation, ...]
    findings: tuple[_Finding, ...]
    canonical_entries: tuple[dict, ...]
    activity_entries: tuple[dict, ...]
    processed_through: datetime

    def of_kind(self, kind: str) -> set[str]:
        return {finding.subject for finding in self.findings if finding.kind == kind}


def _recorded(entries: tuple[dict, ...]) -> list[datetime]:
    return [datetime.fromisoformat(entry["recorded_at"]) for entry in entries]


async def _analysis(
    client: Client,
    *,
    until: datetime,
    since: datetime | None = None,
    maximum_records: int = 50,
    maximum_rows: int = 20,
) -> _Run:
    """Run one pass of the external analysis over one explicit interval.

    Nothing in here is Vellis. It is the shape of an owner-configured agent that wakes
    up, reads a bounded slice of what happened, looks at the state those records were
    evaluated at and at current state, and writes down what it would propose. Every call
    it makes is recorded as an observation, so what it concludes can be held against
    what it actually asked.
    """
    observations: list[_Observation] = []
    findings: list[_Finding] = []

    changes = await _call(
        client,
        "rtg_history",
        _interval("canonical", maximum_records=maximum_records, since=since, until=until),
    )
    assert changes["status"] == "accepted", changes["findings"]
    seen_changes = tuple(changes["canonical_entries"])
    observations.append(
        _Observation(
            "rtg_history", "the canonical interval", maximum_records, changes["evaluated_revision"]
        )
    )

    attempts = await _call(
        client,
        "rtg_history",
        _interval("activity", maximum_records=maximum_records, since=since, until=until),
    )
    assert attempts["status"] == "accepted", attempts["findings"]
    seen_attempts = tuple(attempts["activity_entries"])
    activity_read = _Observation(
        "rtg_history", "the activity interval", maximum_records, attempts["evaluated_revision"]
    )
    observations.append(activity_read)

    # The same request refused for the same reason more than once is the shape of a
    # problem the owner can act on; one refusal is just a mistake.
    repeated: dict[tuple[str, str], int] = {}
    for entry in seen_attempts:
        if entry["outcome_category"] == "rejected":
            key = (entry["capability"], entry["semantic_scope"])
            repeated[key] = repeated.get(key, 0) + 1
    for (capability, scope), count in repeated.items():
        if count > 1:
            findings.append(
                _Finding("repeatedFailure", f"{capability} on {scope}", (activity_read,))
            )

    # What the vocabulary was when those records were written. A finding about the state
    # in an interval has to be read with the definitions that state had.
    if seen_changes:
        evaluated = seen_changes[-1]["revision"]
        then = await _call(
            client, "rtg_definition_summary", {"historical_selection": {"revision": evaluated}}
        )
        assert then["status"] == "accepted", then["findings"]
        observations.append(
            _Observation(
                "rtg_definition_summary",
                f"the vocabulary at revision {evaluated}",
                None,
                then["evaluated_revision"],
            )
        )
        # The question is only askable if that state had the concept to ask it about, so
        # the discovery above shapes the query rather than merely accompanying it.
        if "project" in _anchor_type_keys(then):
            was_stale = await _call(
                client, "rtg_query", _stale_reviews(maximum_rows=maximum_rows, revision=evaluated)
            )
            assert was_stale["status"] == "accepted", was_stale["findings"]
            observations.append(
                _Observation(
                    "rtg_query",
                    f"stale reviews at revision {evaluated}",
                    maximum_rows,
                    was_stale["evaluated_revision"],
                )
            )
            for project, review in sorted(_stale_pairs(was_stale)):
                findings.append(
                    _Finding("staleData", f"{project}/{review}", tuple(observations[-2:]))
                )

    vocabulary = await _call(client, "rtg_definition_summary")
    assert vocabulary["status"] == "accepted", vocabulary["findings"]
    current_vocabulary = _Observation(
        "rtg_definition_summary",
        "the current vocabulary",
        None,
        vocabulary["evaluated_revision"],
    )
    observations.append(current_vocabulary)

    for entry in vocabulary["anchor_types"]:
        type_key = entry["type_key"]
        used = await _call(
            client, "rtg_query", _anchors_of_type(type_key, maximum_rows=maximum_rows)
        )
        assert used["status"] == "accepted", used["findings"]
        looked = _Observation(
            "rtg_query", f"anchors of type {type_key}", maximum_rows, used["evaluated_revision"]
        )
        observations.append(looked)
        if not used["rows"]:
            findings.append(_Finding("unusedVocabulary", type_key, (current_vocabulary, looked)))

    moments = _recorded(seen_changes) + _recorded(seen_attempts)
    return _Run(
        observations=tuple(observations),
        findings=tuple(findings),
        canonical_entries=seen_changes,
        activity_entries=seen_attempts,
        processed_through=max(moments) if moments else until,
    )


# --- Rediscovering what memory says now -----------------------------------------------


def _identity(definition: dict) -> str:
    return str(definition["type_key"])


async def _rediscover_vocabulary(client: Client) -> tuple[dict[str, Any], int]:
    """Rebuild the complete current vocabulary from discovery alone.

    A definition delta replaces the whole vocabulary, so a proposal has to be built from
    everything currently active rather than from the part the analysis happened to look
    at. Summary then inspection is the only way an agent has to obtain that, and it is
    the reason both reads carry the revision they were evaluated at.
    """
    summary = await _call(client, "rtg_definition_summary")
    assert summary["status"] == "accepted", summary["findings"]
    keys = [entry["type_key"] for entry in summary["anchor_types"]]

    detail = await _call(client, "rtg_definition_inspect", {"request": {"anchor_type_keys": keys}})
    assert detail["status"] == "accepted", detail["findings"]
    assert detail["evaluated_revision"] == summary["evaluated_revision"], (
        "the definitions moved between the two reads"
    )

    anchor_types: dict[str, dict] = {}
    associated_data_types: dict[str, dict] = {}
    link_types: dict[str, dict] = {}
    relationship_constraints: list[dict] = []
    for neighborhood in detail["anchor_details"]:
        anchor_types.setdefault(_identity(neighborhood["anchor_type"]), neighborhood["anchor_type"])
        for each in neighborhood["associated_data_types"]:
            associated_data_types.setdefault(_identity(each), each)
        for each in neighborhood["link_types"]:
            link_types.setdefault(_identity(each), each)
        for each in neighborhood["relationship_constraints"]:
            if each not in relationship_constraints:
                relationship_constraints.append(each)

    return (
        {
            "anchor_types": list(anchor_types.values()),
            "associated_data_types": list(associated_data_types.values()),
            "link_types": list(link_types.values()),
            "relationship_constraints": relationship_constraints,
        },
        summary["evaluated_revision"],
    )


def _without_anchor_type(vocabulary: dict[str, Any], type_key: str) -> dict[str, Any]:
    return {
        **vocabulary,
        "anchor_types": [
            each for each in vocabulary["anchor_types"] if each["type_key"] != type_key
        ],
    }


def _anchor_type_keys(payload: dict) -> set[str]:
    return {entry["type_key"] for entry in payload["anchor_types"]}


# --- Bounded intervals of both ledgers ------------------------------------------------


@pytest.mark.anyio
async def test_a_run_reads_explicit_bounded_intervals_of_both_ledgers(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes an analysis that needs an unbounded or open-ended read of either ledger.

    Both ledgers answer the interval the run named, every record they return falls
    inside it, and the run's own later observations fall outside it — so the bound is
    something Vellis honors rather than something the caller has to trust itself about.
    """
    until = now()

    async with agent:
        run = await _analysis(agent, until=until)
        afterwards = await _call(agent, "rtg_history", _interval("activity", maximum_records=200))

    assert run.canonical_entries and run.activity_entries
    assert all(moment <= until for moment in _recorded(run.canonical_entries))
    assert all(moment <= until for moment in _recorded(run.activity_entries))
    # Every read of a ledger or of the graph carried its own maximum; the only reads that
    # carried none are discovery, which takes none.
    assert all(
        observation.bound is not None and observation.bound > 0
        for observation in run.observations
        if observation.tool in {"rtg_history", "rtg_query"}
    )
    assert {observation.tool for observation in run.observations if observation.bound is None} == {
        "rtg_definition_summary"
    }
    assert {observation.tool for observation in run.observations} <= set(TOOL_NAMES)

    # The run's own reads are recorded after the bound it named, and it did not see them.
    assert len(afterwards["activity_entries"]) == len(run.activity_entries) + len(run.observations)
    assert memory.current_state().revision == 3


@pytest.mark.anyio
async def test_an_interval_holding_more_than_the_run_asked_for_is_refused_whole(
    agent: Client,
) -> None:
    """Excludes a truncated interval reaching an analysis as a complete one.

    A run that quietly received the first few records of a longer interval would report
    findings that look complete and are not, and would move its continuation point past
    records it never read.
    """
    until = now()

    async with agent:
        whole = await _call(
            agent, "rtg_history", _interval("activity", maximum_records=50, until=until)
        )
        truncated = await _call(
            agent, "rtg_history", _interval("activity", maximum_records=2, until=until)
        )

    assert whole["status"] == "accepted"
    assert len(whole["activity_entries"]) == 3
    assert truncated["status"] == "rejected"
    assert truncated["activity_entries"] == []
    assert truncated["evaluated_revision"] is None


@pytest.mark.anyio
async def test_a_bounded_finding_query_refuses_rather_than_reporting_half_the_cleanup(
    agent: Client,
) -> None:
    """Excludes a cleanup list that is shorter than the problem it describes."""
    async with agent:
        complete = await _call(agent, "rtg_query", _stale_reviews(maximum_rows=20))
        clipped = await _call(agent, "rtg_query", _stale_reviews(maximum_rows=1))

    assert complete["status"] == "accepted"
    assert _stale_pairs(complete) == {("p-orbit", "d-orbit"), ("p-beacon", "d-beacon")}
    assert clipped["status"] == "rejected"
    assert clipped["rows"] == []


# --- Continuing where the last run stopped --------------------------------------------


@pytest.mark.anyio
async def test_a_later_run_continues_from_where_the_last_one_stopped(agent: Client) -> None:
    """Excludes a scheduled analysis that has to reread all history to stay current.

    The two intervals partition the ledger exactly: no record is analyzed twice and none
    is skipped. The second run then shows what continuation buys it — a read of all
    history under the bound the second interval needed is refused, so the incremental
    interval is not a convenience over a full read, it is what makes the run answerable
    at all.
    """
    first_until = now()

    async with agent:
        first = await _analysis(agent, until=first_until)

        # Ordinary use continues between the two runs.
        added = await _call(
            agent,
            "rtg_change",
            {
                "change": {
                    "anchor_upserts": [
                        {"uuid": "a-2", "type_key": "person", "display_name": "Grace"}
                    ]
                }
            },
        )
        assert added["status"] == "accepted"
        second_until = now()

        second = await _analysis(
            agent, since=first.processed_through + timedelta(microseconds=1), until=second_until
        )

        everything = await _call(
            agent, "rtg_history", _interval("activity", maximum_records=200, until=second_until)
        )
        every_change = await _call(
            agent, "rtg_history", _interval("canonical", maximum_records=200, until=second_until)
        )
        as_one_read = await _call(
            agent,
            "rtg_history",
            _interval("activity", maximum_records=len(second.activity_entries), until=second_until),
        )

    assert len(second.activity_entries) < len(everything["activity_entries"])
    assert _recorded(first.activity_entries) + _recorded(second.activity_entries) == _recorded(
        tuple(everything["activity_entries"])
    )
    assert _recorded(first.canonical_entries) + _recorded(second.canonical_entries) == _recorded(
        tuple(every_change["canonical_entries"])
    )

    # The second run saw the first run's own observations, exactly once each.
    assert len(second.activity_entries) >= len(first.observations)
    assert as_one_read["status"] == "rejected"


@pytest.mark.anyio
async def test_vellis_keeps_no_schedule_and_no_continuation_point(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a scheduler, a job registry, a worker, or a consumed interval.

    Two things together say scheduling stayed outside. Nothing happened that the run did
    not ask for: the ledger grew by exactly the calls it made. And the interval it read
    is not consumed — asked again it answers identically — so where to continue from is
    the agent's own state and nowhere in Vellis.
    """
    until = now()
    before = _everything(memory)

    async with agent:
        tools = [tool.name for tool in await agent.list_tools()]
        run = await _analysis(agent, until=until)
        again = await _call(
            agent, "rtg_history", _interval("canonical", maximum_records=50, until=until)
        )

    assert tuple(sorted(tools)) == tuple(sorted(TOOL_NAMES))
    after = _everything(memory)
    # One record per call the agent made, and nothing else: no background pass ran.
    assert len(after.activity) == len(before.activity) + len(run.observations) + 1
    assert again["canonical_entries"] == list(run.canonical_entries)
    assert _canonically_unchanged(before, after)


# --- What the run can explain ---------------------------------------------------------


@pytest.mark.anyio
async def test_every_finding_names_the_bounded_observations_it_came_from(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a finding a cold reader cannot trace back to what was actually read.

    Each citation has to be an observation this run made, through the selected surface,
    at a revision the ledger actually holds, and each finding has to rest on at least one
    read that named its own maximum. A finding citing a revision Vellis never evaluated
    would be unfalsifiable advice about the owner's own memory, and one resting only on
    unbounded reads would be a conclusion the owner cannot re-derive.
    """
    until = now()

    async with agent:
        run = await _analysis(agent, until=until)

    # The revisions the ledger itself reported, plus the one it is at now.
    committed = {entry["revision"] for entry in run.canonical_entries} | {
        memory.current_state().revision
    }
    assert run.findings
    for finding in run.findings:
        assert finding.drawn_from, finding
        assert any(observation.bound is not None for observation in finding.drawn_from), finding
        for observation in finding.drawn_from:
            assert observation in run.observations
            assert observation.tool in TOOL_NAMES
            assert observation.bound is None or observation.bound > 0
            assert observation.evaluated_revision in committed

    assert run.of_kind("staleData") == {"p-orbit/d-orbit", "p-beacon/d-beacon"}
    assert run.of_kind("unusedVocabulary") == {"fax"}
    assert run.of_kind("repeatedFailure") == {"graphChange on 1 anchors"}


@pytest.mark.anyio
async def test_unused_vocabulary_takes_a_discovery_and_a_query_together(agent: Client) -> None:
    """Excludes calling a type unused from either read alone.

    Discovery says the type is active; the bounded query says nothing is stored under
    it. Neither is the finding: an active type with instances is in use, and a type with
    no instances that discovery does not carry was never in the vocabulary at all.
    """
    async with agent:
        vocabulary = await _call(agent, "rtg_definition_summary")
        unused = await _call(agent, "rtg_query", _anchors_of_type("fax", maximum_rows=20))
        used = await _call(agent, "rtg_query", _anchors_of_type("person", maximum_rows=20))
        never = await _call(agent, "rtg_query", _anchors_of_type("meeting", maximum_rows=20))

    assert _anchor_type_keys(vocabulary) == {"person", "project", "fax"}
    assert unused["status"] == "accepted"
    assert unused["rows"] == []
    assert used["status"] == "accepted"
    assert used["rows"] != []
    assert never["status"] == "rejected"


@pytest.mark.anyio
async def test_repeated_failures_are_readable_without_having_changed_anything(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a failed attempt that either vanishes or leaves a mark on memory."""
    async with agent:
        attempts = await _call(agent, "rtg_history", _interval("activity", maximum_records=50))
        changes = await _call(agent, "rtg_history", _interval("canonical", maximum_records=50))

    refusals = [
        entry for entry in attempts["activity_entries"] if entry["outcome_category"] == "rejected"
    ]
    assert len(refusals) == 3
    assert {(entry["capability"], entry["semantic_scope"]) for entry in refusals} == {
        ("graphChange", "1 anchors")
    }
    # Three refusals, and the canonical ledger holds only the four records of real work.
    assert [entry["revision"] for entry in changes["canonical_entries"]] == [0, 1, 2, 3]
    assert memory.current_state().revision == 3


# --- Rediscovering before proposing ---------------------------------------------------


@pytest.mark.anyio
async def test_a_delta_is_built_from_rediscovered_current_definitions(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a proposal that silently retires vocabulary added after the analysis ran.

    The run observed the vocabulary at its own evaluated revision. The owner then added
    a type. Because a delta replaces the whole vocabulary, the set the run observed —
    minus the unused type it wanted to retire — would have deleted the owner's new type
    along with it. Rediscovering first is what makes the proposal say what the agent
    meant.
    """
    until = now()

    async with agent:
        run = await _analysis(agent, until=until)
        observed = _anchor_type_keys(
            await _call(
                agent,
                "rtg_definition_summary",
                {"historical_selection": {"revision": run.canonical_entries[-1]["revision"]}},
            )
        )

    # The owner does their own vocabulary work between the analysis and the proposal.
    assert stage_complete_fixture(
        memory,
        GraphDefinitionSet(
            anchor_types=(
                *_starting_vocabulary().anchor_types,
                AnchorTypeDefinition(type_key="venue", description="Somewhere things happen."),
            ),
            associated_data_types=_starting_vocabulary().associated_data_types,
            link_types=_starting_vocabulary().link_types,
        ),
        provenance=OWNER,
    ).accepted
    assert activate_clean_delta(memory, provenance=OWNER).accepted

    async with agent:
        rediscovered, revision = await _rediscover_vocabulary(agent)
        staged = await _call(
            agent,
            "rtg_set_definition_delta",
            {"request": {"proposed_definitions": _without_anchor_type(rediscovered, "fax")}},
        )
        activated = await _call(agent, "rtg_activate_definition_delta")
        settled = await _call(agent, "rtg_definition_summary")
        kept = await _call(
            agent, "rtg_definition_inspect", {"request": {"anchor_type_keys": ["project"]}}
        )

    # The counterexample: acting on the observed set would have taken "venue" with it.
    assert run.of_kind("unusedVocabulary") == {"fax"}
    assert "venue" not in observed - {"fax"}

    assert revision > run.canonical_entries[-1]["revision"]
    assert staged["status"] == "accepted"
    assert staged["assessment"]["conforms"] is True
    assert activated["status"] == "accepted"
    assert _anchor_type_keys(settled) == {"person", "project", "venue"}

    # The retirement took one anchor type and nothing else: the families the proposal was
    # rebuilt from, rather than named, are all still here.
    neighborhood = kept["anchor_details"][0]
    assert [each["type_key"] for each in neighborhood["associated_data_types"]] == ["review"]
    assert [each["type_key"] for each in neighborhood["link_types"]] == ["worksOn"]
    assert neighborhood["associated_data_types"][0]["property_constraints"][0] == {
        "property_name": "reviewedYear",
        "required": True,
        "json_kind": "numberValue",
        "description": "The year this project was last looked at.",
        "value_shape": None,
        "value_range": {"lower_bound": 2000, "upper_bound": 2100, "permitted_values": []},
        "pattern": None,
    }


@pytest.mark.anyio
async def test_a_cleanup_change_is_rechecked_against_current_state_before_it_is_proposed(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a cleanup that acts on what the analysis saw rather than on what is true.

    The run found two stale reviews. The owner refreshed one of them before the proposal
    was prepared. A change built from the run's own observation would have deleted the
    owner's fresh work; the recheck finds only the review that is still stale. The
    vocabulary is rediscovered in the same breath, because the concepts a change is
    written in can have been retired since the run read them.
    """
    until = now()

    async with agent:
        run = await _analysis(agent, until=until)

    assert run.of_kind("staleData") == {"p-orbit/d-orbit", "p-beacon/d-beacon"}

    # The owner gets to one of them first.
    assert memory.apply_graph_change(
        GraphChange(associated_data_upserts=(_review("d-beacon", "p-beacon", 2026),)),
        provenance=OWNER,
    ).accepted

    async with agent:
        vocabulary = await _call(agent, "rtg_definition_summary")
        grounding = await _call(
            agent, "rtg_definition_inspect", {"request": {"anchor_type_keys": ["project"]}}
        )
        rechecked = await _call(agent, "rtg_query", _stale_reviews(maximum_rows=20))
        still_stale = sorted(review for _, review in _stale_pairs(rechecked))
        removed = await _call(
            agent, "rtg_change", {"change": {"associated_data_removals": still_stale}}
        )
        settled = await _call(agent, "rtg_query", _stale_reviews(maximum_rows=20))

    # Rediscovered at the state the change was written against, not at the run's.
    assert vocabulary["evaluated_revision"] > run.canonical_entries[-1]["revision"]
    assert grounding["evaluated_revision"] == vocabulary["evaluated_revision"]
    assert "project" in _anchor_type_keys(vocabulary)
    assert "review" in {
        each["type_key"] for each in grounding["anchor_details"][0]["associated_data_types"]
    }
    assert rechecked["evaluated_revision"] == vocabulary["evaluated_revision"]

    assert still_stale == ["d-orbit"]
    assert removed["status"] == "accepted"
    assert settled["rows"] == []

    graph = memory.current_state().graph
    assert graph.associated_data_object("d-orbit") is None
    refreshed = graph.associated_data_object("d-beacon")
    assert refreshed is not None
    assert refreshed.properties["reviewedYear"] == normalize(2026)
    assert graph.associated_data_object("d-kite") is not None


# --- Approval ------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_declined_proposal_leaves_memory_as_though_it_were_never_asked(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes an analysis that can reach canonical memory without the owner.

    Declining is not something Vellis is told; a declined proposal is one that never
    becomes a call. So the evidence is that a complete analysis — the same one that
    produces the findings a cleanup would come from — is incapable of changing anything
    on its own.
    """
    until = now()
    before = _everything(memory)

    async with agent:
        run = await _analysis(agent, until=until)

    after = _everything(memory)
    assert run.findings
    assert _canonically_unchanged(before, after)
    assert len(after.activity) == len(before.activity) + len(run.observations)


@pytest.mark.anyio
async def test_an_approved_cleanup_reaches_memory_as_one_ordinary_change(
    agent: Client, memory: RTGSystem
) -> None:
    """Excludes a cleanup that arrives as anything other than the owner's own change.

    Approved, the proposal is one graph change at one new revision, and what it cleaned
    up is still in the history that recorded it — improvement moves memory forward, it
    does not rewrite where memory has been.
    """
    until = now()

    async with agent:
        run = await _analysis(agent, until=until)
        approved = await _call(
            agent, "rtg_change", {"change": {"associated_data_removals": ["d-orbit"]}}
        )
        remaining = await _call(agent, "rtg_query", _stale_reviews(maximum_rows=20))
        as_it_was = await _call(
            agent,
            "rtg_query",
            _stale_reviews(maximum_rows=20, revision=run.canonical_entries[-1]["revision"]),
        )

    assert "p-orbit/d-orbit" in run.of_kind("staleData")
    assert approved["status"] == "accepted"
    assert approved["resulting_revision"] == 4
    assert _stale_pairs(remaining) == {("p-beacon", "d-beacon")}
    # The state the finding was drawn from still says what it said.
    assert _stale_pairs(as_it_was) == {("p-orbit", "d-orbit"), ("p-beacon", "d-beacon")}
