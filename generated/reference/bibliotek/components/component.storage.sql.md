# component.storage.sql

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `SqlStorage`
- Lifecycle: `accepted`
- Purpose: Own a small SQLite-backed SQL execution boundary without application table, ledger, or domain semantics.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `execute` | `ExecuteSql` | in `statement: String`; in `parameters: SqlParameters[0..1]`; out `result: SqlExecutionResult` | `SqlStatementInvalid`, `SqlParameterInvalid`, `SqlExecutionFailed`, `SqlStoragePermissionDenied` | Execute one data-definition or data-manipulation statement, return affected-row metadata, and never return result rows. |
| `query` | `QuerySql` | in `statement: String`; in `parameters: SqlParameters[0..1]`; out `result: SqlQueryResult` | `SqlStatementInvalid`, `SqlParameterInvalid`, `SqlExecutionFailed`, `SqlStoragePermissionDenied` | Execute one row-returning statement and return rows in database result order as column-name keyed JSON-compatible scalar objects. |
| `transaction` | `ExecuteSqlTransaction` | in `operations: SqlOperation[0..*]`; out `result: SqlTransactionResult` | `SqlStatementInvalid`, `SqlParameterInvalid`, `SqlTransactionFailed`, `SqlStoragePermissionDenied` | Execute operations whose parameters satisfy SqlParametersWellFormed in request order in one SQLite transaction and return corresponding results in that order. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenSqlStorage` | in `databasePath: FileSystemFilePath`; out `storage: SqlStorage` | `SqlStoragePathInvalid`, `SqlStorageUnavailable`, `SqlStoragePermissionDenied` | Open or create one SQLite database and bind the returned handle permanently to that path. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `database` | `SqlDatabase` | `referenced` | Independently durable database state governed through this component. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `execute` | `database` | `write` | apply one caller statement under serialized handle access. |
| `query` | `database` | `read` | return database-ordered JSON-compatible rows without mutation. |
| `transaction` | `database` | `write` | apply request-ordered operations as one atomic SQLite transaction. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.storage.sql.execute_effect` | `ExecuteSql` | `storage.execute` | Omitted parameters mean an empty positional parameter set. Supplied parameters satisfy SqlParametersWellFormed. Success applies exactly one statement and reports affected rows and an optional inserted-row identity; callers use query for rows. |
| `contract.storage.sql.query_effect` | `QuerySql` | `storage.query` | Omitted parameters mean an empty positional parameter set. Supplied parameters satisfy SqlParametersWellFormed. Success returns deterministic column-name keyed rows in database result order; scalar/null values are JSON-compatible and serialized JSON text remains uninterpreted. |
| `contract.storage.sql.transaction_effect` | `ExecuteSqlTransaction` | `storage.transaction` | Operations execute and produce results in caller order and either all commit or all roll back. |
| `contract.storage.sql.serialized_handle_access` | `SqlStorage` | `storage` | One opened handle serializes use of its SQLite connection so worker-thread callers do not observe connection thread affinity. |
| `invariant.storage.sql.no_implicit_database_change` | `SqlStorage` | `storage` | A handle never changes databases implicitly. |
| `invariant.storage.sql.transaction_atomicity` | `SqlStorage` | `storage` | A transaction commits all operations or none. |
| `invariant.storage.sql.generic_storage` | `SqlStorage` | `storage` | Storage owns no RTG tables, ledger policy, replay, migrations, authorization, ORM mapping, or domain interpretation. |
| `invariant.storage.sql.json_compatible_rows` | `SqlStorage` | `storage` | Query result rows contain only JSON-compatible scalar values or null. |
| `contract.storage.sql.intentional_boundary` | `SqlStorage` | `storage` | The component is generic SQLite execution infrastructure. It defines no application tables, domain events, RTG ledger policy, ORM or query-builder surface, schema migration, authorization, backup, replication, remote database, alternate SQL backend, or distributed transaction behavior. |
| `contract.storage.sql.execute_sql.failures` | `ExecuteSql` | `storage.execute` | A rejected or failed statement is rolled back and the opened handle remains usable. |
| `contract.storage.sql.query_sql.failures` | `QuerySql` | `storage.query` | Failure changes no database state and exposes no application-specific row mapping. |
| `contract.storage.sql.execute_sql_transaction.failures` | `ExecuteSqlTransaction` | `storage.transaction` | Every operation commits or every operation rolls back. |
| `contract.storage.sql.open_sql_storage.failures` | `OpenSqlStorage` | `openSqlStorageSubject` | Failure returns no usable handle and never redirects to another database. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `SqlNamedScalar` | `attribute` | `name: String`, `value: JsonScalar` | One uniquely named SQL parameter or result-column value. |
| `SqlParameters` | `attribute` | `kind: SqlParameterKind` = `SqlParameterKind::positional`, `positional[0..*]: JsonScalar`, `named[0..*]: SqlNamedScalar` | Exactly one positional or named parameter representation is used for an invocation. Named entries have unique names. Empty positional parameters are the default. |
| `SqlOperation` | `attribute` | `statement: String`, `parameters[0..1]: SqlParameters`, `returnsRows: Boolean` = `false` | One execute or query operation in a transaction; omitted parameters mean an empty positional parameter set and returnsRows selects the result kind. |
| `SqlRow` | `attribute` | `columns[0..*]: SqlNamedScalar` | One column-name keyed row. Column names are unique and every value is a JSON-compatible SQL scalar or null. |
| `SqlOperationResult` | `attribute` | — | One execution or query result in transaction request order. |
| `SqlExecutionResult` | `attribute` | `affectedRowCount: Integer`, `lastInsertedRowId[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `SqlQueryResult` | `attribute` | `rows[0..*]: SqlRow` | Defined by its typed fields and action requirements. |
| `SqlTransactionResult` | `attribute` | `results[0..*]: SqlOperationResult` | Defined by its typed fields and action requirements. |
| `SqlStoragePathInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlStorageUnavailable` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlStoragePermissionDenied` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlStatementInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlParameterInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlExecutionFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlTransactionFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SqlDatabase` | `item` | `databasePath: FileSystemFilePath` | One independently durable SQLite database file and the serialized connection lifecycle of an opened handle. Tables and rows remain caller-defined. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `SqlParameterKind` | `positional`, `named` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `ExecuteSqlContractVerification` | `ExecuteSql` | `executeEffect`, `executeSqlFailureSemantics` | `components/storage/sql/tests/test_storage_sql_contract.py#ExecuteSqlContractVerification` |
| `QuerySqlContractVerification` | `QuerySql` | `queryEffect`, `querySqlFailureSemantics` | `components/storage/sql/tests/test_storage_sql_contract.py#QuerySqlContractVerification` |
| `ExecuteSqlTransactionContractVerification` | `ExecuteSqlTransaction` | `transactionEffect`, `executeSqlTransactionFailureSemantics` | `components/storage/sql/tests/test_storage_sql_contract.py#ExecuteSqlTransactionContractVerification` |
| `OpenSqlStorageContractVerification` | `OpenSqlStorage` | `openSqlStorageFailureSemantics` | `components/storage/sql/tests/test_storage_sql_contract.py#OpenSqlStorageContractVerification` |
| `SqlStorageBoundaryVerification` | `SqlStorage` | `serializedHandleAccess`, `noImplicitDatabaseChange`, `transactionAtomicity`, `genericStorage`, `jsonCompatibleRows`, `intentionalBoundary` | `components/storage/sql/tests/test_storage_sql_contract.py#SqlStorageBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
