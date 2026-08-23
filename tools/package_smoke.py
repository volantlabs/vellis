"""Build wheel and sdist, then exercise each installed successor boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "pyproject.toml").open("rb") as _pyproject:
    VERSION: str = tomllib.load(_pyproject)["project"]["version"]


def _run(
    *arguments: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _documented_install_commands(root: Path) -> tuple[list[str], list[str]]:
    """Extract and validate the install commands documented in README.md.

    The tool-install and uvx lines are returned for execution. The clone block is
    validated for shape only -- executing it would re-resolve every dependency into
    yet another fresh venv for coverage the git+file:// arm already provides -- so a
    typo there still fails here without paying for a second full sync.
    """
    readme = (root / "README.md").read_text(encoding="utf-8")
    section_match = re.search(r"^## Install\n(.*?)(?=^## |\Z)", readme, re.MULTILINE | re.DOTALL)
    if section_match is None:
        raise AssertionError("README.md has no '## Install' section to verify")
    fenced_blocks = re.findall(r"```sh\n(.*?)```", section_match.group(1), re.DOTALL)
    lines_by_block = [block.splitlines() for block in fenced_blocks]
    install_lines = [
        line for lines in lines_by_block for line in lines if line.startswith("uv tool install")
    ]
    trial_lines = [
        line for lines in lines_by_block for line in lines if line.startswith("uvx --from")
    ]
    clone_blocks = [lines for lines in lines_by_block if lines and lines[0].startswith("git clone")]
    canonical_url = "git+https://github.com/volantlabs/vellis"
    if len(install_lines) != 1 or canonical_url not in install_lines[0]:
        raise AssertionError(
            "README.md '## Install' section must contain exactly one "
            f"'uv tool install {canonical_url}' line; found {install_lines!r}"
        )
    if len(trial_lines) != 1 or canonical_url not in trial_lines[0]:
        raise AssertionError(
            "README.md '## Install' section must contain exactly one "
            f"'uvx --from {canonical_url} ...' line; found {trial_lines!r}"
        )
    if len(clone_blocks) != 1 or clone_blocks[0] != [
        "git clone https://github.com/volantlabs/vellis && cd vellis",
        "uv sync",
        "uv run vellis --help",
    ]:
        raise AssertionError(
            "README.md '## Install' section must contain exactly one clone block: "
            f"found {clone_blocks!r}"
        )
    source_url = f"git+file://{root}"
    install_argv = shlex.split(install_lines[0].replace(canonical_url, source_url))
    trial_argv = shlex.split(trial_lines[0].replace(canonical_url, source_url))
    return install_argv, trial_argv


def _run_isolated_tool(
    *arguments: str, cwd: Path, environment: dict[str, str], temporary: Path
) -> subprocess.CompletedProcess[str]:
    """Run a ``uv tool``/``uvx`` command, re-verifying isolation on every call.

    The isolation check lives here, not beside where ``environment`` is built, so
    there is exactly one function in this module capable of running a tool-install
    command against real ``uv`` state -- a future call site cannot silently skip
    the check by threading a different or unvalidated environment into a bare
    ``_run(...)``, and forgetting ``env=`` here is a hard error, not a fallback to
    the real ``os.environ``.
    """
    resolved_temporary = temporary.resolve()
    for variable in ("UV_TOOL_DIR", "UV_TOOL_BIN_DIR"):
        resolved = Path(environment[variable]).resolve()
        if resolved != resolved_temporary and resolved_temporary not in resolved.parents:
            raise AssertionError(
                f"refusing to run an isolated tool command with {variable}="
                f"{environment[variable]!r} outside its isolated temp root {temporary}"
            )
    return _run(*arguments, cwd=cwd, env=environment)


def _verify_documented_install(
    root: Path, temporary: Path, cache_environment: dict[str, str]
) -> None:
    """Run the exact commands documented in README.md against this checkout's committed HEAD.

    ``git+file://{root}`` exercises a real clone's failure mode -- installing from a
    working-tree directory would pass even if a file needed by ``git+https`` were
    untracked -- so this validates HEAD, not the working tree. Every
    ``uv tool``/``uvx`` invocation routes through
    ``_run_isolated_tool``, which re-verifies isolation itself rather than trusting a
    check performed elsewhere, so a refactor cannot silently overwrite the operator's
    real installed ``vellis``.
    """
    install_argv, trial_argv = _documented_install_commands(root)

    tool_dir = temporary / "documented-install-tool-dir"
    tool_bin = temporary / "documented-install-tool-bin"

    environment = dict(cache_environment)
    environment["UV_TOOL_DIR"] = str(tool_dir)
    environment["UV_TOOL_BIN_DIR"] = str(tool_bin)

    _run_isolated_tool(
        install_argv[0],
        "--no-config",
        *install_argv[1:],
        cwd=temporary,
        environment=environment,
        temporary=temporary,
    )

    shim = tool_bin / "vellis"
    if not shim.is_file() or not os.access(shim, os.X_OK):
        raise AssertionError(f"documented install did not produce an executable shim at {shim}")

    which_probe = os.environ.copy()
    which_probe["PATH"] = f"{tool_bin}{os.pathsep}{which_probe['PATH']}"
    resolved = _run(
        "python3",
        "-c",
        "import shutil; print(shutil.which('vellis'))",
        cwd=temporary,
        env=which_probe,
    ).stdout.strip()
    if resolved == "" or Path(resolved).resolve() != shim.resolve():
        raise AssertionError(f"shutil.which('vellis') resolved to {resolved!r}, not {shim}")

    help_result = _run(str(shim), "--help", cwd=temporary)
    for subcommand in ("setup", "connect", "serve", "backup", "restore", "audit", "configure"):
        if subcommand not in help_result.stdout:
            raise AssertionError(f"documented install help omits subcommand {subcommand!r}")

    bare = subprocess.run([str(shim)], cwd=temporary, check=False, capture_output=True, text=True)
    if bare.returncode == 0 or "usage:" not in bare.stderr or "Traceback" in bare.stderr:
        raise AssertionError(f"bare 'vellis' did not exit as a clean usage error: {bare!r}")

    tool_python = tool_dir / "vellis" / "bin" / "python"
    bare_module = subprocess.run(
        [str(tool_python), "-m", "vellis"],
        cwd=temporary,
        check=False,
        capture_output=True,
        text=True,
    )
    if (
        bare_module.returncode == 0
        or "usage:" not in bare_module.stderr
        or "Traceback" in bare_module.stderr
    ):
        raise AssertionError(
            f"bare 'python -m vellis' did not exit as a clean usage error: {bare_module!r}"
        )

    version_check = _run(
        str(tool_python),
        "-c",
        "import sys, vellis\n"
        "print(f'{sys.version_info.major}.{sys.version_info.minor}')\n"
        "print(vellis.__version__)",
        cwd=temporary,
    )
    reported_python, reported_version = version_check.stdout.splitlines()
    if tuple(int(part) for part in reported_python.split(".")) < (3, 14):
        raise AssertionError(
            f"documented install resolved Python {reported_python}, expected >= 3.14"
        )
    if reported_version != VERSION:
        raise AssertionError(
            f"documented install imported version {reported_version!r}, expected {VERSION!r}"
        )

    _run_isolated_tool(
        trial_argv[0],
        "--no-config",
        *trial_argv[1:],
        cwd=temporary,
        environment=environment,
        temporary=temporary,
    )

    data_directory = temporary / "documented-install-data"
    _run(
        str(shim),
        "setup",
        "--blank",
        "--no-connect",
        "--data-dir",
        str(data_directory),
        cwd=temporary,
    )
    _run(str(shim), "audit", "--data-dir", str(data_directory), cwd=temporary)


def _smoke(artifact: Path, root: Path, label: str) -> None:
    environment = root / f"environment-{label}"
    _run("uv", "venv", "--python", "3.14", str(environment), cwd=root)
    python = environment / "bin" / "python"
    binary = environment / "bin" / "vellis"
    _run("uv", "pip", "install", "--python", str(python), str(artifact), cwd=root)
    _assert_installed_import(python, environment, root, label)
    if (environment / "bin" / "vellis-rtg-knowledge-graph").exists():
        raise AssertionError("legacy executable remains installed")
    setup_help = _run(str(binary), "setup", "--help", cwd=root)
    if "--yes" in setup_help.stdout:
        raise AssertionError("installed setup exposes the unselected --yes option")
    rejected_yes = subprocess.run(
        [str(binary), "setup", "--blank", "--no-connect", "--yes"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if rejected_yes.returncode == 0:
        raise AssertionError("installed setup accepted the unselected --yes option")
    invalid_setup_modes = (
        ("--blank", "--report-out", "report.json", "--no-connect"),
        ("--from-v1", "missing.json", "--preview", "--no-connect"),
        ("--from-v1", "missing.json", "--confirm-source-digest", "a", "--no-connect"),
    )
    for index, arguments in enumerate(invalid_setup_modes):
        invalid_destination = root / f"invalid-setup-{label}-{index}"
        rejected = subprocess.run(
            [
                str(binary),
                "setup",
                "--data-dir",
                str(invalid_destination),
                *arguments,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if rejected.returncode == 0 or invalid_destination.exists():
            raise AssertionError(f"installed setup accepted incompatible flags: {arguments!r}")

    probe_environment = os.environ.copy()
    decoy = root / f"decoy-{label}"
    decoy.mkdir()
    decoy_binary = decoy / "vellis"
    decoy_binary.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    decoy_binary.chmod(0o700)
    probe_environment["PATH"] = (
        f"{decoy}{os.pathsep}{environment / 'bin'}{os.pathsep}{probe_environment['PATH']}"
    )

    blank = root / f"blank-{label}"
    starter = root / f"starter-{label}"
    _setup(binary, root, blank, "--blank")
    guided = _setup(
        binary,
        root,
        starter,
        "--starter",
        "--transport",
        "http",
        env=probe_environment,
    )
    _assert_exact_guided_commands(guided.stdout, binary, starter)
    _run(str(python), "-c", _STARTER_ASSERTION, str(starter), cwd=root)

    backup = root / f"backup-{label}.sqlite3"
    _run(str(binary), "backup", "--data-dir", str(blank), "--out", str(backup), cwd=root)
    restored = root / f"from-backup-{label}"
    _setup(binary, root, restored, "--from-backup", str(backup))

    imported = root / f"from-v1-{label}"
    _v1_setup(binary, root, imported, label)

    probe = _run(
        str(python),
        "-c",
        _BOUNDARY_PROBE,
        str(binary),
        str(starter),
        str(blank),
        cwd=root,
        env=probe_environment,
    )
    if probe.stdout.strip() != "stdio=10:0 http=10:0 open=10:0":
        raise AssertionError(f"{label} boundary probe returned {probe.stdout!r}")

    for memory in (blank, starter, restored, imported):
        _run(str(binary), "audit", "--data-dir", str(memory), cwd=root)


def _assert_installed_import(python: Path, environment: Path, root: Path, label: str) -> None:
    imported = _run(
        str(python),
        "-c",
        "import vellis; print(vellis.__version__); print(vellis.__file__)",
        cwd=root,
    )
    version, source = imported.stdout.splitlines()
    if version != VERSION or not Path(source).resolve().is_relative_to(environment.resolve()):
        raise AssertionError(f"{label} imported an unexpected Vellis: {imported.stdout!r}")
    _assert_installed_matches_source(Path(source).resolve().parent, label)


def _build_distribution(root: Path, out_dir: Path, environment: dict[str, str]) -> None:
    """Purge the intermediate tree, then build.

    The purge belongs to the build rather than beside it, so a build cannot be
    invoked without it.
    """
    _purge_build_tree(root)
    _run("uv", "build", "--wheel", "--sdist", "--out-dir", str(out_dir), cwd=root, env=environment)


def _purge_build_tree(root: Path) -> None:
    """Remove the backend's intermediate build tree before building.

    The setuptools backend copies sources into build/ and never removes files
    that no longer exist in the source tree, so an uncleaned tree ships modules
    deleted from source and modules never committed to it.
    """
    shutil.rmtree(root / "build", ignore_errors=True)


def _module_digests(package: Path) -> dict[str, str]:
    """Digest the modules setuptools actually packages.

    Package discovery excludes any directory without __init__.py, so comparing
    every .py file underneath would report a developer's scratch directory as a
    missing module.
    """
    digests: dict[str, str] = {}
    directories = [package]
    while directories:
        current = directories.pop()
        for path in sorted(current.iterdir()):
            if path.is_dir():
                if (path / "__init__.py").exists():
                    directories.append(path)
            elif path.suffix == ".py":
                digests[str(path.relative_to(package))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return digests


def _assert_installed_matches_source(installed: Path, label: str) -> None:
    """Compare installed module content against the source tree.

    A version string cannot distinguish a fresh artifact from a stale one, because
    a rebuilt distribution keeps the same name and version. Content can.
    """
    expected = _module_digests(ROOT / "vellis")
    actual = _module_digests(installed)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    altered = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    if missing or extra or altered:
        raise AssertionError(
            f"{label} does not match the source tree: "
            f"missing={missing} unexpected={extra} altered={altered}"
        )


def _setup(
    binary: Path,
    root: Path,
    memory: Path,
    mode: str,
    *extra: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run(
        str(binary),
        "setup",
        "--data-dir",
        str(memory),
        mode,
        *extra,
        "--no-connect",
        cwd=root,
        env=env,
    )


def _assert_exact_guided_commands(output: str, binary: Path, memory: Path) -> None:
    lines = output.splitlines()
    serve_line = next(line for line in lines if "Start the foreground server:" in line)
    connect_line = next(line for line in lines if "When wanted, connect each client:" in line)
    serve = shlex.split(serve_line.split(": ", 1)[1])
    connect = shlex.split(connect_line.split(": ", 1)[1])
    if (
        not Path(serve[0]).samefile(binary)
        or serve[1:5] != ["serve", "--transport", "http", "--data-dir"]
        or len(serve) != 6
        or not Path(serve[5]).samefile(memory)
    ):
        raise AssertionError(f"guided serve command diverged: {serve!r}")
    if not Path(connect[0]).samefile(binary) or connect[1:] != [
        "connect",
        "--client",
        "CLIENT",
        "--transport",
        "http",
    ]:
        raise AssertionError(f"guided connect command diverged: {connect!r}")


def _v1_setup(binary: Path, root: Path, memory: Path, label: str) -> None:
    source = root / f"v1-{label}.json"
    report = root / f"v1-preview-{label}.json"
    source.write_text(json.dumps(_EMPTY_V1, separators=(",", ":")), encoding="utf-8")
    preview = _run(
        str(binary),
        "setup",
        "--from-v1",
        str(source),
        "--preview",
        "--report-out",
        str(report),
        cwd=root,
    )
    source_digest = _digest_from_output(preview.stdout, "source")
    report_digest = _digest_from_output(preview.stdout, "report")
    _run(
        str(binary),
        "setup",
        "--data-dir",
        str(memory),
        "--from-v1",
        str(source),
        "--confirm-source-digest",
        source_digest,
        "--confirm-report-digest",
        report_digest,
        "--no-connect",
        cwd=root,
    )


def _digest_from_output(output: str, name: str) -> str:
    match = re.search(rf"^{name} sha256: ([0-9a-f]{{64}})$", output, re.MULTILINE)
    if match is None:
        raise AssertionError(f"missing {name} digest in preview output")
    return match.group(1)


_EMPTY_V1 = {
    "graph": {"anchors": [], "data_objects": [], "links": [], "anchor_data_index": {}},
    "schema": {"definitions": []},
    "constraints": {"constraints": []},
    "migration": {"migrations": []},
}


_STARTER_ASSERTION = r"""
import sys
from collections import Counter
from pathlib import Path
from vellis.domain import AssociatedDataTypeDefinition, DefinitionKind, ValueKind
from vellis.operations import read_state
from vellis.paths import store_path

