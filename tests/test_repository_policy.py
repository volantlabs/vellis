from __future__ import annotations

import re
import subprocess

import yaml

from tools import model_layout

ROOT = model_layout.ROOT


def _just_recipes() -> set[str]:
    result = subprocess.run(
        ["just", "--summary"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.split())


def test_documented_commands_exist() -> None:
    documents = [
        *ROOT.glob("*.md"),
        ROOT / "model" / "README.md",
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".github").rglob("*.md"),
        *(ROOT / ".agents" / "skills").rglob("*.md"),
    ]
    documented = {
        command
        for path in documents
        for command in re.findall(r"\bjust\s+([a-z][a-z0-9-]*)", path.read_text(encoding="utf-8"))
    }

    assert documented
    assert documented <= _just_recipes()


def test_reference_finder_quotes_untrusted_questions() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-reference-find", "$(printf unsafe)"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "'$(printf unsafe)'" in result.stdout + result.stderr


def test_reference_finder_routes_positional_specification_and_limit() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-reference-find", "part or item", "sysml-2.1", "5"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    command = result.stdout + result.stderr
    assert "specification='sysml-2.1'" in command
    assert '--specification "$specification"' in command
    assert "--limit '5'" in command


def test_snippet_probe_quotes_untrusted_source() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-probe", "$(printf unsafe)"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "'$(printf unsafe)'" in result.stdout + result.stderr


def test_ci_runs_locked_setup_before_full_check() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["check"]["steps"]
    commands = [" ".join(str(step["run"]).split()) for step in steps if "run" in step]
    checkout = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")
    )

    assert checkout["with"]["fetch-depth"] == 0
    assert "uv sync --locked" in commands
    assert commands.index("just model-setup") < commands.index("just check")
