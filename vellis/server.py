"""Foreground STDIO and HTTP lifecycle for the public successor server."""

from __future__ import annotations

import os
import secrets
import sqlite3
import stat
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import uvicorn

from vellis.database import connect_database, require_supported_database
from vellis.mcp import build_server

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_ENDPOINT = "/mcp"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

AsgiApp = Callable[
    [
        dict[str, Any],
        Callable[[], Awaitable[dict[str, Any]]],
        Callable[[dict[str, Any]], Awaitable[None]],
    ],
    Awaitable[None],
]


class TokenPublicationDurabilityError(RuntimeError):
    """The token changed, but its directory durability could not be confirmed."""


class BearerMiddleware:
    """Protect every HTTP request with one exact bearer token."""

    def __init__(self, app: AsgiApp, token: bytes) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        values = [
            value
            for name, value in scope.get("headers", ())
            if bytes(name).lower() == b"authorization"
        ]
        if len(values) != 1 or not _valid_bearer(bytes(values[0]), self.token):
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"www-authenticate", b"Bearer"),
                        (b"content-type", b"text/plain; charset=utf-8"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"Unauthorized"})
            return
        await self.app(scope, receive, send)


def _valid_bearer(header: bytes, token: bytes) -> bool:
    prefix = b"Bearer "
    supplied = header[len(prefix) :] if header.startswith(prefix) else b""
    return header.startswith(prefix) and bool(supplied) and secrets.compare_digest(supplied, token)


def probe_database(database_path: Path) -> None:
    try:
        connection = connect_database(database_path, read_only=True)
        try:
            require_supported_database(connection)
        finally:
            connection.close()
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise RuntimeError(
            f"database probe failed for {database_path}; verify --data-dir and run Vellis audit "
            "or setup before serving"
        ) from error


def read_http_token(path: Path) -> bytes:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise PermissionError(f"HTTP token path is not a regular file: {path}")
    if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PermissionError(f"HTTP token file is not owner-private: {path}")
    token = path.read_bytes()
    if not token:
        raise ValueError(f"HTTP token file is empty: {path}")
    return token


def write_new_http_token(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(secrets.token_urlsafe(32).encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        try:
            _flush_directory(path.parent)
        except OSError as error:
            raise TokenPublicationDurabilityError(
                "the HTTP token changed, but directory durability could not be confirmed; "
                "reconnect every HTTP client"
            ) from error
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _flush_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def http_application(database_path: Path, token: bytes | None) -> AsgiApp:
    app = build_server(database_path).http_app(
        path=DEFAULT_ENDPOINT,
        stateless_http=True,
        json_response=True,
    )
    return app if token is None else BearerMiddleware(app, token)  # pyright: ignore[reportArgumentType,reportReturnType]


def serve_stdio(database_path: Path) -> None:
    probe_database(database_path)
    build_server(database_path).run(transport="stdio", show_banner=False)


def serve_http(
    database_path: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    token_file: Path | None = None,
) -> None:
    probe_database(database_path)
    try:
        token = None if token_file is None else read_http_token(token_file)
    except (OSError, ValueError) as error:
        raise RuntimeError(
            f"HTTP token validation failed for {token_file}; provide a readable, nonempty "
            "owner-private token file"
        ) from error
    if host not in LOOPBACK_HOSTS and token is None:
        raise RuntimeError(
            "HTTP token validation failed: non-loopback serving requires --token-file pointing "
            "to a readable, nonempty owner-private token file"
        )
    try:
        uvicorn.run(http_application(database_path, token), host=host, port=port, log_config=None)
    except (OSError, SystemExit) as error:
        raise RuntimeError(
            f"HTTP bind/start failed for {host}:{port}; choose an available host/port and retry"
        ) from error
