"""Public-CLI-only Codex and Claude registration with secret-free recovery."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from vellis.mcp import TOOL_NAMES


class ClientKind(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class TransportKind(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[tuple[str, ...]], CommandResult]


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    changed: bool
    summary: str
    recovery_command: str | None = None
    readiness_confirmed: bool = False


def subprocess_runner(arguments: tuple[str, ...]) -> CommandResult:
    completed = subprocess.run(arguments, check=False, capture_output=True, text=True)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def resolve_vellis_executable(executable: Path | None = None) -> Path:
    candidate = shutil.which("vellis") if executable is None else str(executable)
    if candidate is None:
        raise FileNotFoundError("the installed vellis console script was not found on PATH")
    resolved = Path(candidate).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise FileNotFoundError(f"the Vellis console script is not executable: {resolved}")
    return resolved


def stdio_target(data_directory: Path, *, executable: Path | None = None) -> tuple[str, ...]:
    return (
        str(resolve_vellis_executable(executable)),
        "serve",
        "--transport",
        "stdio",
        "--data-dir",
        str(data_directory.resolve()),
    )


def entry_exists(client: ClientKind, runner: Runner = subprocess_runner) -> bool:
    result = runner((client.value, "mcp", "get", "vellis"))
    return result.returncode == 0


def add_command(
    client: ClientKind,
    transport: TransportKind,
    *,
    data_directory: Path,
    url: str,
    token_environment: str,
    executable: Path | None = None,
) -> tuple[str, ...]:
    if transport is TransportKind.STDIO:
        target = stdio_target(data_directory, executable=executable)
        if client is ClientKind.CODEX:
            return ("codex", "mcp", "add", "vellis", "--", *target)
        return ("claude", "mcp", "add", "--scope", "user", "vellis", "--", *target)
    if client is ClientKind.CODEX:
        return (
            "codex",
            "mcp",
            "add",
            "vellis",
            "--url",
            url,
            "--bearer-token-env-var",
            token_environment,
        )
    header = f"Authorization: Bearer ${{{token_environment}}}"
    return (
        "claude",
        "mcp",
        "add",
        "--transport",
        "http",
        "--scope",
        "user",
        "vellis",
        url,
        "--header",
        header,
    )


def remove_command(client: ClientKind) -> tuple[str, ...]:
    return (client.value, "mcp", "remove", "vellis")


def render_command(arguments: Sequence[str]) -> str:
    return shlex.join(arguments)


def probe_target(
    transport: TransportKind,
    *,
    data_directory: Path,
    url: str,
    token: str | None,
    executable: Path | None = None,
) -> None:
    try:
        asyncio.run(_probe_target(transport, data_directory, url, token, executable))
    except Exception as error:  # noqa: BLE001 - normalize a public client boundary failure
        raise RuntimeError("the intended Vellis target probe failed") from error


async def _probe_target(
    transport: TransportKind,
    data_directory: Path,
    url: str,
    token: str | None,
    executable: Path | None,
) -> None:
    if transport is TransportKind.STDIO:
        command, *arguments = stdio_target(data_directory, executable=executable)
        selected = StdioTransport(command, arguments)
    else:
        headers = None if token is None else {"Authorization": f"Bearer {token}"}
        selected = StreamableHttpTransport(url, headers=headers)
    async with Client(selected) as client:
        tools = await client.list_tools()
    names = tuple(value.name for value in tools)
    if names != TOOL_NAMES:
        raise RuntimeError("target did not expose the selected Vellis tools")


def register_client(
    client: ClientKind,
    transport: TransportKind,
    *,
    data_directory: Path,
    url: str,
    token_environment: str,
    replace: bool,
    confirmed: bool,
    runner: Runner = subprocess_runner,
    environ: Mapping[str, str] | None = None,
    probe: Callable[..., None] = probe_target,
    executable: Path | None = None,
) -> RegistrationResult:
    environment = os.environ if environ is None else environ
    exists = entry_exists(client, runner)
    if exists and not replace:
        return RegistrationResult(False, "vellis already exists; pass --replace to replace it")
    token = environment.get(token_environment) if transport is TransportKind.HTTP else None
    if transport is TransportKind.HTTP and not token:
        raise ValueError(f"environment variable {token_environment} must contain the HTTP token")
    addition = add_command(
        client,
        transport,
        data_directory=data_directory,
        url=url,
        token_environment=token_environment,
        executable=executable,
    )
    if client is ClientKind.CLAUDE and transport is TransportKind.HTTP:
        help_result = runner(("claude", "mcp", "add", "--help"))
        help_text = f"{help_result.stdout}\n{help_result.stderr}"
        if help_result.returncode != 0 or not _claude_supports_header_environment(help_text):
            raise RuntimeError(
                "installed Claude CLI does not document supported HTTP header environment "
                "template expansion; automated HTTP registration was refused"
            )
    probe(
        transport,
        data_directory=data_directory,
        url=url,
        token=token,
        executable=executable,
    )
    if exists and not confirmed:
        return RegistrationResult(
            False,
            f"confirmation required to run {render_command(remove_command(client))} then "
            f"{render_command(addition)}",
        )
    if exists:
        try:
            removed = runner(remove_command(client))
        except Exception as error:  # noqa: BLE001 - preserve external-state truth
            return RegistrationResult(
                False,
                f"client removal invocation failed; external entry state is uncertain: {error}",
                _uncertain_removal_recovery(client, addition),
                readiness_confirmed=False,
            )
        if removed.returncode != 0:
            return RegistrationResult(
                False,
                "public client removal failed; external entry state is uncertain and add was "
                "not attempted",
                _uncertain_removal_recovery(client, addition),
                readiness_confirmed=False,
            )
    return _complete_registration(
        addition,
        existed=exists,
        runner=runner,
        probe=probe,
        transport=transport,
        data_directory=data_directory,
        url=url,
        token=token,
        executable=executable,
    )


def _complete_registration(
    addition: tuple[str, ...],
    *,
    existed: bool,
    runner: Runner,
    probe: Callable[..., None],
    transport: TransportKind,
    data_directory: Path,
    url: str,
    token: str | None,
    executable: Path | None,
) -> RegistrationResult:
    try:
        added = runner(addition)
    except Exception as error:  # noqa: BLE001 - preserve external-state truth
        recovery = render_command(addition)
        return RegistrationResult(
            existed,
            (
                "client registration invocation failed after removal"
                if existed
                else "client registration invocation failed"
            )
            + f": {error}",
            recovery,
        )
    if added.returncode != 0:
        recovery = render_command(addition)
        return RegistrationResult(
            existed,
            (
                "client registration failed after removal"
                if existed
                else "client registration failed"
            ),
            recovery,
        )
    try:
        probe(
            transport,
            data_directory=data_directory,
            url=url,
            token=token,
            executable=executable,
        )
    except Exception as error:  # noqa: BLE001 - external entry already changed
        return RegistrationResult(
            True,
            f"public client entry changed, but target readiness could not be reconfirmed: {error}",
            readiness_confirmed=False,
        )
    return RegistrationResult(True, "public client entry configured", readiness_confirmed=True)


def _claude_supports_header_environment(help_text: str) -> bool:
    lowered = help_text.casefold()
    return (
        "--header" in help_text
        and "${" in help_text
        and "environment variable" in lowered
        and ("expand" in lowered or "template" in lowered)
    )


def _uncertain_removal_recovery(client: ClientKind, addition: tuple[str, ...]) -> str:
    commands = (
        (client.value, "mcp", "get", "vellis"),
        remove_command(client),
        addition,
    )
    return " ; ".join(render_command(command) for command in commands)
