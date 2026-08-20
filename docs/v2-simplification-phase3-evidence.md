# Vellis v2 simplification — Phase 3 evidence

This is the execution and evidence frame for `W003`, not product authority or a second design.
Accepted meaning remains under `model/`; the approved task plan supplies the selected realization
constraints cited by `system-evolution.yaml`.

## Conformance matrix

| Qualified authority | In-scope obligation | Required non-effect | Nearest plausible wrong implementation | Focused evidence |
|---|---|---|---|---|
| `Definition Summary Request`, `Definition Inspection Request`, `Discover evaluated definitions` | Complete shallow anchor summary and complete request-ordered focused neighborhoods for current, revision, and time | No pagination, partial neighborhood, recursive copy, draft persistence, or duplicate definition resolver | Discovery loads a second definition model or silently omits an incompletely answerable neighborhood | Cold summary/inspect, unknown/duplicate rejection, state-selection, completeness, and resolver-instrumentation tests |
| `Identity Selection`, `Identity Query Payload`, `Unified Query Meaning` | Direct mixed known/missing UUID selection, structural/system fields, and requested-only property/legacy hydration | No preliminary match/get, topology/type requirement, silent missing UUID, or hydration of omitted properties | Known UUIDs are forced through the pattern compiler or complete objects leak unrequested properties | Request-order, missing, mixed-kind, selected/all/omitted property, null/absence, and legacy tests |
| `Pattern Selection`, `Pattern Query Payload`, `Unified Query Meaning` | One connected conjunction whose named nodes/links all bind distinct identities except a true reused-node self-link | No hidden selector, projection language, aggregation, traversal, disconnected product, general OR, or caller ordering | The predecessor projection/aggregation analyzer survives behind new names | Structural rejection, single/path/branch/cycle/parallel/self-link, intersection, binding, and independent-oracle tests |
| `Query Predicate And Search Integrity` | Closed typed predicates, Unicode folded contains/prefix, RE2 substring search, and structured Boolean FTS over names/text properties | No raw FTS syntax, ranking, fuzzy/semantic search, locale normalization, or cross-kind comparison | User text reaches SQL/FTS syntax or text comparison silently changes equality meaning | Predicate matrix, malformed regex/terms, case/diacritic distinctions, historical FTS, and parameterization tests |
| `Bounded Query Safety`, `Locality And Bounded Materialization` | Establish at most `maximumMatches + 1` distinct complete UUID tuples before requested hydration; return unique objects deterministically | No complete graph/definition aggregate, excluded-ledger scan, unrelated hydration, truncation, or retained population temp state | Compiler hydrates first, truncates an over-bound answer, or scans unrelated properties/history | Exact/max-plus-one, hydration instrumentation, query-plan, unrelated-population, restart, and connection-cleanup evidence |

## Selected inherited realization decisions

- Query values remain frozen, slotted, framework-free domain dataclasses in a dedicated domain
  module so the already catalog-sized scalar/graph module does not grow into a mixed concern.
- Validation produces deterministic domain findings before SQL compilation. The compiler consumes
  one flat validated selection; it does not expose an AST, optimizer, planner hierarchy, visitor,
  expression language, or registry.
- Discovery, identity query, and pattern query are explicit operation functions. Each owns one
  connection and one read snapshot. Phase 7 will add activity transaction ownership without
  duplicating query meaning.
- Pattern SQL uses parameterized incremental CTEs, each joining only the prior binding relation and
  one selector. Intermediate steps are materialized to prevent SQLite from recreating a flat join;
  the final complete-binding step is not materialized, so the outer caller bound plus one stops
  complete-tuple evaluation before hydration. An independent small brute-force evaluator shares no
  compiler, SQL, repository, or production predicate helper.
- FTS5 remains the selected `unicode61 remove_diacritics 2` Boolean index. User terms and phrases
  are structured and quoted by Vellis; no raw FTS expression crosses the boundary.
- RE2 compilation uses one process-wide `lru_cache(maxsize=256)` on the pure `(pattern,
  caseSensitive)` compilation function. This is a bounded memoization detail, not a cache
  abstraction, request state, or result authority; correctness does not depend on retention.

## Intended subtraction and touched boundaries

This phase replaces definition discovery and graph query behavior in the final package paths. Once
the successor evidence is complete, delete the predecessor projection/aggregation/query analyzer,
SQLite compiler, query-contract fixtures, and topology-coupled tests whose last behavior is owned by
this phase. Do not retain a compatibility adapter or translate predecessor requests.

Logical relations touched are versioned definitions, graph structure, associations, properties,
search documents, and the FTS virtual relation. Draft relations are read only through a narrow hook;
Phase 4 owns actual overlay persistence and will activate draft-state query evidence.

