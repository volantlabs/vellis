from __future__ import annotations

import json
from pathlib import Path

import pytest

from components.storage.json_file import (
    JsonDocumentInvalid,
    JsonDocumentNotFound,
    JsonValueNotSerializable,
    LocalJsonFileStorage,
    StorageDirectoryNotFound,
    StoragePathInvalid,
    StorageRootInvalid,
)
from components.storage.json_file.protocol import JsonFileStorage
from components.storage.json_file.reference import create_reference_component


def open_storage(root: Path) -> JsonFileStorage:
    return LocalJsonFileStorage.open(root)


def test_write_read_list_delete_round_trip(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    written = storage.write(
        "projects/a/document.json",
        {"name": "alpha", "items": [1, True, None], "nested": {"ok": "yes"}},
    )

    assert written.relative_path == "projects/a/document.json"
    assert written.size_bytes > 0

    document = storage.read("projects/a/document.json")
    assert document.value == {"items": [1, True, None], "name": "alpha", "nested": {"ok": "yes"}}
    assert document.metadata.relative_path == written.relative_path

    listed = storage.list(".")
    assert [metadata.relative_path for metadata in listed.documents] == ["projects/a/document.json"]

    deleted = storage.delete("projects/a/document.json")
    assert deleted.relative_path == "projects/a/document.json"
    with pytest.raises(JsonDocumentNotFound):
        storage.read("projects/a/document.json")


def test_write_replaces_whole_document(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    storage.write("document.json", {"old": True, "remove": "this"})
    storage.write("document.json", {"new": True})

    assert storage.read("document.json").value == {"new": True}


def test_write_recreates_parent_directories_after_delete_cleanup(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    storage.write("a/b/c/document.json", {"version": 1})
    storage.delete("a/b/c/document.json")
    storage.write("a/b/c/document.json", {"version": 2})

    assert storage.read("a/b/c/document.json").value == {"version": 2}


def test_list_is_recursive_and_metadata_only(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    storage.write("root.json", {"root": True})
    storage.write("nested/one.json", {"one": 1})
    storage.write("nested/deeper/two.json", {"two": 2})
    (tmp_path / "nested" / "ignore.txt").write_text("ignore", encoding="utf-8")

    listed = storage.list("nested")

    assert [metadata.relative_path for metadata in listed.documents] == [
        "nested/deeper/two.json",
        "nested/one.json",
    ]
    assert all(hasattr(metadata, "size_bytes") for metadata in listed.documents)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.json",
        "/absolute.json",
        "not-json.txt",
        "nested/../escape.json",
        "windows\\separator.json",
    ],
)
def test_document_paths_must_remain_json_files_inside_root(tmp_path: Path, path: str) -> None:
    storage = open_storage(tmp_path)

    with pytest.raises(StoragePathInvalid):
        storage.write(path, {"invalid": True})


def test_existing_symlink_document_that_escapes_root_is_rejected(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        (tmp_path / "link.json").symlink_to(outside)

        with pytest.raises(StoragePathInvalid):
            storage.read("link.json")
        with pytest.raises(StoragePathInvalid):
            storage.write("link.json", {"invalid": True})
        with pytest.raises(StoragePathInvalid):
            storage.delete("link.json")
    finally:
        outside.unlink(missing_ok=True)


def test_write_through_symlink_parent_that_escapes_root_is_rejected(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)
    outside_dir = tmp_path.parent / "outside-json-storage"
    outside_dir.mkdir(exist_ok=True)
    try:
        (tmp_path / "link").symlink_to(outside_dir, target_is_directory=True)

        with pytest.raises(StoragePathInvalid):
            storage.write("link/document.json", {"invalid": True})
    finally:
        (tmp_path / "link").unlink(missing_ok=True)
        outside_file = outside_dir / "document.json"
        outside_file.unlink(missing_ok=True)
        outside_dir.rmdir()


def test_read_invalid_json_reports_document_invalid(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)
    (tmp_path / "broken.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(JsonDocumentInvalid):
        storage.read("broken.json")


def test_write_rejects_unserializable_value_without_partial_target(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    with pytest.raises(JsonValueNotSerializable):
        storage.write("bad.json", {"bad": object()})  # type: ignore[dict-item]

    assert not (tmp_path / "bad.json").exists()


def test_write_rejects_non_finite_float_without_partial_target(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    with pytest.raises(JsonValueNotSerializable):
        storage.write("bad.json", {"bad": float("nan")})

    assert not (tmp_path / "bad.json").exists()


def test_failed_replace_preserves_previous_complete_document(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)
    storage.write("document.json", {"stable": True})
    before = (tmp_path / "document.json").read_text(encoding="utf-8")

    with pytest.raises(JsonValueNotSerializable):
        storage.write("document.json", {"bad": object()})  # type: ignore[dict-item]

    assert (tmp_path / "document.json").read_text(encoding="utf-8") == before
    assert storage.read("document.json").value == {"stable": True}


def test_missing_directory_list_reports_not_found(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    with pytest.raises(StorageDirectoryNotFound):
        storage.list("missing")


def test_reference_component_is_usable(tmp_path: Path) -> None:
    storage = create_reference_component(tmp_path)

    storage.write("reference.json", {"ok": True})

    assert storage.read("reference.json").value == {"ok": True}


def test_no_forbidden_dependency_imports() -> None:
    component_root = Path(__file__).parents[1]
    forbidden_terms = ("boto3", "sqlalchemy", "sqlite3", "requests", "elasticsearch")

    for path in component_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in forbidden_terms), path


def test_written_file_contains_valid_json(tmp_path: Path) -> None:
    storage = open_storage(tmp_path)

    storage.write("valid.json", {"z": 1})

    with (tmp_path / "valid.json").open("r", encoding="utf-8") as file:
        assert json.load(file) == {"z": 1}


def test_open_rejects_file_root(tmp_path: Path) -> None:
    file_root = tmp_path / "file.txt"
    file_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(StorageRootInvalid):
        LocalJsonFileStorage.open(file_root)


def test_open_rejects_empty_root() -> None:
    with pytest.raises(StorageRootInvalid):
        LocalJsonFileStorage.open("")


def test_storage_handle_does_not_redirect_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    storage_a = open_storage(root_a)
    storage_b = open_storage(root_b)

    storage_a.write("document.json", {"root": "a"})
    storage_b.write("document.json", {"root": "b"})

    assert storage_a.read("document.json").value == {"root": "a"}
    assert storage_b.read("document.json").value == {"root": "b"}
