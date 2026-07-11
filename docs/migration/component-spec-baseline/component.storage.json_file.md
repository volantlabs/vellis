---
id: component.storage.json_file
type: Component
status: accepted
owner: humans
model: model/bibliotek/components/component.storage.json_file.sysml
code:
  roots:
    - components/storage/json_file
---

# JSON File Storage

## Purpose

Provide local filesystem-backed storage for JSON documents inside a caller-specified root directory.

The component gives consumers a bounded file-oriented storage surface for `.json` files while owning path validation, JSON serialization, JSON parsing, document metadata reporting, and the supporting directory structure needed to store those documents within that root.

## Responsibilities

- Bind storage operations to one configured local filesystem root.
- Write, read, delete, and recursively list `.json` files within the owned directory tree.
- Create parent directories needed for valid write operations inside the root, including after empty directories have been removed.
- Optionally remove empty parent directories after deleting documents, without making directories part of the public storage model.
- Parse stored JSON into data values on reads.
- Serialize supplied data values as JSON on writes.
- Report document metadata for written, read, deleted, and listed documents.
- Normalize and validate relative document paths before filesystem access.
- Prevent storage operations from escaping the configured root.
- Report missing files, invalid paths, JSON parse failures, and filesystem failures through the public contract.

## Non-responsibilities

- Does not own files outside the configured storage root.
- Does not manage non-JSON file formats.
- Does not expose directories as first-class stored resources.
- Does not define application schemas for stored JSON documents.
- Does not provide append, patch, merge, query, indexing, search, migration, or partial document update semantics.
- Does not maintain a separate metadata index.
- Does not provide encryption, access control, backup, replication, or remote storage.
- Does not coordinate concurrent writers across processes unless a future accepted contract explicitly adds that guarantee.
- Does not watch the filesystem for external changes.

## Provided contracts

### `JsonFileStorage.open`

Kind:

- function

Inputs:

- `root_path`

Outputs:

- `JsonFileStorage`

Errors:

- `StorageRootInvalid`
- `StorageRootUnavailable`
- `StoragePermissionDenied`

Semantics:

- Returns a storage handle bound to the configured local filesystem root.
- The root may be an existing directory or a path that can be created as a directory.
- All document operations through the returned handle are scoped to this root.
- The handle must not silently fall back to another root.

### `JsonFileStorage.write`

Kind:

- function

Inputs:

- `relative_path`
- `json_value`

Outputs:

- `JsonDocumentMetadata`

Errors:

- `StoragePathInvalid`
- `JsonValueNotSerializable`
- `StoragePermissionDenied`
- `StorageWriteFailed`

Semantics:

- Creates a new `.json` file or fully replaces an existing `.json` file at `relative_path` under the storage root.
- Parent directories inside the storage root are created as needed.
- Parent directory creation must tolerate repeated or concurrent attempts to create the same directory.
- The stored file must contain valid JSON representing `json_value`.
- The write is atomic from the perspective of this component's readers: a reader observes either the previous complete document, no document, or the complete newly written document, never a partial JSON file.
- The write replaces the whole JSON document and does not append, patch, merge, or preserve sub-document structure.
- Returned metadata describes the document after the successful write.
- `relative_path` must identify a `.json` file and must not escape the root through absolute paths, parent traversal, symlinks, or platform-specific path aliases.

### `JsonFileStorage.read`

Kind:

- function

Inputs:

- `relative_path`

Outputs:

- `JsonDocument`

Errors:

- `StoragePathInvalid`
- `JsonDocumentNotFound`
- `JsonDocumentInvalid`
- `StoragePermissionDenied`
- `StorageReadFailed`

Semantics:

- Reads and parses the `.json` file at `relative_path` under the storage root.
- Returns the parsed JSON value and document metadata rather than raw file bytes.
- Fails if the target path does not exist, is not a regular `.json` file, or contains invalid JSON.
- `relative_path` must identify a `.json` file and must not escape the root through absolute paths, parent traversal, symlinks, or platform-specific path aliases.

### `JsonFileStorage.delete`

Kind:

- function

Inputs:

- `relative_path`

Outputs:

- `JsonDocumentMetadata`

Errors:

- `StoragePathInvalid`
- `JsonDocumentNotFound`
- `StoragePermissionDenied`
- `StorageDeleteFailed`

Semantics:

