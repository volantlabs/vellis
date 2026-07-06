---
id: component.storage.sql
type: Component
status: accepted
owner: humans
code:
  roots:
    - components/storage/sql
---

# SQL Storage

## Purpose

Provide a small SQLite-backed SQL execution surface for components that need durable relational storage without owning database connection mechanics directly.

The component is generic storage infrastructure. It does not know about RTG graphs, controller ledgers, migrations, schemas, constraints, audit policy, replay semantics, or application authorization.

## Responsibilities

- Open a storage handle bound to a caller-specified SQLite database path.
- Execute SQL statements with caller-supplied parameters.
- Return query rows as JSON-compatible objects.
- Execute ordered groups of SQL operations in one SQLite transaction.
- Report SQL, connection, transaction, and parameter errors through public storage errors.
- Preserve SQLite transaction semantics for committed and rolled-back operation groups.
- Serialize access to a storage handle's SQLite connection so callers may use one opened handle
  from worker-thread execution models without exposing SQLite connection thread affinity.
- Keep database file creation and connection lifecycle scoped to the configured SQLite database.

## Non-responsibilities

- Does not define application tables or schemas.
- Does not own RTG ledger tables, replay policy, audit rules, or transaction identifiers.
- Does not interpret stored rows as domain events.
- Does not provide ORM behavior, query builders, migrations, schema diffing, or application-level validation.
- Does not provide Postgres, MySQL, remote database, replication, backup, encryption, authorization, or distributed transaction behavior in v1.
- Does not inspect or mutate JSON File Storage documents.

## Provided contracts

### `SqlStorage.open`

Kind:

- function

Inputs:

- `database_path`

Outputs:

- `SqlStorage`

Errors:

- `SqlStoragePathInvalid`
- `SqlStorageUnavailable`
- `SqlStoragePermissionDenied`

Semantics:

- Returns a SQL storage handle bound to one SQLite database file.
- The database file may already exist or may be created when the path is valid.
- The handle must not silently redirect to another database path.

### `SqlStorage.execute`

Kind:

- function

Inputs:

- `statement`
- `parameters`

Outputs:

- `SqlExecutionResult`

Errors:

- `SqlStatementInvalid`
- `SqlParameterInvalid`
- `SqlExecutionFailed`
- `SqlStoragePermissionDenied`

Semantics:

- Executes one SQL statement with caller-supplied parameters.
- Supports data definition and data manipulation statements.
- Does not return result rows; callers use `query` for row-returning statements.
- Returns metadata such as affected row count and last inserted row identifier when available.
- Rolls back failed statement execution while the storage handle owns serialized access to its SQLite connection.

### `SqlStorage.query`

Kind:

- function

Inputs:

- `statement`
- `parameters`

Outputs:

- `SqlQueryResult`

Errors:

- `SqlStatementInvalid`
- `SqlParameterInvalid`
- `SqlExecutionFailed`
- `SqlStoragePermissionDenied`

Semantics:

- Executes one row-returning SQL statement with caller-supplied parameters.
- Returns rows as deterministic JSON-compatible objects keyed by column name.
- Values must be representable as JSON-compatible scalars or `null` in v1.
- Callers that need to store structured JSON payloads may serialize them into text columns; this component does not parse or validate those payloads.
- Does not map rows to application-specific domain objects.

### `SqlStorage.transaction`

Kind:

- function

Inputs:

- `operations`

Outputs:

- `SqlTransactionResult`

Errors:

- `SqlStatementInvalid`
- `SqlParameterInvalid`
- `SqlTransactionFailed`
- `SqlStoragePermissionDenied`

Semantics:

- Executes an ordered group of execute/query operations in one SQLite transaction.
- Commits when every operation succeeds.
- Rolls back when any operation fails.
- Returns operation results in request order.

## Required contracts

May consume:

- Local filesystem APIs for SQLite database files.
- Standard SQLite database APIs.
- Standard JSON-compatible value conventions for returned row values.

Must not consume:

- RTG graph, schema, constraints, migration, controller, validation, query, discovery, or JSON File Storage internals.
- ORM frameworks as required dependencies.
- Remote database services.
- Application-specific authorization, ledger, replay, audit, or schema migration frameworks.

## Related components

- `component.rtg.controller` may use this component to own RTG ledger tables and record controller request, response, and error payloads.
- Controller ledger payloads are stored as caller-serialized JSON text rather than SQL Storage owned document values.

## Owned state

- Configured SQLite database file.
- SQLite connection lifecycle for opened handles.
- Rows and tables created or modified through this component by callers, without interpreting their application meaning.

## Invariants

### `invariant.storage.sql.no_implicit_database_change`

A storage handle bound to one SQLite database path must not redirect operations to another path.

### `invariant.storage.sql.transaction_atomicity`

Operations submitted through one `transaction` call commit together or roll back together according to SQLite transaction semantics.

### `invariant.storage.sql.generic_storage`

The component does not interpret SQL rows as RTG ledger, graph, schema, constraint, migration, query, or discovery records.

### `invariant.storage.sql.json_compatible_rows`

Query result rows are returned as JSON-compatible objects in v1.

## Verification

Required checks:

- Contract tests for opening a SQLite database path.
- Contract tests for execute, query, and transaction behavior.
- Rollback tests proving failed transactions do not partially commit.
- Rollback tests proving failed execute operations leave the handle usable from worker-thread execution contexts.
- Error mapping tests for invalid statements, invalid parameters, unavailable paths, and permission failures where practical.
- No-forbidden-dependency checks proving the component does not depend on RTG components or ORM frameworks.

Required evidence:

- A caller can create tables, insert rows, query rows, and update rows through public contracts.
- A caller can run a transaction with multiple operations and observe rollback after failure.
- Returned query rows are JSON-compatible objects.
- One opened handle can be used from worker-thread execution contexts while preserving
  serialized operation semantics.

## Change rules

Agents may:

- Implement or refactor SQLite connection handling inside `components/storage/sql`.
- Add boundary tests for generic SQL behavior.
- Improve error mapping while preserving public error categories.

Agents may not:

- Add RTG ledger table ownership to this component.
- Add ORM-specific public APIs without explicit approval.
- Add non-SQLite backends to v1 behavior without explicit approval.
- Add application authorization, audit, replay, backup, replication, or distributed transaction responsibilities without explicit approval.

## Open questions

- Should future versions add a backend-neutral SQL dialect contract, or keep this component explicitly SQLite-backed?
- Should query results support binary values or richer SQLite type metadata after v1?
