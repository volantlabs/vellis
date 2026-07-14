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
        attribute 'metadata' : JsonDocumentMetadata;
    }

    attribute def JsonDocumentList {
        attribute documents[0..*] : JsonDocumentMetadata;
    }

    attribute def StorageRootInvalid { attribute 'message' : String; }
    attribute def StorageRootUnavailable { attribute 'message' : String; }
    attribute def StoragePermissionDenied { attribute 'message' : String; }
    attribute def StoragePathInvalid { attribute 'message' : String; }
    attribute def JsonDocumentNotFound { attribute 'message' : String; }
    attribute def JsonDocumentInvalid { attribute 'message' : String; }
    attribute def JsonValueNotSerializable { attribute 'message' : String; }
    attribute def StorageWriteFailed { attribute 'message' : String; }
    attribute def StorageReadFailed { attribute 'message' : String; }
    attribute def StorageDeleteFailed { attribute 'message' : String; }
    attribute def StorageDirectoryNotFound { attribute 'message' : String; }

    item def JsonStorageRoot {
        attribute rootPath : FileSystemRootPath;
        attribute documents[0..*] : JsonDocument;
        doc /* Durable JSON documents addressable below one configured root. */
    }

    action def WriteJsonDocument {
        in relativePath : JsonRelativePath;
        in jsonValue : JsonValue;
        out 'metadata' : JsonDocumentMetadata;
        doc /* Create or fully replace one JSON document atomically within the configured root. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "JsonValueNotSerializable",
                "StoragePermissionDenied", "StorageWriteFailed");
        }
    }

    action def ReadJsonDocument {
        in relativePath : JsonRelativePath;
        out document : JsonDocument;
        doc /* Read and parse one regular JSON document within the configured root. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "JsonDocumentNotFound", "JsonDocumentInvalid",
                "StoragePermissionDenied", "StorageReadFailed");
        }
    }

    action def DeleteJsonDocument {
        in relativePath : JsonRelativePath;
        out 'metadata' : JsonDocumentMetadata;
        doc /* Delete one JSON document and optionally remove empty parent directories. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "JsonDocumentNotFound",
                "StoragePermissionDenied", "StorageDeleteFailed");
        }
    }

    action def ListJsonDocuments {
        in relativeDirectoryPath : JsonRelativePath default = ".";
        out result : JsonDocumentList;
        doc /* Recursively list JSON document metadata below a relative directory. */
        @FailureContract {
            errorIds = ("StoragePathInvalid", "StorageDirectoryNotFound",
                "StoragePermissionDenied", "StorageReadFailed");
        }
    }

    part def <'component.storage.json_file'> JsonFileStorage {
        doc /* Own a durable namespace of JSON documents beneath one authoritative filesystem root. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

        ref item storageRoot : JsonStorageRoot {
            doc /* Independently durable canonical document state governed through this component. */
        }

        perform action write[0..*] : WriteJsonDocument;
        perform action read[0..*] : ReadJsonDocument;
        perform action delete[0..*] : DeleteJsonDocument;
        perform action list[0..*] : ListJsonDocuments;

        dependency writeStorage from write to storageRoot {
            @StateAccess { kind = StateAccessKind::write; }
            doc /* replace exactly one normalized JSON document atomically. */
        }
        dependency readStorage from read to storageRoot {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* return one parsed document without changing state. */
        }
        dependency deleteStorage from delete to storageRoot {
            @StateAccess { kind = StateAccessKind::delete; }
            doc /* remove exactly the addressed document. */
        }
        dependency listStorage from list to storageRoot {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* return recursive normalized metadata without parsed values and without changing state. */
        }
    }

    action def OpenJsonFileStorage {
        in rootPath : FileSystemRootPath;
        out part storage : JsonFileStorage;
        doc /* Create or open a handle bound to exactly one filesystem root. */
        @FailureContract {
            errorIds = ("StorageRootInvalid", "StorageRootUnavailable", "StoragePermissionDenied");
        }
    }


    requirement <'contract.storage.json_file.write_effect'> writeEffect {
        subject operation : WriteJsonDocument;
        require constraint {
            doc /* Success creates or fully replaces the addressed document and leaves every other document unchanged; failure exposes no partial new value. */
        }
    }

    requirement <'contract.storage.json_file.read_effect'> readEffect {
        subject operation : ReadJsonDocument;
        require constraint {
            doc /* Success returns the complete parsed value and metadata for the addressed document; success and failure leave storage state unchanged. */
        }
    }

    requirement <'contract.storage.json_file.delete_effect'> deleteEffect {
        subject operation : DeleteJsonDocument;
        require constraint {
            doc /* Success removes only the addressed document; a rejected delete leaves all documents unchanged. */
        }
    }

    requirement <'contract.storage.json_file.list_effect'> listEffect {
        subject operation : ListJsonDocuments;
        require constraint {
            doc /* Success recursively returns metadata for regular .json documents below the requested directory in ascending normalized relative-path order, never parsed values or files outside the root, and leaves storage state unchanged. */
        }
    }

    requirement <'invariant.storage.json_file.root_containment'> rootContainment {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* No operation shall read, write, list, or delete outside the configured root. */
        }
    }

    requirement <'invariant.storage.json_file.json_only_documents'> jsonOnlyDocuments {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Document operations are limited to regular files with normalized .json paths. */
        }
    }

    requirement <'invariant.storage.json_file.valid_json_at_rest'> validJsonAtRest {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Every successfully written document contains syntactically valid JSON. */
        }
    }

    requirement <'invariant.storage.json_file.atomic_full_document_writes'> atomicFullDocumentWrites {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Readers observe the previous complete value, no value, or the complete new value. */
        }
    }

    requirement <'invariant.storage.json_file.caller_schema_neutrality'> callerSchemaNeutrality {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Storage preserves caller JSON values without application-schema enforcement. */
        }
    }

    requirement <'invariant.storage.json_file.no_implicit_root_change'> noImplicitRootChange {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* A handle bound to one root never redirects operations to a different root. */
        }
    }

    requirement <'contract.storage.json_file.path_semantics'> pathSemantics {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Every operation normalizes its relative path before access and rejects absolute paths, parent traversal, symlink traversal, non-JSON document targets, and platform aliases that escape the root. */
        }
    }

    requirement <'contract.storage.json_file.directory_semantics'> directorySemantics {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Writes create valid parent directories as needed. Deletes may remove empty parents, and later valid writes recreate them without exposing directories as stored resources. */
        }
    }

    requirement <'contract.storage.json_file.metadata_semantics'> metadataSemantics {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* Write, read, delete, and list metadata reports the normalized relative path, serialized filesystem size, and filesystem modification time without a separate metadata index. */
        }
    }

    requirement <'contract.storage.json_file.intentional_boundary'> intentionalBoundary {
        subject storage : JsonFileStorage;
        require constraint {
            doc /* The component is local filesystem JSON-document storage only. It exposes no directories, non-JSON formats, partial updates, query/index/search, schema policy, separate metadata index, remote storage, encryption, authorization, backup, replication, cross-process writer coordination, or filesystem watching. */
        }
    }

    requirement <'contract.storage.json_file.write_json_document.failures'> writeJsonDocumentFailureSemantics {
        subject operation : WriteJsonDocument;
        require constraint {
            doc /* A failed write shall not expose a partial target document. */
        }
    }

    requirement <'contract.storage.json_file.read_json_document.failures'> readJsonDocumentFailureSemantics {
        subject operation : ReadJsonDocument;
        require constraint {
            doc /* Failures shall identify invalid paths, missing documents, invalid JSON, or IO failure. */
        }
    }

    requirement <'contract.storage.json_file.delete_json_document.failures'> deleteJsonDocumentFailureSemantics {
        subject operation : DeleteJsonDocument;
        require constraint {
            doc /* A later valid write shall recreate any removed parent directories. */
        }
    }

    requirement <'contract.storage.json_file.list_json_documents.failures'> listJsonDocumentsFailureSemantics {
        subject operation : ListJsonDocuments;
        require constraint {
            doc /* Results shall contain only normalized paths within the configured root. */
        }
    }

    requirement <'contract.storage.json_file.open_json_file_storage.failures'> openJsonFileStorageFailureSemantics {
        subject operation : OpenJsonFileStorage;
        require constraint {
            doc /* The operation shall not silently select another root. */
        }
    }

    part contractContext {
        part storage : JsonFileStorage;
        satisfy writeEffect by storage.write;
        satisfy readEffect by storage.read;
        satisfy deleteEffect by storage.delete;
        satisfy listEffect by storage.list;
        satisfy rootContainment by storage;
        satisfy jsonOnlyDocuments by storage;
        satisfy validJsonAtRest by storage;
        satisfy atomicFullDocumentWrites by storage;
        satisfy callerSchemaNeutrality by storage;
        satisfy noImplicitRootChange by storage;
        satisfy pathSemantics by storage;
        satisfy directorySemantics by storage;
        satisfy metadataSemantics by storage;
        satisfy intentionalBoundary by storage;

        satisfy writeJsonDocumentFailureSemantics by storage.write;
        satisfy readJsonDocumentFailureSemantics by storage.read;
        satisfy deleteJsonDocumentFailureSemantics by storage.delete;
        satisfy listJsonDocumentsFailureSemantics by storage.list;
        action openJsonFileStorageSubject : OpenJsonFileStorage;
        satisfy openJsonFileStorageFailureSemantics by openJsonFileStorageSubject;
    }

    verification def WriteJsonDocumentContractVerification {
        subject operation : WriteJsonDocument;
        objective {
            verify writeEffect;

            verify writeJsonDocumentFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py#WriteJsonDocumentContractVerification";
            implementationScope = "LocalJsonFileStorage";
        }
    }

    verification def ReadJsonDocumentContractVerification {
        subject operation : ReadJsonDocument;
        objective {
            verify readEffect;

            verify readJsonDocumentFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py#ReadJsonDocumentContractVerification";
            implementationScope = "LocalJsonFileStorage";
        }
    }

    verification def DeleteJsonDocumentContractVerification {
        subject operation : DeleteJsonDocument;
        objective {
            verify deleteEffect;

            verify deleteJsonDocumentFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py#DeleteJsonDocumentContractVerification";
            implementationScope = "LocalJsonFileStorage";
        }
    }

    verification def ListJsonDocumentsContractVerification {
        subject operation : ListJsonDocuments;
        objective {
            verify listEffect;

            verify listJsonDocumentsFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py#ListJsonDocumentsContractVerification";
            implementationScope = "LocalJsonFileStorage";
        }
    }
    verification def OpenJsonFileStorageContractVerification {
        subject operation : OpenJsonFileStorage;
        objective { verify openJsonFileStorageFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py#OpenJsonFileStorageContractVerification"; implementationScope = "LocalJsonFileStorage"; }
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
verify pathSemantics;
            verify directorySemantics;
            verify metadataSemantics;
            verify intentionalBoundary;
        }
        @EvidenceBinding {
                        evidenceId = "components/storage/json_file/tests/test_storage_json_file_contract.py#JsonFileStorageBoundaryVerification";
            implementationScope = "LocalJsonFileStorage";
        }
    }
}
