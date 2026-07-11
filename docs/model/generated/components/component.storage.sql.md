# component.storage.sql

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `SqlStorage`
- Lifecycle: `accepted`
- Purpose: Own a small SQLite-backed SQL execution boundary without application table, ledger, or domain semantics.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `execute` | `ExecuteSql` | in `statement: String`; in `parameters: SqlParameters`; out `result: SqlExecutionResult` | `SqlStatementInvalid`, `SqlParameterInvalid`, `SqlExecutionFailed`, `SqlStoragePermissionDenied` | Execute one data-definition or data-manipulation statement, return affected-row metadata, and never return result rows. |
| `query` | `QuerySql` | in `statement: String`; in `parameters: SqlParameters`; out `result: SqlQueryResult` | `SqlStatementInvalid`, `SqlParameterInvalid`, `SqlExecutionFailed`, `SqlStoragePermissionDenied` | Execute one row-returning statement and return rows in database result order as column-name keyed JSON-compatible scalar objects. |
| `transaction` | `ExecuteSqlTransaction` | in `operations: SqlOperation[0..*]`; out `result: SqlTransactionResult` | `SqlStatementInvalid`, `SqlParameterInvalid`, `SqlTransactionFailed`, `SqlStoragePermissionDenied` | Execute operations in request order in one SQLite transaction and return corresponding results in that order. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenSqlStorage` | in `databasePath: FileSystemFilePath`; out `storage: SqlStorage` | `SqlStoragePathInvalid`, `SqlStorageUnavailable`, `SqlStoragePermissionDenied` | Open or create one SQLite database and bind the returned handle permanently to that path. |

## Required capabilities

| Feature | Kind | Required contract | Cardinality |
|---|---|---|---|
| — | — | — | No required capabilities. |

## Owned state

| State feature | Type | Authority | Lifetime | Persistence |
|---|---|---|---|---|
| `database` | `SqlDatabase` | `canonicalOwner` | `independent` | `durable` |

## Action and state effects

| Action | State / capability | Access | Contract-significant effect |
|---|---|---|---|
| `execute` | `database` | `write` | apply one caller statement under serialized handle access |
| `query` | `database` | `read` | return database-ordered JSON-compatible rows without mutation |
| `transaction` | `database` | `write` | apply request-ordered operations as one atomic SQLite transaction |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.storage.sql.execute_effect` | Success applies exactly one statement and reports affected rows and an optional inserted-row identity; callers use query for rows. |
| `contract.storage.sql.query_effect` | Success returns deterministic column-name keyed rows in database result order; scalar/null values are JSON-compatible and serialized JSON text remains uninterpreted. |
| `contract.storage.sql.transaction_effect` | Operations execute and produce results in caller order and either all commit or all roll back. |
| `contract.storage.sql.serialized_handle_access` | One opened handle serializes use of its SQLite connection so worker-thread callers do not observe connection thread affinity. |
| `invariant.storage.sql.no_implicit_database_change` | A handle never changes databases implicitly. |
| `invariant.storage.sql.transaction_atomicity` | A transaction commits all operations or none. |
| `invariant.storage.sql.generic_storage` | Storage owns no RTG tables, ledger policy, replay, migrations, authorization, ORM mapping, or domain interpretation. |
| `invariant.storage.sql.json_compatible_rows` | Query result rows contain only JSON-compatible scalar values or null. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `SqlScalar` | `attribute` | — | One SQL parameter value: null, Boolean, number, or string. Query results use only these JSON-compatible scalar kinds. |
| `SqlParameters` | `attribute` | `positional[0..*]: SqlScalar`, `named: JsonObject` | Exactly one positional or named parameter representation is used for an invocation. Empty positional parameters are the default. |
| `SqlOperation` | `attribute` | `statement: String`, `parameters: SqlParameters`, `returnsRows: Boolean` = `false` | One execute or query operation in a transaction; returnsRows selects its result kind. |
| `SqlRow` | `attribute` | `values: JsonObject` | Defined by its typed fields and action requirements. |
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

| Enumeration | Model and external values |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `SqlStorageBoundaryVerification` | `executeEffect`, `queryEffect`, `transactionEffect`, `serializedHandleAccess`, `noImplicitDatabaseChange`, `transactionAtomicity`, `genericStorage`, `jsonCompatibleRows` | `components/storage/sql/tests/test_storage_sql_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
