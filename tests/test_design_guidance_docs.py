from __future__ import annotations

import re
from pathlib import Path


def test_boundary_quality_guidance_covers_controller_recovery_and_audit_heuristics() -> None:
    text = Path(".agents/skills/component-authoring/references/boundary-quality.md").read_text(
        encoding="utf-8"
    )

    for term in (
        "distinct public operations",
        "internal representation",
        "generic mutation backdoors",
        "compatibility shims",
        "empty state or from a supplied snapshot",
        "degraded",
        "audit persistence",
    ):
        assert term in text


def test_documentation_sync_guidance_uses_model_to_projection_direction() -> None:
    text = Path(".agents/skills/documentation-sync/SKILL.md").read_text(encoding="utf-8")

    for term in (
        "SysML",
        "generated",
        "projection",
        "second source of component truth",
        "Include untracked files",
        "local-link",
    ):
        assert term in text


def test_component_authoring_has_a_black_box_stop_rule() -> None:
    text = Path(".agents/skills/component-authoring/SKILL.md").read_text(encoding="utf-8")

    assert "Hard Stop Rule" in text
    assert "composition" in text
    assert "substitution" in text
    assert "private helpers" in text
    assert "Conformance Hierarchy" in text
    assert "different suitable language" in text
    assert "Before retiring a predecessor specification" in text


def test_documentation_retirement_preserves_non_contract_knowledge() -> None:
    text = Path(".agents/skills/documentation-sync/SKILL.md").read_text(encoding="utf-8")

    for term in (
        "contractual facts",
        "rationale",
        "unresolved questions",
        "realization drift",
    ):
        assert term in text


def test_rtg_guidance_covers_schema_refinements_and_grouped_cardinality() -> None:
    schema_text = Path(
        ".agents/skills/rtg-schema-design/references/schema-design.md"
    ).read_text(encoding="utf-8")
    operation_text = Path(".agents/skills/rtg-knowledge-graph-mcp/SKILL.md").read_text(
        encoding="utf-8"
    )

    for term in ("allowed_values", "date_time", "numeric bounds", "RE2"):
        assert term in schema_text
    for term in ("capabilities", "group_by_bindings", "unique tuple", "one global count"):
        assert term in operation_text


def test_component_authoring_distinguishes_library_application_and_distribution() -> None:
    text = Path(".agents/skills/component-authoring/references/model-organization.md").read_text(
        encoding="utf-8"
    )

    for term in (
        "library package",
        "ordinary `package`",
        "public import",
        "private import",
        "KPAR",
        "runtime",
    ):
        assert term in text


def test_reusable_modeling_skills_do_not_embed_repository_product_names() -> None:
    reusable_paths = (
        Path(".agents/skills/component-authoring"),
        Path(".agents/skills/python-component-implementation"),
        Path(".agents/skills/documentation-sync"),
    )
    forbidden = ("Bibliotek", "Vellis", "model/implementation-drift.yaml")

    for root in reusable_paths:
        for path in root.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for term in forbidden:
                    assert term not in text, f"{path} embeds repository-specific term {term!r}"


def test_repository_modeling_guide_explains_the_complete_post_cutover_loop() -> None:
    text = Path("docs/engineering/sysml-modeling.md").read_text(encoding="utf-8")

    for term in (
        "normative design",
        "Artifact authority and ownership",
        "generated/reference/",
        "generated/model/",
        "model_app_manifest.json",
        "just model-render",
        "just model-diff",
        "just model-check-formal",
        "just model-check",
        "just model-handoff TARGET=<stable-id>",
        "Author, review, and implementation workflows",
        "Troubleshooting",
        "Never hand-edit",
    ):
        assert term in text


def test_application_docs_defer_the_canonical_tool_inventory_to_the_model() -> None:
    text = Path("apps/rtg_knowledge_graph/README.md").read_text(encoding="utf-8")

    assert "Full exposed MCP tool list" not in text
    assert "generated/reference/vellis/index.md" in text
    assert "modeled Vellis façade" in text


def test_stdio_onboarding_distinguishes_client_launch_from_non_mcp_smoke_run() -> None:
    root_readme = Path("README.md").read_text(encoding="utf-8")
    app_readme = Path("apps/rtg_knowledge_graph/README.md").read_text(encoding="utf-8")

    assert "uv run vellis setup" in root_readme
    assert "no MCP JSON editing" in root_readme
    assert "registers the stdio MCP server user-wide" in app_readme


def test_beta_onboarding_is_cross_platform_and_prints_focused_config() -> None:
    root_readme = Path("README.md").read_text(encoding="utf-8")
    app_readme = Path("apps/rtg_knowledge_graph/README.md").read_text(encoding="utf-8")

    for term in (
        "winget install --id astral-sh.uv -e",
        "uv run vellis setup",
        "uv run vellis doctor",
        "do not need to install Python or",
    ):
        assert term in root_readme
    for term in (
        "native Windows",
        "without Bash or `just`",
        "%APPDATA%\\Claude\\claude_desktop_config.json",
        "--empty --manual-recovery",
        "Codex",
        "Claude Desktop",
    ):
        assert term in app_readme


def test_documented_just_commands_are_repository_recipes() -> None:
    justfile = Path("justfile").read_text(encoding="utf-8")
    recipes = set(re.findall(r"(?m)^([a-z][a-z0-9-]*)(?:\s+[^:]*)?:", justfile))
    documented: set[str] = set()
    for path in (
        Path("README.md"),
        Path("AGENTS.md"),
        Path("CONTRIBUTING.md"),
        Path("model/README.md"),
        Path("docs/README.md"),
        Path("docs/engineering/sysml-modeling.md"),
        Path("apps/rtg_knowledge_graph/README.md"),
    ):
        text = path.read_text(encoding="utf-8")
        documented.update(re.findall(r"`just\s+([a-z][a-z0-9-]*)", text))

    assert documented <= recipes
