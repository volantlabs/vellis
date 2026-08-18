"""Evidence that plaintext owner memory is private on supported POSIX hosts."""

from __future__ import annotations

import io
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from vellis import preserve
from vellis.canonical import Provenance
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.paths import store_path
from vellis.setup import FreshVocabularyChoice, prepare_local_system
from vellis.store import StoreError
from vellis.streaming import export_ndjson, import_ndjson
from vellis.system import RTGSystem
from vellis.v1_streaming import import_v1_stream

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX mode enforcement only")

REPRESENTATIVE_V1_EXPORT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "v1" / "v1.0-representative-export.json"
)


@contextmanager
def _umask(value: int) -> Iterator[None]:
    previous = os.umask(value)
    try:
        yield
    finally:
        os.umask(previous)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _new_source(path: Path) -> RTGSystem:
    path.parent.mkdir(mode=0o700)
    system = RTGSystem.open(path)
    assert system.initialize_fresh(
        GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
        provenance=Provenance("owner"),
        initialization_summary="fresh",
    ).accepted
    return system


def test_setup_and_sqlite_companions_are_private_under_umask_022(tmp_path: Path) -> None:
    directory = tmp_path / "memory"
    with _umask(0o022):
        report = prepare_local_system(
            data_directory=directory,
            choice=FreshVocabularyChoice.BLANK,
        )
    assert report.succeeded, report.summary
    memory = store_path(directory)
    assert _mode(directory) == 0o700
    assert _mode(memory) == 0o600

    system = RTGSystem.open(memory)
    try:
        assert _mode(Path(f"{memory}-wal")) == 0o600
        assert _mode(Path(f"{memory}-shm")) == 0o600
    finally:
        system.close()


def test_normalized_and_v1_import_publications_remain_private(tmp_path: Path) -> None:
    source = _new_source(tmp_path / "source" / "vellis.sqlite3")
    snapshot = io.StringIO()
    try:
        export_ndjson(source.store.path, snapshot)
    finally:
        source.close()
    snapshot.seek(0)

    normalized = tmp_path / "normalized" / "vellis.sqlite3"
    v1 = tmp_path / "v1" / "vellis.sqlite3"
    with _umask(0o022):
        import_ndjson(snapshot, normalized)
        imported = import_v1_stream(REPRESENTATIVE_V1_EXPORT, v1)

    assert imported.is_acceptable
    for memory in (normalized, v1):
        assert _mode(memory.parent) == 0o700
        assert _mode(memory) == 0o600
        reopened = RTGSystem.open(memory)
        reopened.close()


def test_preserved_snapshot_publication_remains_private(tmp_path: Path) -> None:
    memory = _new_source(tmp_path / "memory" / "vellis.sqlite3")
    memory.close()
    document = tmp_path / "memory.snapshot.ndjson"

    with _umask(0o022):
        result = preserve.main(
            ["--data-dir", str(memory.store.path.parent), "--out", str(document)],
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    assert result == preserve.EXIT_SUCCESS
    assert _mode(document) == 0o600


@pytest.mark.parametrize("unsafe_mode", [0o644, 0o400])
def test_insecure_existing_database_is_refused_without_mutation(
    tmp_path: Path, unsafe_mode: int
) -> None:
    system = _new_source(tmp_path / "memory" / "vellis.sqlite3")
    memory = system.store.path
    revision = system.store.current_revision()
    system.close()
    before = memory.read_bytes()
    memory.chmod(unsafe_mode)

    with pytest.raises(StoreError, match=r"chmod 0600"):
        RTGSystem.open(memory)

    assert _mode(memory) == unsafe_mode
    assert memory.read_bytes() == before
    memory.chmod(0o600)
    reopened = RTGSystem.open(memory)
    try:
        assert reopened.store.current_revision() == revision
    finally:
        reopened.close()


def test_insecure_existing_directory_and_symlinked_database_are_refused(tmp_path: Path) -> None:
    system = _new_source(tmp_path / "memory" / "vellis.sqlite3")
    memory = system.store.path
    system.close()
    directory = memory.parent
    directory.chmod(0o755)
    with pytest.raises(StoreError, match=r"chmod 0700"):
        RTGSystem.open(memory)
    assert _mode(directory) == 0o755

    directory.chmod(0o700)
    link = directory / "linked.sqlite3"
    link.symlink_to(memory)
    with pytest.raises(StoreError, match="not a regular database file"):
        RTGSystem.open(link)
    assert link.is_symlink()