state = read_state(store_path(Path(sys.argv[1])))
counts = Counter(value.kind for value in state.definitions)
assert counts == {
    DefinitionKind.ANCHOR: 12,
    DefinitionKind.ASSOCIATED_DATA: 12,
    DefinitionKind.LINK: 9,
}
dates = {
    (definition.type_key, prop.name)
    for definition in state.definitions
    if isinstance(definition, AssociatedDataTypeDefinition)
    for prop in definition.properties
    if prop.value_kind is ValueKind.DATE
}
assert len(dates) == 8
assert state.graph == ()
"""


_BOUNDARY_PROBE = r"""
import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from fastmcp.exceptions import ToolError
from vellis.onboarding import ClientKind, TransportKind, add_command, stdio_target

async def inspect(transport, exercise=False):
    async with Client(transport) as client:
        tools = await client.list_tools()
        result = await client.call_tool("rtg_type_summary", {})
        if exercise:
            revision = await client.call_tool(
                "rtg_type_summary", {"state": {"kind": "revision", "revision": 0}}
            )
            assert revision.structured_content["status"] == "accepted"
            query = await client.call_tool("rtg_query", {"selection": {
                "kind": "pattern", "maxMatches": 10,
                "nodes": [
                    {"name": "task", "kind": "anchor", "typeKeys": ["life.task"],
                     "predicates": [{"field": {"kind": "displayName"},
                                     "operator": "prefix", "value": "A"}]},
                    {"name": "area", "kind": "anchor", "typeKeys": ["life.area"]},
                ],
                "directAssociations": [],
                "links": [{"name": "belongs", "source": "task", "target": "area",
                           "typeKeys": ["life.belongs_to"]}],
            }})
            assert query.structured_content["matches"] == []
            staged = await client.call_tool("rtg_draft_change", {"definitionUpserts": [
                {"kind": "anchor", "typeKey": "wire.anchor", "description": "Wire anchor"},
                {"kind": "associatedData", "typeKey": "wire.details",
                 "description": "Wire details", "permittedAnchorTypeKeys": ["wire.anchor"],
                 "properties": [
                    {"name": "when", "description": "A date",
                     "valueKind": "date", "nullable": True},
                    {"name": "label", "description": "A label", "valueKind": "text"}],
                 "anchorsPerObject": {"minimum": 1, "maximum": 1},
                 "objectsPerAnchor": {"minimum": 0, "maximum": 1}},
            ]})
            assert staged.structured_content["draftPresent"] is True
            date = {"kind": "date", "value": "2026-01-01"}
            predicates = [
                *({"field": {"kind": "property", "name": "when"}, "operator": op}
                  for op in ("present", "missing", "isNull", "isNotNull")),
                *({"field": {"kind": "property", "name": "when"}, "operator": op,
                   "value": date} for op in ("equal", "notEqual", "lessThan",
                   "lessThanOrEqual", "greaterThan", "greaterThanOrEqual")),
                {"field": {"kind": "property", "name": "when"}, "operator": "anyOf",
                 "values": [date, {"kind": "null", "value": None}]},
                *({"field": {"kind": "property", "name": "label"}, "operator": op,
                   "value": "alpha"} for op in ("contains", "prefix", "regex")),
                *({"field": {"kind": "property", "name": "label"}, "operator": op,
                   "terms": ["alpha"]} for op in ("allTerms", "anyTerms")),
                {"field": {"kind": "property", "name": "label"}, "operator": "phrase",
                 "phrase": "alpha beta"},
            ]
            for predicate in predicates:
                selected = await client.call_tool("rtg_query", {"state": {"kind": "draft"},
                    "selection": {"kind": "pattern", "maxMatches": 10,
                    "nodes": [{"name": "data", "kind": "associatedData",
                               "typeKeys": ["wire.details"], "predicates": [predicate]}],
                    "directAssociations": [], "links": []}})
                assert selected.structured_content["status"] == "accepted"
            inspected = await client.call_tool(
                "rtg_draft_inspect", {"categories": ["definitions"], "limit": 1}
            )
            entries = list(inspected.structured_content["entries"])
            cursor = inspected.structured_content.get("cursor")
            while cursor is not None:
                inspected = await client.call_tool("rtg_draft_inspect", {"cursor": cursor})
                entries.extend(inspected.structured_content["entries"])
                cursor = inspected.structured_content.get("cursor")
            added = next(entry for entry in entries if entry["key"] == "wire.anchor")
            assert "current" in added and added["current"] is None
            assert added["proposed"]["typeKey"] == "wire.anchor"
            details = next(
                entry for entry in entries
                if entry["key"] == "wire.details"
            )
            assert all(
                "allowedValues" not in prop for prop in details["proposed"]["properties"]
            )
            validated = await client.call_tool(
                "rtg_validate", {"scope": "draft", "limit": 10}
            )
            assert validated.structured_content["clean"] is True
            await client.call_tool("rtg_draft_change", {
                "definitionRemovals": ["life.area"]
            })
            removed_page = await client.call_tool(
                "rtg_draft_inspect", {"categories": ["definitions"], "limit": 1}
            )
            removed_entries = list(removed_page.structured_content["entries"])
            cursor = removed_page.structured_content.get("cursor")
            while cursor is not None:
                removed_page = await client.call_tool(
                    "rtg_draft_inspect", {"cursor": cursor}
                )
                removed_entries.extend(removed_page.structured_content["entries"])
                cursor = removed_page.structured_content.get("cursor")
            removed = next(
                entry for entry in removed_entries if entry["key"] == "life.area"
            )
            assert removed["current"]["typeKey"] == "life.area"
            assert "proposed" in removed and removed["proposed"] is None
            history = await client.call_tool("rtg_history", {
                "ledger": "canonical", "range": {"kind": "sequence", "through": 0},
                "maximumRecords": 10,
            })
            assert history.structured_content["headSequence"] == 0
            await client.call_tool("rtg_draft_discard", {})
            dirty_definitions = (
                {"kind": "anchor", "typeKey": "", "description": "A"},
                {"kind": "anchor", "typeKey": "bad.anchor", "description": ""},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": [], "properties": [],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
                {"kind": "associatedData", "typeKey": "bad.empty-allowed",
                 "description": "Explicit empty allowed values",
                 "permittedAnchorTypeKeys": ["life.person"], "properties": [
                    {"name": "x", "description": "X", "valueKind": "text",
                     "allowedValues": []}],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a"], "properties": [
                    {"name": "x", "description": "X", "valueKind": "integer",
                     "allowedValues": [{"kind": "text", "value": "wrong"}]}],
                 "anchorsPerObject": {"minimum": 0},
                 "objectsPerAnchor": {"minimum": 0}},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a"], "properties": [
                    {"name": "x", "description": "X", "valueKind": "text",
                     "minimumLength": 2, "maximumLength": 1, "pattern": "("}],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
                {"kind": "link", "typeKey": "bad.link", "description": "Link",
                 "permittedSourceTypeKeys": [], "permittedTargetTypeKeys": ["a"],
                 "linksPerSource": {"minimum": 0}, "linksPerTarget": {"minimum": 0}},
            )
            for definition in dirty_definitions:
                staged_dirty = await client.call_tool(
                    "rtg_draft_change", {"definitionUpserts": [definition]}
                )
                assert staged_dirty.structured_content["status"] == "accepted"
                if definition["typeKey"] == "bad.empty-allowed":
                    page = await client.call_tool(
                        "rtg_draft_inspect", {"typeKeys": ["bad.empty-allowed"], "limit": 10}
                    )
                    prop = page.structured_content["entries"][0]["proposed"]["properties"][0]
                    assert prop["allowedValues"] == []
                dirty = await client.call_tool(
                    "rtg_validate", {"scope": "draft", "limit": 1000}
                )
                assert dirty.structured_content["clean"] is False
                await client.call_tool("rtg_draft_discard", {})
            malformed_definitions = (
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a", "a"], "properties": [],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a"], "properties": [
                    {"name": "x", "description": "X", "valueKind": "integer"},
                    {"name": "x", "description": "X", "valueKind": "integer"}],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a"], "properties": [
                    {"name": "x", "description": "X", "valueKind": "integer",
                     "allowedValues": [{"kind": "integer", "value": 1},
                                       {"kind": "integer", "value": 1}]}],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
                {"kind": "link", "typeKey": "bad.link", "description": "Link",
                 "permittedSourceTypeKeys": ["a"], "permittedTargetTypeKeys": ["a", "a"],
                 "linksPerSource": {"minimum": 0}, "linksPerTarget": {"minimum": 0}},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a"], "properties": [],
                 "anchorsPerObject": {"minimum": 1},
                 "objectsPerAnchor": {"minimum": 2, "maximum": 1}},
                {"kind": "associatedData", "typeKey": "bad.data", "description": "Data",
                 "permittedAnchorTypeKeys": ["a"], "properties": [
                    {"name": "x", "description": "X", "valueKind": "number",
                     "allowedValues": [{"kind": "number", "value": float("inf")}]}],
                 "anchorsPerObject": {"minimum": 1}, "objectsPerAnchor": {"minimum": 0}},
            )
            malformed = (
                ("rtg_query", {"selection": {"kind": "identities",
                                              "objects": [{"uuid": "bad"}]}}),
                ("rtg_type_summary", {"state": {"kind": "time",
                                                 "timestamp": "2026-01-01T00:00:00"}}),
                ("rtg_change", {"expectedRevision": 0,
                                "removeUuids": ["bad"]}),
                ("rtg_query", {"selection": {"kind": "pattern", "maxMatches": 10,
                    "nodes": [{"name": "item", "kind": "anchor", "predicates": [{
                        "field": {"kind": "displayName"}, "operator": "present"}]}],
                    "directAssociations": [], "links": []}}),
                ("rtg_query", {"selection": {"kind": "pattern", "maxMatches": 10,
                    "nodes": [{"name": "item", "kind": "anchor", "predicates": [{
                        "field": {"kind": "displayName"}, "operator": "equal"}]}],
                    "directAssociations": [], "links": []}}),
                ("rtg_query", {"selection": {"kind": "pattern", "maxMatches": 10,
                    "nodes": [{"name": "item", "kind": "anchor", "predicates": [{
                        "field": {"kind": "displayName"}, "operator": "equal",
                        "value": {"kind": "null", "value": None}}]}],
                    "directAssociations": [], "links": []}}),
                ("rtg_query", {"selection": {"kind": "pattern", "maxMatches": 10,
                    "nodes": [{"name": "item", "kind": "anchor", "predicates": [{
                        "field": {"kind": "displayName"}, "operator": "notEqual",
                        "value": {"kind": "null", "value": None}}]}],
                    "directAssociations": [], "links": []}}),
                ("rtg_query", {"selection": {"kind": "pattern", "maxMatches": 10,
                    "nodes": [{"name": "item", "kind": "anchor", "predicates": [{
                        "field": {"kind": "displayName"}, "operator": "anyOf",
                        "values": []}]}], "directAssociations": [], "links": []}}),
                *(("rtg_draft_change", {"definitionUpserts": [definition]})
                  for definition in malformed_definitions),
            )
            activity_before = await client.call_tool(
                "rtg_history", {"ledger": "activity", "maximumRecords": 1000}
            )
            before_head = activity_before.structured_content["headSequence"]
            for name, arguments in malformed:
                try:
                    await client.call_tool(name, arguments)
                except ToolError:
                    pass
                else:
                    raise AssertionError(f"malformed {name} input reached the operation")
            activity_after = await client.call_tool(
                "rtg_history", {"ledger": "activity", "maximumRecords": 1000}
            )
            assert activity_after.structured_content["headSequence"] == before_head + 1
    return len(tools), result.structured_content["evaluatedRevision"]

