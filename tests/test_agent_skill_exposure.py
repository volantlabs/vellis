from __future__ import annotations

import json
import os
import re
from pathlib import Path


def test_repo_agent_skills_are_exposed_to_claude_code() -> None:
    source_root = Path(".agents/skills")
    claude_root = Path(".claude/skills")
    source_skills = sorted(path.name for path in source_root.iterdir() if path.is_dir())

    assert source_skills
    for skill_name in source_skills:
        target = claude_root / skill_name
        assert target.is_symlink()
        assert os.readlink(target) == f"../../.agents/skills/{skill_name}"
        assert (target / "SKILL.md").is_file()


def test_skills_check_validates_claude_code_skill_exposure() -> None:
    justfile = Path("justfile").read_text(encoding="utf-8")

    assert "skills-sync:" in justfile
    assert "tools/sync_agent_skills.py --check" in justfile


def test_rtg_mcp_skill_json_examples_are_parseable() -> None:
    text = Path(".agents/skills/rtg-knowledge-graph-mcp/SKILL.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)

    assert blocks
    for block in blocks:
        json.loads(block)
