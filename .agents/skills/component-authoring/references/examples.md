# Representative Patterns

## Stateful storage

Model the root/resource authority, document value, public operations, containment and atomicity
invariants, and write/delete effects. Do not model temporary files or filesystem call sequences.

## Declarative query

Model the stable read capability, request/result values, validation obligations, predicate
calculations, matching and ordering rules, diagnostics, and explicit no mutation. Do not model the
iteration or indexing algorithm.

## Controller

Model lower-level component roles, required actions, public intent lanes, cross-component
invariants, observable validate/apply/restore ordering, and ledger/replay outcomes. Do not model
private normalized plans or helper decomposition unless exposed as contracts.
