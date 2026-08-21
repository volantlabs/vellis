"""Owner-private audited SQLite online backup and backup initialization."""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
from pathlib import Path

from vellis.audit import audit_database
from vellis.database import connect_database, require_supported_database
from vellis.operations import InitializationResult


class BackupIntegrityError(RuntimeError):
    """A source or copied database did not pass complete audit."""


class BackupPublicationDurabilityError(RuntimeError):
    """The destination exists but directory durability could not be confirmed."""


def backup_database(source: Path, destination: Path) -> Path:
    """Copy one live database without reading or copying adjacent sidecars."""
    published, _, _ = _copy_database(source, destination)
    return published


def initialize_from_backup(source: Path, destination: Path) -> InitializationResult:
    """Publish an audited lineage into an absent destination database."""
    _require_clean(source, "backup source", immutable=True)
    _prepare_empty_destination(destination)
    published, lineage_uuid, revision = _copy_database(source, destination, source_immutable=True)
    return InitializationResult(str(published), lineage_uuid, revision)


def _copy_database(
    source: Path, destination: Path, *, source_immutable: bool = False
) -> tuple[Path, str, int]:
    if destination.exists():
        raise FileExistsError(f"backup destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"backup destination directory does not exist: {destination.parent}"
        )
    descriptor, temporary_text = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_text)
    os.fchmod(descriptor, 0o600)
    os.close(descriptor)
    source_connection = None
    destination_connection = None
    try:
        source_connection = connect_database(source, read_only=True, immutable=source_immutable)
        require_supported_database(source_connection)
        destination_connection = sqlite3.connect(temporary, isolation_level=None)
        source_connection.backup(destination_connection, pages=64, progress=_backup_progress)
        destination_connection.close()
        destination_connection = None
        source_connection.close()
        source_connection = None
        os.chmod(temporary, 0o600)
        if os.name == "posix" and stat.S_IMODE(temporary.stat().st_mode) != 0o600:
            raise PermissionError("temporary backup is not owner-private")
        _require_clean(temporary, "copied database", immutable=True)
        lineage_uuid, revision = _database_identity(temporary)
        _remove_sqlite_sidecars(temporary)
        _flush_file(temporary)
        _flush_directory(destination.parent)
        _publish_without_replace(temporary, destination)
        _flush_directory_after_publication(destination.parent)
        return destination, lineage_uuid, revision
    except BaseException:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
        try:
            temporary.unlink()
        except OSError:
            # Preserve the primary failure, especially an indeterminate publication result.
            pass
        try:
            _remove_sqlite_sidecars(temporary)
        except OSError:
            pass
        raise


def _require_clean(path: Path, label: str, *, immutable: bool = False) -> None:
    report = audit_database(path, immutable=immutable)
    if not report.clean:
        raise BackupIntegrityError(f"{label} failed audit: {report.findings[0]}")


def _database_identity(path: Path) -> tuple[str, int]:
    connection = connect_database(path, read_only=True, immutable=True)
    try:
        require_supported_database(connection)
        row = connection.execute(
            "SELECT lineage_uuid, head_revision FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
        assert row is not None
        return str(row["lineage_uuid"]), int(row["head_revision"])
    finally:
        connection.close()


def _backup_progress(status: int, remaining: int, total: int) -> None:
    """Keep online-backup progress private while permitting concurrency evidence."""


def _remove_sqlite_sidecars(database: Path) -> None:
    for sidecar in (Path(f"{database}-wal"), Path(f"{database}-shm")):
        try:
            os.unlink(sidecar)
        except FileNotFoundError:
            pass


def _prepare_empty_destination(destination: Path) -> None:
    parent = destination.parent
    if not parent.exists():
        parent.mkdir(parents=True, mode=0o700)
        return
    if not parent.is_dir():
        raise NotADirectoryError(f"backup destination parent is not a directory: {parent}")
    if any(parent.iterdir()):
        raise FileExistsError(f"backup initialization destination is not empty: {parent}")
    if os.name == "posix" and stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise PermissionError("backup initialization destination must use owner-private mode 0700")


def _publish_without_replace(temporary: Path, destination: Path) -> None:
    try:
        os.link(temporary, destination)
    except FileExistsError as error:
        raise FileExistsError(
            f"backup destination appeared during publication: {destination}"
        ) from error
    try:
        temporary.unlink()
    except OSError as cleanup_error:
        try:
            destination.unlink()
        except OSError as rollback_error:
            raise OSError(
                "backup publication cleanup and rollback both failed; destination is indeterminate"
            ) from rollback_error
        raise OSError("backup publication rolled back after cleanup failure") from cleanup_error


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


def _flush_directory_after_publication(path: Path) -> None:
    try:
        _flush_directory(path)
    except OSError as error:
        raise BackupPublicationDurabilityError(
            "backup destination is published, but directory durability could not be confirmed"
        ) from error
