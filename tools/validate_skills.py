from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOCAL_LINK = re.compile(r"\[[^]]*]\(([^)]+)\)")
REQUIRED_INTERFACE_KEYS = {"display_name", "short_description", "default_prompt"}


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _frontmatter(skill_file: Path, errors: list[str]) -> dict[str, object]:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"{skill_file}: missing YAML frontmatter")
        return {}
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        errors.append(f"{skill_file}: unterminated YAML frontmatter")
        return {}
    try:
        value = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as error:
        errors.append(f"{skill_file}: invalid YAML frontmatter: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{skill_file}: frontmatter must be a mapping")
        return {}
    return value


def _validate_local_links(skill_dir: Path, errors: list[str]) -> None:
    skill_root = skill_dir.resolve()
    markdown_files = [skill_dir / "SKILL.md", *sorted(skill_dir.rglob("*.md"))]
    for source in dict.fromkeys(markdown_files):
        text = source.read_text(encoding="utf-8")
        for target_text in LOCAL_LINK.findall(text):
            target_text = target_text.split("#", 1)[0].strip()
            if not target_text or "://" in target_text or target_text.startswith("#"):
                continue
            target = (source.parent / target_text).resolve()
            try:
                target.relative_to(skill_root)
            except ValueError:
                errors.append(f"{source}: local link escapes the skill: {target_text}")
                continue
            if not target.exists():
                errors.append(f"{source}: missing linked file {target_text}")


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    metadata_file = skill_dir / "agents" / "openai.yaml"

    if len(skill_dir.name) > 64 or not SKILL_NAME.fullmatch(skill_dir.name):
        errors.append(f"{skill_dir}: skill folder must be lowercase hyphenated and <=64 characters")
    if not skill_file.exists():
        return [*errors, f"{skill_dir}: missing SKILL.md"]

    frontmatter = _frontmatter(skill_file, errors)
    if frontmatter.get("name") != skill_dir.name:
        errors.append(f"{skill_file}: frontmatter name must be {skill_dir.name!r}")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{skill_file}: description must be non-empty")
    _validate_local_links(skill_dir, errors)

    if not metadata_file.exists():
        errors.append(f"{metadata_file}: missing skill UI metadata")
        return errors
    try:
        metadata = load_yaml(metadata_file)
    except yaml.YAMLError as error:
        errors.append(f"{metadata_file}: invalid YAML metadata: {error}")
        return errors
    if not isinstance(metadata, dict):
        errors.append(f"{metadata_file}: expected mapping")
        return errors
    interface = metadata.get("interface")
    if not isinstance(interface, dict):
        errors.append(f"{metadata_file}: missing interface mapping")
    else:
        missing = REQUIRED_INTERFACE_KEYS - set(interface)
        if missing:
            errors.append(f"{metadata_file}: missing interface keys: {sorted(missing)}")
        display_name = interface.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            errors.append(f"{metadata_file}: display_name must be non-empty")
        short = interface.get("short_description")
        if not isinstance(short, str) or not short.strip():
            errors.append(f"{metadata_file}: short_description must be non-empty")
        prompt = interface.get("default_prompt")
        if not isinstance(prompt, str) or f"${skill_dir.name}" not in prompt:
            errors.append(f"{metadata_file}: default_prompt must contain ${skill_dir.name}")
    policy = metadata.get("policy")
    if policy is not None and not isinstance(policy, dict):
        errors.append(f"{metadata_file}: policy must be a mapping when present")
    elif isinstance(policy, dict):
        implicit = policy.get("allow_implicit_invocation")
        if implicit is not None and not isinstance(implicit, bool):
            errors.append(
                f"{metadata_file}: policy.allow_implicit_invocation must be Boolean when present"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repo-local agent skills.")
    parser.add_argument("skills_root", nargs="?", default=".agents/skills")
    args = parser.parse_args()
    skills_root = Path(args.skills_root)
    if not skills_root.exists():
        raise SystemExit(f"skills root not found: {skills_root}")
    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    errors = [error for skill_dir in skill_dirs for error in validate_skill(skill_dir)]
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Validated {len(skill_dirs)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
