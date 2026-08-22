"""The one installed owner command for the simplified Vellis v2 boundary."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sys
from pathlib import Path

from vellis.audit import audit_database
from vellis.backup_operations import backup_database, initialize_from_backup
from vellis.domain import RevisionState, TimeState, parse_timestamp
from vellis.history_domain import ActivityMode
from vellis.history_operations import configure_activity_mode
from vellis.onboarding import (
    ClientKind,
    TransportKind,
    entry_exists,
    probe_target,
    register_client,
)
from vellis.operations import initialize_blank, initialize_with_definitions
from vellis.paths import resolve_data_directory, store_path
from vellis.restore_operations import restore_state
from vellis.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    LOOPBACK_HOSTS,
    TokenPublicationDurabilityError,
    read_http_token,
    serve_http,
    serve_stdio,
    write_new_http_token,
)
from vellis.settings_operations import HttpTokenChangedError, record_http_token_rotation
from vellis.starter import everyday_life_starter
from vellis.v1_import_operations import initialize_from_v1, preview_v1_import

EXIT_SUCCESS = 0
EXIT_FAILED = 1
DEFAULT_HTTP_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_TOKEN_ENVIRONMENT = "VELLIS_HTTP_TOKEN"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vellis")
    commands = parser.add_subparsers(dest="command", required=True)
    _setup_parser(commands)
    _connect_parser(commands)
    _serve_parser(commands)
    _backup_parser(commands)
    _restore_parser(commands)
    _audit_parser(commands)
    _configure_parser(commands)
    return parser


def _setup_parser(commands) -> None:
    parser = commands.add_parser("setup", help="Initialize one empty Vellis destination.")
    parser.add_argument("--data-dir")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--blank", action="store_true")
    modes.add_argument("--starter", action="store_true")
    modes.add_argument("--from-v1", type=Path)
    modes.add_argument("--from-backup", type=Path)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--confirm-source-digest")
    parser.add_argument("--confirm-report-digest")
    parser.add_argument("--connect", choices=("codex", "claude", "both"))
    parser.add_argument("--transport", choices=tuple(TransportKind))
    parser.add_argument("--no-connect", action="store_true")


def _connect_parser(commands) -> None:
    parser = commands.add_parser("connect", help="Register the fixed vellis client entry.")
    parser.add_argument("--client", choices=tuple(ClientKind), required=True)
    parser.add_argument("--transport", choices=tuple(TransportKind), required=True)
    parser.add_argument("--data-dir")
    parser.add_argument("--url")
    parser.add_argument("--token-env")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _serve_parser(commands) -> None:
    parser = commands.add_parser("serve", help="Run Vellis in the foreground.")
    parser.add_argument("--transport", choices=tuple(TransportKind), default="stdio")
    parser.add_argument("--data-dir")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=_bindable_port, default=DEFAULT_PORT)
    parser.add_argument("--token-file", type=Path)


def _bindable_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "HTTP bind port must be an integer from 1 to 65535"
        ) from error
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("HTTP bind port must be from 1 to 65535")
    return port


def _backup_parser(commands) -> None:
    parser = commands.add_parser("backup", help="Create an audited SQLite backup.")
    parser.add_argument("--data-dir")
    parser.add_argument("--out", type=Path, required=True)


def _restore_parser(commands) -> None:
    parser = commands.add_parser("restore", help="Restore history as one new revision.")
    parser.add_argument("--data-dir")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--revision", type=int)
    selection.add_argument("--time")
    parser.add_argument("--yes", action="store_true")


def _audit_parser(commands) -> None:
    parser = commands.add_parser("audit", help="Read-only complete integrity audit.")
    parser.add_argument("--data-dir")


def _configure_parser(commands) -> None:
    parser = commands.add_parser("configure", help="Change one explicit owner setting.")
    parser.add_argument("--data-dir")
    setting = parser.add_mutually_exclusive_group(required=True)
    setting.add_argument("--activity-mode", choices=tuple(ActivityMode))
    setting.add_argument("--rotate-http-token", action="store_true")
    parser.add_argument("--yes", action="store_true")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    arguments.vellis_executable = _capture_invocation_executable()
    try:
        return _dispatch(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Vellis could not complete {arguments.command}: {error}", file=sys.stderr)
        return EXIT_FAILED


def _dispatch(arguments) -> int:
    if arguments.command == "setup":
        return _setup(arguments)
    if arguments.command == "connect":
        return _connect(arguments)
    if arguments.command == "serve":
        return _serve(arguments)
    if arguments.command == "backup":
        return _backup(arguments)
    if arguments.command == "restore":
        return _restore(arguments)
    if arguments.command == "audit":
        return _audit(arguments)
    return _configure(arguments)


def _directory(arguments) -> Path:
    return resolve_data_directory(arguments.data_dir)


def _setup(arguments) -> int:
    interactive = sys.stdin.isatty()
    selected = _setup_mode(arguments)
    if selected is None:
        if not interactive:
            raise ValueError(
                "noninteractive setup requires an explicit initialization mode; "
                "pass --starter for the recommended Everyday Life vocabulary "
                "or --blank for an empty graph"
            )
        selected = _interactive_setup_mode(arguments)
    if selected == "cancelled":
        print("Setup cancelled; no destination was published.")
        return EXIT_SUCCESS
    _validate_setup_mode_flags(arguments, selected)
    if selected == "v1-preview":
        preview = preview_v1_import(arguments.from_v1, report_out=arguments.report_out)
        print(f"source sha256: {preview.source_sha256}")
        print(f"report sha256: {preview.report_sha256}")
        return EXIT_SUCCESS
    _validate_setup_connection(arguments, interactive)
    directory = _directory(arguments)
    database = store_path(directory)
    if interactive and not _confirm(f"Initialize {directory}?"):
        print("Setup cancelled; no destination was published.")
        return EXIT_SUCCESS
    revision = _initialize(arguments, selected, database)
    print(f"Vellis initialized revision {revision} at {database}")
    if interactive and arguments.connect is None and not arguments.no_connect:
        _interactive_connection_choice(arguments)
    return EXIT_SUCCESS if _complete_setup_connection(arguments, directory) else EXIT_FAILED


def _complete_setup_connection(arguments, directory: Path) -> bool:
    if arguments.transport == TransportKind.HTTP:
        return _finish_http_setup(directory, arguments.connect, False, arguments.vellis_executable)
    if arguments.connect is not None:
        return _connect_selected(arguments.connect, directory, False, arguments.vellis_executable)
    return True


def _validate_setup_connection(arguments, interactive: bool) -> None:
    if arguments.no_connect and arguments.connect is not None:
        raise ValueError("--no-connect cannot be combined with --connect")
    if not interactive and arguments.connect is None and not arguments.no_connect:
        raise ValueError("noninteractive setup requires --connect <codex|claude> or --no-connect")
    if not interactive and arguments.connect is not None and arguments.transport is None:
        raise ValueError("noninteractive connection requires an explicit --transport <stdio|http>")


def _validate_setup_mode_flags(arguments, selected: str) -> None:
    if selected == "v1-preview":
        if arguments.confirm_source_digest or arguments.confirm_report_digest:
            raise ValueError("v1 preview does not accept confirmation digests")
        if arguments.connect is not None or arguments.no_connect or arguments.transport is not None:
            raise ValueError("v1 preview does not accept connection options")
        return
    if selected != "v1" and (
        arguments.report_out is not None
        or arguments.confirm_source_digest is not None
        or arguments.confirm_report_digest is not None
    ):
        raise ValueError("v1 report and confirmation options require --from-v1")
    if selected == "v1":
        if arguments.report_out is not None:
            raise ValueError("--report-out is valid only for v1 preview")
        if not arguments.confirm_source_digest or not arguments.confirm_report_digest:
            raise ValueError("confirmed v1 import requires both preview digests")


def _finish_http_setup(
    directory: Path,
    selected: str | None,
    confirmed: bool,
    executable: Path | None,
) -> bool:
    token_file = directory / "http-token"
    write_new_http_token(token_file)
    print("HTTP token created privately; its value was not printed.")
    token = read_http_token(token_file).decode("ascii")
    reachable = False
    if selected is not None:
        try:
            probe_target(
                TransportKind.HTTP,
                data_directory=directory,
                url=DEFAULT_HTTP_URL,
                token=token,
            )
        except OSError, RuntimeError, ValueError:
            pass
        else:
            reachable = True
            if os.environ.get(DEFAULT_TOKEN_ENVIRONMENT) == token:
                return _connect_selected_http(selected, directory, confirmed, executable)
    _print_http_next_steps(
        directory,
        selected,
        include_serve=not reachable,
        executable=executable,
    )
    return True


def _print_http_next_steps(
    directory: Path,
    selected: str | None,
    *,
    include_serve: bool,
    executable: Path | None,
) -> None:
    if executable is None:
        raise RuntimeError(
            "guided HTTP commands require invocation through an identifiable installed vellis "
            "console script"
        )
    executable_command = str(executable)
    print("Next steps:")
    quoted_token = shlex.quote(str(directory / "http-token"))
    print(
        "1. Prepare the runtime environment without printing the token: export "
        f'VELLIS_HTTP_TOKEN="$(< {quoted_token})"'
    )
    next_step = 2
    if include_serve:
        serve = (
            executable_command,
            "serve",
            "--transport",
            "http",
            "--data-dir",
            str(directory),
        )
        print(f"{next_step}. Start the foreground server: {shlex.join(serve)}")
        next_step += 1
    if selected is None:
        connect = (
            executable_command,
            "connect",
            "--client",
            "CLIENT",
            "--transport",
            "http",
        )
        print(f"{next_step}. When wanted, connect each client: {shlex.join(connect)}")
        return
    clients = tuple(ClientKind) if selected == "both" else (ClientKind(selected),)
    for index, client in enumerate(clients, start=next_step):
        client_command = (
            executable_command,
            "connect",
            "--client",
            client.value,
            "--transport",
            "http",
            "--url",
            DEFAULT_HTTP_URL,
        )
        print(f"{index}. Connect {client.value}: {shlex.join(client_command)}")


def _connect_selected_http(
    selected: str, directory: Path, confirmed: bool, executable: Path | None
) -> bool:
    clients = tuple(ClientKind) if selected == "both" else (ClientKind(selected),)
    for client in clients:
        result = register_client(
            client,
            TransportKind.HTTP,
            data_directory=directory,
            url=DEFAULT_HTTP_URL,
            token_environment=DEFAULT_TOKEN_ENVIRONMENT,
            replace=False,
            confirmed=confirmed,
            executable=executable,
        )
        if not _report_registration(client, result):
            return False
    return True


def _interactive_connection_choice(arguments) -> None:
    available = [value.value for value in ClientKind if shutil.which(value.value) is not None]
    if not available:
        arguments.no_connect = True
        executable = arguments.vellis_executable
        guidance = (
            "the installed Vellis console script"
            if executable is None
            else shlex.quote(str(executable))
        )
        print(f"No supported Codex or Claude CLI was found; connect later with {guidance} connect.")
        return
    while True:
        choice = input("Connection transport [stdio/http/none] (stdio): ").strip().casefold()
        if choice in {"", "stdio"}:
            arguments.transport = TransportKind.STDIO
            break
        if choice == "http":
            arguments.transport = TransportKind.HTTP
            break
        if choice == "none":
            arguments.no_connect = True
            return
        print("Choose stdio, http, or none.")
    choices = list(available)
    if len(available) == 2:
        choices.append("both")
    choices.append("none")
    _choose_interactive_client(arguments, available, choices)


def _choose_interactive_client(arguments, available: list[str], choices: list[str]) -> None:
    permitted = set(available)
    if len(available) == 2:
        permitted.add("both")
    while True:
        selected = input(f"Client [{'/'.join(choices)}]: ").strip().casefold()
        if selected == "none":
            arguments.no_connect = True
            return
        if selected in permitted:
            arguments.connect = selected
            return
        print("Choose one of the listed clients or none.")


def _interactive_setup_mode(arguments) -> str:
    while True:
        choice = (
            input("Initialization [starter (recommended)/blank/v1/backup] (starter): ")
            .strip()
            .casefold()
        )
        if choice in {"", "starter"}:
            arguments.starter = True
            return "starter"
        if choice == "blank":
            arguments.blank = True
            return "blank"
        if choice == "backup":
            source = input("Backup SQLite file: ").strip()
            if source:
                arguments.from_backup = Path(source)
                return "backup"
            print("A backup path is required.")
            continue
        if choice == "v1":
            selected = _interactive_v1_choice(arguments)
            if selected is not None:
                return selected
            continue
        print("Choose starter, blank, v1, or backup.")


def _interactive_v1_choice(arguments) -> str | None:
    source = input("V1 JSON snapshot: ").strip()
    if not source:
        print("A v1 snapshot path is required.")
        return None
    report = input("Preview report file (leave blank for no extra copy): ").strip()
    arguments.from_v1 = Path(source)
    arguments.report_out = Path(report) if report else None
    preview = preview_v1_import(arguments.from_v1, report_out=arguments.report_out)
    print(f"source sha256: {preview.source_sha256}")
    print(f"report sha256: {preview.report_sha256}")
    print(
        "dispositions: "
        f"preserved={preview.disposition_counts.preserved}, "
        f"converted={preview.disposition_counts.converted}, "
        f"omitted={preview.disposition_counts.omitted}, "
        f"blocking={preview.disposition_counts.blocking}"
    )
    if not preview.acceptable:
        print("The preview contains blocking dispositions and cannot be imported.")
        return "cancelled"
    if not _confirm("Import exactly this source and report?"):
        return "cancelled"
    arguments.confirm_source_digest = preview.source_sha256
    arguments.confirm_report_digest = preview.report_sha256
    arguments.report_out = None
    return "v1"


def _setup_mode(arguments) -> str | None:
    if arguments.preview:
        if arguments.from_v1 is None:
            raise ValueError("--preview requires --from-v1")
        return "v1-preview"
    if arguments.blank:
        return "blank"
    if arguments.starter:
        return "starter"
    if arguments.from_v1 is not None:
        return "v1"
    if arguments.from_backup is not None:
        return "backup"
    return None


def _initialize(arguments, selected: str, database: Path) -> int:
    if selected == "blank":
        return initialize_blank(database).resulting_revision
    elif selected == "starter":
        return initialize_with_definitions(database, everyday_life_starter()).resulting_revision
    elif selected == "backup":
        return initialize_from_backup(arguments.from_backup, database).resulting_revision
    else:
        if not arguments.confirm_source_digest or not arguments.confirm_report_digest:
            raise ValueError("confirmed v1 import requires both preview digests")
        result = initialize_from_v1(
            arguments.from_v1,
            database,
            confirmed_source_sha256=arguments.confirm_source_digest,
            confirmed_report_sha256=arguments.confirm_report_digest,
        )
        return result.resulting_revision


def _connect_selected(
    selected: str, directory: Path, confirmed: bool, executable: Path | None
) -> bool:
    if executable is None:
        raise RuntimeError(
            "STDIO registration requires invocation through an identifiable installed vellis "
            "console script"
        )
    clients = tuple(ClientKind) if selected == "both" else (ClientKind(selected),)
    for client in clients:
        result = register_client(
            client,
            TransportKind.STDIO,
            data_directory=directory,
            url=DEFAULT_HTTP_URL,
            token_environment=DEFAULT_TOKEN_ENVIRONMENT,
            replace=False,
            confirmed=confirmed,
            executable=executable,
        )
        if not _report_registration(client, result):
            return False
    return True


def _report_registration(client: ClientKind, result) -> bool:
    print(f"{client.value}: {result.summary}")
    if result.recovery_command is not None:
        print(f"Recovery command: {result.recovery_command}")
        return False
    return result.readiness_confirmed


def _connect(arguments) -> int:
    transport = TransportKind(arguments.transport)
    client = ClientKind(arguments.client)
    if transport is TransportKind.STDIO and (
        arguments.url is not None or arguments.token_env is not None
    ):
        raise ValueError("STDIO connection does not use --url or --token-env")
    if transport is TransportKind.STDIO and arguments.vellis_executable is None:
        raise RuntimeError(
            "STDIO registration requires invocation through an identifiable installed vellis "
            "console script"
        )
    url = DEFAULT_HTTP_URL if arguments.url is None else arguments.url
    token_environment = (
        DEFAULT_TOKEN_ENVIRONMENT if arguments.token_env is None else arguments.token_env
    )
    if client is ClientKind.CLAUDE and transport is TransportKind.HTTP:
        print(
            "Claude registration stores a literal Authorization header template and expands "
            f"${{{token_environment}}} at runtime. You remain responsible for supplying and "
            "protecting that environment variable in Claude's runtime."
        )
    result = register_client(
        client,
        transport,
        data_directory=_directory(arguments),
        url=url,
        token_environment=token_environment,
        replace=arguments.replace,
        confirmed=arguments.yes,
        executable=arguments.vellis_executable,
    )
    if (
        arguments.replace
        and not arguments.yes
        and result.summary.startswith("confirmation required")
    ):
        print(result.summary)
        if not _confirm("Apply this external client replacement?"):
            print("Client replacement cancelled.")
            return EXIT_SUCCESS
        result = register_client(
            client,
            transport,
            data_directory=_directory(arguments),
            url=url,
            token_environment=token_environment,
            replace=True,
            confirmed=True,
            executable=arguments.vellis_executable,
        )
    print(result.summary)
    if result.recovery_command is not None:
        print(f"Recovery command: {result.recovery_command}")
        return EXIT_FAILED
    if not result.readiness_confirmed:
        return EXIT_FAILED
    return EXIT_SUCCESS


def _capture_invocation_executable() -> Path | None:
    invocation = sys.argv[0]
    located = shutil.which(invocation)
    candidate = Path(located) if located is not None else Path(invocation)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None
    name = resolved.name.casefold()
    return resolved if name in {"vellis", "vellis.exe"} else None


def _serve(arguments) -> int:
    directory = _directory(arguments)
    database = store_path(directory)
    if arguments.transport == TransportKind.STDIO:
        if arguments.token_file is not None:
            raise ValueError("STDIO serving does not use --token-file")
        serve_stdio(database)
        return EXIT_SUCCESS
    token_file = arguments.token_file
    if token_file is None:
        default = directory / "http-token"
        token_file = default if default.exists() else None
    if token_file is None and arguments.host in LOOPBACK_HOSTS:
        print("Warning: loopback HTTP is running without a token for local development.")
    if arguments.host not in LOOPBACK_HOSTS:
        print("Warning: plaintext HTTP requires a trusted LAN, tunnel, or external TLS proxy.")
    serve_http(database, host=arguments.host, port=arguments.port, token_file=token_file)
    return EXIT_SUCCESS


def _backup(arguments) -> int:
    result = backup_database(store_path(_directory(arguments)), arguments.out.resolve())
    print(f"Backup created at {result}")
    return EXIT_SUCCESS


def _restore(arguments) -> int:
    if not arguments.yes and not _confirm("Restore the selected state as a new revision?"):
        print("Restore cancelled.")
        return EXIT_SUCCESS
    selection = (
        RevisionState(arguments.revision)
        if arguments.revision is not None
        else TimeState(parse_timestamp(arguments.time))
    )
    result = restore_state(store_path(_directory(arguments)), selection)
    print(result.summary)
    return EXIT_SUCCESS if result.status.value == "accepted" else EXIT_FAILED


def _audit(arguments) -> int:
    report = audit_database(store_path(_directory(arguments)))
    if report.clean:
        print("Audit clean.")
        return EXIT_SUCCESS
    for finding in report.findings:
        print(finding, file=sys.stderr)
    return EXIT_FAILED


def _configure(arguments) -> int:
    directory = _directory(arguments)
    if arguments.activity_mode is not None:
        result = configure_activity_mode(
            store_path(directory), ActivityMode(arguments.activity_mode)
        )
        print(result.summary)
        return EXIT_SUCCESS
    if not arguments.yes and not _confirm("Rotate the HTTP token?"):
        print("Token rotation cancelled.")
        return EXIT_SUCCESS
    try:
        record_http_token_rotation(
            store_path(directory), lambda: write_new_http_token(directory / "http-token")
        )
        _report_rotated_token_clients()
    except HttpTokenChangedError as error:
        raise HttpTokenChangedError(_rotation_changed_message(str(error))) from error
    except TokenPublicationDurabilityError as error:
        raise HttpTokenChangedError(
            _rotation_changed_message(
                "the HTTP token changed, but filesystem durability is unconfirmed and "
                "supported-client enumeration is incomplete"
            )
        ) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise RuntimeError("HTTP token rotation failed before the token changed") from error
    return EXIT_SUCCESS


def _report_rotated_token_clients() -> None:
    try:
        print(_rotation_changed_message("The HTTP token file changed."))
        found = [
            client.value
            for client in ClientKind
            if shutil.which(client.value) is not None and entry_exists(client)
        ]
        if found:
            print("Reconnect these supported client entries: " + ", ".join(found))
        print("Manually configured HTTP clients cannot be enumerated and must also be updated.")
    except Exception as error:  # noqa: BLE001 - token publication already occurred
        raise HttpTokenChangedError(
            _rotation_changed_message(
                "the HTTP token changed; supported-client enumeration is incomplete, and "
                "manual clients cannot be enumerated"
            )
        ) from error


def _rotation_changed_message(detail: str) -> str:
    guidance = (
        "A running Vellis HTTP server still accepts the old credential until it is restarted. "
        "Stop and restart the foreground server, then reconnect every HTTP client; manually "
        "configured clients cannot be enumerated. This command changes only the default "
        "<data-directory>/http-token file. A server started with --token-file uses a custom file "
        "that this command does not change; replace that custom file yourself, then restart and "
        "reconnect its clients."
    )
    return detail if "--token-file uses a custom file" in detail else f"{detail} {guidance}"


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().casefold() in {"y", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
