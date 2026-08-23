from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from . import system_evolution_repository as repository
    from .model_layout import ROOT, SYSTEM_EVOLUTION_PATH, SYSTEM_EVOLUTION_SCHEMA_PATH
    from .system_evolution_record import invariant_findings, load_record, schema_findings
except ImportError:  # pragma: no cover - direct script execution
    import system_evolution_repository as repository  # type: ignore[no-redef]
    from model_layout import (  # type: ignore[no-redef]
        ROOT,
        SYSTEM_EVOLUTION_PATH,
        SYSTEM_EVOLUTION_SCHEMA_PATH,
    )
    from system_evolution_record import (  # type: ignore[no-redef]
        invariant_findings,
        load_record,
        schema_findings,
    )


# Compatibility aliases for existing repository tooling and focused tests. Product
# code does not import this workflow module.
_git_text = repository.git_text
_is_vellis_check_command = repository.is_vellis_check_command
_repository_baseline = repository.repository_baseline


def validate_record(record: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    schema_path = root / SYSTEM_EVOLUTION_SCHEMA_PATH.relative_to(ROOT)
    findings = schema_findings(record, schema_path)
    if findings:
        return findings
    findings.extend(invariant_findings(record))
    findings.extend(repository.repository_findings(record, root=root))
    return findings


def status(record: dict[str, Any]) -> str:
    ordered = record["work_items"]
    active = next((item["id"] for item in ordered if item["lifecycle"] == "active"), None)
    complete = {item["id"] for item in ordered if item["lifecycle"] == "complete"}
    ready = [
        item["id"]
        for item in ordered
        if item["lifecycle"] == "ready" and set(item["dependencies"]).issubset(complete)
    ]
    closed = {"resolved", "accepted", "out-of-scope"}
    open_findings = sum(item["disposition"] not in closed for item in record["findings"])
    lines = (
        f"evolution: {record['evolution']['id']}",
        f"lifecycle: {record['evolution']['lifecycle']}",
        f"approval: {record['evolution']['approval']['status']}",
        f"next_work: {active or (ready[0] if ready else 'none')}",
        f"open_findings: {open_findings}",
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect system evolution records.")
    parser.add_argument("command", choices=("check", "status"))
    parser.add_argument("--record", type=Path, default=SYSTEM_EVOLUTION_PATH)
    args = parser.parse_args()
    record = load_record(args.record)
    findings = validate_record(record, root=ROOT)
    if findings:
        print("\n".join(findings))
        return 1
    if args.command == "status":
        print(status(record))
    else:
        print(f"Validated evolution record {record['evolution']['id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
