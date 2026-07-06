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


def test_documentation_sync_guidance_covers_public_affordance_examples() -> None:
    text = Path(".agents/skills/documentation-sync/SKILL.md").read_text(encoding="utf-8")

    for term in (
        "public affordance names",
        "eval prompts",
        "examples",
        "reference-app docs",
    ):
        assert term in text
