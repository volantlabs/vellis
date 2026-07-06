from __future__ import annotations

import tempfile
from pathlib import Path

from components.storage.json_file.implementation import LocalJsonFileStorage
from components.storage.json_file.protocol import JsonFileStorage


def create_reference_component(root_path: str | Path | None = None) -> JsonFileStorage:
    if root_path is None:
        root_path = tempfile.mkdtemp(prefix="vellis-json-file-storage-")
    return LocalJsonFileStorage.open(root_path)


def main() -> None:
    storage = create_reference_component()
    metadata = storage.write("example/document.json", {"hello": "world"})
    document = storage.read(metadata.relative_path)
    print(document)


if __name__ == "__main__":
    main()
