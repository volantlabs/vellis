from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from components.rtg.controller import RtgControllerValidationFailed
from tools.repo_twin.check import evaluate_findings, has_errors
from tools.repo_twin.evidence import run_and_record
from tools.repo_twin.model import Finding, ScanResult
from tools.repo_twin.report import render_report
from tools.repo_twin.scanner import scan_repo
from tools.repo_twin.store import current_snapshot, snapshot_loaded, sync_scan
from tools.repo_twin.view import GraphView


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-root", default=".", help="Repository root to scan.")
    common.add_argument(
        "--storage-root",
        default=".data/repo-twin",
        help="Local repo twin storage root.",
    )
    parser = argparse.ArgumentParser(prog="repo_twin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "sync",
        parents=[common],
        help="Sync the repo twin from current repo state.",
    )

    check_parser = subparsers.add_parser(
        "check",
        parents=[common],
        help="Check the repo twin for drift.",
    )
    check_parser.add_argument("--json", action="store_true", help="Print findings as JSON.")

    report_parser = subparsers.add_parser(
        "report",
        parents=[common],
        help="Print a repo twin report.",
    )
    report_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")

    query_parser = subparsers.add_parser(
        "query",
        parents=[common],
        help="Run a canned repo twin query.",
    )
    query_parser.add_argument(
        "name",
        choices=(
            "components",
            "orphans",
            "evidence",
            "blast-radius",
            "unimplemented",
            "untested",
        ),
    )
    query_parser.add_argument("argument", nargs="?")
    query_parser.add_argument("--json", action="store_true")

    evidence_parser = subparsers.add_parser(
        "evidence",
        parents=[common],
        help="Run a command and record evidence.",
    )
    evidence_parser.add_argument("kind", choices=("test_run", "lint", "typecheck", "skills_check"))

    args, evidence_command = _parse_args(parser, argv)
    repo_root = Path(args.repo_root).resolve()
    storage_root = Path(args.storage_root)
    if not storage_root.is_absolute():
        storage_root = repo_root / storage_root

    if args.command == "sync":
        scan = scan_repo(repo_root)
        if scan.parse_issues:
            _print_parse_issue_findings(scan)
            return 1
        try:
            summary = sync_scan(scan, storage_root)
        except RtgControllerValidationFailed as error:
            print(
                "ERROR sync_rejected repo: the twin controller rejected the change batch "
                f"({error}). No changes were applied.",
                file=sys.stderr,
            )
            _print_parse_issue_findings(scan)
            return 1
        print(
            "repo twin sync: "
            f"{summary.created} created, {summary.updated} updated, {summary.pruned} pruned; "
            f"{summary.anchors} anchors, {summary.data_objects} data objects, {summary.links} links"
        )
        return 0
    if args.command == "check":
        findings = evaluate_findings(scan_repo(repo_root), storage_root)
        if args.json:
            print(json.dumps([finding.to_json() for finding in findings], indent=2, sort_keys=True))
        else:
            _print_findings(findings)
        return 1 if has_errors(findings) else 0
    if args.command == "report":
        print(render_report(scan_repo(repo_root), storage_root, output_format=args.format), end="")
        return 0
    if args.command == "query":
        return _query(args.name, args.argument, storage_root, as_json=args.json)
    if args.command == "evidence":
        return run_and_record(repo_root, storage_root, args.kind, evidence_command)
    return 2


def _parse_args(
    parser: argparse.ArgumentParser,
    argv: list[str] | None,
) -> tuple[argparse.Namespace, tuple[str, ...]]:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args[:1] != ["evidence"]:
        return parser.parse_args(raw_args), ()

    if "--" in raw_args:
        separator_index = raw_args.index("--")
        args = parser.parse_args(raw_args[:separator_index])
        return args, tuple(raw_args[separator_index + 1 :])

    args, evidence_command = parser.parse_known_args(raw_args)
    return args, tuple(evidence_command)


def _print_parse_issue_findings(scan: ScanResult) -> None:
    for issue in scan.parse_issues:
        print(
            f"ERROR parse_error {issue.source_path}: {issue.message} "
            "The existing twin was preserved; fix the model/index and re-run sync.",
            file=sys.stderr,
        )


def _print_findings(findings: tuple[Finding, ...]) -> None:
    if not findings:
        print("repo twin check: clean")
        return
    for finding in findings:
        print(
            f"{finding.severity.upper()} {finding.finding_id} {finding.subject}: "
            f"{finding.detail} {finding.suggested_action}"
        )


def _query(name: str, argument: str | None, storage_root: Path, *, as_json: bool) -> int:
    if not snapshot_loaded(storage_root):
        print("repo twin snapshot not found; run `just graph-sync` first.", file=sys.stderr)
        return 1
    view = GraphView.from_snapshot(current_snapshot(storage_root))
    if name == "components":
        result = view.components()
    elif name == "orphans":
        result = view.orphans()
    elif name == "unimplemented":
        result = view.unimplemented()
    elif name == "untested":
        result = view.untested()
    elif name == "evidence":
        if argument is None:
            raise SystemExit("query evidence requires a component ID")
        result = view.evidence_for(argument)
    elif name == "blast-radius":
        if argument is None:
            raise SystemExit("query blast-radius requires a component ID")
        result = view.blast_radius(argument)
    else:
        raise SystemExit(f"unknown query: {name}")
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
