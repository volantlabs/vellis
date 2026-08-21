# Phase 6 — streamed v1 initialization evidence

## Qualified authority and bounded frame

- Model baseline: `sha256:8af0ac5250d5186b8baa693bc8ebcc2b5e69f0e130754fbc676cb2302bfa8794`.
- Qualified authority: `RTG::'V1 Snapshot'`, `RTG::'Recovery Candidate'`,
  `RTG::'Recovery Finding'`, `RTG::'Recovery Report'`,
  `Vellis::'V1 Import Preview'`, `Vellis::'Begin from Vellis v1 snapshot'`,
  `VellisRequirements::initialization`, and
  `VellisVerification::'V1 Import Is Streamed Explicit And Lossless'`.
- Work/decision/finding: `W006`, `D007`, and `F007` in `system-evolution.yaml`.
- Read semantic closure: `model/README.md`, the recovery values in
  `model/10-rtg-domain.sysml`, recovery/initialization behavior in
  `model/20-rtg-system.sysml` and `model/30-vellis.sysml`, the initialization
  requirement, its verification, and inherited scalar/graph/lineage/storage
  semantics. Unread external MCP/client lifecycle detail remains W007; predecessor
  subtraction and ordinary-check cleanup remain W008.

| Authority obligation | Coverage | Required effect | Required non-effect | Nearest wrong implementation | Focused evidence |
| --- | --- | --- | --- | --- | --- |
| Exact bounded preview | Full | Stream one exact v1 JSON source through unpublished SQLite and produce deterministic candidate/report digests | No destination, whole source graph, or predecessor storage access | `json.load` or an in-memory graph hides scale and source drift | Large source instrumentation, preview non-publication, digest repeatability/change |
| Explicit preservation/conversion | Full | Preserve live graph/definition meaning and legacy metadata; convert one whole property when its declaration/live occurrences require text | No date/timestamp inference, silent coercion, partial-property conversion, or binary64 loss in converted text | Each occurrence is independently guessed or large decimal text passes through float | Kind matrix, nullability, nested/mixed/unsafe/large-number cases, legacy inspection |
| Conservative relationship mapping | Full | Map only one exact local bound role for one type and report every other rule | No approximation, subset widening, overlap composition, or retained rule identity | A familiar-looking v1 count becomes a v2 bound despite a narrower population | Four local-role cases plus subset/overlap/unknown omission |
| Complete validation and publication | Full | Block every unresolved live identity/type/reference/preservation defect; publish one audited revision-zero lineage and exact private report after matching confirmation | No imported history, activity, draft, partial destination, or report-only success | Either artifact becomes visible before the complete data directory is ready, or confirmation checks only source bytes | Corruption/reference cases, changed source/report refusal, atomic-boundary injection, audit/read/query |

## Closed input and disposition inventory

The importer recognizes exactly one predecessor document shape. It does not define a
general migration language.

| Inventory | Closed members and treatment |
| --- | --- |
| Top-level source families | `graph`, `schema`, `constraints`, `migration`; missing or wrong-shaped families make the document unreadable |
| Graph event families | `anchors`, `data_objects`, `links`, and every `anchor_data_index` value/member; a map value must be an array and every array member must be a UUID string. Every association is independently normalized before live-object selection, normalization is reported at its endpoint source pointer, absent/invalid live endpoints block, explicitly non-live endpoints omit/report, and normalized duplicates block |
| Definition event families | `anchor`, `data_object`, and `link`; `system.live` defaults true; false entries are omitted/reported |
| Property inference inputs | One live data-type/property declaration plus every live occurrence: Boolean, safe integer, finite binary64 number, text, null, nested array/object, unsafe integer, incompatible non-null kinds |
| Property outcomes | One non-null scalar kind; nullable when null coexists; otherwise whole-property text using canonical JSON for every occurrence; string declarations never infer date/timestamp |
| Constraint outcomes | Exactly one of `anchorsPerObject`, `objectsPerAnchor`, `linksPerSource`, or `linksPerTarget` for one complete converted type population. One shared derivation unions declared types with types proven by live associations/link endpoints. The exact shape permits only names, that final full type set, the one structural join, and `required: false`; subsets, UUID filters, predicates, selected/returned shape, summaries/aggregations, limits, extra joins/requirements, required joins, and every unknown payload/query/member field omit/report |
| Property refinement outcomes | Absence remains absence for each of `allowed_values`, `minimum`, `maximum`, `minimum_length`, `maximum_length`, and `pattern`; every supplied field must convert to its declared kind and the combined definition must conform, otherwise the refinement bundle is omitted/reported |
| Report dispositions | `preserved`, `converted`, `omitted`, `blocking`; every entry carries code, original v1 source pointer, summary, and only applicable target UUID/type/property. Candidate validation paths are resolved through staged provenance one finding at a time and never escape as v2 `/objects` or `/definitions` paths |
| Confirmation boundary | Exact source SHA-256 plus exact deterministic machine-report SHA-256; either mismatch refuses publication |
| Publication boundary | Database and report are fully sealed, audited, and flushed inside one owner-private temporary data directory; one directory rename is the only visibility/readiness boundary, followed by a truthful durability flush |

