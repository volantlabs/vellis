from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

JsonObject = dict[str, Any]

EXPECTED_TOOLS = {
    "rtg_get_system_state",
    "rtg_get_usage_guide",
    "rtg_stage_schema_migration",
    "rtg_validate_live_anchor_records",
    "rtg_apply_live_anchor_records",
    "rtg_validate_live_graph_changes",
    "rtg_apply_live_graph_changes",
    "rtg_stage_knowledge_changes",
    "rtg_apply_migration_cutover",
    "rtg_abandon_migration",
    "rtg_execute_query",
    "rtg_resolve_anchor_by_fact",
    "rtg_get_object",
    "rtg_list_migrations",
    "rtg_get_migration",
    "rtg_validate_graph",
    "rtg_discover_anchor_types",
    "rtg_get_schema_pack",
    "rtg_export_system_snapshot",
    "rtg_persist_system_snapshot",
    "rtg_list_persisted_snapshots",
    "rtg_load_persisted_snapshot",
    "rtg_replay_ledger",
    "rtg_verify_replay_from_ledger",
    "rtg_list_migration_history",
    "rtg_flush_ledger_failures",
    "rtg_restore_from_snapshot",
}

SCHEMA_IDS = {
    name: f"10000000-0000-0000-0000-{index:012d}"
    for index, name in enumerate(
        (
            "Person",
            "PersonFacts",
            "Area",
            "AreaFacts",
            "Project",
            "ProjectFacts",
            "Task",
            "TaskFacts",
            "Event",
            "EventFacts",
            "Note",
            "NoteFacts",
            "Resource",
            "ResourceFacts",
            "belongs_to",
            "supports",
            "owns",
            "mentions",
            "depends_on",
        ),
        start=1,
    )
}

PROJECT_TITLES_BY_REF = {
    "project-vellis-beta": "Vellis beta and open source launch",
    "project-career-map": "Career map refresh",
    "project-home-systems": "Home systems cleanup",
    "project-health-routine": "Health routine reset",
    "project-tax-planning": "2026 tax planning",
}


def test_individual_rtg_mcp_suite_manages_multi_domain_life_graph(tmp_path: Path) -> None:
    async def run_flow(session: ClientSession, storage_root: Path) -> None:
        assert EXPECTED_TOOLS <= await _tool_names(session)

        await _bootstrap_individual_schema(session)
        await _ingest_individual_graph(session)

        discovery = await _call_tool(session, "rtg_discover_anchor_types", {})
        assert _anchor_type_keys(discovery) == {
            "Area",
            "Event",
            "Note",
            "Person",
            "Project",
            "Resource",
            "Task",
        }

        schema_pack = await _call_tool(
            session,
            "rtg_get_schema_pack",
            {
                "anchor_type_keys": ["Project"],
                "schema_pack_options": {"include_live_counts": True},
            },
        )
        assert schema_pack["ok"] is True
        assert schema_pack["result"]["live_counts"]["Project"] == 5
        assert _associated_schema_types(schema_pack) == {"ProjectFacts"}

        professional_next = await _query_tasks(
            session,
            domain="professional",
            status="next",
        )
        assert _returned_property_values(professional_next, "task_facts", "title") == {
            "Invite first beta testers",
            "Draft the Vellis public roadmap",
            "Prepare mentor agenda",
        }

        personal_next = await _query_tasks(
            session,
            domain="personal",
            status="next",
        )
        assert _returned_property_values(personal_next, "task_facts", "title") == {
            "Renew home insurance",
            "Schedule annual physical",
            "Review monthly budget",
        }

        vellis_project_support = await _call_tool(
            session,
            "rtg_execute_query",
            {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "task", "anchor_type_keys": ["Task"]},
                        {"name": "project", "anchor_type_keys": ["Project"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "task_supports_project",
                            "source_bucket": "task",
                            "target_bucket": "project",
                            "link_type_keys": ["supports"],
                        }
                    ],
                    "data_requirements": [
                        {
                            "name": "project_facts",
                            "anchor_bucket": "project",
                            "data_type_key": "ProjectFacts",
                            "predicates": [
                                {
                                    "path": ["title"],
                                    "operator": "equals",
                                    "value": "Vellis beta and open source launch",
                                }
                            ],
                        },
                        {
                            "name": "task_facts",
                            "anchor_bucket": "task",
                            "data_type_key": "TaskFacts",
                            "predicates": [
                                {
                                    "path": ["status"],
                                    "operator": "in",
                                    "values": ["next", "waiting"],
                                }
                            ],
                        },
                    ],
                    "return_spec": {
                        "anchor_buckets": ["task", "project"],
                        "link_requirements": ["task_supports_project"],
                        "properties": [["task_facts", ["title"]], ["task_facts", ["status"]]],
                    },
                },
                "query_options": {"live_filter": "live"},
            },
        )
        assert _returned_property_values(vellis_project_support, "task_facts", "title") == {
            "Invite first beta testers",
            "Draft the Vellis public roadmap",
            "Collect eval feedback",
        }

        cross_domain_summary = await _call_tool(
            session,
            "rtg_execute_query",
            {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "project", "anchor_type_keys": ["Project"]},
                        {"name": "area", "anchor_type_keys": ["Area"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "project_area",
                            "source_bucket": "project",
                            "target_bucket": "area",
                            "link_type_keys": ["belongs_to"],
                        }
                    ],
                    "data_requirements": [
                        {
                            "name": "area_facts",
                            "anchor_bucket": "area",
                            "data_type_key": "AreaFacts",
                            "predicates": [
                                {"path": ["active"], "operator": "equals", "value": True}
                            ],
                        },
                        {
                            "name": "project_facts",
                            "anchor_bucket": "project",
                            "data_type_key": "ProjectFacts",
                            "predicates": [
                                {"path": ["status"], "operator": "equals", "value": "active"}
                            ],
                        },
                    ],
                    "return_spec": {
                        "anchor_buckets": ["project", "area"],
                        "properties": [
                            ["project_facts", ["title"]],
                            ["area_facts", ["domain"]],
                        ],
                    },
                },
                "query_options": {"live_filter": "live"},
            },
        )
        assert len(cross_domain_summary["result"]["bindings"]) == 4
        assert _returned_property_values(cross_domain_summary, "area_facts", "domain") == {
            "personal",
            "professional",
        }

        validation = await _call_tool(session, "rtg_validate_graph", {})
        assert validation["ok"] is True
        assert validation["result"]["accepted"] is True

        snapshot = await _call_tool(session, "rtg_export_system_snapshot", {})
        assert snapshot["ok"] is True
        assert len(snapshot["result"]["graph"]["anchors"]) == 29

        persisted = await _call_tool(
            session,
            "rtg_persist_system_snapshot",
            {"relative_path": "snapshots/individual-rtg-open-source.json"},
        )
        assert persisted["ok"] is True
        assert persisted["result"]["status"] == "snapshot_persisted"
        assert (storage_root / "snapshots" / "individual-rtg-open-source.json").is_file()

        await _add_valid_task(
            session,
            task_ref="task-sudden-purchase",
            fact_ref="task-sudden-purchase-facts",
            title="Buy extra monitor",
            domain="professional",
            status="next",
            priority="low",
            due="2026-07-24",
            context="desk",
            project_ref="project-vellis-beta",
        )
        assert await _task_count(session) == 9

        restored = await _call_tool(
            session,
            "rtg_restore_from_snapshot",
            {"snapshot": snapshot["result"]},
        )
        assert restored["ok"] is True
        assert restored["result"]["status"] == "restore_applied"
        assert await _task_count(session) == 8

        replay = await _call_tool(session, "rtg_replay_ledger", {})
        assert replay["ok"] is False
        assert replay["error"]["type"] == "RtgControllerReplayFailed"

        flush = await _call_tool(session, "rtg_flush_ledger_failures", {})
        assert flush["ok"] is True
        assert flush["result"]["status"] == "ledger_failures_flushed"

    asyncio.run(_run_with_mcp_server(tmp_path, run_flow))


