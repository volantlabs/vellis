from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_ROOT = ROOT / "model"

_DECLARATION = re.compile(
    r"(?P<requirement>\brequirement\s+(?P<definition>def\b)?[^;{}]*\{)"
    r"|(?P<objective>\bobjective(?:\s+[^;{}]+)?\s*\{)"
)
_REQUIRED = re.compile(r"\brequire\s+constraint\s*\{")
_DOC = re.compile(r"\bdoc\s*/\*")


def _mask_literals_and_comments(source: str) -> str:
    """Preserve structural offsets while hiding braces in strings and comments."""
    masked = list(source)
    index = 0
    while index < len(source):
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            end = len(source) if end < 0 else end
            masked[index:end] = " " * (end - index)
            index = end
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = len(source) if end < 0 else end + 2
            masked[index:end] = " " * (end - index)
            index = end
        elif source[index] in {'"', "'"}:
            quote = source[index]
            end = index + 1
            while end < len(source):
                if source[end] == "\\":
                    end += 2
                elif source[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            masked[index:end] = " " * (end - index)
            index = end
        else:
            index += 1
    return "".join(masked)


def _close_brace(masked: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _depth_at(masked: str, opening: int, position: int) -> int:
    depth = 0
    for character in masked[opening:position]:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
    return depth


def policy_findings(path: Path, source: str) -> tuple[str, ...]:
    masked = _mask_literals_and_comments(source)
    findings: list[str] = []
    for declaration in _DECLARATION.finditer(masked):
        opening = masked.find("{", declaration.start(), declaration.end())
        closing = _close_brace(masked, opening)
        line = source.count("\n", 0, declaration.start()) + 1
        if declaration.group("objective") is not None:
            label = "objective"
        elif declaration.group("definition") is not None:
            label = "requirement definition"
        else:
            label = "requirement usage"
        if closing is None:
            findings.append(f"{path}:{line}: {label} has no closing brace")
            continue
        required = [
            match
            for match in _REQUIRED.finditer(masked, opening + 1, closing)
            if _depth_at(masked, opening, match.start()) == 1
        ]
        bare_docs = [
            match
            for match in _DOC.finditer(source, opening + 1, closing)
            if _depth_at(masked, opening, match.start()) == 1
        ]
        if not required:
            findings.append(f"{path}:{line}: {label} has no directly owned required constraint")
        if bare_docs:
            findings.append(
                f"{path}:{line}: {label} owns normative documentation outside a required constraint"
            )
    return tuple(findings)


def model_policy_findings(root: Path = MODEL_ROOT) -> tuple[str, ...]:
    findings: list[str] = []
    for path in sorted(root.glob("*.sysml")):
        findings.extend(policy_findings(path, path.read_text(encoding="utf-8")))
    return tuple(findings)


def main() -> int:
    findings = model_policy_findings()
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("Validated required-constraint ownership for authored requirements and objectives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
