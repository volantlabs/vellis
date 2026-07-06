from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path

from components.storage.json_file.protocol import (
    JsonDocument,
    JsonDocumentInvalid,
    JsonDocumentList,
    JsonDocumentMetadata,
    JsonDocumentNotFound,
    JsonValue,
    JsonValueNotSerializable,
    StorageDeleteFailed,
    StorageDirectoryNotFound,
    StorageError,
    StoragePathInvalid,
    StoragePermissionDenied,
    StorageReadFailed,
    StorageRootInvalid,
    StorageRootUnavailable,
    StorageWriteFailed,
)


class LocalJsonFileStorage:
    """Local filesystem implementation of the JSON File Storage component."""

    def __init__(self, root_path: str | PathLike[str]) -> None:
        self._root = self._open_root(root_path)

    @classmethod
    def open(cls, root_path: str | PathLike[str]) -> LocalJsonFileStorage:
        return cls(root_path)

    @property
    def root_path(self) -> Path:
        return self._root

    def write(
        self,
        relative_path: str | PathLike[str],
        json_value: JsonValue,
    ) -> JsonDocumentMetadata:
        target = self._resolve_document_path(relative_path, must_exist=False)

        try:
            serialized = json.dumps(
                json_value,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        except (TypeError, ValueError) as error:
            raise JsonValueNotSerializable(str(error)) from error

        payload = f"{serialized}\n"
        temporary_path: Path | None = None

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_contained_resolved(target.parent)

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, target)
            temporary_path = None
            return self._metadata_for(target, StorageWriteFailed)
        except PermissionError as error:
            raise StoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise StorageWriteFailed(str(error)) from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def read(self, relative_path: str | PathLike[str]) -> JsonDocument:
        target = self._resolve_document_path(relative_path, must_exist=True)

        try:
            with target.open("r", encoding="utf-8") as file:
                value = json.load(file)
            return JsonDocument(value=value, metadata=self._metadata_for(target, StorageReadFailed))
        except json.JSONDecodeError as error:
            raise JsonDocumentInvalid(str(error)) from error
        except PermissionError as error:
            raise StoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise StorageReadFailed(str(error)) from error

    def delete(self, relative_path: str | PathLike[str]) -> JsonDocumentMetadata:
        target = self._resolve_document_path(relative_path, must_exist=True)

        try:
            metadata = self._metadata_for(target, StorageDeleteFailed)
            target.unlink()
            self._remove_empty_parents(target.parent)
            return metadata
        except PermissionError as error:
            raise StoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise StorageDeleteFailed(str(error)) from error

    def list(self, relative_directory_path: str | PathLike[str] = ".") -> JsonDocumentList:
        directory = self._resolve_directory_path(relative_directory_path)

        if not directory.exists():
            raise StorageDirectoryNotFound(str(relative_directory_path))
        if not directory.is_dir():
            raise StoragePathInvalid(str(relative_directory_path))

        documents: list[JsonDocumentMetadata] = []
        try:
            for path in sorted(directory.rglob("*.json")):
                if not path.is_file():
                    continue
                self._ensure_contained_resolved(path)
                documents.append(self._metadata_for(path, StorageReadFailed))
        except PermissionError as error:
            raise StoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise StorageReadFailed(str(error)) from error

        return JsonDocumentList(documents=tuple(documents))

    @staticmethod
    def _open_root(root_path: str | PathLike[str]) -> Path:
        if os.fspath(root_path) == "":
            raise StorageRootInvalid("root_path must not be empty")

        root = Path(root_path)

        try:
            if root.exists() and not root.is_dir():
                raise StorageRootInvalid(f"storage root is not a directory: {root}")
            root.mkdir(parents=True, exist_ok=True)
            return root.resolve(strict=True)
        except StorageRootInvalid:
            raise
        except PermissionError as error:
            raise StoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise StorageRootUnavailable(str(error)) from error

    def _resolve_document_path(
        self,
        relative_path: str | PathLike[str],
        *,
        must_exist: bool,
    ) -> Path:
        relative = self._validate_relative_path(relative_path, require_json=True)
        self._reject_symlink_components(relative, check_final=must_exist)
        target = self._root.joinpath(relative)

        if must_exist:
            if not target.exists():
                raise JsonDocumentNotFound(str(relative_path))
            if not target.is_file():
                raise StoragePathInvalid(str(relative_path))
            self._ensure_contained_resolved(target)
        else:
            if target.is_symlink():
                raise StoragePathInvalid(f"path traverses a symlink: {relative_path}")
            self._ensure_contained_lexically(target)

        return target

    def _resolve_directory_path(self, relative_path: str | PathLike[str]) -> Path:
        relative = self._validate_relative_path(relative_path, require_json=False)
        self._reject_symlink_components(relative, check_final=True)
        directory = self._root.joinpath(relative)
        self._ensure_contained_lexically(directory)
        if directory.exists():
            self._ensure_contained_resolved(directory)
        return directory

    def _validate_relative_path(
        self,
        relative_path: str | PathLike[str],
        *,
        require_json: bool,
    ) -> Path:
        raw_path = Path(relative_path)
        raw_text = os.fspath(relative_path)

        if not require_json and raw_text in {"", "."}:
            return Path(".")
        if raw_path.is_absolute():
            raise StoragePathInvalid(f"path must be relative: {relative_path}")
        if "\\" in raw_text:
            raise StoragePathInvalid(f"path must use platform separators: {relative_path}")

        parts = raw_path.parts
        if not parts:
            raise StoragePathInvalid("path must not be empty")
        if any(part in {"", ".", ".."} for part in parts):
            if parts != (".",):
                raise StoragePathInvalid(f"path must not contain traversal: {relative_path}")
        if require_json and raw_path.suffix != ".json":
            raise StoragePathInvalid(f"document path must end in .json: {relative_path}")

        return raw_path

    def _reject_symlink_components(self, relative_path: Path, *, check_final: bool) -> None:
        current = self._root
        parts = relative_path.parts
        parts_to_check = parts if check_final else parts[:-1]

        for part in parts_to_check:
            if part == ".":
                continue
            current = current / part
            if current.is_symlink():
                raise StoragePathInvalid(f"path traverses a symlink: {relative_path}")
            if not current.exists():
                return

    def _ensure_contained_lexically(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self._root)
        except ValueError as error:
            raise StoragePathInvalid(f"path escapes storage root: {path}") from error

    def _ensure_contained_resolved(self, path: Path) -> None:
        try:
            path.resolve(strict=True).relative_to(self._root)
        except ValueError as error:
            raise StoragePathInvalid(f"path escapes storage root: {path}") from error
        except FileNotFoundError as error:
            raise StoragePathInvalid(f"path does not exist: {path}") from error

    def _metadata_for(
        self,
        path: Path,
        failure_error: type[StorageError],
    ) -> JsonDocumentMetadata:
        try:
            stat = path.stat()
            self._ensure_contained_resolved(path)
            return JsonDocumentMetadata(
                relative_path=path.resolve(strict=True).relative_to(self._root).as_posix(),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            )
        except PermissionError as error:
            raise StoragePermissionDenied(str(error)) from error
        except OSError as error:
            raise failure_error(str(error)) from error

    def _remove_empty_parents(self, start: Path) -> None:
        current = start
        while current != self._root:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent
