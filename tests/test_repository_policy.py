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


def test_ci_runs_locked_setup_before_full_check() -> None:
    workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")

    assert "uv sync --locked" in workflow
    assert workflow.index("run: just model-setup") < workflow.index("run: just check")