def test_individual_rtg_mcp_suite_recovers_from_realistic_agent_mistakes(
    tmp_path: Path,
) -> None:
    async def run_flow(session: ClientSession, _storage_root: Path) -> None:
        await _bootstrap_individual_schema(session)
        await _ingest_individual_graph(session)
        baseline_task_count = await _task_count(session)
        state_before_dry_run = await _call_tool(session, "rtg_get_system_state", {})

        dry_run_missing_facts = await _call_tool(
            session,
            "rtg_validate_live_graph_changes",
            {
                "graph_changes": {
                    "anchor_writes": [
                        {
                            "ref": {"local_ref": "dry-run-task-without-facts"},
                            "type": "Task",
                            "display_name": "Dry-run unstructured task",
                        }
                    ]
                }
            },
        )
        state_after_dry_run = await _call_tool(session, "rtg_get_system_state", {})

        assert dry_run_missing_facts["ok"] is True
        assert dry_run_missing_facts["result"]["accepted"] is False
        assert _finding_codes(dry_run_missing_facts["result"]) >= {
            "schema_object.missing_required_associated_data"
        }
        assert await _task_count(session) == baseline_task_count
        assert (
            state_after_dry_run["result"]["ledger_record_count"]
            == state_before_dry_run["result"]["ledger_record_count"]
        )

        missing_facts = await _call_tool(
            session,
            "rtg_apply_live_graph_changes",
            {
                "graph_changes": {
                    "anchor_writes": [
                        {
                            "ref": {"local_ref": "task-without-facts"},
                            "type": "Task",
                            "display_name": "Unstructured task",
                        }
                    ]
                }
            },
        )
        assert missing_facts["ok"] is False
        assert _finding_codes(missing_facts) >= {"schema_object.missing_required_associated_data"}
        assert await _task_count(session) == baseline_task_count

        wrong_property_kind = await _call_tool(
            session,
            "rtg_apply_live_graph_changes",
            {
                "graph_changes": {
                    "anchor_writes": [
                        {
                            "ref": {"local_ref": "task-kind-error"},
                            "type": "Task",
                            "display_name": "Task with bad due date",
                        }
                    ],
                    "data_object_writes": [
                        {
                            "ref": {"local_ref": "task-kind-error-facts"},
                            "type": "TaskFacts",
                            "properties": {
                                "title": "Task with bad due date",
                                "domain": "professional",
                                "status": "next",
                                "priority": "medium",
                                "due": 20260731,
                                "context": "laptop",
                            },
                            "anchor_refs": [{"local_ref": "task-kind-error"}],
                        }
                    ],
                }
            },
        )
        assert wrong_property_kind["ok"] is False
        assert _finding_codes(wrong_property_kind) >= {"schema_object.property_kind_mismatch"}
        assert await _task_count(session) == baseline_task_count

        project_uuid = await _anchor_uuid_by_fact(
            session,
            "Project",
            "ProjectFacts",
            "title",
            "Vellis beta and open source launch",
        )
        self_uuid = await _anchor_uuid_by_fact(session, "Person", "PersonFacts", "name", "Self")
        bad_link = await _call_tool(
            session,
            "rtg_apply_live_graph_changes",
            {
                "graph_changes": {
                    "link_writes": [
                        {
                            "ref": {"local_ref": "person-invalid-supports-project"},
                            "type": "supports",
                            "source_ref": {"resource_id": self_uuid},
                            "target_ref": {"resource_id": project_uuid},
                        }
                    ]
                }
            },
        )
        assert bad_link["ok"] is False
        assert _finding_codes(bad_link) >= {"schema_object.link_endpoint_type_invalid"}

        repaired = await _add_valid_task(
            session,
            task_ref="task-repaired-beta-note",
            fact_ref="task-repaired-beta-note-facts",
            title="Summarize beta invite audience",
            domain="professional",
            status="next",
            priority="medium",
            due="2026-07-21",
            context="laptop",
            project_ref="project-vellis-beta",
        )
        assert repaired["ok"] is True
        assert await _task_count(session) == baseline_task_count + 1

        old_project_facts_uuid = await _schema_uuid_for_data_type(
            session,
            anchor_type="Project",
            data_type="ProjectFacts",
        )
        stricter_project_facts_uuid = "10000000-0000-0000-0000-000000000099"
        migration_uuid = "10000000-0000-0000-0000-000000000100"
        staged = await _call_tool(
            session,
            "rtg_stage_knowledge_changes",
            {
                "knowledge_changes": {
                    "schema_changes": {
                        "definition_writes": [
                            {
                                "ref": {"resource_id": stricter_project_facts_uuid},
                                "definition": _data_schema(
                                    stricter_project_facts_uuid,
                                    "ProjectFacts",
                                    "Project facts with an explicit sponsor.",
                                    {
                                        "title": _field("string"),
                                        "domain": _field("string"),
                                        "status": _field("string"),
                                        "priority": _field("string"),
                                        "desired_outcome": _field("string"),
                                        "next_review": _field("string"),
                                        "sponsor": _field("string"),
                                    },
                                ),
                            }
                        ]
                    },
                    "migration_changes": {
                        "migration_writes": [
                            {
                                "ref": {"resource_id": migration_uuid},
                                "migration": {
                                    "migration_id": migration_uuid,
                                    "description": "Require project sponsor data.",
                                    "status": "ready",
                                    "schema_make_live": [stricter_project_facts_uuid],
                                    "schema_make_non_live": [old_project_facts_uuid],
                                },
                            }
                        ]
                    },
                },
                "validation_mode": "skip",
            },
        )
        assert staged["ok"] is True

        failed_cutover = await _call_tool(
            session,
            "rtg_apply_migration_cutover",
            {"migration_id": migration_uuid},
        )
        assert failed_cutover["ok"] is False
        assert failed_cutover["error"]["type"] == "RtgControllerValidationFailed"
        assert _finding_codes(failed_cutover) >= {"schema_object.missing_required_property"}

        current_project_facts_uuid = await _schema_uuid_for_data_type(
            session,
            anchor_type="Project",
            data_type="ProjectFacts",
        )
        assert current_project_facts_uuid == old_project_facts_uuid

        validation = await _call_tool(session, "rtg_validate_graph", {})
        assert validation["ok"] is True
        assert validation["result"]["accepted"] is True

    asyncio.run(_run_with_mcp_server(tmp_path, run_flow))


