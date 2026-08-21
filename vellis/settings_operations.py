"""Small database-owned owner configuration activity operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vellis.activity_repository import append_activity
from vellis.database import connect_database, require_supported_database
from vellis.domain import OperationOutcome, OperationStatus
from vellis.public_wire import public_result
from vellis.wire import serialize_wire


class HttpTokenChangedError(RuntimeError):
    """The filesystem token changed but a later rotation step failed."""


def record_http_token_rotation(
    database_path: Path, publish_token: Callable[[], None]
) -> OperationOutcome:
    connection = connect_database(database_path)
    token_changed = False
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        revision = int(
            connection.execute(
                "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
            ).fetchone()[0]
        )
        result = OperationOutcome(
            OperationStatus.ACCEPTED,
            "HTTP token rotated",
            (),
            revision,
        )
        serialize_wire(result)
        publish_token()
        token_changed = True
        append_activity(
            connection,
            capability="vellis_configure",
            outcome="accepted",
            initiator="owner",
            source="cli",
            evaluated_revision=revision,
            resulting_revision=None,
            summary=result.summary,
            semantic_payload={"setting": "httpToken", "effect": "rotated"},
            verbose_payload={
                "request": {"rotateHttpToken": True},
                "response": public_result(result),
            },
        )
        connection.commit()
        return result
    except BaseException as error:
        connection.rollback()
        if token_changed:
            raise HttpTokenChangedError(
                "the HTTP token changed, but later rotation work failed; a running Vellis HTTP "
                "server still accepts the old credential until it is restarted. Stop and restart "
                "the foreground server, then reconnect every HTTP client; supported-client "
                "enumeration may be incomplete and manual clients cannot be enumerated. The "
                "command changes only the default <data-directory>/http-token file; a server "
                "started with --token-file uses a custom file that the command does not change, "
                "so replace that file yourself before restarting and reconnecting"
            ) from error
        raise
    finally:
        connection.close()