async def main():
    binary, starter_memory, blank_memory = sys.argv[1:]
    target = stdio_target(Path(starter_memory), executable=Path(binary))
    assert Path(target[0]) == Path(binary).resolve()
    assert target[1:4] == ("serve", "--transport", "stdio")
    registered = add_command(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=Path(starter_memory),
        url="",
        token_environment="UNUSED",
        executable=Path(binary),
    )
    assert registered[registered.index("--") + 1:] == target
    stdio = await inspect(StdioTransport(target[0], list(target[1:])), exercise=True)
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        port = stream.getsockname()[1]
    process = subprocess.Popen([
        binary, "serve", "--transport", "http", "--data-dir", starter_memory,
        "--port", str(port)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    token = (Path(starter_memory) / "http-token").read_text(encoding="ascii")
    url = f"http://127.0.0.1:{port}/mcp"
    transport = StreamableHttpTransport(url, headers={"Authorization": f"Bearer {token}"})
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                http = await inspect(transport, exercise=True)
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.05)
    finally:
        process.terminate()
        process.wait(timeout=10)
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        open_port = stream.getsockname()[1]
    open_process = subprocess.Popen([
        binary, "serve", "--transport", "http", "--data-dir", blank_memory,
        "--port", str(open_port)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    open_url = f"http://127.0.0.1:{open_port}/mcp"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                opened = await inspect(StreamableHttpTransport(open_url))
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.05)
    finally:
        open_process.terminate()
        open_process.wait(timeout=10)
    print(
        f"stdio={stdio[0]}:{stdio[1]} http={http[0]}:{http[1]} "
        f"open={opened[0]}:{opened[1]}"
    )

asyncio.run(main())
"""


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vellis-package-") as temporary_text:
        temporary = Path(temporary_text)
        distribution = temporary / "dist"
        environment = os.environ.copy()
        environment["UV_CACHE_DIR"] = str(temporary / "uv-cache")
        documented_install_root = temporary / "documented-install"
        documented_install_root.mkdir()
        _verify_documented_install(ROOT, documented_install_root, environment)
        _build_distribution(ROOT, distribution, environment)
        wheel = next(distribution.glob(f"vellis-{VERSION}-py3-none-any.whl"))
        source = next(distribution.glob(f"vellis-{VERSION}.tar.gz"))
        _smoke(wheel, temporary, "wheel")
        _smoke(source, temporary, "sdist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