def test_individual_rtg_mcp_suite_replays_ledger_after_server_restart(
    tmp_path: Path,
) -> None:
    async def run_flow() -> None:
        storage_root = tmp_path / "restart-storage"
        sql_database_path = tmp_path / "restart-controller.sqlite"
        params = _server_params(tmp_path, storage_root, sql_database_path)

        async with _mcp_session(params) as first_session:
            await _bootstrap_individual_schema(first_session)
            await _ingest_individual_graph(first_session)
            assert await _task_count(first_session) == 8

        async with _mcp_session(params) as restarted_session:
            empty_discovery = await _call_tool(
                restarted_session,
                "rtg_discover_anchor_types",
                {},
            )
            assert empty_discovery["ok"] is True
            assert empty_discovery["result"]["anchor_types"] == []

            replay = await _call_tool(restarted_session, "rtg_replay_ledger", {})
            assert replay["ok"] is True
            assert replay["result"]["status"] == "replay_applied"
            assert replay["result"]["details"]["mutating_requests_replayed"] >= 3

            assert await _task_count(restarted_session) == 8
            validation = await _call_tool(restarted_session, "rtg_validate_graph", {})
            assert validation["result"]["accepted"] is True

    asyncio.run(run_flow())


async def _run_with_mcp_server(
    tmp_path: Path,
    flow: Callable[[ClientSession, Path], Awaitable[None]],
) -> None:
    storage_root = tmp_path / "mcp-storage"
    sql_database_path = tmp_path / "controller.sqlite"
    async with _mcp_session(_server_params(tmp_path, storage_root, sql_database_path)) as session:
        await flow(session, storage_root)


