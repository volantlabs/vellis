from __future__ import annotations

import os
from pathlib import Path

from tools import model_layout, sync_agent_skills, validate_skills

EXPECTED_SKILLS = {
    "documentation-sync",
    "rtg-schema-design",
    "sysml-modeling",
    "sysml-reference",
}


def test_exact_skill_inventory_and_metadata() -> None:
    skill_root = model_layout.ROOT / ".agents" / "skills"
    skill_dirs = {path.name: path for path in skill_root.iterdir() if path.is_dir()}

    assert set(skill_dirs) == EXPECTED_SKILLS
    errors = [
        error
        for path in skill_dirs.values()
        for error in validate_skills.validate_skill(path)
    ]
    assert errors == []


def test_exact_managed_skill_exposure() -> None:
    claude_root = model_layout.ROOT / ".claude" / "skills"
    links = {path.name: path for path in claude_root.iterdir()}

    assert set(links) == EXPECTED_SKILLS
    assert all(path.is_symlink() for path in links.values())
    assert sync_agent_skills.sync_agent_skills(check=True) == []


def test_sync_removes_only_obsolete_managed_links(tmp_path: Path, monkeypatch: object) -> None:
    source_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    (source_root / "current").mkdir(parents=True)
    claude_root.mkdir(parents=True)
    obsolete = claude_root / "obsolete"
    obsolete.symlink_to(
        os.path.relpath(source_root / "obsolete", claude_root), target_is_directory=True
    )
    unrelated = claude_root / "personal"
    unrelated.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    monkeypatch.setattr(sync_agent_skills, "SOURCE_ROOT", source_root)  # type: ignore[attr-defined]
    monkeypatch.setattr(sync_agent_skills, "CLAUDE_ROOT", claude_root)  # type: ignore[attr-defined]

    errors = sync_agent_skills.sync_agent_skills()

    assert not obsolete.exists() and not obsolete.is_symlink()
    assert unrelated.is_symlink()
    assert any("refusing to remove unmanaged" in error for error in errors)
    assert (claude_root / "current").is_symlink()
