from __future__ import annotations

import argparse
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / ".agents" / "skills"
CLAUDE_ROOT = REPO_ROOT / ".claude" / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Expose repo-local source-of-truth skills in Claude Code's project layout.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate existing Claude skill symlinks without modifying them.",
    )
    args = parser.parse_args()

    errors = sync_agent_skills(check=args.check)
    if errors:
        for error in errors:
            print(error)
        return 1
    action = "Validated" if args.check else "Synced"
    print(f"{action} Claude skill links for {len(_source_skill_dirs())} skill(s).")
    return 0


def sync_agent_skills(*, check: bool = False) -> list[str]:
    errors: list[str] = []
    source_skill_dirs = _source_skill_dirs()
    if not SOURCE_ROOT.exists():
        return [f"skills source root not found: {SOURCE_ROOT}"]

    if check and not CLAUDE_ROOT.exists():
        return [f"Claude skills root not found: {CLAUDE_ROOT}"]
    if not check:
        CLAUDE_ROOT.mkdir(parents=True, exist_ok=True)

    for source_dir in source_skill_dirs:
        target = CLAUDE_ROOT / source_dir.name
        expected = os.path.relpath(source_dir, target.parent)
        errors.extend(_ensure_link(target, expected, check=check))
    return errors


def _source_skill_dirs() -> list[Path]:
    if not SOURCE_ROOT.exists():
        return []
    return sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir())


def _ensure_link(target: Path, expected: str, *, check: bool) -> list[str]:
    if target.is_symlink():
        actual = os.readlink(target)
        if actual == expected:
            return []
        if check:
            return [f"{target}: points to {actual!r}, expected {expected!r}"]
        target.unlink()
    elif target.exists():
        return [f"{target}: refusing to replace non-symlink skill exposure"]
    elif check:
        return [f"{target}: missing Claude skill symlink to {expected!r}"]

    if check:
        return []
    target.symlink_to(expected, target_is_directory=True)
    return []


if __name__ == "__main__":
    raise SystemExit(main())