### Exact relationship-rule field inventory

| Source object | Exact reducible members | Every other present member |
| --- | --- | --- |
| Cardinality payload | `query_spec`, `counted_binding`, `group_by_bindings`, optional integer `minimum`/`maximum` | Omit/report |
| Query specification | `anchor_buckets`, plus exactly one relevant `data_requirements` or `link_requirements` collection; the other may be absent or empty | `return_spec`, projections, aggregations/summaries, result limits, or any later query member omit/report |
| Anchor bucket | `name`, complete duplicate-free `anchor_type_keys` | UUID filters, predicates, selected shape, or any later member omit/report |
| Data requirement | `name`, `anchor_bucket`, one `data_type_key`, and explicit `required: false` | Property predicates, UUID filters, selected properties, required-join semantics, or any later member omit/report |
| Link requirement | `name`, `source_bucket`, `target_bucket`, one `link_type_keys` member, and explicit `required: false` | UUID filters, predicates, selected shape, required-join semantics, or any later member omit/report |

The focused table-driven evidence mutates every category above. This is deliberately a
closed exact-shape test: unfamiliar v1 fields never acquire guessed meaning.

## Transient storage and materialization inventory

- The unpublished candidate database uses the 25 VEL2 application relations plus one
  transient staging relation. The staging relation is dropped before audit/publication;
  no 26th relation survives.
- Staging retains one canonical JSON record per source graph/definition/constraint/
  migration entry and one association pair per source index member. It is not a second
  canonical-state authority.
- The only nested materialization is one source entry, one legacy metadata subtree, one
  property value, one definition, one graph object, or one report disposition at a time.
- Property-wide facts, UUID/type reservations, association membership, definition
  dependencies, and report order live in indexed SQLite rows. Candidate graph and
  definition sets are never held as whole Python collections.
- Candidate-finding provenance is resolved with one indexed staging lookup per finding;
  there is no source-wide path map or retained finding collection.
- Source hashing uses fixed-size byte blocks. Candidate/report hashing streams ordered
  rows. Publication re-reads and restages the source rather than trusting preview memory.
- No Decimal or nested JSON value crosses the importer boundary into active domain,
  graph properties, query, or transport. Decimal exists only while parsing/canonicalizing
  one legacy value.

## Intended subtraction and public boundary

Phase 6 replaces the successor v1 initialization behavior directly. It adds no v1
storage opener, in-place migration, compatibility facade, general schema converter,
migration framework, replay path, public draft/system metadata, or date inference. The
predecessor adapter remains reachable until W007/W008 replaces the runnable boundary;
this phase must not claim that residue removed.

## Mandatory bounded root-cause audit

After three non-clean review pairs, the complete import boundary was enumerated before
another freeze. The audit distinguishes an intentional refusal/omission from a branch
that could silently bypass reservation, refinement, provenance, or disposition work.

