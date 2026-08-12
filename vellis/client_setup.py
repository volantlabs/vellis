"""Public-CLI-only setup of supported MCP clients.

This module deliberately knows nothing about either client's configuration files.  It
inspects and changes the named ``vellis`` entry only by executing argument arrays for the
public ``codex mcp`` and ``claude mcp`` commands.  The caller can therefore preview the
complete effect, require an explicit replacement decision, and keep client failure
separate from already-established Vellis memory.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ClientKind(Enum):
    CODEX = "codex"
    CLAUDE = "claude"


class ClientState(Enum):
    ABSENT = "absent"
    MATCHING = "matching"
    DIFFERING = "differing"
    UNAVAILABLE = "unavailable"
    UNPARSEABLE = "unparseable"


class ClientAction(Enum):
    NONE = "no-op"
    ADD = "add"
    REPLACE = "replace"
    MANUAL = "manual"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str]], CommandResult]


@dataclass(frozen=True, slots=True)
class ClientPlan:
    client: ClientKind
    state: ClientState
    action: ClientAction
    inspection_argv: tuple[str, ...]
    remove_argv: tuple[str, ...] | None
    add_argv: tuple[str, ...]
    manual_command: str
    detail: str


@dataclass(frozen=True, slots=True)
class ClientOutcome:
    plan: ClientPlan
    succeeded: bool
    changed: bool
    detail: str


def subprocess_runner(argv: Sequence[str]) -> CommandResult:
    """Execute one public CLI argument array without a shell."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed public CLIs, never a shell
            list(argv),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return CommandResult(returncode=126, stderr=f"executable unavailable: {error}")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def server_argv(project_directory: Path, data_directory: Path | None = None) -> tuple[str, ...]:
    """Return the exact STDIO server command a client stores."""
    command = [
        "uv",
        "--directory",
        str(project_directory.resolve()),
        "run",
        "python",
        "-m",
        "vellis",
    ]
    if data_directory is not None:
        command.extend(("--data-dir", str(data_directory.resolve())))
    return tuple(command)


def render_command(argv: Sequence[str], *, platform: str | None = None) -> str:
    """Render a copyable command for the requested supported command-line family."""
    selected = sys.platform if platform is None else platform
    if selected == "win32":
        return subprocess.list2cmdline(list(argv))
    return shlex.join(argv)


def plan_clients(
    *,
    clients: Iterable[ClientKind],
    replace_clients: Iterable[ClientKind],
    project_directory: Path,
    data_directory: Path | None,
    runner: Runner = subprocess_runner,
    platform: str | None = None,
) -> tuple[ClientPlan, ...]:
    """Inspect selected clients and classify the complete proposed effect."""
    selected = tuple(dict.fromkeys(clients))
    replacements = frozenset(replace_clients)
    if not replacements.issubset(selected):
        raise ValueError("a client can be replaced only when it is also selected")
    target = server_argv(project_directory, data_directory)
    return tuple(
        _plan_one(client, target, client in replacements, runner, platform) for client in selected
    )


def apply_plans(
    plans: Sequence[ClientPlan],
    *,
    runner: Runner = subprocess_runner,
    platform: str | None = None,
) -> tuple[ClientOutcome, ...]:
    """Reinspect and apply only an unchanged, explicitly previewed plan."""
    outcomes: list[ClientOutcome] = []
    for previewed in plans:
        current = _plan_one(
            previewed.client,
            _target_from_add(previewed),
            previewed.action is ClientAction.REPLACE,
            runner,
            platform,
        )
        if (current.state, current.action, current.add_argv) != (
            previewed.state,
            previewed.action,
            previewed.add_argv,
        ):
            outcomes.append(
                ClientOutcome(
                    plan=current,
                    succeeded=False,
                    changed=False,
                    detail=(
                        "client state changed after preview; inspect it with the public CLI "
                        "and use setup's reported client-only retry command"
                    ),
                )
            )
            continue
        outcomes.append(_apply_one(current, runner))
    return tuple(outcomes)


def _plan_one(
    client: ClientKind,
    target: tuple[str, ...],
    replace_differing: bool,
    runner: Runner,
    platform: str | None,
) -> ClientPlan:
    inspection = _inspection_argv(client)
    result = runner(inspection)
    state, detail = _classify(client, result, target)
    add = _add_argv(client, target)
    remove = _remove_argv(client)
    if state is ClientState.MATCHING:
        action = ClientAction.NONE
    elif state is ClientState.ABSENT:
        action = ClientAction.ADD
    elif state is ClientState.DIFFERING:
        action = ClientAction.REPLACE if replace_differing else ClientAction.REFUSE
    elif state is ClientState.UNAVAILABLE:
        action = ClientAction.MANUAL
    else:
        action = ClientAction.REFUSE
    return ClientPlan(
        client=client,
        state=state,
        action=action,
        inspection_argv=inspection,
        remove_argv=remove if action is ClientAction.REPLACE else None,
        add_argv=add,
        manual_command=render_command(add, platform=platform),
        detail=detail,
    )