Public boundaries affected are the operation-layer equivalents of `rtg_type_summary`,
`rtg_type_inspect`, and the identity/pattern forms of `rtg_query`. MCP schemas and transport remain
Phase 7 work.

## Explicit non-goals

- Draft composition or draft persistence.
- Active mutation or canonical revision creation.
- Activity publication, MCP/Pydantic adapters, or CLI behavior.
- Projection, aggregation, ranking, fuzzy search, semantic search, traversal, or pagination.
- Numerical performance promises beyond the selected locality and bound distinctions.

## Evidence log

### Implemented distinction

- `vellis/query_domain.py` supplies frozen, slotted, framework-free request, selector, predicate,
  hydration, payload, and result values. Fixed discriminators cannot be overridden. Raw
  construction validates structural types, canonical UUIDs, kind-compatible hydrated fields,
  deterministic findings, and accepted-versus-rejected payload presence.
- `vellis/definition_repository.py` remains the one definition resolver, now with an optional
  targeted key set. `vellis/discovery_repository.py` first identifies only shallow anchor or
  focused-neighborhood keys and resolves only those definitions. Summary never decodes unrelated
  associated-data/link/property definitions; inspection returns complete request-ordered
  neighborhoods.
- `vellis/query_validation.py` rejects duplicate/unknown/incompatible names, filters, fields,
  properties, endpoints, and exact predicate payloads. It enforces the one fixed item limit,
  connectedness, explicit typing for property work, same-kind operands, RE2 validity, and the
  absence of hidden projection, aggregation, traversal, disconnected products, or general OR.
  Direct-association and link endpoint types must retain at least one definition-compatible local
  alternative; known-UUID filters narrow that compatibility check to their actual selected types.
- `vellis/query_repository.py` emits one flat family of parameterized SQL CTEs. Node and link
  candidates narrow by indexed intervals, kind, type, UUID, and predicates. Connected binding is
  extended one selector at a time through connection-local CTEs rather than a flat join subject to
  SQLite's 64-table ceiling. Intermediate relations are materialized, while the final binding join
  remains under the outer `maximumMatches + 1` limit without SQL ordering. An over-bound result is
  rejected immediately; an accepted complete bounded row set is then sorted deterministically in
  memory before hydration.
  Large type/UUID filters use parameterized `json_each` values rather than variable interpolation or
  an AST. Structural hydration is targeted by selected UUID, property hydration groups identical
  requested name sets, and legacy metadata is read only for selectors that request it.
- `vellis/search_repository.py` registers three connection-local text functions, safely constructs
  FTS expressions from tokenizer-produced terms/phrases, and maintains historical search documents
  without deleting retired index entries. FTS5 uses `unicode61 remove_diacritics 2`; contains/prefix
  use exact code points or Unicode case folding without diacritic removal; query regex is RE2
  substring search.
- `vellis/read_operations.py` owns one read-only connection and snapshot for summary, inspect, and
  query. Current/revision/time are complete. A single explicit draft-overlay hook remains inactive
  until W004 supplies the normalized draft bucket; no second draft resolver or persisted draft
  representation was introduced.

### Focused evidence

- `uv run pytest -q tests/vellis/test_domain_v2.py tests/vellis/test_canonical_encoding_v2.py tests/vellis/test_storage_v2.py tests/vellis/test_query_v2_successor.py`
  passes 94 tests. The 28 Phase 3 tests cover cold summary/inspection, unknown and duplicate keys,
  mixed known/missing identity selection, omitted/selected/all properties, absent versus null,
  optional legacy disclosure, type-plus-UUID intersection, single/path/branch/cycle/parallel/self-
  link patterns, direct associations, selector binding, deterministic rows, object deduplication,
  exact/max-plus-one refusal, a connected pattern above SQLite's flat 64-table join ceiling, and
  rejection of a consequential case-sensitivity payload on a non-text operator. Definition- and
  known-identity-narrowed direct/link selectors reject endpoint combinations that have no permitted
  type alternative; an untyped link selector likewise rejects when no current link definition can
  connect the selected endpoint kinds/types. The large-pattern regression also asserts that only
  intermediate binding CTEs are materialized and the final complete-binding step remains bounded by
  the outer limit. Query-plan evidence rejects a temporary SQL ordering tree, so deterministic
  response ordering cannot force full complete-result evaluation before that bound.
- The predicate matrix covers presence, missing, null, non-null, Boolean equality, every selected
  ordering operator across integer boundaries, number, exact text, date, and timestamp ordering,
  anyOf, case-sensitive and folded
  contains/prefix, RE2 substring search, and all-term/any-term/phrase FTS. It distinguishes
  case/diacritic behavior and rejects malformed RE2 and multi-token term operands.
