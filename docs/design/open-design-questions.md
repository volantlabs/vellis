# Open model-design questions

These are non-normative design questions retained from the component-spec migration. They do not
modify current SysML contracts. Resolve a question by changing the appropriate model deliberately
and deleting or rewriting the question; do not answer it only in implementation code.

## Validation boundaries

- What concrete reuse, ownership, dependency, or scaling pressure should trigger extraction of the
  schema/object, constraint/network, or migration/cutover tracks from the composite change validator?

## Controller evolution

- Should authorization remain outside the controller, or should a future controller contract accept
  caller context for a separate authorization capability?
- Is there a durable normalized-operation value worth adding alongside full request/response ledger
  records, or should normalization remain private?
- Should a reusable support/diagnostic component enrich query and validation results with live model
  context beyond the generic guidance already owned by those contracts?
- If a future asynchronous runtime owns reusable audit behavior, what real second consumer and stable
  ledger/replay contract would justify extracting the controller's current audit authority?

## Discovery evolution

- Do aliases and search terms belong in curated discovery views or in a separate search component?
- When discovery is implemented, should it gain snapshot import/export and participate in coordinated
  controller snapshots?

## Migration representation

- What future component or contract should own space-efficient delta migrations for field renames or
  other changes that currently require materialized replacement candidates?

## Query evolution

- What fuzzy-matching semantics and threshold controls, if any, should extend the current exact,
  substring, and deterministic-regex predicates?

## SQL storage evolution

- Should a later storage contract remain explicitly SQLite-based or introduce a backend-neutral SQL
  dialect with independently specified compatibility semantics?
- Should query results later admit binary values or richer SQLite type metadata beyond the current
  JSON-compatible scalar contract?
