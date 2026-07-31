from __future__ import annotations

import argparse
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / ".agents" / "skills"
CLAUDE_ROOT = REPO_ROOT / ".claude" / "skills"


def _source_skill_dirs() -> list[Path]:
    if not SOURCE_ROOT.exists():
        return []
    return sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir())


def _points_into_source(link: Path) -> bool:
    if not link.is_symlink():
        return False
    destination = Path(os.path.abspath(link.parent / os.readlink(link)))
    return destination.is_relative_to(SOURCE_ROOT.resolve())


def _ensure_link(target: Path, expected: str, *, check: bool) -> list[str]:
    if target.is_symlink():
        actual = os.readlink(target)
        if actual == expected:
            return []
        if not _points_into_source(target):
            return [f"{target}: refusing to replace unrelated symlink to {actual!r}"]
        if check:
            return [f"{target}: points to {actual!r}, expected {expected!r}"]
        target.unlink()
    elif target.exists():
        return [f"{target}: refusing to replace real file or directory"]
    elif check:
        return [f"{target}: missing managed skill symlink to {expected!r}"]
    if not check:
        target.symlink_to(expected, target_is_directory=True)
    return []


def sync_agent_skills(*, check: bool = False) -> list[str]:
    if not SOURCE_ROOT.exists():
        return [f"skills source root not found: {SOURCE_ROOT}"]
    if check and not CLAUDE_ROOT.exists():
        return [f"Claude skills root not found: {CLAUDE_ROOT}"]
    if not check:
        CLAUDE_ROOT.mkdir(parents=True, exist_ok=True)

    source_dirs = _source_skill_dirs()
    source_names = {path.name for path in source_dirs}
    errors: list[str] = []
    if CLAUDE_ROOT.exists():
        for target in sorted(CLAUDE_ROOT.iterdir()):
            if target.name in source_names:
                continue
            if target.is_symlink() and _points_into_source(target):
                if check:
                    errors.append(f"{target}: obsolete managed skill symlink")
                else:
                    target.unlink()
            else:
                errors.append(f"{target}: refusing to remove unmanaged skill exposure")
    for source_dir in source_dirs:
        target = CLAUDE_ROOT / source_dir.name
        expected = os.path.relpath(source_dir, target.parent)
        errors.extend(_ensure_link(target, expected, check=check))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Expose repo-local skills to Claude Code.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    errors = sync_agent_skills(check=args.check)
    if errors:
        print("\n".join(errors))
        return 1
    action = "Validated" if args.check else "Synced"
    print(f"{action} Claude skill links for {len(_source_skill_dirs())} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