- Hydration instrumentation raises if an over-bound pattern tries to hydrate and records only the
  explicitly requested property decoder. Discovery instrumentation shows shallow summary decodes
  only anchor definitions. Revision-zero graph/FTS selection is empty while revision one returns the
  indexed content; time before revision zero rejects.
- `tests/vellis/v2_query_oracle.py` is a small brute-force topology evaluator that imports no SQL,
  compiler, repository, or production predicate helper. It agrees for single, association, branch,
  cycle, parallel, and self-link cases. A monkeypatched compiler that removes selector inequality
  disagrees, proving the oracle catches the nearest wrong distinctness join.
- Ruff, BasedPyright, and the explicit C901-at-10 check pass over every Phase 3 successor module.
- `just test` collects 1,329 tests: 1,327 pass. Its only two failures are the already tracked
  `F010`/`W008` completed-campaign coupling cases
  `test_committed_campaign_is_stale_and_valid` and
  `test_qualified_model_references_are_resolved_by_the_official_validator`; no Phase 3 test or
  successor path fails.

### Subtraction and locality review

The successor query path imports no predecessor `query`, `sqlite_query`, `Store`, recursive JSON,
Decimal, Pydantic, FastMCP, projection, aggregation, hidden witness, or generic query-language
module. It contains no AST, optimizer, planner class, visitor, registry, cache abstraction, or
reusable populated temporary relation. The tokenizer's connection-local temporary FTS relations
disappear with the operation connection.

The predecessor query/compiler remains reachable only through the not-yet-replaced predecessor
Store/MCP boundary. Deleting it now would either break unrelated still-predecessor tools or require
the Phase 7 adapter rewrite early. No successor module calls or translates it. `F002` therefore
remains honestly conflicting and is owned by W008: W007 removes the owning public adapter, then W008
deletes the orphaned predecessor compiler/tests and closes the finding. The successor behavior is
conforming, but the repository-wide subtraction claim is deliberately not yet made.

Current resolution reads the metadata head and indexed version intervals, never canonical replay.
Summary resolves only anchor keys, inspect only its requested closure, pattern compilation selects
the bound tuple before values, and hydration queries only bound UUIDs and requested property sets.
No complete graph or definition-set aggregate survives a successor read operation.

### Third-pair root-cause audit

Three consecutive non-clean authority/engineering review attempts sampled one shared boundary:
query validity was correct only when every definition needed to establish a candidate relationship
combination happened to be present in the initially referenced-key set. The bounded audit covered
the complete selected matrix rather than adding another isolated case:

- Direct associations with explicit, untyped, and known-UUID-narrowed anchor/data selectors.
- Links with explicit, untyped, and known-UUID-narrowed link selectors and endpoint selectors.
- Both valid local alternatives and candidate sets with no permitted combination.
- Patterns above SQLite's flat-join ceiling and the separate question of bounding complete tuples.

The corrected resolver use is ordered and targeted: load explicitly selected definitions; load all
current link definitions only for an untyped link selector; load all current associated-data
definitions only for an untyped data endpoint in a direct association; load link-permitted endpoint
definitions; then load the permitted anchor definitions of the resulting associated-data
definitions. This is the one existing definition resolver over request-relevant definition
populations, not a graph load or a second resolver. Tests now reject impossible typed/untyped and
UUID-narrowed endpoint combinations while accepting a compatible untyped alternative. Separately,
only intermediate binding CTEs are materialized to break SQLite flattening; the final complete tuple
join remains beneath the outer `maximumMatches + 1` limit. SQL performs no final ordering; only an
accepted row set already proven complete and within the bound is sorted afterward.

### Second convergence root-cause audit

After three further non-clean review pairs, the remaining shared cause was unbounded SQL parameter
expansion in targeted definition resolution. The audit covered every definition-key population that
can grow independently of a public request list: definition headers, permitted members, property
definitions, allowed values, focused-neighborhood endpoint keys, and untyped relationship closure.
All now use a single JSON parameter with `json_each` rather than one placeholder per key. The
discriminating query test lowers SQLite's runtime variable limit to 12, resolves twelve current link
definitions from one untyped selector, and still returns the expected domain result; the prior
placeholder expansion fails that same case before query evaluation.

The same bounded-relation rule applies to `anyOf`: property and display-name alternatives use one
structured JSON parameter through `json_each`, never one SQL expression/parameter per value. Tests
exercise the full public maximum of 1,000 alternatives for both forms and return domain results
without reaching SQLite's expression-depth or variable-count limits.
