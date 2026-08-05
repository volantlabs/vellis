from __future__ import annotations

import re
import subprocess

from tools import model_layout

ROOT = model_layout.ROOT


def _just_recipes() -> set[str]:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    return {
        match.group(1)
        for line in justfile.splitlines()
        if not line.startswith("set ")
        and (match := re.match(r"^([a-z][a-z0-9-]*)(?: [^:]*)?:", line))
    }


def test_obsolete_v1_namespaces_are_absent() -> None:
    for relative in (
        "vellis_next",
        "model/foundation",
        "model/bibliotek",
    ):
        assert not (ROOT / relative).exists(), relative

    model_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "model").glob("*.sysml"))
    )
    for obsolete_name in ("Bibliotek", "SoftwareComponentModeling"):
        assert obsolete_name not in model_text


def test_required_model_first_commands_remain_available() -> None:
    required = {
        "check",
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

    assert required <= _just_recipes()


def test_reference_finder_quotes_untrusted_questions() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-reference-find", "$(printf unsafe)"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "'$(printf unsafe)'" in result.stdout + result.stderr


def test_public_guidance_does_not_restore_v1_workflows() -> None:
    documents = [
        *ROOT.glob("*.md"),
        ROOT / "model" / "README.md",
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".github").rglob("*.md"),
        *(ROOT / ".agents" / "skills").rglob("*.md"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in documents)

    for obsolete_reference in (
        "components/rtg",
        "model/bibliotek",
        "SoftwareComponentModeling",
    ):
        assert obsolete_reference not in text


def test_ci_runs_locked_setup_before_full_check() -> None:
    workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")

    assert "uv sync --locked" in workflow
    assert workflow.index("run: just model-setup") < workflow.index("run: just check")


def test_selected_mcp_contract_is_not_advertised_as_a_runtime() -> None:
    realization = (ROOT / "docs" / "mcp-realization.md").read_text(encoding="utf-8").casefold()
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8").casefold()
    recipes = _just_recipes()

    assert "non-normative" in realization
    assert "fastmcp" in realization
    assert "text and structured content" in realization
    assert "advisory annotations" in realization
    assert "cannot change authorization" in realization
    assert "fastmcp" not in project
    assert not ({"run", "serve", "mcp", "mcp-run", "mcp-serve"} & recipes)
    assert not any((ROOT / root).exists() for root in ("apps", "components", "vellis"))