def _server_params(
    cwd: Path,
    storage_root: Path,
    sql_database_path: Path,
) -> StdioServerParameters:
    repo_root = Path(__file__).resolve().parents[3]
    return StdioServerParameters(
        command="uv",
        args=[
            "--directory",
            str(repo_root),
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--transport",
            "stdio",
            "--storage-root",
            str(storage_root),
            "--sql-database-path",
            str(sql_database_path),
            "--empty",
            "--manual-recovery",
        ],
        cwd=cwd,
    )


@asynccontextmanager
async def _mcp_session(params: StdioServerParameters):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _tool_names(session: ClientSession) -> set[str]:
    result = await session.list_tools()
    return {tool.name for tool in result.tools}


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: JsonObject,
) -> JsonObject:
    result = await session.call_tool(name, arguments)
    assert result.isError is False
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return cast(JsonObject, structured)
    text = cast(Any, result).content[0].text
    return cast(JsonObject, json.loads(text))


async def _bootstrap_individual_schema(session: ClientSession) -> None:
    definitions = [
        _anchor_schema(SCHEMA_IDS["Person"], "Person", "A person.", "PersonFacts"),
        _data_schema(
            SCHEMA_IDS["PersonFacts"],
            "PersonFacts",
            "Personal relationship and contact context.",
            {
                "name": _field("string"),
                "relationship": _field("string"),
                "domain": _field("string"),
                "preferred_contact": _field("string"),
            },
        ),
        _anchor_schema(SCHEMA_IDS["Area"], "Area", "A life or work area.", "AreaFacts"),
        _data_schema(
            SCHEMA_IDS["AreaFacts"],
            "AreaFacts",
            "Area classification facts.",
            {
                "title": _field("string"),
                "domain": _field("string"),
                "focus": _field("string"),
                "active": _field("boolean"),
            },
        ),
        _anchor_schema(SCHEMA_IDS["Project"], "Project", "A project or outcome.", "ProjectFacts"),
        _data_schema(
            SCHEMA_IDS["ProjectFacts"],
            "ProjectFacts",
            "Project planning facts.",
            {
                "title": _field("string"),
                "domain": _field("string"),
                "status": _field("string"),
                "priority": _field("string"),
                "desired_outcome": _field("string"),
                "next_review": _field("string"),
            },
        ),
        _anchor_schema(SCHEMA_IDS["Task"], "Task", "An actionable task.", "TaskFacts"),
        _data_schema(
            SCHEMA_IDS["TaskFacts"],
            "TaskFacts",
            "Task planning facts.",
            {
                "title": _field("string"),
                "domain": _field("string"),
                "status": _field("string"),
                "priority": _field("string"),
                "due": _field("string"),
                "context": _field("string"),
            },
        ),
        _anchor_schema(SCHEMA_IDS["Event"], "Event", "A calendar or planning event.", "EventFacts"),
        _data_schema(
            SCHEMA_IDS["EventFacts"],
            "EventFacts",
            "Event scheduling facts.",
            {
                "title": _field("string"),
                "domain": _field("string"),
                "status": _field("string"),
                "start": _field("string"),
                "summary": _field("string"),
            },
        ),
        _anchor_schema(SCHEMA_IDS["Note"], "Note", "A note or observation.", "NoteFacts"),
        _data_schema(
            SCHEMA_IDS["NoteFacts"],
            "NoteFacts",
            "Note classification facts.",
            {
                "title": _field("string"),
                "domain": _field("string"),
                "topic": _field("string"),
                "summary": _field("string"),
            },
        ),
        _anchor_schema(
            SCHEMA_IDS["Resource"],
            "Resource",
            "A document, URL, or external artifact.",
            "ResourceFacts",
        ),
        _data_schema(
            SCHEMA_IDS["ResourceFacts"],
            "ResourceFacts",
            "Resource locator facts.",
            {
                "title": _field("string"),
                "domain": _field("string"),
                "kind": _field("string"),
                "locator": _field("string"),
            },
        ),
        _link_schema(
            SCHEMA_IDS["belongs_to"],
            "belongs_to",
            "A work item or artifact belongs to an area.",
            ["Project", "Task", "Event", "Note", "Resource"],
            ["Area"],
        ),
        _link_schema(
            SCHEMA_IDS["supports"],
            "supports",
            "A task, event, note, or resource supports a project.",
            ["Task", "Event", "Note", "Resource"],
            ["Project"],
        ),
        _link_schema(
            SCHEMA_IDS["owns"],
            "owns",
            "A person owns or is responsible for an area, project, task, or event.",
            ["Person"],
            ["Area", "Project", "Task", "Event"],
        ),
        _link_schema(
            SCHEMA_IDS["mentions"],
            "mentions",
            "A note mentions a person.",
            ["Note"],
            ["Person"],
        ),
        _link_schema(
            SCHEMA_IDS["depends_on"],
            "depends_on",
            "A task depends on another task.",
            ["Task"],
            ["Task"],
        ),
    ]
    staged = await _call_tool(
        session,
        "rtg_stage_knowledge_changes",
        {
            "knowledge_changes": {
                "schema_changes": {
                    "definition_writes": [
                        {"ref": {"resource_id": item["uuid"]}, "definition": item}
                        for item in definitions
                    ]
                },
                "migration_changes": {
                    "migration_writes": [
                        {
                            "ref": {"resource_id": "10000000-0000-0000-0000-000000000020"},
                            "migration": {
                                "migration_id": "10000000-0000-0000-0000-000000000020",
                                "description": (
                                    "Make the initial individual life-management schema live."
                                ),
                                "status": "ready",
                                "schema_make_live": list(SCHEMA_IDS.values()),
                            },
                        }
                    ]
                },
            }
        },
    )
    assert staged["ok"] is True

    migration = await _call_tool(
        session,
        "rtg_get_migration",
        {"migration_id": "10000000-0000-0000-0000-000000000020"},
    )
    assert migration["ok"] is True
    assert migration["result"]["status"] == "ready"

    cutover = await _call_tool(
        session,
        "rtg_apply_migration_cutover",
        {"migration_id": "10000000-0000-0000-0000-000000000020"},
    )
    assert cutover["ok"] is True
    assert cutover["result"]["status"] == "cutover_applied"


