library package BibliotekStorageSql {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    attribute def SqlScalar {
        doc /* One SQL parameter value: null, Boolean, number, or string. Query results use only these JSON-compatible scalar kinds. */
    }
    attribute def SqlParameters {
        attribute positional[0..*] : SqlScalar;
        attribute named : JsonObject;
        doc /* Exactly one positional or named parameter representation is used for an invocation. Empty positional parameters are the default. */
    }
    attribute def SqlOperation {
        attribute statement : String;
        attribute parameters : SqlParameters;
        attribute returnsRows : Boolean = false;
        doc /* One execute or query operation in a transaction; returnsRows selects its result kind. */
    }
    attribute def SqlRow { attribute values : JsonObject; }
    attribute def SqlOperationResult { doc /* One execution or query result in transaction request order. */ }
    attribute def SqlExecutionResult :> SqlOperationResult {
        attribute affectedRowCount : Integer;
        attribute lastInsertedRowId[0..1] : Integer;
    }
    attribute def SqlQueryResult :> SqlOperationResult { attribute rows[0..*] : SqlRow; }
    attribute def SqlTransactionResult { attribute results[0..*] : SqlOperationResult; }

    attribute def SqlStoragePathInvalid { attribute message : String; }
    attribute def SqlStorageUnavailable { attribute message : String; }
    attribute def SqlStoragePermissionDenied { attribute message : String; }
    attribute def SqlStatementInvalid { attribute message : String; }
    attribute def SqlParameterInvalid { attribute message : String; }
    attribute def SqlExecutionFailed { attribute message : String; }
    attribute def SqlTransactionFailed { attribute message : String; }

    item def SqlDatabase {
        attribute databasePath : FileSystemFilePath;
        doc /* One independently durable SQLite database file and the serialized connection lifecycle of an opened handle. Tables and rows remain caller-defined. */
    }

    action def ExecuteSql {
        in statement : String;
        in parameters : SqlParameters;
        out result : SqlExecutionResult;
        doc /* Execute one data-definition or data-manipulation statement, return affected-row metadata, and never return result rows. */
        @FailureContract {
            errorIds = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlExecutionFailed",
                "SqlStoragePermissionDenied");
            obligation = "A rejected or failed statement is rolled back and the opened handle remains usable.";
        }
    }
    action def QuerySql {
        in statement : String;
        in parameters : SqlParameters;
        out result : SqlQueryResult;
        doc /* Execute one row-returning statement and return rows in database result order as column-name keyed JSON-compatible scalar objects. */
        @FailureContract {
            errorIds = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlExecutionFailed",
                "SqlStoragePermissionDenied");
            obligation = "Failure changes no database state and exposes no application-specific row mapping.";
        }
    }
    action def ExecuteSqlTransaction {
        in operations[0..*] : SqlOperation;
        out result : SqlTransactionResult;
        doc /* Execute operations in request order in one SQLite transaction and return corresponding results in that order. */
        @FailureContract {
            errorIds = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlTransactionFailed",
                "SqlStoragePermissionDenied");
            obligation = "Every operation commits or every operation rolls back.";
        }
    }

    part def SqlStorage {
        doc /* Own a small SQLite-backed SQL execution boundary without application table, ledger, or domain semantics. */
        @SpecIdentity { id = "component.storage.sql"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @DependencyPolicy {
            allowedComponentIds = ();
            forbiddenComponentIds = ("component.storage.json_file", "component.rtg.graph",
                "component.rtg.schema", "component.rtg.constraints", "component.rtg.migration",
                "component.rtg.query", "component.rtg.controller");
        }
        ref item database : SqlDatabase {
            @StateAuthority {
                authority = StateAuthorityKind::canonicalOwner;
                lifetime = StateLifetime::independent;
                persistence = StatePersistence::durable;
            }
        }
        perform action execute[0..*] : ExecuteSql;
        perform action query[0..*] : QuerySql;
        perform action transaction[0..*] : ExecuteSqlTransaction;
        dependency executeDatabase from execute to database {
            @StateAccess { kind = StateAccessKind::write; effect = "apply one caller statement under serialized handle access"; }
        }
        dependency queryDatabase from query to database {
            @StateAccess { kind = StateAccessKind::read; effect = "return database-ordered JSON-compatible rows without mutation"; }
        }
        dependency transactionDatabase from transaction to database {
            @StateAccess { kind = StateAccessKind::write; effect = "apply request-ordered operations as one atomic SQLite transaction"; }
        }
    }

    action def OpenSqlStorage {
        in databasePath : FileSystemFilePath;
        out part storage : SqlStorage;
        doc /* Open or create one SQLite database and bind the returned handle permanently to that path. */
        @FailureContract {
            errorIds = ("SqlStoragePathInvalid", "SqlStorageUnavailable",
                "SqlStoragePermissionDenied");
            obligation = "Failure returns no usable handle and never redirects to another database.";
        }
    }

    requirement executeEffect { subject operation : ExecuteSql; doc /* Success applies exactly one statement and reports affected rows and an optional inserted-row identity; callers use query for rows. */ @StableId { id = "contract.storage.sql.execute_effect"; } }
    requirement queryEffect { subject operation : QuerySql; doc /* Success returns deterministic column-name keyed rows in database result order; scalar/null values are JSON-compatible and serialized JSON text remains uninterpreted. */ @StableId { id = "contract.storage.sql.query_effect"; } }
    requirement transactionEffect { subject operation : ExecuteSqlTransaction; doc /* Operations execute and produce results in caller order and either all commit or all roll back. */ @StableId { id = "contract.storage.sql.transaction_effect"; } }
    requirement serializedHandleAccess { subject storage : SqlStorage; doc /* One opened handle serializes use of its SQLite connection so worker-thread callers do not observe connection thread affinity. */ @StableId { id = "contract.storage.sql.serialized_handle_access"; } }
    requirement noImplicitDatabaseChange { subject storage : SqlStorage; doc /* A handle never changes databases implicitly. */ @StableId { id = "invariant.storage.sql.no_implicit_database_change"; } }
    requirement transactionAtomicity { subject storage : SqlStorage; doc /* A transaction commits all operations or none. */ @StableId { id = "invariant.storage.sql.transaction_atomicity"; } }
    requirement genericStorage { subject storage : SqlStorage; doc /* Storage owns no RTG tables, ledger policy, replay, migrations, authorization, ORM mapping, or domain interpretation. */ @StableId { id = "invariant.storage.sql.generic_storage"; } }
    requirement jsonCompatibleRows { subject storage : SqlStorage; doc /* Query result rows contain only JSON-compatible scalar values or null. */ @StableId { id = "invariant.storage.sql.json_compatible_rows"; } }

    verification def SqlStorageBoundaryVerification {
        subject storage : SqlStorage;
        objective {
            verify executeEffect; verify queryEffect; verify transactionEffect;
            verify serializedHandleAccess; verify noImplicitDatabaseChange;
            verify transactionAtomicity; verify genericStorage; verify jsonCompatibleRows;
        }
        @EvidenceBinding {
            verificationId = "verification.storage.sql.boundary";
            evidenceId = "components/storage/sql/tests/test_storage_sql_contract.py";
            implementationScope = "SqliteStorage";
        }
    }
}
