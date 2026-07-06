from __future__ import annotations

import argparse
from pathlib import Path

import yaml

REQUIRED_INTERFACE_KEYS = {"display_name", "short_description", "default_prompt"}


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    metadata_file = skill_dir / "agents" / "openai.yaml"

    if not skill_file.exists():
        return [f"{skill_dir}: missing SKILL.md"]

    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"{skill_file}: missing YAML frontmatter")
    else:
        parts = text.split("---\n", 2)
        if len(parts) < 3:
            errors.append(f"{skill_file}: unterminated YAML frontmatter")
        else:
            frontmatter = yaml.safe_load(parts[1]) or {}
            if frontmatter.get("name") != skill_dir.name:
                errors.append(f"{skill_file}: frontmatter name must be {skill_dir.name!r}")
            if not frontmatter.get("description"):
                errors.append(f"{skill_file}: missing description")

    if not metadata_file.exists():
        errors.append(f"{metadata_file}: missing skill UI metadata")
    else:
        metadata = load_yaml(metadata_file)
        if not isinstance(metadata, dict):
            errors.append(f"{metadata_file}: expected mapping")
        else:
            interface = metadata.get("interface")
            if not isinstance(interface, dict):
                errors.append(f"{metadata_file}: missing interface mapping")
            else:
                missing = REQUIRED_INTERFACE_KEYS - set(interface)
                if missing:
                    errors.append(
                        f"{metadata_file}: missing interface keys: {', '.join(sorted(missing))}"
                    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repo-local agent skill metadata.")
    parser.add_argument(
        "skills_root",
        nargs="?",
        default=".agents/skills",
        help="Directory containing skill folders.",
    )
    args = parser.parse_args()

    skills_root = Path(args.skills_root)
    if not skills_root.exists():
        raise SystemExit(f"skills root not found: {skills_root}")

    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    errors = [error for skill_dir in skill_dirs for error in validate_skill(skill_dir)]

    if errors:
        for error in errors:
            print(error)
        return 1

    print(f"Validated {len(skill_dirs)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