async def _ingest_individual_graph(session: ClientSession) -> None:
    anchors = [
        _anchor("person-self", "Person", "Self"),
        _anchor("person-mentor", "Person", "Morgan - mentor"),
        _anchor("person-partner", "Person", "Jordan - partner"),
        _anchor("area-open-source", "Area", "Open source product work"),
        _anchor("area-career", "Area", "Career development"),
        _anchor("area-home", "Area", "Home and household"),
        _anchor("area-health", "Area", "Health"),
        _anchor("area-finance", "Area", "Personal finance"),
        _anchor("project-vellis-beta", "Project", "Vellis beta and open source launch"),
        _anchor("project-career-map", "Project", "Career map refresh"),
        _anchor("project-home-systems", "Project", "Home systems cleanup"),
        _anchor("project-health-routine", "Project", "Health routine reset"),
        _anchor("project-tax-planning", "Project", "2026 tax planning"),
        _anchor("task-beta-invites", "Task", "Invite first beta testers"),
        _anchor("task-eval-feedback", "Task", "Collect eval feedback"),
        _anchor("task-roadmap", "Task", "Draft the Vellis public roadmap"),
        _anchor("task-mentor-agenda", "Task", "Prepare mentor agenda"),
        _anchor("task-home-insurance", "Task", "Renew home insurance"),
        _anchor("task-physical", "Task", "Schedule annual physical"),
        _anchor("task-tax-docs", "Task", "Gather tax documents"),
        _anchor("task-budget-review", "Task", "Review monthly budget"),
        _anchor("event-beta-review", "Event", "Vellis beta review"),
        _anchor("event-doctor", "Event", "Annual physical"),
        _anchor("event-family-planning", "Event", "Household planning"),
        _anchor("note-beta-feedback", "Note", "Beta feedback themes"),
        _anchor("note-vellis-positioning", "Note", "Open source positioning"),
        _anchor("note-home-routines", "Note", "Household routine preferences"),
        _anchor("note-health-baseline", "Note", "Health baseline notes"),
        _anchor("resource-vellis-repo", "Resource", "Vellis GitHub repository"),
    ]
    data_objects = [
        _data(
            "person-self-facts",
            "PersonFacts",
            {
                "name": "Self",
                "relationship": "self",
                "domain": "personal",
                "preferred_contact": "n/a",
            },
            "person-self",
        ),
        _data(
            "person-mentor-facts",
            "PersonFacts",
            {
                "name": "Morgan",
                "relationship": "mentor",
                "domain": "professional",
                "preferred_contact": "email",
            },
            "person-mentor",
        ),
        _data(
            "person-partner-facts",
            "PersonFacts",
            {
                "name": "Jordan",
                "relationship": "partner",
                "domain": "personal",
                "preferred_contact": "text",
            },
            "person-partner",
        ),
        _data(
            "area-open-source-facts",
            "AreaFacts",
            {
                "title": "Open source product work",
                "domain": "professional",
                "focus": "Ship useful AI-native components.",
                "active": True,
            },
            "area-open-source",
        ),
        _data(
            "area-career-facts",
            "AreaFacts",
            {
                "title": "Career development",
                "domain": "professional",
                "focus": "Choose high-leverage work and relationships.",
                "active": True,
            },
            "area-career",
        ),
        _data(
            "area-home-facts",
            "AreaFacts",
            {
                "title": "Home and household",
                "domain": "personal",
                "focus": "Keep household systems calm and current.",
                "active": True,
            },
            "area-home",
        ),
        _data(
            "area-health-facts",
            "AreaFacts",
            {
                "title": "Health",
                "domain": "personal",
                "focus": "Preserve energy and baseline care.",
                "active": True,
            },
            "area-health",
        ),
        _data(
            "area-finance-facts",
            "AreaFacts",
            {
                "title": "Personal finance",
                "domain": "personal",
                "focus": "Track commitments, taxes, and spending.",
                "active": True,
            },
            "area-finance",
        ),
        _project_facts(
            "project-vellis-beta-facts",
            "Vellis beta and open source launch",
            "professional",
            "active",
            "high",
            "A public beta that agents can use through RTG MCP.",
            "2026-07-09",
            "project-vellis-beta",
        ),
        _project_facts(
            "project-career-map-facts",
            "Career map refresh",
            "professional",
            "active",
            "medium",
            "Clarify next durable professional bets.",
            "2026-07-16",
            "project-career-map",
        ),
        _project_facts(
            "project-home-systems-facts",
            "Home systems cleanup",
            "personal",
            "active",
            "medium",
            "Reduce household admin drift.",
            "2026-07-20",
            "project-home-systems",
        ),
        _project_facts(
            "project-health-routine-facts",
            "Health routine reset",
            "personal",
            "active",
            "high",
            "Restore a reliable baseline care loop.",
            "2026-07-22",
            "project-health-routine",
        ),
        _project_facts(
            "project-tax-planning-facts",
            "2026 tax planning",
            "personal",
            "waiting",
            "medium",
            "Prepare documents before advisor review.",
            "2026-08-01",
            "project-tax-planning",
        ),
        _task_facts(
            "task-beta-invites-facts",
            "Invite first beta testers",
            "professional",
            "next",
            "high",
            "2026-07-08",
            "email",
            "task-beta-invites",
        ),
        _task_facts(
            "task-eval-feedback-facts",
            "Collect eval feedback",
            "professional",
            "waiting",
            "high",
            "2026-07-15",
            "mcp-client",
            "task-eval-feedback",
        ),
        _task_facts(
            "task-roadmap-facts",
            "Draft the Vellis public roadmap",
            "professional",
            "next",
            "high",
            "2026-07-10",
            "writing",
            "task-roadmap",
        ),
        _task_facts(
            "task-mentor-agenda-facts",
            "Prepare mentor agenda",
            "professional",
            "next",
            "medium",
            "2026-07-12",
            "notes",
            "task-mentor-agenda",
        ),
        _task_facts(
            "task-home-insurance-facts",
            "Renew home insurance",
            "personal",
            "next",
            "medium",
            "2026-07-18",
            "phone",
            "task-home-insurance",
        ),
        _task_facts(
            "task-physical-facts",
            "Schedule annual physical",
            "personal",
            "next",
            "high",
            "2026-07-11",
            "phone",
            "task-physical",
        ),
        _task_facts(
            "task-tax-docs-facts",
            "Gather tax documents",
            "personal",
            "waiting",
            "medium",
            "2026-07-25",
            "files",
            "task-tax-docs",
        ),
        _task_facts(
            "task-budget-review-facts",
            "Review monthly budget",
            "personal",
            "next",
            "medium",
            "2026-07-07",
            "spreadsheet",
            "task-budget-review",
        ),
        _data(
            "event-beta-review-facts",
            "EventFacts",
            {
                "title": "Vellis beta review",
                "domain": "professional",
                "status": "scheduled",
                "start": "2026-07-14T10:00:00-07:00",
                "summary": "Review first beta session outcomes.",
            },
            "event-beta-review",
        ),
        _data(
            "event-doctor-facts",
            "EventFacts",
            {
                "title": "Annual physical",
                "domain": "personal",
                "status": "tentative",
                "start": "2026-07-21T09:00:00-07:00",
                "summary": "Confirm appointment once scheduling call is complete.",
            },
            "event-doctor",
        ),
        _data(
            "event-family-planning-facts",
            "EventFacts",
            {
                "title": "Household planning",
                "domain": "personal",
                "status": "scheduled",
                "start": "2026-07-06T18:00:00-07:00",
                "summary": "Review insurance, budget, and home routines.",
            },
            "event-family-planning",
        ),
        _note_facts(
            "note-beta-feedback-facts",
            "Beta feedback themes",
            "professional",
            "feedback",
            "Early testers need clearer schema examples.",
            "note-beta-feedback",
        ),
        _note_facts(
            "note-vellis-positioning-facts",
            "Open source positioning",
            "professional",
            "strategy",
            "Emphasize local-first RTG and inspectable component contracts.",
            "note-vellis-positioning",
        ),
        _note_facts(
            "note-home-routines-facts",
            "Household routine preferences",
            "personal",
            "home",
            "Prefer fewer recurring chores with explicit owners.",
            "note-home-routines",
        ),
        _note_facts(
            "note-health-baseline-facts",
            "Health baseline notes",
            "personal",
            "health",
            "Capture labs, sleep, training, and annual care actions.",
            "note-health-baseline",
        ),
        _data(
            "resource-vellis-repo-facts",
            "ResourceFacts",
            {
                "title": "Vellis GitHub repository",
                "domain": "professional",
                "kind": "repository",
                "locator": "https://github.com/volantlabs/vellis",
            },
            "resource-vellis-repo",
        ),
    ]
    links = [
        _link("project-vellis-area", "belongs_to", "project-vellis-beta", "area-open-source"),
        _link("project-career-area", "belongs_to", "project-career-map", "area-career"),
        _link("project-home-area", "belongs_to", "project-home-systems", "area-home"),
        _link("project-health-area", "belongs_to", "project-health-routine", "area-health"),
        _link("project-tax-area", "belongs_to", "project-tax-planning", "area-finance"),
        _link("task-beta-project", "supports", "task-beta-invites", "project-vellis-beta"),
        _link("task-feedback-project", "supports", "task-eval-feedback", "project-vellis-beta"),
        _link("task-roadmap-project", "supports", "task-roadmap", "project-vellis-beta"),
        _link("task-mentor-project", "supports", "task-mentor-agenda", "project-career-map"),
        _link("task-home-project", "supports", "task-home-insurance", "project-home-systems"),
        _link("task-physical-project", "supports", "task-physical", "project-health-routine"),
        _link("task-tax-project", "supports", "task-tax-docs", "project-tax-planning"),
        _link("task-budget-project", "supports", "task-budget-review", "project-tax-planning"),
        _link("event-beta-project", "supports", "event-beta-review", "project-vellis-beta"),
        _link("event-doctor-project", "supports", "event-doctor", "project-health-routine"),
        _link("event-family-project", "supports", "event-family-planning", "project-home-systems"),
        _link("note-feedback-project", "supports", "note-beta-feedback", "project-vellis-beta"),
        _link(
            "note-positioning-project", "supports", "note-vellis-positioning", "project-vellis-beta"
        ),
        _link("note-home-project", "supports", "note-home-routines", "project-home-systems"),
        _link("note-health-project", "supports", "note-health-baseline", "project-health-routine"),
        _link("resource-repo-project", "supports", "resource-vellis-repo", "project-vellis-beta"),
        _link("self-owns-vellis", "owns", "person-self", "project-vellis-beta"),
        _link("self-owns-health", "owns", "person-self", "project-health-routine"),
        _link("partner-owns-home", "owns", "person-partner", "project-home-systems"),
        _link("mentor-owns-career-event", "owns", "person-mentor", "event-beta-review"),
        _link(
            "note-positioning-mentions-mentor",
            "mentions",
            "note-vellis-positioning",
            "person-mentor",
        ),
        _link(
            "task-feedback-depends-beta", "depends_on", "task-eval-feedback", "task-beta-invites"
        ),
    ]
    result = await _call_tool(
        session,
        "rtg_apply_live_graph_changes",
        {
            "graph_changes": {
                "anchor_writes": anchors,
                "data_object_writes": data_objects,
                "link_writes": links,
            }
        },
    )
    assert result["ok"] is True
    assert result["result"]["status"] == "applied"


