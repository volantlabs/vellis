from __future__ import annotations

import os
from pathlib import Path

from tools import model_layout, sync_agent_skills, validate_skills


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


def test_all_source_skills_have_valid_metadata() -> None:
    skill_root = model_layout.ROOT / ".agents" / "skills"
    skill_dirs = {path.name: path for path in skill_root.iterdir() if path.is_dir()}

    assert skill_dirs
    errors = [
        error for path in skill_dirs.values() for error in validate_skills.validate_skill(path)
    ]
    assert errors == []


def test_implementation_skill_routing_distinguishes_slice_from_evolution() -> None:
    skill_root = model_layout.ROOT / ".agents" / "skills"
    executor = (skill_root / "sysml-implementation" / "SKILL.md").read_text(encoding="utf-8")
    evolution = (skill_root / "sysml-evolution" / "SKILL.md").read_text(encoding="utf-8")

    assert "one bounded semantic slice" in executor.split("---", 2)[1]
    assert "already implemented" in evolution.split("---", 2)[1]

def test_portable_core_validation_is_axis_selected() -> None:
    guidance = (model_layout.ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Wording, links, or metadata" in guidance
    assert "A rule an agent must follow" in guidance
    assert "A record contract" in guidance
    assert "A routing boundary" in guidance
    assert "A claim about SysML or KerML meaning" in guidance


def test_new_portable_skills_do_not_embed_project_bindings() -> None:
    skill_root = model_layout.ROOT / ".agents" / "skills"
    forbidden = (
        "Vellis",
        "RTG",
        "FastMCP",
        "MCP",
        "Python",
        "Git",
        "just ",
        ".data/",
        "model/",
    )

    for skill_name in ("sysml-implementation-planning", "sysml-implementation-campaign"):
        files = [
            path
            for path in (skill_root / skill_name).rglob("*")
            if path.is_file() and path.suffix in {".md", ".yaml", ".json"}
        ]
        content = "\n".join(path.read_text(encoding="utf-8") for path in files)
        assert not any(term in content for term in forbidden)


def test_managed_skill_exposure_matches_source_inventory() -> None:
    skill_root = model_layout.ROOT / ".agents" / "skills"
    source_skills = {path.name for path in skill_root.iterdir() if path.is_dir()}
    claude_root = model_layout.ROOT / ".claude" / "skills"
    links = {path.name: path for path in claude_root.iterdir()}

    assert set(links) == source_skills
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


def test_skill_validator_accepts_extensible_layout_metadata_and_policy(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(
        skill_dir,
        "# Sample\n\n[Guide](references/index.md)\n\n"
        "TODO is legitimate discussion text.\n" + "Detailed instruction.\n" * 501,
    )
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        skill_file.read_text(encoding="utf-8").replace(
            "description: Use this sample skill when validating repository skill guardrails.\n",
            "description: A focused repository validator.\ncompatibility: local\n",
        ),
        encoding="utf-8",
    )
    nested = skill_dir / "references" / "nested"
    nested.mkdir(parents=True)
    (skill_dir / "references" / "index.md").write_text("[Deep](nested/deep.md)\n", encoding="utf-8")
    (nested / "deep.md").write_text("Complete guidance.\n", encoding="utf-8")
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "assets").mkdir()
    (skill_dir / "assets" / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
    (skill_dir / "agents" / "openai.yaml").write_text(
        "interface:\n"
        '  display_name: "Sample Skill"\n'
        '  short_description: "Validate"\n'
        '  default_prompt: "Use $sample-skill to validate this sample."\n'
        '  icon_small: "../assets/icon.svg"\n'
        "dependencies:\n"
        "  tools: []\n"
        "policy:\n"
        "  allow_implicit_invocation: false\n"
        "  future_policy: preserved\n",
        encoding="utf-8",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert errors == []


def test_skill_validator_rejects_missing_or_escaping_local_links(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(
        skill_dir, "# Sample\n\n[Missing](references/missing.md)\n[Escape](../outside.md)\n"
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("missing linked file" in error for error in errors)
    assert any("local link escapes" in error for error in errors)


def test_skill_validator_requires_core_ui_metadata(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(skill_dir)
    metadata = skill_dir / "agents" / "openai.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            '  short_description: "Validate repository skill metadata"\n', ""
        ),
        encoding="utf-8",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("missing interface keys" in error for error in errors)


def test_skill_validator_rejects_non_boolean_invocation_policy(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(skill_dir)
    metadata = skill_dir / "agents" / "openai.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "allow_implicit_invocation: true", "allow_implicit_invocation: []"
        ),
        encoding="utf-8",
    )

    errors = validate_skills.validate_skill(skill_dir)

    assert any("must be Boolean when present" in error for error in errors)


def test_skill_validator_reports_malformed_yaml(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    _write_valid_skill(skill_dir)
    (skill_dir / "agents" / "openai.yaml").write_text("interface: [\n", encoding="utf-8")

    errors = validate_skills.validate_skill(skill_dir)

    assert any("invalid YAML metadata" in error for error in errors)

    (skill_dir / "SKILL.md").write_text("---\nname: [\n---\n", encoding="utf-8")
    errors = validate_skills.validate_skill(skill_dir)
    assert any("invalid YAML frontmatter" in error for error in errors)