- Deletes the `.json` file at `relative_path` under the storage root.
- The operation fails if the target document does not exist.
- Deleting a document may remove empty parent directories under the storage root.
- Directory cleanup must not make later valid write operations fail solely because the parent directory was removed.
- Returned metadata describes the document that was deleted.
- `relative_path` must identify a `.json` file and must not escape the root through absolute paths, parent traversal, symlinks, or platform-specific path aliases.

### `JsonFileStorage.list`

Kind:

- function

Inputs:

- `relative_directory_path`

Outputs:

- `JsonDocumentList`

Errors:

- `StoragePathInvalid`
- `StorageDirectoryNotFound`
- `StoragePermissionDenied`
- `StorageReadFailed`

Semantics:

- Recursively lists `.json` documents under `relative_directory_path` within the storage root.
- Returned document paths are relative to the storage root.
- Returned list entries include document metadata.
- Listing must not return files outside the storage root.

### `JsonDocument`

Kind:

- data structure

Fields:

- `value`
- `metadata`

Semantics:

- Represents a stored JSON document read from the component.
- `value` is the parsed JSON value.
- `metadata` describes the file that contained the parsed value.

### `JsonDocumentList`

Kind:

- data structure

Fields:

- `documents`

Semantics:

- Represents recursive list results under a requested relative directory path.
- `documents` contains `JsonDocumentMetadata` entries, one per listed `.json` file.
- List results do not include parsed document values.

### `JsonDocumentMetadata`

Kind:

- data structure

Fields:

- `relative_path`
- `size_bytes`
- `modified_at`

Semantics:

- `relative_path` is normalized and relative to the storage root.
- `size_bytes` is the serialized file size reported by the filesystem.
- `modified_at` is the filesystem modification time for the stored document.
- Metadata is derived from the filesystem and must not require a separate metadata index.

## Required contracts

May consume:

- Local filesystem directory and file APIs.
- Standard JSON parser and serializer APIs.
- Standard path normalization APIs.

Must not consume:

- Remote object storage services.
- Database engines.
- Application-specific JSON schema validators.
- Cross-component identity, authorization, search, indexing, backup, replication, or migration services.

## Owned state

- The configured local filesystem root directory.
- `.json` files written or deleted through this component inside the configured root.
- Supporting parent directories created or removed by this component inside the configured root.

## Invariants

### `root_containment`

No operation may read, write, list, or delete files outside the configured storage root.

### `json_only_documents`

Document operations are limited to regular files whose normalized relative paths end in `.json`.

### `valid_json_at_rest`

Files successfully written by this component must contain syntactically valid JSON.

### `atomic_full_document_writes`

Successful write operations must publish complete JSON documents atomically from the perspective of this component's readers, and failed writes must not leave partial JSON files at the target document path.

### `caller_schema_neutrality`

The component must preserve caller-supplied JSON values without enforcing application-specific schemas.

### `no_implicit_root_change`

A storage handle bound to one root must not redirect operations to another root.

## Verification

Required checks:

- Contract tests for write, read, delete, and list behavior against a temporary local filesystem root.
- Path containment tests for absolute paths, parent traversal, symlink traversal, nested directories, and platform-specific path separators.
- JSON serialization and parse failure tests.
- Atomic write tests proving failed write operations do not expose partial JSON at the target path.
- No-forbidden-dependency check proving the component does not depend on database, remote object storage, search, authorization, backup, replication, or migration services.

Required evidence:

- Round-trip write, read, delete, and list tests using representative JSON values.
- Boundary tests proving operations cannot escape the configured root.
- Recursive list behavior tests.
- Directory cleanup and recreation tests proving write tolerates parent directories that were removed after delete.
- Metadata tests proving write, read, delete, and list return normalized paths, file sizes, and modified times.
- Error mapping tests for missing documents, invalid JSON, invalid paths, and permission or filesystem failures where practical.

## Change rules

Agents may:

- Implement or refactor private internals inside `components/storage/json_file`.
- Add helper modules inside the component root.
- Add or update boundary-level tests for the provided contracts.
- Improve JSON formatting or metadata details when public behavior remains compatible.

Agents may not:

- Change this component from local filesystem storage to remote or database-backed storage without explicit approval.
- Add application-specific schema validation without explicit approval.
- Add append, patch, merge, or schema-aware update behavior without explicit approval.
- Add a separate metadata index without explicit approval.
- Add cross-component dependencies without explicit approval.
- Weaken root containment, JSON-only document handling, valid-JSON-at-rest, or atomic-write invariants.
- Change lifecycle status from `draft` without human owner approval.

## Open questions

- None.