async def _add_valid_task(
    session: ClientSession,
    *,
    task_ref: str,
    fact_ref: str,
    title: str,
    domain: str,
    status: str,
    priority: str,
    due: str,
    context: str,
    project_ref: str,
) -> JsonObject:
    project_uuid = await _anchor_uuid_by_fact(
        session,
        "Project",
        "ProjectFacts",
        "title",
        PROJECT_TITLES_BY_REF[project_ref],
    )
    return await _call_tool(
        session,
        "rtg_apply_live_anchor_records",
        {
            "anchor_records": [
                {
                    "ref": {"local_ref": task_ref},
                    "type": "Task",
                    "display_name": title,
                    "facts": [
                        {
                            "ref": {"local_ref": fact_ref},
                            "type": "TaskFacts",
                            "properties": {
                                "title": title,
                                "domain": domain,
                                "status": status,
                                "priority": priority,
                                "due": due,
                                "context": context,
                            },
                        }
                    ],
                }
            ],
            "link_writes": [
                {
                    "ref": {"local_ref": f"{task_ref}-supports-project"},
                    "type": "supports",
                    "source_ref": {"local_ref": task_ref},
                    "target_ref": {"resource_id": project_uuid},
                }
            ],
        },
    )


async def _query_tasks(session: ClientSession, *, domain: str, status: str) -> JsonObject:
    return await _call_tool(
        session,
        "rtg_execute_query",
        {
            "query_spec": {
                "anchor_buckets": [{"name": "task", "anchor_type_keys": ["Task"]}],
                "data_requirements": [
                    {
                        "name": "task_facts",
                        "anchor_bucket": "task",
                        "data_type_key": "TaskFacts",
                        "predicates": [
                            {"path": ["domain"], "operator": "equals", "value": domain},
                            {"path": ["status"], "operator": "equals", "value": status},
                        ],
                    }
                ],
                "return_spec": {
                    "anchor_buckets": ["task"],
                    "data_requirements": ["task_facts"],
                    "properties": [
                        ["task_facts", ["title"]],
                        ["task_facts", ["priority"]],
                        ["task_facts", ["due"]],
                    ],
                },
            },
            "query_options": {"live_filter": "live"},
        },
    )


