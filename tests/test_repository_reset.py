from __future__ import annotations

import re

from tools import model_layout

ROOT = model_layout.ROOT


def test_v1_roots_and_generated_products_are_absent() -> None:
    for relative in (
        "apps",
        "components",
        "vellis",
        "vellis_next",
        "model/foundation",
        "model/bibliotek",
        "model/vellis",
        "generated",
    ):
        assert not (ROOT / relative).exists(), relative


def test_model_does_not_reintroduce_v1_architecture() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "model").glob("*.sysml"))
    )

    assert "Bibliotek" not in text
    assert "library package" not in text
    assert "component." not in text
    assert "SoftwareComponentModeling" not in text


def test_supported_commands_are_exactly_the_reset_workflow() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    recipes = {
        match.group(1)
        for line in justfile.splitlines()
        if not line.startswith("set ")
        and (match := re.match(r"^([a-z][a-z0-9-]*)(?: [^:]*)?:", line))
    }

    assert recipes == {
        "check",
        "default",
        "format",
        "lint",
        "model-check",
        "model-reference-check",
        "model-reference-find",
        "model-reference-render",
        "model-setup",
        "setup",
        "skills-check",
        "skills-sync",
        "test",
        "typecheck",
    }


def test_public_docs_do_not_advertise_removed_software() -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        *sorted((ROOT / "docs").glob("*.md")),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in documents)

    for removed_claim in (
        "uv run vellis",
        "rtg-mcp",
        "serve-mcp",
        "model-render",
        "model-package",
        "model-handoff",
        "model-audit",
        "components/rtg",
        "model/bibliotek",
    ):
        assert removed_claim not in text


def test_ci_runs_locked_setup_before_full_check() -> None:
    workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")

    assert "uv sync --locked" in workflow
    assert workflow.index("run: just model-setup") < workflow.index("run: just check")
    assert "windows" not in workflow.casefold()
