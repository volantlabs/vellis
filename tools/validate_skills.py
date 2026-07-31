from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOCAL_LINK = re.compile(r"\[[^]]*]\(([^)]+)\)")
REQUIRED_INTERFACE_KEYS = {"display_name", "short_description", "default_prompt"}
ALLOWED_FRONTMATTER_KEYS = {"name", "description"}
PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|FIXME)\b|[<\[](?:placeholder|insert[^>\]]*)[>\]]",
    re.IGNORECASE,
)


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
    value = yaml.safe_load(parts[1]) or {}
    if not isinstance(value, dict):
        errors.append(f"{skill_file}: frontmatter must be a mapping")
        return {}
    unexpected = set(value) - ALLOWED_FRONTMATTER_KEYS
    if unexpected:
        errors.append(f"{skill_file}: prohibited frontmatter keys: {sorted(unexpected)}")
    return value


def _validate_references(skill_dir: Path, skill_text: str, errors: list[str]) -> None:
    references_root = skill_dir / "references"
    linked: set[Path] = set()
    for target_text in LOCAL_LINK.findall(skill_text):
        target_text = target_text.split("#", 1)[0].strip()
        if not target_text or "://" in target_text or target_text.startswith("#"):
            continue
        target = (skill_dir / target_text).resolve()
        try:
            relative = target.relative_to(skill_dir.resolve())
        except ValueError:
            errors.append(f"{skill_dir / 'SKILL.md'}: local link escapes the skill: {target_text}")
            continue
        if not target.exists():
            errors.append(f"{skill_dir / 'SKILL.md'}: missing linked file {target_text}")
        if relative.parts and relative.parts[0] == "references":
            if len(relative.parts) != 2:
                errors.append(f"{skill_dir}: references must be one level deep: {relative}")
            linked.add(target)

    if not references_root.exists():
        return
    for path in references_root.rglob("*"):
        if path.is_dir():
            if path != references_root:
                errors.append(f"{skill_dir}: nested reference directory is prohibited: {path}")
            continue
        if path.resolve() not in linked:
            errors.append(f"{path}: reference is not linked directly from SKILL.md")


def _validate_layout(skill_dir: Path, errors: list[str]) -> None:
    allowed = {Path("SKILL.md"), Path("agents/openai.yaml")}
    for path in skill_dir.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(skill_dir)
        if relative in allowed:
            continue
        if len(relative.parts) == 2 and relative.parts[0] == "references":
            continue
        errors.append(f"{path}: prohibited auxiliary skill file")


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    metadata_file = skill_dir / "agents" / "openai.yaml"

    if len(skill_dir.name) > 64 or not SKILL_NAME.fullmatch(skill_dir.name):
        errors.append(f"{skill_dir}: skill folder must be lowercase hyphenated and <=64 characters")
    if not skill_file.exists():
        return [*errors, f"{skill_dir}: missing SKILL.md"]

    _validate_layout(skill_dir, errors)
    skill_text = skill_file.read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill_file, errors)
    if frontmatter.get("name") != skill_dir.name:
        errors.append(f"{skill_file}: frontmatter name must be {skill_dir.name!r}")
    description = frontmatter.get("description")
    if not isinstance(description, str) or len(description.strip()) < 40:
        errors.append(f"{skill_file}: description must be non-empty and trigger-oriented")
    elif "use" not in description.casefold() and "when" not in description.casefold():
        errors.append(f"{skill_file}: description must state when to use the skill")
    if PLACEHOLDER.search(skill_text):
        errors.append(f"{skill_file}: placeholder content is prohibited")
    _validate_references(skill_dir, skill_text, errors)

    if not metadata_file.exists():
        errors.append(f"{metadata_file}: missing skill UI metadata")
        return errors
    metadata = load_yaml(metadata_file)
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
        short = interface.get("short_description")
        if not isinstance(short, str) or not 25 <= len(short) <= 64:
            errors.append(f"{metadata_file}: short_description must be 25-64 characters")
        prompt = interface.get("default_prompt")
        if not isinstance(prompt, str) or f"${skill_dir.name}" not in prompt:
            errors.append(f"{metadata_file}: default_prompt must contain ${skill_dir.name}")
    policy = metadata.get("policy")
    if not isinstance(policy, dict) or policy.get("allow_implicit_invocation") is not True:
        errors.append(f"{metadata_file}: policy.allow_implicit_invocation must be true")
    if PLACEHOLDER.search(metadata_file.read_text(encoding="utf-8")):
        errors.append(f"{metadata_file}: placeholder content is prohibited")
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
