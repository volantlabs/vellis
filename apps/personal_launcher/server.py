from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from apps.personal_launcher.service import PersonalLauncherService


def run_server(
    service: PersonalLauncherService,
    *,
    host: str,
    port: int,
    static_dir: Path | None = None,
) -> None:
    directory = static_dir or Path(__file__).parent / "static"
    handler = make_handler(service, directory)
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def make_handler(
    service: PersonalLauncherService,
    static_dir: Path,
) -> type[BaseHTTPRequestHandler]:
    static_root = static_dir.resolve()

    class PersonalLauncherHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/state":
                self._send_json(service.state())
                return
            if parsed.path in {"", "/"}:
                self._send_static(static_root / "index.html")
                return
            if parsed.path.startswith("/static/"):
                requested = static_root / unquote(parsed.path.removeprefix("/static/"))
                self._send_static(requested)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self._read_json_body()
                if parsed.path == "/api/launch":
                    self._send_json(service.launch(payload))
                    return
                if parsed.path == "/api/switch":
                    self._send_json(service.switch(payload))
                    return
                if parsed.path == "/api/close":
                    self._send_json(service.close(payload))
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as error:
                self._send_json(
                    {
                        "error": str(error),
                        "error_type": error.__class__.__name__,
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            body = self.rfile.read(length)
            decoded = json.loads(body.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("request body must be a JSON object")
            return decoded

        def _send_static(self, requested: Path) -> None:
            try:
                resolved = requested.resolve()
                resolved.relative_to(static_root)
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not resolved.exists() or not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            data = resolved.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return PersonalLauncherHandler
