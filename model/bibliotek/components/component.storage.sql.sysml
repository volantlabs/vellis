library package BibliotekStorageSql {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import SequenceFunctions::*;

    enum def SqlParameterKind {
        enum positional;
        enum named;
    }
    attribute def SqlNamedScalar {
        attribute name : String;
        attribute value : JsonScalar;
        doc /* One uniquely named SQL parameter or result-column value. */
    }
    attribute def SqlParameters {
        attribute kind : SqlParameterKind default = SqlParameterKind::positional;
        attribute positional[0..*] : JsonScalar;
        attribute named[0..*] : SqlNamedScalar;
        doc /* Exactly one positional or named parameter representation is used for an invocation. Named entries have unique names. Empty positional parameters are the default. */
    }
    constraint def SqlParametersWellFormed {
        in parameters : SqlParameters;
        (parameters.kind == SqlParameterKind::positional and parameters.named->isEmpty()) or
        (parameters.kind == SqlParameterKind::named and parameters.positional->isEmpty())
    }
    attribute def SqlOperation {
        attribute statement : String;
        attribute parameters[0..1] : SqlParameters;
        attribute returnsRows : Boolean default = false;
        doc /* One execute or query operation in a transaction; omitted parameters mean an empty positional parameter set and returnsRows selects the result kind. */
    }
    attribute def SqlRow {
        attribute columns[0..*] : SqlNamedScalar;
        doc /* One column-name keyed row. Column names are unique and every value is a JSON-compatible SQL scalar or null. */
    }
    abstract attribute def SqlOperationResult { doc /* One execution or query result in transaction request order. */ }
    attribute def SqlExecutionResult :> SqlOperationResult {
        attribute affectedRowCount : Integer;
        attribute lastInsertedRowId[0..1] : Integer;
    }
    attribute def SqlQueryResult :> SqlOperationResult { attribute rows[0..*] : SqlRow; }
    attribute def SqlTransactionResult { attribute results[0..*] : SqlOperationResult; }

    attribute def SqlStoragePathInvalid { attribute 'message' : String; }
    attribute def SqlStorageUnavailable { attribute 'message' : String; }
    attribute def SqlStoragePermissionDenied { attribute 'message' : String; }
    attribute def SqlStatementInvalid { attribute 'message' : String; }
    attribute def SqlParameterInvalid { attribute 'message' : String; }
    attribute def SqlExecutionFailed { attribute 'message' : String; }
    attribute def SqlTransactionFailed { attribute 'message' : String; }

    item def SqlDatabase {
        attribute databasePath : FileSystemFilePath;
        doc /* One independently durable SQLite database file and the serialized connection lifecycle of an opened handle. Tables and rows remain caller-defined. */
    }

    action def ExecuteSql {
        in statement : String;
        in parameters[0..1] : SqlParameters;
        out result : SqlExecutionResult;
        doc /* Execute one data-definition or data-manipulation statement, return affected-row metadata, and never return result rows. */
        @FailureContract {
            errorIds = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlExecutionFailed",
                "SqlStoragePermissionDenied");
        }
    }
    action def QuerySql {
        in statement : String;
        in parameters[0..1] : SqlParameters;
        out result : SqlQueryResult;
        doc /* Execute one row-returning statement and return rows in database result order as column-name keyed JSON-compatible scalar objects. */
        @FailureContract {
            errorIds = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlExecutionFailed",
                "SqlStoragePermissionDenied");
        }
    }
    action def ExecuteSqlTransaction {
        in operations[0..*] : SqlOperation;
        out result : SqlTransactionResult;
        doc /* Execute operations whose parameters satisfy SqlParametersWellFormed in request order in one SQLite transaction and return corresponding results in that order. */
        @FailureContract {
            errorIds = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlTransactionFailed",
                "SqlStoragePermissionDenied");
        }
    }

    part def <'component.storage.sql'> SqlStorage {
        doc /* Own a small SQLite-backed SQL execution boundary without application table, ledger, or domain semantics. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        ref item database : SqlDatabase {
            doc /* Independently durable database state governed through this component. */
        }
        perform action execute[0..*] : ExecuteSql;
        perform action query[0..*] : QuerySql;
        perform action transaction[0..*] : ExecuteSqlTransaction;
        dependency executeDatabase from execute to database { @StateAccess { kind = StateAccessKind::write; }
            doc /* apply one caller statement under serialized handle access. */
        }
        dependency queryDatabase from query to database { @StateAccess { kind = StateAccessKind::read; }
            doc /* return database-ordered JSON-compatible rows without mutation. */
        }
        dependency transactionDatabase from transaction to database { @StateAccess { kind = StateAccessKind::write; }
            doc /* apply request-ordered operations as one atomic SQLite transaction. */
        }
    }

    action def OpenSqlStorage {
        in databasePath : FileSystemFilePath;
        out part storage : SqlStorage;
        doc /* Open or create one SQLite database and bind the returned handle permanently to that path. */
        @FailureContract {
            errorIds = ("SqlStoragePathInvalid", "SqlStorageUnavailable",
                "SqlStoragePermissionDenied");
        }
    }


    requirement <'contract.storage.sql.execute_effect'> executeEffect {
        subject operation : ExecuteSql;
        require constraint {
            doc /* Omitted parameters mean an empty positional parameter set. Supplied parameters satisfy SqlParametersWellFormed. Success applies exactly one statement and reports affected rows and an optional inserted-row identity; callers use query for rows. */
        }
    }

    requirement <'contract.storage.sql.query_effect'> queryEffect {
        subject operation : QuerySql;
        require constraint {
            doc /* Omitted parameters mean an empty positional parameter set. Supplied parameters satisfy SqlParametersWellFormed. Success returns deterministic column-name keyed rows in database result order; scalar/null values are JSON-compatible and serialized JSON text remains uninterpreted. */
        }
    }

    requirement <'contract.storage.sql.transaction_effect'> transactionEffect {
        subject operation : ExecuteSqlTransaction;
        require constraint {
            doc /* Operations execute and produce results in caller order and either all commit or all roll back. */
        }
    }

    requirement <'contract.storage.sql.serialized_handle_access'> serializedHandleAccess {
        subject storage : SqlStorage;
        require constraint {
            doc /* One opened handle serializes use of its SQLite connection so worker-thread callers do not observe connection thread affinity. */
        }
    }

    requirement <'invariant.storage.sql.no_implicit_database_change'> noImplicitDatabaseChange {
        subject storage : SqlStorage;
        require constraint {
            doc /* A handle never changes databases implicitly. */
        }
    }

    requirement <'invariant.storage.sql.transaction_atomicity'> transactionAtomicity {
        subject storage : SqlStorage;
        require constraint {
            doc /* A transaction commits all operations or none. */
        }
    }

    requirement <'invariant.storage.sql.generic_storage'> genericStorage {
        subject storage : SqlStorage;
        require constraint {
            doc /* Storage owns no RTG tables, ledger policy, replay, migrations, authorization, ORM mapping, or domain interpretation. */
        }
    }

    requirement <'invariant.storage.sql.json_compatible_rows'> jsonCompatibleRows {
        subject storage : SqlStorage;
        require constraint {
            doc /* Query result rows contain only JSON-compatible scalar values or null. */
        }
    }

    requirement <'contract.storage.sql.intentional_boundary'> intentionalBoundary {
        subject storage : SqlStorage;
        require constraint {
            doc /* The component is generic SQLite execution infrastructure. It defines no application tables, domain events, RTG ledger policy, ORM or query-builder surface, schema migration, authorization, backup, replication, remote database, alternate SQL backend, or distributed transaction behavior. */
        }
    }

    requirement <'contract.storage.sql.execute_sql.failures'> executeSqlFailureSemantics {
        subject operation : ExecuteSql;
        require constraint {
            doc /* A rejected or failed statement is rolled back and the opened handle remains usable. */
        }
    }

    requirement <'contract.storage.sql.query_sql.failures'> querySqlFailureSemantics {
        subject operation : QuerySql;
        require constraint {
            doc /* Failure changes no database state and exposes no application-specific row mapping. */
        }
    }

    requirement <'contract.storage.sql.execute_sql_transaction.failures'> executeSqlTransactionFailureSemantics {
        subject operation : ExecuteSqlTransaction;
        require constraint {
            doc /* Every operation commits or every operation rolls back. */
        }
    }

    requirement <'contract.storage.sql.open_sql_storage.failures'> openSqlStorageFailureSemantics {
        subject operation : OpenSqlStorage;
        require constraint {
            doc /* Failure returns no usable handle and never redirects to another database. */
        }
    }

    part contractContext {
        part storage : SqlStorage;
        satisfy executeEffect by storage.execute;
        satisfy queryEffect by storage.query;
        satisfy transactionEffect by storage.transaction;
        satisfy serializedHandleAccess by storage;
        satisfy noImplicitDatabaseChange by storage;
        satisfy transactionAtomicity by storage;
        satisfy genericStorage by storage;
        satisfy jsonCompatibleRows by storage;
        satisfy intentionalBoundary by storage;

        satisfy executeSqlFailureSemantics by storage.execute;
        satisfy querySqlFailureSemantics by storage.query;
        satisfy executeSqlTransactionFailureSemantics by storage.transaction;
        action openSqlStorageSubject : OpenSqlStorage;
        satisfy openSqlStorageFailureSemantics by openSqlStorageSubject;
    }

    verification def ExecuteSqlContractVerification {
        subject operation : ExecuteSql;
        objective {
            verify executeEffect;

            verify executeSqlFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/sql/tests/test_storage_sql_contract.py#ExecuteSqlContractVerification";
            implementationScope = "SqliteStorage";
        }
    }

    verification def QuerySqlContractVerification {
        subject operation : QuerySql;
        objective {
            verify queryEffect;

            verify querySqlFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/sql/tests/test_storage_sql_contract.py#QuerySqlContractVerification";
            implementationScope = "SqliteStorage";
        }
    }

    verification def ExecuteSqlTransactionContractVerification {
        subject operation : ExecuteSqlTransaction;
        objective {
            verify transactionEffect;

            verify executeSqlTransactionFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/storage/sql/tests/test_storage_sql_contract.py#ExecuteSqlTransactionContractVerification";
            implementationScope = "SqliteStorage";
        }
    }
    verification def OpenSqlStorageContractVerification {
        subject operation : OpenSqlStorage;
        objective { verify openSqlStorageFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/storage/sql/tests/test_storage_sql_contract.py#OpenSqlStorageContractVerification"; implementationScope = "SqliteStorage"; }
    }



    verification def SqlStorageBoundaryVerification {
        subject storage : SqlStorage;
        objective {
verify serializedHandleAccess; verify noImplicitDatabaseChange;
            verify transactionAtomicity; verify genericStorage; verify jsonCompatibleRows; verify intentionalBoundary;
        }
        @EvidenceBinding {
                        evidenceId = "components/storage/sql/tests/test_storage_sql_contract.py#SqlStorageBoundaryVerification";
            implementationScope = "SqliteStorage";
        }
    }
}
