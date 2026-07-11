from __future__ import annotations

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


def test_component_authoring_distinguishes_library_application_and_distribution() -> None:
    text = Path(
        ".agents/skills/component-authoring/references/model-organization.md"
    ).read_text(encoding="utf-8")

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
