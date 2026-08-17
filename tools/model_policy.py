from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_ROOT = ROOT / "model"


@dataclass(frozen=True)
class _Token:
    text: str
    start: int


def _tokens(source: str) -> tuple[_Token, ...]:
    """Lex the structural subset needed for ownership without parsing model meaning."""
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        if source[index].isspace():
            index += 1
        elif source.startswith("//*", index):
            end = source.find("*/", index + 3)
            index = len(source) if end < 0 else end + 2
        elif source.startswith("//", index):
            end = source.find("\n", index + 2)
            index = len(source) if end < 0 else end
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = len(source) if end < 0 else end + 2
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
            index = end
        elif source[index].isalpha() or source[index] == "_":
            end = index + 1
            while end < len(source) and (source[end].isalnum() or source[end] == "_"):
                end += 1
            tokens.append(_Token(source[index:end], index))
            index = end
        elif source[index] in "{};":
            tokens.append(_Token(source[index], index))
            index += 1
        else:
            index += 1
    return tuple(tokens)


def _closing_braces(tokens: tuple[_Token, ...]) -> dict[int, int]:
    openings: list[int] = []
    closings: dict[int, int] = {}
    for index, token in enumerate(tokens):
        if token.text == "{":
            openings.append(index)
        elif token.text == "}" and openings:
            closings[openings.pop()] = index
    return closings


def _body_opening(tokens: tuple[_Token, ...], declaration: int) -> int | None:
    for index in range(declaration + 1, len(tokens)):
        if tokens[index].text == "{":
            return index
        if tokens[index].text == ";":
            return None
    return None


def _body_depths(tokens: tuple[_Token, ...], opening: int, closing: int) -> dict[int, int]:
    depth = 1
    depths: dict[int, int] = {}
    for index in range(opening + 1, closing):
        depths[index] = depth
        if tokens[index].text == "{":
            depth += 1
        elif tokens[index].text == "}":
            depth -= 1
    return depths


def policy_findings(path: Path, source: str) -> tuple[str, ...]:
    tokens = _tokens(source)
    closings = _closing_braces(tokens)
    findings: list[str] = []
    for declaration, token in enumerate(tokens):
        if token.text not in {"requirement", "objective"}:
            continue
        is_satisfaction = (
            token.text == "requirement"
            and declaration > 0
            and tokens[declaration - 1].text == "satisfy"
        )
        if is_satisfaction:
            continue
        opening = _body_opening(tokens, declaration)
        if opening is None:
            continue
        closing = closings.get(opening)
        line = source.count("\n", 0, token.start) + 1
        if token.text == "objective":
            label = "objective"
        elif declaration + 1 < len(tokens) and tokens[declaration + 1].text == "def":
            label = "requirement definition"
        else:
            label = "requirement usage"
        if closing is None:
            findings.append(f"{path}:{line}: {label} has no closing brace")
            continue
        depths = _body_depths(tokens, opening, closing)
        required = [
            index
            for index in range(opening + 1, closing)
            if depths[index] == 1 and tokens[index].text == "require"
        ]
        bare_docs = [
            index
            for index in range(opening + 1, closing)
            if depths[index] == 1 and tokens[index].text == "doc"
        ]
        if bare_docs and not required:
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