| Root inventory | Closed members | Counterexample evidence |
| --- | --- | --- |
| Graph identity reservation | Canonical UUID from every live and non-live anchor, data object, and link; all three same-kind families at both liveness values; all three cross-kind pairs; invalid and normalized spellings | Same-kind repetition blocks as `duplicate-identity` because v1 history is not imported; cross-kind repetition blocks as `identity-kind-conflict`; normalization is reported before conflict; invalid non-live UUIDs still block |
| Definition identity reservation | Exact type key from every live and non-live anchor, data, and link definition; all same-kind families/liveness values and all three cross-kind pairs | Same-kind repetition is not interpreted as reactivation; cross-kind reuse blocks; case-distinct keys remain distinct; invalid non-live identity/kind blocks before omission |
| Six supplied refinements | `allowed_values`, `minimum`, `maximum`, `minimum_length`, `maximum_length`, and `pattern` across Boolean, integer, number, text, and whole-property JSON-text conversion | Thirty table cases prove exact compatible mapping or an omission disposition. JSON-text conversion reports every supplied constraint and unknown refinement rather than returning early |
| Candidate finding provenance | Present property name/index, missing required named property, digit-only property name versus actual numeric index, empty invalid property, property refinement suffix, exact digit-only definition key versus actual definition index, shared missing members across definitions, object type/display/structural source, association, link source/target, permitted members, and all four cardinality roles | Exact staged domain keys win before positional interpretation. `targetProperty` is only decoded property segment 3, never the remaining finding-path suffix. An empty invalid key retains its exact double-slash source pointer but produces no optional target identity. An absent object property is resolved through its staged type definition before numeric fallback. A referenced-member fallback is accepted only when it identifies one definition. Canonical UUIDs cannot be digit-only and have no key/index ambiguity |
| Pre-conversion exits | Liveness, non-live omission, malformed/duplicate identity, association endpoint classification, definition conflict, converted property, constraint non-reducibility, and caught graph/definition conversion error | Identity scan precedes every liveness omission. Invalid liveness in all graph/definition families and constraints becomes a blocking report rather than aborting preview. Every later skip is preceded by a disposition or is a bounded candidate-selection step already covered by a blocking disposition |
| Recovery disposition construction | One constructor normalizes optional targets: UUID only after canonical UUID parsing; type key/property only as exact nonempty text | All four disposition families canonicalize uppercase UUIDs, omit invalid raw values regardless of length, retain exact type/property text, and leave invalid raw content only in source pointer/summary |
| RFC 6901 provenance | Every dynamic property name, map key, UUID spelling, definition type key, endpoint/type member, cardinality subject, and index passes through one shared domain-safe segment escaper | Table cases cover `/` and `~`; domain findings and end-to-end converted, omitted, and candidate-finding pointers preserve exact names as `~1`/`~0`. A special link type with an unknown special endpoint resolves back to its exact v1 member pointer and affected type key |
| Association disposition completeness | Shape-invalid, endpoint-invalid/absent, non-live, duplicate, normalized, and canonical live members | Every source association member has a terminal blocking, omitted, or preserved disposition. A normalized live member additionally has its endpoint normalization disposition; canonical association preservation is counted deterministically |
| Relationship overlap | Exact-alone and exact plus filtered, extra-grouped, extra-requirement, subset-membership, multi-link-type, selector-name collision, mixed malformed/member, or unknown-type rule for each applicable local role | Exact queries require globally unique nonempty names across anchor, data, and link selectors. Permissive target extraction requires the complete counted/grouped data-anchor or link-endpoint pair and enumerates every unique recognizable type member. A true same-role overlap suppresses exact mapping; an unrelated broken count/group pair or unknown-only member is omitted/reported without suppressing a safe exact rule |
| Collection-valued source fields | Top-level graph/schema/constraint/migration arrays/maps; association lists; definition payload/property maps; `value_kinds`; required/optional data types; allowed source/target types; property values/refinements; query buckets/requirements/groups/type members | Scalar, object/list inversion, and null are table-tested for every inference-relevant collection. Preservation-critical definition/graph shapes block; nonreducible constraint shapes explicitly omit/report; no wrong-shaped collection silently becomes absent |

The source identity reservation scan is transient staging work, not imported history. A
same-kind duplicate—including one live and one non-live entry—therefore blocks instead
of inventing a predecessor reactivation transition that v2 explicitly does not import.
The refinement matrix contains only v1-representable target kinds: v1 strings remain
text and are never inferred as dates or timestamps.

## Implemented realization and root-cause sweep

- `v1_stage.py` validates the one complete source shape and streams its six array
  families plus direct associations through `ijson` into the single unpublished
  staging relation. `v1_association_conversion.py` then classifies every association,
  independent of later live-data selection, and creates only normalized live pairs.
  Source staging hashes the exact file before and after the pass and refuses a source
  that changes during staging.
- `v1_identity.py` scans canonical UUID and exact type-key reservations across all
  source graph/definition entries before liveness can omit anything. Its transient
  reservation rows drive conflict skips, so later converters cannot reinterpret a
  duplicate as a new object or lose a non-live kind conflict.
- `json_pointer.py` is the sole RFC 6901 dynamic-segment encoder shared by successor
  domain findings and `v1_pointer.py`'s importer-facing re-export. The report constructor
  is likewise the sole target normalizer: it parses canonical UUID identity instead of
  using spelling length and retains exact applicable type/property text only.
- `v1_definition_conversion.py` performs property-wide inference across declarations
  and every live occurrence, maps only the four exact local-bound roles, and records
  every non-live, converted, omitted, conflicting, or invalid definition decision.
  `v1_population.py` is the single derivation of each converted permitted population;
  both emitted definitions and bound exactness use declarations plus live
  association/endpoint evidence, so a declaration-only subset never maps.
  Before inference it validates every closed collection shape. Relationship-rule target
  extraction is intentionally more permissive than exact mapping, allowing every
  recognizable member of a granular, filtered, or multi-type rule to suppress an
  otherwise unsafe exact mapping for that member's role. Recognition still requires
  both halves of the role's counted/grouped pair, so an unrelated malformed binding
  cannot suppress a safe exact mapping. Exactness separately requires globally unique
  selector names across all anchor, data, and link collections.
