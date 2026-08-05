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


def _write_valid_skill(skill_dir: Path, body: str = "# Sample\n\nUseful instructions.\n") -> None:
    (skill_dir / "agents").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_dir.name}\n"
        "description: Use this sample skill when validating repository skill guardrails.\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    (skill_dir / "agents" / "openai.yaml").write_text(
        "interface:\n"
        '  display_name: "Sample Skill"\n'
        '  short_description: "Validate repository skill metadata"\n'
        f'  default_prompt: "Use ${skill_dir.name} to validate this sample."\n'
        "policy:\n"
        "  allow_implicit_invocation: true\n",
        encoding="utf-8",
    )


def test_exact_skill_inventory_and_metadata() -> None:
    """The four complementary skills are an intentional repository contract."""
    skill_root = model_layout.ROOT / ".agents" / "skills"
    skill_dirs = {path.name: path for path in skill_root.iterdir() if path.is_dir()}

    assert set(skill_dirs) == EXPECTED_SKILLS
    errors = [
        error for path in skill_dirs.values() for error in validate_skills.validate_skill(path)
    ]
    assert errors == []


def test_exact_managed_skill_exposure() -> None:
    """Managed exposure mirrors the intentional four-skill inventory exactly."""
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


def test_sync_replaces_only_a_stale_managed_target(tmp_path: Path, monkeypatch: object) -> None:
    source_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    current = source_root / "current"
    current.mkdir(parents=True)
    claude_root.mkdir(parents=True)
    exposed = claude_root / "current"
    exposed.symlink_to(source_root / "obsolete", target_is_directory=True)
    monkeypatch.setattr(sync_agent_skills, "SOURCE_ROOT", source_root)  # type: ignore[attr-defined]
    monkeypatch.setattr(sync_agent_skills, "CLAUDE_ROOT", claude_root)  # type: ignore[attr-defined]

    errors = sync_agent_skills.sync_agent_skills()

    assert errors == []
    assert exposed.resolve() == current.resolve()


def test_sync_refuses_to_replace_a_real_skill_exposure(tmp_path: Path, monkeypatch: object) -> None:
    source_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    (source_root / "current").mkdir(parents=True)
    real_exposure = claude_root / "current"
    real_exposure.mkdir(parents=True)
    monkeypatch.setattr(sync_agent_skills, "SOURCE_ROOT", source_root)  # type: ignore[attr-defined]
    monkeypatch.setattr(sync_agent_skills, "CLAUDE_ROOT", claude_root)  # type: ignore[attr-defined]

    errors = sync_agent_skills.sync_agent_skills()

    assert real_exposure.is_dir() and not real_exposure.is_symlink()
    assert any("refusing to replace real file or directory" in error for error in errors)


def test_skill_validator_rejects_unbounded_or_extended_metadata(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    (skill_dir / "agents").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: sample-skill\n"
        "description: Use this sample skill when validating skill guardrails.\n"
        "---\n"
        "# Sample\n" + "instruction\n" * 500,
        encoding="utf-8",
    )
    (skill_dir / "agents" / "openai.yaml").write_text(
        "interface:\n"
        '  display_name: "Sample Skill"\n'
        '  short_description: "Validate sample skill metadata"\n'
        '  default_prompt: "Use $sample-skill to validate this sample."\n'
        '  icon_small: "./icon.svg"\n'
        "dependencies: {}\n"
        "policy:\n"
        "  allow_implicit_invocation: true\n",
        encoding="utf-8",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("must not exceed 500 lines" in error for error in errors)
    assert any("prohibited metadata keys" in error for error in errors)
    assert any("prohibited interface keys" in error for error in errors)


def test_skill_validator_rejects_unsafe_or_unlinked_references_and_placeholders(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "sample-skill"
    references = skill_dir / "references"
    (references / "nested").mkdir(parents=True)
    (references / "linked.md").write_text("Linked.\n", encoding="utf-8")
    (references / "orphan.md").write_text("Orphan.\n", encoding="utf-8")
    (references / "nested" / "deep.md").write_text("Deep.\n", encoding="utf-8")
    _write_valid_skill(
        skill_dir,
        "# Sample\n\n"
        "[Linked](references/linked.md)\n"
        "[Missing](references/missing.md)\n"
        "[Escape](../outside.md)\n"
        "TODO\n",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("missing linked file" in error for error in errors)
    assert any("local link escapes" in error for error in errors)
    assert any("nested reference directory" in error for error in errors)
    assert any("reference is not linked directly" in error for error in errors)
    assert any("placeholder content is prohibited" in error for error in errors)


def test_skill_validator_requires_implicit_invocation_policy(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(skill_dir)
    metadata = skill_dir / "agents" / "openai.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "allow_implicit_invocation: true", "allow_implicit_invocation: false"
        ),
        encoding="utf-8",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("policy.allow_implicit_invocation must be true" in error for error in errors)


def test_skill_validator_requires_a_trigger_word_not_a_substring(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(skill_dir)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        skill_file.read_text(encoding="utf-8").replace(
            "Use this sample skill when validating repository skill guardrails.",
            "Because this sample skill validates repository guardrails effectively.",
        ),
        encoding="utf-8",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("description must state when to use the skill" in error for error in errors)


def test_skill_validator_reports_malformed_yaml(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(skill_dir)
    (skill_dir / "agents" / "openai.yaml").write_text("interface: [\n", encoding="utf-8")

    errors = validate_skills.validate_skill(skill_dir)

    assert any("invalid YAML metadata" in error for error in errors)

    (skill_dir / "SKILL.md").write_text("---\nname: [\n---\n", encoding="utf-8")
    errors = validate_skills.validate_skill(skill_dir)
    assert any("invalid YAML frontmatter" in error for error in errors)
