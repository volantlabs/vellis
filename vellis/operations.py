"""Explicit operation functions owning one VEL2 connection and transaction."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from vellis.audit import audit_connection
from vellis.canonical_encoding import ZERO_HASH, CanonicalHeader, canonical_record_hash
from vellis.database import connect_database, create_schema, require_supported_database
from vellis.definition_repository import insert_initial_definitions, load_definitions
from vellis.domain import (
    GraphObject,
    StateSelection,
    SystemEnvelope,
    TypeDefinition,
    parse_timestamp,
)
from vellis.domain_validation import definition_set_findings
from vellis.graph_repository import load_graph
from vellis.state_repository import resolve_state


@dataclass(frozen=True, slots=True)
class InitializationResult:
    database_path: str
    lineage_uuid: str
    resulting_revision: int = 0


@dataclass(frozen=True, slots=True)
class StateResult:
    evaluated_revision: int
    definitions: tuple[TypeDefinition, ...]
    graph: tuple[GraphObject, ...]


def initialize_blank(
    database_path: Path,
    *,
    initiator: str = "owner",
    source: str | None = None,
    recorded_at: str | None = None,
) -> InitializationResult:
    return initialize_with_definitions(
        database_path,
        (),
        initiator=initiator,
        source=source,
        recorded_at=recorded_at,
    )


def initialize_with_definitions(
    database_path: Path,
    definitions: tuple[TypeDefinition, ...],
    *,
    initiator: str = "owner",
    source: str | None = None,
    recorded_at: str | None = None,
) -> InitializationResult:
    destination = database_path.resolve()
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    _ensure_parent(destination.parent)
    canonical_definitions = tuple(_with_initial_system(value) for value in definitions)
    findings = definition_set_findings(canonical_definitions, require_system=True)
    if findings:
        raise ValueError(findings[0].summary)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    os.chmod(temporary, 0o600)
    connection: sqlite3.Connection | None = None
    try:
        connection = connect_database(temporary)
        create_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        result = _publish_initial_state(
            connection,
            destination,
            canonical_definitions,
            initiator,
            source,
            recorded_at,
        )
        _serialize_result(result)
        connection.commit()
        audit = audit_connection(connection)
        if not audit.clean:
            raise ValueError(f"unpublished initialized database failed audit: {audit.findings[0]}")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.close()
        connection = None
        _flush_file(temporary)
        _flush_directory(destination.parent)
        _publish_without_replace(temporary, destination)
        _flush_directory_after_publication(destination.parent)
        return result
    except BaseException:
        if connection is not None:
            connection.rollback()
            connection.close()
        _remove_temporary_family(temporary)
        raise


def read_state(database_path: Path, selection: StateSelection | None = None) -> StateResult:
    connection = connect_database(database_path, read_only=True)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN")
        state = resolve_state(connection, selection)
        result = StateResult(
            state.evaluated_revision,
            load_definitions(connection, state),
            load_graph(connection, state),
        )
        _serialize_result(result)
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _publish_initial_state(
    connection: sqlite3.Connection,
    destination: Path,
    definitions: tuple[TypeDefinition, ...],
    initiator: str,
    source: str | None,
    recorded_at: str | None,
) -> InitializationResult:
    lineage_uuid = str(uuid.uuid4())
    timestamp = parse_timestamp(recorded_at or _utc_now())
    bounded_summary = _initialization_summary(definitions)
    connection.execute(
        """
        INSERT INTO canonical_record(
            revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
            initiator, source, transition_kind, summary, affected_type_keys,
            affected_uuids, previous_hash, record_hash
        ) VALUES (0, ?, ?, ?, ?, ?, 'initialization', ?, ?, '[]', ?, ?)
        """,
        (
            timestamp.canonical,
            timestamp.epoch_seconds,
            timestamp.nanosecond,
            initiator,
            source,
            bounded_summary,
            json.dumps(sorted(value.type_key for value in definitions), separators=(",", ":")),
            ZERO_HASH,
            ZERO_HASH,
        ),
    )
    connection.execute(
        """
        INSERT INTO metadata_setting(singleton, lineage_uuid, head_revision)
        VALUES (1, ?, 0)
        """,
        (lineage_uuid,),
    )
    introduced = insert_initial_definitions(connection, definitions)
    header = CanonicalHeader(
        lineage_uuid,
        0,
        timestamp,
        initiator,
        source,
        "initialization",
        bounded_summary,
    )
    record_hash = canonical_record_hash(ZERO_HASH, header, introduced, ())
    connection.execute(
        "UPDATE canonical_record SET record_hash = ? WHERE revision = 0", (record_hash,)
    )
    return InitializationResult(str(destination), lineage_uuid)


def _with_initial_system(definition: TypeDefinition) -> TypeDefinition:
    if definition.system is not None:
        raise ValueError("fresh definition input cannot supply system metadata")
    return replace(definition, system=SystemEnvelope(0, 0))


def _bounded_summary(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= 1_024:
        return value
    return encoded[:1_021].decode("utf-8", errors="ignore") + "..."


def _initialization_summary(definitions: tuple[TypeDefinition, ...]) -> str:
    counts = {kind: 0 for kind in ("anchor", "associatedData", "link")}
    for definition in definitions:
        counts[definition.kind.value] += 1
    summary = (
        f"Initialized Vellis database: definitions={len(definitions)} "
        f"(anchor={counts['anchor']}, associatedData={counts['associatedData']}, "
        f"link={counts['link']}), graphObjects=0"
    )
    if definitions:
        keys = ", ".join(sorted(definition.type_key for definition in definitions))
        summary = f"{summary}; definitionKeys={keys}"
    return _bounded_summary(summary)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _serialize_result(value: InitializationResult | StateResult) -> None:
    if isinstance(value, InitializationResult):
        payload = {
            "databasePath": value.database_path,
            "lineageUuid": value.lineage_uuid,
            "resultingRevision": value.resulting_revision,
        }
    else:
        payload = {
            "evaluatedRevision": value.evaluated_revision,
            "definitionCount": len(value.definitions),
            "graphObjectCount": len(value.graph),
        }
    json.dumps(payload, allow_nan=False, ensure_ascii=False)


def _ensure_parent(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
        return
    if not path.is_dir():
        raise NotADirectoryError(f"data directory is not a directory: {path}")
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise PermissionError(
            f"data directory must use owner-private mode 0700 before initialization: {path}"
        )


def _flush_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _flush_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_without_replace(temporary: Path, destination: Path) -> None:
    try:
        os.link(temporary, destination)
    except FileExistsError as error:
        raise FileExistsError(f"destination appeared during publication: {destination}") from error
    try:
        os.unlink(temporary)
    except OSError as cleanup_error:
        try:
            os.unlink(destination)
        except OSError as rollback_error:
            raise OSError(
                "publication cleanup and rollback both failed; destination state is indeterminate"
            ) from rollback_error
        raise OSError("publication rolled back because temporary cleanup failed") from cleanup_error


def _flush_directory_after_publication(path: Path) -> None:
    try:
        _flush_directory(path)
    except OSError:
        # Publication already succeeded. Never report rollback or failure after that effect.
        pass


def _remove_temporary_family(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