async def _task_count(session: ClientSession) -> int:
    result = await _call_tool(
        session,
        "rtg_execute_query",
        {
            "query_spec": {
                "anchor_buckets": [{"name": "task", "anchor_type_keys": ["Task"]}],
            },
            "query_options": {"live_filter": "live"},
        },
    )
    return len(result["result"]["bindings"])


async def _anchor_uuid_by_fact(
    session: ClientSession,
    anchor_type: str,
    data_type: str,
    property_name: str,
    value: str,
) -> str:
    result = await _call_tool(
        session,
        "rtg_execute_query",
        {
            "query_spec": {
                "anchor_buckets": [{"name": "anchor", "anchor_type_keys": [anchor_type]}],
                "data_requirements": [
                    {
                        "name": "facts",
                        "anchor_bucket": "anchor",
                        "data_type_key": data_type,
                        "predicates": [
                            {"path": [property_name], "operator": "equals", "value": value}
                        ],
                    }
                ],
            },
            "query_options": {"live_filter": "live"},
        },
    )
    assert len(result["result"]["bindings"]) == 1
    return cast(str, result["result"]["bindings"][0]["anchors"]["anchor"])


async def _schema_uuid_for_data_type(
    session: ClientSession,
    *,
    anchor_type: str,
    data_type: str,
) -> str:
    result = await _call_tool(
        session,
        "rtg_get_schema_pack",
        {"anchor_type_keys": [anchor_type]},
    )
    for schema in result["result"]["schema_pack"]["associated_data_object_schemas"]:
        if schema["type_key"] == data_type:
            return cast(str, schema["uuid"])
    raise AssertionError(f"schema not found: {data_type}")