- `v1_graph_conversion.py` converts one live object at a time, canonicalizes UUIDs,
  confines Decimal/nested JSON to conversion, and persists only typed v2 scalars plus
  optional canonical `legacyV1` text.
- `v1_candidate_validation.py` was added from the upfront validation inventory rather
  than stopping at the first persistence error. It streams every definition and object
  with only its directly referenced neighborhood. After persistence, the shared
  complete effective-state iterator emits every structural and cardinality finding.
  Focused evidence proves two independent dangling links and two independent
  cardinality subjects are all reported.
- `v1_provenance.py` maps each candidate finding back to the original staged graph,
  definition, property, association, or constraint pointer with bounded SQL lookups.
  The report therefore identifies source input to repair rather than leaking converted
  candidate paths.
- `v1_report.py` streams machine and human reports through the same exact order:
  source pointer, target UUID, target type key, target property, then code. Neither
  rendering retains the source-wide disposition list.
  `v1_import_operations.py` rebuilds the candidate for confirmation, seals canonical
  revision zero from streamed row descriptors, drops staging, audits the unpublished
  database, then atomically renames the complete owner-private data directory. There is
  no between-artifact visibility state. Pre-boundary failure publishes neither artifact;
  a post-boundary directory-flush failure reports that both exist and durability is
  unconfirmed rather than claiming rollback.
- The published database has 25 application relations, one canonical initialization
  record, empty activity, no draft, no imported transition history, and no retained
  staging relation. Discovery and selected identity query work immediately, including
  explicit legacy metadata selection and converted text inspection.

The review-five shared-pointer sweep briefly pushed the cohesive domain validator over
the 800-line subtraction trigger. The immediate review extracted its already-distinct
complete-cardinality concern into `cardinality_validation.py`; it did not introduce a
framework or forwarding layer. No touched successor production module now exceeds the
trigger: `domain_validation.py` is the largest by logical size at 771 physical and 707
logical lines, while the definition converter is 783/699. All touched production functions satisfy
C901 <= 10. The
916-line predecessor
`v1_streaming.py` and its C901 violation remain reachable through the predecessor
adapter and stay explicitly owned by W008; neither is evidence about the successor
path.

## Evidence status

Evaluated on the exact review-eight candidate working tree:

- `uv run pytest -q tests/vellis/test_v1_import_v2.py`: **215 passed**.
- Successor Phase 2–6 suite (the seven explicitly listed successor test modules):
  **459 passed**.
- Successor Phase 6 C901 inventory: **0 findings** across the seventeen new Phase 6
  production modules and the four bounded successor validation/repository additions.
- `uv run ruff check vellis --select F821 --output-format concise`: passed.
- `just lint`: passed.
- `just typecheck`: passed with **0 errors, 0 warnings, 0 notes**.
- `just model-check`: passed for all six authored model files with the pinned official
  Java pilot 0.60.1.
- `just model-reference-check`: passed; the pinned reference corpus is current.
- `just system-evolution-check`: passed.
- `git diff --check`: passed.
- `just test`: **1,692 passed, 2 failed**; both failures are the exact pre-existing
  F010/W008 completed-campaign coupling cases in
  `tests/test_implementation_campaign.py`. No Phase 6 or successor test failed.

The focused evidence is inventory-driven: all live/non-live identity families and
cross-kind pairs; all source families, association container/member
shapes, endpoint normalization and dispositions; every property refinement field; every
refinement field across every v1 target-kind/conversion path; every
population/join/filter/return-shape rule-field category; declared-plus-inferred exact and
subset populations for all four bound roles; source provenance for object, property,
definition, reference, and constraint findings; scalar inference outcomes; exact shared
machine/human ordering; central target normalization; shared RFC 6901 domain and import
paths; complete association dispositions; the collection-shape, four-role overlap, and
multi-link-member, global-selector-collision, complete-pair recognition, and digit-name
versus positional-index and property-segment-versus-refinement-suffix provenance matrices;
huge-exponent number selection; four report dispositions; both
confirmation digests; the one directory-rename readiness boundary; complete-finding
paths; and every retained materialization site have a named test or inspection. Phase 7
still owns the public CLI adapter; Phase 8 still owns predecessor reachability and
deletion.
