from __future__ import annotations

from pathlib import Path


def test_rtg_agent_affordance_eval_prompt_exists_and_covers_affordances() -> None:
    prompt = Path("docs/evals/rtg-agent-affordance-eval-prompt.md")
    text = prompt.read_text(encoding="utf-8")

    for term in (
        "app starts empty",
        "schema",
        "constraints",
        "validation",
        "migration",
        "rtg_validate_live_graph_changes",
        "rtg_stage_knowledge_changes",
        "rtg_apply_migration_cutover",
        "ok: false",
        "query",
        "snapshot",
        "ledger",
        "human-facing brief",
    ):
        assert term in text


def test_rtg_agent_affordance_eval_runbook_covers_mcp_launch_and_sequence() -> None:
    runbook = Path("docs/evals/rtg-agent-affordance-eval-runbook.md")
    text = runbook.read_text(encoding="utf-8")

    for term in (
        "uv --directory",
        "just rtg-eval-info",
        "mcp.first_call",
        "fresh explicit storage root",
        "fresh_single_session",
        "not exposed as an MCP tool or resource",
        "Prompt 1: Bootstrap Model",
        "Prompt 2: Ingest And Query Live Graph",
        "Prompt 3: Evolve Evidence Model",
        "validation_report",
        "rtg_apply_live_graph_changes",
        "rtg_validate_live_graph_changes",
        "rtg_apply_live_anchor_records",
        "rtg_validate_live_anchor_records",
        "lookup_examples",
        "rtg_stage_knowledge_changes",
        "rtg_apply_migration_cutover",
        "rtg_resolve_anchor_by_fact",
        "replay_window",
        "rtg-individual-life-graph-beta-prompt.md",
    ):
        assert term in text


def test_individual_life_graph_beta_prompt_covers_initial_user_profile() -> None:
    prompt = Path("docs/evals/rtg-individual-life-graph-beta-prompt.md")
    text = prompt.read_text(encoding="utf-8")

    for term in (
        "personal and professional",
        "Start by inspecting the available RTG system state",
        "MCP-provided guidance",
        "Do not look for or use a prebuilt beta schema or seed payload",
        "Person",
        "Area",
        "Project",
        "Task",
        "Vellis beta and open source launch",
        "snake_case",
        "ISO-8601 placeholder strings",
        "Do not leave required",
        "date-like strings empty",
        "Preserve supplied domain, status, and priority facts",
        "Use useful links, not exhaustive links",
        "including all eight requested tasks",
        "well-formed but semantically invalid write attempts",
        "do not count a malformed tool",
        "without polluting",
        "durable planning graph",
        "schema evolution that should fail",
        "Persist a compact snapshot",
        "verify replay or",
        "replay-readiness",
        "reconciled counts",
        "concise final brief",
    ):
        assert term in text
    assert "life_graph_schema_v1" not in text
    assert "rtg_stage_schema_migration" not in text
    assert "tool_call_shapes" not in text
    assert "Expected default beta counts" not in text