def _anchor_type_keys(discovery: JsonObject) -> set[str]:
    return {item["type_key"] for item in discovery["result"]["anchor_types"]}


def _associated_schema_types(schema_pack: JsonObject) -> set[str]:
    return {
        item["type_key"]
        for item in schema_pack["result"]["schema_pack"]["associated_data_object_schemas"]
    }


def _returned_property_values(result: JsonObject, data_name: str, property_name: str) -> set[str]:
    return {row["properties"][data_name][property_name] for row in result["result"]["returns"]}


def _finding_codes(result: JsonObject) -> set[str]:
    return {item["code"] for item in result["validation_report"]["findings"]}


def _anchor(ref: str, type_key: str, display_name: str) -> JsonObject:
    return {"ref": {"local_ref": ref}, "type": type_key, "display_name": display_name}


def _data(ref: str, type_key: str, properties: JsonObject, anchor_ref: str) -> JsonObject:
    return {
        "ref": {"local_ref": ref},
        "type": type_key,
        "properties": properties,
        "anchor_refs": [{"local_ref": anchor_ref}],
    }


def _link(ref: str, type_key: str, source_ref: str, target_ref: str) -> JsonObject:
    return {
        "ref": {"local_ref": ref},
        "type": type_key,
        "source_ref": {"local_ref": source_ref},
        "target_ref": {"local_ref": target_ref},
    }


def _field(kind: str) -> JsonObject:
    return {"required": True, "value_kinds": [kind]}


def _anchor_schema(
    uuid: str,
    type_key: str,
    description: str,
    required_data_type: str,
) -> JsonObject:
    return {
        "uuid": uuid,
        "kind": "anchor",
        "type_key": type_key,
        "description": description,
        "payload": {"required_data_types": [required_data_type]},
        "system": {"live": False},
    }


def _data_schema(
    uuid: str,
    type_key: str,
    description: str,
    properties: dict[str, JsonObject],
) -> JsonObject:
    return {
        "uuid": uuid,
        "kind": "data_object",
        "type_key": type_key,
        "description": description,
        "payload": {"properties": properties},
        "system": {"live": False},
    }


def _link_schema(
    uuid: str,
    type_key: str,
    description: str,
    allowed_source_types: list[str],
    allowed_target_types: list[str],
) -> JsonObject:
    return {
        "uuid": uuid,
        "kind": "link",
        "type_key": type_key,
        "description": description,
        "payload": {
            "allowed_source_types": allowed_source_types,
            "allowed_target_types": allowed_target_types,
        },
        "system": {"live": False},
    }


def _project_facts(
    ref: str,
    title: str,
    domain: str,
    status: str,
    priority: str,
    desired_outcome: str,
    next_review: str,
    anchor_ref: str,
) -> JsonObject:
    return _data(
        ref,
        "ProjectFacts",
        {
            "title": title,
            "domain": domain,
            "status": status,
            "priority": priority,
            "desired_outcome": desired_outcome,
            "next_review": next_review,
        },
        anchor_ref,
    )


def _task_facts(
    ref: str,
    title: str,
    domain: str,
    status: str,
    priority: str,
    due: str,
    context: str,
    anchor_ref: str,
) -> JsonObject:
    return _data(
        ref,
        "TaskFacts",
        {
            "title": title,
            "domain": domain,
            "status": status,
            "priority": priority,
            "due": due,
            "context": context,
        },
        anchor_ref,
    )


def _note_facts(
    ref: str,
    title: str,
    domain: str,
    topic: str,
    summary: str,
    anchor_ref: str,
) -> JsonObject:
    return _data(
        ref,
        "NoteFacts",
        {
            "title": title,
            "domain": domain,
            "topic": topic,
            "summary": summary,
        },
        anchor_ref,
    )
