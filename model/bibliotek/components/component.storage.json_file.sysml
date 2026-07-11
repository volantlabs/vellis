library package BibliotekStorageJsonFile {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /*
     * Local filesystem-backed JSON document storage scoped to one caller-supplied root.
     * The model defines its black-box state authority and contract-significant effects while
     * leaving filesystem algorithms and layout to the realization.
     */

    attribute def JsonRelativePath {
        attribute value : String;
        doc /* A normalized component-relative path. Document paths name regular .json files; directory paths name locations below the root. Absolute paths, parent traversal, symlink escape, and platform aliases that escape the root are invalid. */
    }

    attribute def JsonDocumentMetadata {
        attribute relativePath : JsonRelativePath;
        attribute sizeBytes : Integer;
        attribute modifiedAt : Timestamp;
        doc /* Filesystem-derived metadata: normalized root-relative path, serialized byte size, and filesystem modification time. */
    }

    attribute def JsonDocument {
        attribute value : JsonValue;
        attribute metadata : JsonDocumentMetadata;
    }

    attribute def JsonDocumentList {
        attribute documents[0..*] : JsonDocumentMetadata;
    }

    attribute def StorageRootInvalid { attribute message : String; }
    attribute def StorageRootUnavailable { attribute message : String; }
    attribute def StoragePermissionDenied { attribute message : String; }
    attribute def StoragePathInvalid { attribute message : String; }
    attribute def JsonDocumentNotFound { attribute message : String; }
    attribute def JsonDocumentInvalid { attribute message : String; }
    attribute def JsonValueNotSerializable { attribute message : String; }
    attribute def StorageWriteFailed { attribute message : String; }
    attribute def StorageReadFailed { attribute message : String; }
    attribute def StorageDeleteFailed { attribute message : String; }
    attribute def StorageDirectoryNotFound { attribute message : String; }

    item def JsonStorageRoot {
        attribute rootPath : FileSystemRootPath;
        attribute documents[0..*] : JsonDocument;
        doc /* Durable JSON documents addressable below one configured root. */
    }

    action def WriteJsonDocument {
        in relativePath : JsonRelativePath;
        in jsonValue : JsonValue;
        out metadata : JsonDocumentMetadata;
        doc /* Create or fully replace one JSON document atomically within the configured root. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "JsonValueNotSerializable",
                "StoragePermissionDenied", "StorageWriteFailed");
            obligation = "A failed write shall not expose a partial target document.";
        }
    }

    action def ReadJsonDocument {
        in relativePath : JsonRelativePath;
        out document : JsonDocument;
        doc /* Read and parse one regular JSON document within the configured root. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "JsonDocumentNotFound", "JsonDocumentInvalid",
                "StoragePermissionDenied", "StorageReadFailed");
            obligation = "Failures shall identify invalid paths, missing documents, invalid JSON, or IO failure.";
        }
    }

    action def DeleteJsonDocument {
        in relativePath : JsonRelativePath;
        out metadata : JsonDocumentMetadata;
        doc /* Delete one JSON document and optionally remove empty parent directories. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "JsonDocumentNotFound",
                "StoragePermissionDenied", "StorageDeleteFailed");
            obligation = "A later valid write shall recreate any removed parent directories.";
        }
    }

    action def ListJsonDocuments {
        in relativeDirectoryPath : JsonRelativePath = ".";
        out result : JsonDocumentList;
        doc /* Recursively list JSON document metadata below a relative directory. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "StorageDirectoryNotFound",
                "StoragePermissionDenied", "StorageReadFailed");
            obligation = "Results shall contain only normalized paths within the configured root.";
        }
    }

    part def JsonFileStorage {
        doc /* Own a durable namespace of JSON documents beneath one authoritative filesystem root. */
        @SpecIdentity {
            id = "component.storage.json_file";
            lifecycleStatus = SpecLifecycle::accepted;
            owner = "humans";
        }
        @DependencyPolicy {
            allowedComponentIds = ();
            forbiddenComponentIds = ("component.storage.sql", "component.rtg.graph",
                "component.rtg.schema", "component.rtg.controller");
        }

        ref item storageRoot : JsonStorageRoot {
            @StateAuthority {
                authority = StateAuthorityKind::canonicalOwner;
                lifetime = StateLifetime::independent;
                persistence = StatePersistence::durable;
            }
        }

        perform action write[0..*] : WriteJsonDocument;
        perform action read[0..*] : ReadJsonDocument;
        perform action delete[0..*] : DeleteJsonDocument;
        perform action list[0..*] : ListJsonDocuments;

        dependency writeStorage from write to storageRoot {
            @StateAccess { kind = StateAccessKind::write; effect = "replace exactly one normalized JSON document atomically"; }
        }
        dependency readStorage from read to storageRoot {
            @StateAccess { kind = StateAccessKind::read; effect = "return one parsed document without changing state"; }
        }
        dependency deleteStorage from delete to storageRoot {
            @StateAccess { kind = StateAccessKind::delete; effect = "remove exactly the addressed document"; }
        }
        dependency listStorage from list to storageRoot {
            @StateAccess { kind = StateAccessKind::read; effect = "return recursive normalized metadata without parsed values and without changing state"; }
        }
    }

    action def OpenJsonFileStorage {
        in rootPath : FileSystemRootPath;
        out part storage : JsonFileStorage;
        doc /* Create or open a handle bound to exactly one filesystem root. */
        @FailureContract {
            errorIds = ("StorageRootInvalid", "StorageRootUnavailable", "StoragePermissionDenied");
            obligation = "The operation shall not silently select another root.";
        }
    }

    requirement writeEffect {
        subject operation : WriteJsonDocument;
        doc /* Success creates or fully replaces the addressed document and leaves every other document unchanged; failure exposes no partial new value. */
        @StableId { id = "contract.storage.json_file.write_effect"; }
    }

    requirement readEffect {
        subject operation : ReadJsonDocument;
        doc /* Success returns the complete parsed value and metadata for the addressed document; success and failure leave storage state unchanged. */
        @StableId { id = "contract.storage.json_file.read_effect"; }
    }

    requirement deleteEffect {
        subject operation : DeleteJsonDocument;
        doc /* Success removes only the addressed document; a rejected delete leaves all documents unchanged. */
        @StableId { id = "contract.storage.json_file.delete_effect"; }
    }

    requirement listEffect {
        subject operation : ListJsonDocuments;
        doc /* Success recursively returns metadata for regular .json documents below the requested directory, never parsed values or files outside the root, and leaves storage state unchanged. */
        @StableId { id = "contract.storage.json_file.list_effect"; }
    }

    requirement rootContainment {
        subject storage : JsonFileStorage;
        doc /* No operation shall read, write, list, or delete outside the configured root. */
        @StableId { id = "invariant.storage.json_file.root_containment"; }
    }

    requirement jsonOnlyDocuments {
        subject storage : JsonFileStorage;
        doc /* Document operations are limited to regular files with normalized .json paths. */
        @StableId { id = "invariant.storage.json_file.json_only_documents"; }
    }

    requirement validJsonAtRest {
        subject storage : JsonFileStorage;
        doc /* Every successfully written document contains syntactically valid JSON. */
        @StableId { id = "invariant.storage.json_file.valid_json_at_rest"; }
    }

    requirement atomicFullDocumentWrites {
        subject storage : JsonFileStorage;
        doc /* Readers observe the previous complete value, no value, or the complete new value. */
        @StableId { id = "invariant.storage.json_file.atomic_full_document_writes"; }
    }

    requirement callerSchemaNeutrality {
        subject storage : JsonFileStorage;
        doc /* Storage preserves caller JSON values without application-schema enforcement. */
        @StableId { id = "invariant.storage.json_file.caller_schema_neutrality"; }
    }

    requirement noImplicitRootChange {
        subject storage : JsonFileStorage;
        doc /* A handle bound to one root never redirects operations to a different root. */
        @StableId { id = "invariant.storage.json_file.no_implicit_root_change"; }
    }

    requirement pathSemantics {
        subject storage : JsonFileStorage;
        doc /* Every operation normalizes its relative path before access and rejects absolute paths, parent traversal, symlink traversal, non-JSON document targets, and platform aliases that escape the root. */
        @StableId { id = "contract.storage.json_file.path_semantics"; }
    }

    requirement directorySemantics {
        subject storage : JsonFileStorage;
        doc /* Writes create valid parent directories as needed. Deletes may remove empty parents, and later valid writes recreate them without exposing directories as stored resources. */
        @StableId { id = "contract.storage.json_file.directory_semantics"; }
    }

    requirement metadataSemantics {
        subject storage : JsonFileStorage;
        doc /* Write, read, delete, and list metadata reports the normalized relative path, serialized filesystem size, and filesystem modification time without a separate metadata index. */
        @StableId { id = "contract.storage.json_file.metadata_semantics"; }
    }

    verification def JsonFileStorageBoundaryVerification {
        subject storage : JsonFileStorage;
        objective {
            verify rootContainment;
            verify jsonOnlyDocuments;
            verify validJsonAtRest;
            verify atomicFullDocumentWrites;
            verify callerSchemaNeutrality;
            verify noImplicitRootChange;
            verify writeEffect;
            verify readEffect;
            verify deleteEffect;
            verify listEffect;
            verify pathSemantics;
            verify directorySemantics;
            verify metadataSemantics;
        }
        @EvidenceBinding {
            verificationId = "verification.storage.json_file.boundary";
            evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py";
            implementationScope = "LocalJsonFileStorage";
        }
    }
}