def _apply_one(plan: ClientPlan, runner: Runner) -> ClientOutcome:
    if plan.action is ClientAction.NONE:
        return ClientOutcome(plan, True, False, "matching user-scoped entry left unchanged")
    if plan.action is ClientAction.MANUAL:
        return ClientOutcome(
            plan,
            False,
            False,
            f"client CLI is unavailable; run: {plan.manual_command}",
        )
    if plan.action is ClientAction.REFUSE:
        corrective = (
            f"select --replace-client {plan.client.value} to replace it deliberately"
            if plan.state is ClientState.DIFFERING
            else (
                "inspect the client with its public CLI and use setup's reported "
                "client-only retry command"
            )
        )
        return ClientOutcome(plan, False, False, f"{plan.detail}; {corrective}")
    if plan.remove_argv is not None:
        removed = runner(plan.remove_argv)
        if removed.returncode != 0:
            return ClientOutcome(
                plan,
                False,
                False,
                f"public CLI removal failed: {_command_failure(removed)}",
            )
    added = runner(plan.add_argv)
    if added.returncode != 0:
        return ClientOutcome(
            plan,
            False,
            plan.remove_argv is not None,
            "public CLI registration failed: "
            f"{_command_failure(added)}; run: {plan.manual_command}",
        )
    return ClientOutcome(plan, True, True, "user-scoped STDIO entry configured")


def _inspection_argv(client: ClientKind) -> tuple[str, ...]:
    if client is ClientKind.CODEX:
        return ("codex", "mcp", "get", "vellis", "--json")
    return ("claude", "mcp", "get", "vellis")


def _remove_argv(client: ClientKind) -> tuple[str, ...]:
    if client is ClientKind.CODEX:
        return ("codex", "mcp", "remove", "vellis")
    return ("claude", "mcp", "remove", "vellis")


def _add_argv(client: ClientKind, target: Sequence[str]) -> tuple[str, ...]:
    if client is ClientKind.CODEX:
        return ("codex", "mcp", "add", "vellis", "--", *target)
    return ("claude", "mcp", "add", "--scope", "user", "vellis", "--", *target)


def _target_from_add(plan: ClientPlan) -> tuple[str, ...]:
    separator = plan.add_argv.index("--")
    return plan.add_argv[separator + 1 :]


def _classify(
    client: ClientKind, result: CommandResult, target: tuple[str, ...]
) -> tuple[ClientState, str]:
    combined = f"{result.stdout}\n{result.stderr}".strip()
    lowered = combined.lower()
    if result.returncode in {126, 127} and lowered.startswith("executable unavailable"):
        return ClientState.UNAVAILABLE, "client executable is not available"
    if result.returncode != 0:
        if _reports_absence(client, combined):
            return ClientState.ABSENT, "no vellis entry is registered"
        return ClientState.UNPARSEABLE, f"client inspection failed: {combined or result.returncode}"
    parsed = (
        _parse_codex(result.stdout) if client is ClientKind.CODEX else _parse_claude(result.stdout)
    )
    if parsed is None:
        return ClientState.UNPARSEABLE, "client inspection output could not be classified"
    command, scope, enabled, clean_environment = parsed
    if command == target and scope == "user" and enabled and clean_environment:
        return ClientState.MATCHING, "the enabled user-scoped STDIO entry already matches"
    return ClientState.DIFFERING, "the registered vellis entry differs from the selected setup"


def _reports_absence(client: ClientKind, text: str) -> bool:
    named_absence = re.search(
        r"^(?:error:\s*)?no mcp server named [\"']vellis[\"'](?:\s+found)?[.]?",
        text,
        re.IGNORECASE,
    )
    if named_absence is not None:
        return True
    if client is ClientKind.CLAUDE:
        return False
    return bool(
        re.search(
            r"(?:mcp )?server (?:named )?[`\"']?vellis[`\"']? (?:was )?not found",
            text,
            re.IGNORECASE,
        )
    )


def _parse_codex(text: str) -> tuple[tuple[str, ...], str, bool, bool] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    transport = value.get("transport")
    if isinstance(transport, dict):
        command = transport.get("command")
        args = transport.get("args", [])
        kind = transport.get("type", "stdio")
        environment = transport.get("env")
    else:
        command = value.get("command")
        args = value.get("args", [])
        kind = value.get("transport", "stdio")
        environment = value.get("env")
    if not isinstance(kind, str) or not isinstance(args, list):
        return None
    if not all(isinstance(argument, str) for argument in args):
        return None
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        return None
    # Codex's CLI-managed configuration is user scoped; the public JSON currently omits
    # a redundant scope field, but accept it when a future version makes it explicit.
    scope = value.get("scope", "user")
    if not isinstance(scope, str):
        return None
    if kind == "stdio":
        if not isinstance(command, str):
            return None
        argv = (command, *args)
    else:
        # A valid HTTP or other non-STDIO entry is still a readable, deliberately
        # replaceable difference.  Its transport-specific fields need not be copied into
        # setup because equality with the selected STDIO command is already impossible.
        argv = ()
    clean_environment = environment is None or environment == {}
    return argv, scope.lower(), enabled, clean_environment


def _parse_claude(text: str) -> tuple[tuple[str, ...], str, bool, bool] | None:
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    command = fields.get("command")
    arguments = fields.get("args", "")
    scope_words = fields.get("scope", "").split()
    scope = scope_words[0].lower() if scope_words else ""
    transport = fields.get("type", fields.get("transport", "")).lower()
    status = fields.get("status", "").lower()
    if not scope or not transport:
        return None
    if transport == "stdio":
        if not command:
            return None
        try:
            argv = (command, *shlex.split(arguments))
        except ValueError:
            return None
    else:
        argv = ()
    enabled = not any(marker in status for marker in ("disabled", "pending approval"))
    environment = fields.get("environment", "").strip().lower()
    clean_environment = environment in {"", "none", "(none)"}
    return argv, scope, enabled, clean_environment


def _command_failure(result: CommandResult) -> str:
    return (result.stderr or result.stdout).strip() or f"exit status {result.returncode}"
