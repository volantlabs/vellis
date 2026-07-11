# component.storage.json_file

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `JsonFileStorage`
- Lifecycle: `accepted`
- Purpose: Own a durable namespace of JSON documents beneath one authoritative filesystem root.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `write` | `WriteJsonDocument` | in `relativePath: JsonRelativePath`; in `jsonValue: JsonValue`; out `metadata: JsonDocumentMetadata` | `StoragePathInvalid`, `JsonValueNotSerializable`, `StoragePermissionDenied`, `StorageWriteFailed` | Create or fully replace one JSON document atomically within the configured root. |
| `read` | `ReadJsonDocument` | in `relativePath: JsonRelativePath`; out `document: JsonDocument` | `StoragePathInvalid`, `JsonDocumentNotFound`, `JsonDocumentInvalid`, `StoragePermissionDenied`, `StorageReadFailed` | Read and parse one regular JSON document within the configured root. |
| `delete` | `DeleteJsonDocument` | in `relativePath: JsonRelativePath`; out `metadata: JsonDocumentMetadata` | `StoragePathInvalid`, `JsonDocumentNotFound`, `StoragePermissionDenied`, `StorageDeleteFailed` | Delete one JSON document and optionally remove empty parent directories. |
| `list` | `ListJsonDocuments` | in `relativeDirectoryPath: JsonRelativePath` = `"."`; out `result: JsonDocumentList` | `StoragePathInvalid`, `StorageDirectoryNotFound`, `StoragePermissionDenied`, `StorageReadFailed` | Recursively list JSON document metadata below a relative directory. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenJsonFileStorage` | in `rootPath: FileSystemRootPath`; out `storage: JsonFileStorage` | `StorageRootInvalid`, `StorageRootUnavailable`, `StoragePermissionDenied` | Create or open a handle bound to exactly one filesystem root. |

## Required capabilities

| Feature | Kind | Required contract | Cardinality |
|---|---|---|---|
| — | — | — | No required capabilities. |

## Owned state

| State feature | Type | Authority | Lifetime | Persistence |
|---|---|---|---|---|
| `storageRoot` | `JsonStorageRoot` | `canonicalOwner` | `independent` | `durable` |

## Action and state effects

| Action | State / capability | Access | Contract-significant effect |
|---|---|---|---|
| `write` | `storageRoot` | `write` | replace exactly one normalized JSON document atomically |
| `read` | `storageRoot` | `read` | return one parsed document without changing state |
| `delete` | `storageRoot` | `delete` | remove exactly the addressed document |
| `list` | `storageRoot` | `read` | return recursive normalized metadata without parsed values and without changing state |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.storage.json_file.write_effect` | Success creates or fully replaces the addressed document and leaves every other document unchanged; failure exposes no partial new value. |
| `contract.storage.json_file.read_effect` | Success returns the complete parsed value and metadata for the addressed document; success and failure leave storage state unchanged. |
| `contract.storage.json_file.delete_effect` | Success removes only the addressed document; a rejected delete leaves all documents unchanged. |
| `contract.storage.json_file.list_effect` | Success recursively returns metadata for regular .json documents below the requested directory, never parsed values or files outside the root, and leaves storage state unchanged. |
| `invariant.storage.json_file.root_containment` | No operation shall read, write, list, or delete outside the configured root. |
| `invariant.storage.json_file.json_only_documents` | Document operations are limited to regular files with normalized .json paths. |
| `invariant.storage.json_file.valid_json_at_rest` | Every successfully written document contains syntactically valid JSON. |
| `invariant.storage.json_file.atomic_full_document_writes` | Readers observe the previous complete value, no value, or the complete new value. |
| `invariant.storage.json_file.caller_schema_neutrality` | Storage preserves caller JSON values without application-schema enforcement. |
| `invariant.storage.json_file.no_implicit_root_change` | A handle bound to one root never redirects operations to a different root. |
| `contract.storage.json_file.path_semantics` | Every operation normalizes its relative path before access and rejects absolute paths, parent traversal, symlink traversal, non-JSON document targets, and platform aliases that escape the root. |
| `contract.storage.json_file.directory_semantics` | Writes create valid parent directories as needed. Deletes may remove empty parents, and later valid writes recreate them without exposing directories as stored resources. |
| `contract.storage.json_file.metadata_semantics` | Write, read, delete, and list metadata reports the normalized relative path, serialized filesystem size, and filesystem modification time without a separate metadata index. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `JsonRelativePath` | `attribute` | `value: String` | A normalized component-relative path. Document paths name regular .json files; directory paths name locations below the root. Absolute paths, parent traversal, symlink escape, and platform aliases that escape the root are invalid. |
| `JsonDocumentMetadata` | `attribute` | `relativePath: JsonRelativePath`, `sizeBytes: Integer`, `modifiedAt: Timestamp` | Filesystem-derived metadata: normalized root-relative path, serialized byte size, and filesystem modification time. |
| `JsonDocument` | `attribute` | `value: JsonValue`, `metadata: JsonDocumentMetadata` | Defined by its typed fields and action requirements. |
| `JsonDocumentList` | `attribute` | `documents[0..*]: JsonDocumentMetadata` | Defined by its typed fields and action requirements. |
| `StorageRootInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StorageRootUnavailable` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StoragePermissionDenied` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StoragePathInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `JsonDocumentNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `JsonDocumentInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `JsonValueNotSerializable` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StorageWriteFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StorageReadFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StorageDeleteFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `StorageDirectoryNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `JsonStorageRoot` | `item` | `rootPath: FileSystemRootPath`, `documents[0..*]: JsonDocument` | Durable JSON documents addressable below one configured root. |

## Public enumerations

| Enumeration | Model and external values |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `JsonFileStorageBoundaryVerification` | `rootContainment`, `jsonOnlyDocuments`, `validJsonAtRest`, `atomicFullDocumentWrites`, `callerSchemaNeutrality`, `noImplicitRootChange`, `writeEffect`, `readEffect`, `deleteEffect`, `listEffect`, `pathSemantics`, `directorySemantics`, `metadataSemantics` | `components/storage/json_file/tests/test_storage_json_file_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
