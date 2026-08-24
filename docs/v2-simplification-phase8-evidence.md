# Phase 8 — final subtraction, synchronized guidance, and closure

This is the execution and evidence frame for `W008`, not product authority. Accepted meaning
remains under `model/`; the approved rebaseline plan fixes this closure scope.

## Conformance frame

Qualified authority is the complete accepted model, especially
`VellisRequirements::'Unified Query Meaning'`, `Atomic Field Change`,
`Durable Draft Governance`, `Historical State And Canonical Ledger`,
`Activity Separation And Privacy`, `MCP Boundary Integrity`, and
`Simple Secure Individual Operation`, together with W008 and D009.

| In-scope obligation | Required non-effect | Nearest plausible wrong implementation | Focused evidence |
|---|---|---|---|
| Only the rebaselined identity/pattern query and selected hydration remain runnable | No projection, aggregation, hidden selector, disconnected product, match/get compatibility, or generic query parser | The installed adapter is new while predecessor compiler modules and tests remain importable | import/reachability inventory, public query tests, predicate and oracle mutation evidence |
| Only field patches, explicit removals, and the one unversioned draft remain | No complete-object replacement, relationship-rule identity, proposal version/status/assessment/token, or cascade | Old governance and store types survive as a private alternate authority | module/test deletion inventory and public change/draft evidence |
| Indexed version history, restore, audit, and SQLite backup are the sole recovery path | No public snapshot, tail, replay, preserve command, or restart replay | Old replay tables and helpers remain importable after the CLI changed | import inventory, installed command list, history/recovery tests |
| Repository guidance and checks describe the runnable successor | No completed-campaign gate in ordinary `just check`; no stale command or capability claim | Runtime is simplified but contributors are still directed into the completed campaign | documentation search, recipe inspection, full gates |
| Closure architecture meets selected subtraction constraints | No private FastMCP/MCP API, product-owned connection access in tests, duplicate definition resolver, shared connection, C901 over 10, or >800-line orchestration module | Complexity is moved behind renamed files or test-only private access | mechanical AST/search/schema/connection inventories and complete suite |

## Intended deletion and boundary inventory

The installed `vellis` entry reaches 64 successor modules. The following 25 predecessor modules are
outside that graph and are deleted with their superseded tests and support fixtures:
`activity`, `canonical`, `changes`, `client_setup`, `definitions`, `discovery`,
`everyday_life`, `governance`, `graph`, `history`, `json_value`, `mutation_impact`,
`normalized`, `outcomes`, `patterns`, `preserve`, `query`, `setup`, `sqlite_query`,
`store`, `streaming`, `system`, `v1`, `v1_streaming`, and `validation`.

Logical relations removed are the predecessor proposal/assessment, relationship-rule,
event/replay/snapshot, complete-object, and generalized query authorities. The VEL2 relations and
their selected indexes remain unchanged. Public boundaries affected are subtraction only: one
installed `vellis` CLI, its seven commands, and the ten selected MCP tools retain their Phase 7
meaning. The portable campaign engine and its explicit recipes remain available, but ordinary
`just check` no longer invokes a completed campaign.

## Explicit non-goals

- No model meaning or VEL2 schema change.
- No compatibility wrapper for prototype-v2 modules, database, API, commands, or tests.
- No campaign-engine redesign.
- No deferred feature placeholder.
- No access to protected `.data/` or real external client configuration.
- No numerical performance target without representative owner evidence.

## Evidence status

Measurements, black-box scenario dispositions, exact gates, and final subtraction results are
recorded here only after they are reproduced against the closure candidate.

## Subtraction measurements

Measurements use the Phase 0 reproduction rules against the current closure tree.

| Measure | Phase 0 | Phase 8 | Change |
|---|---:|---:|---:|
| Authored SysML lines | 4,750 | 2,470 | -2,280 |
| Product Python lines under `vellis/` | 23,854 | 20,497 | -3,357 |
| Test Python lines | 28,692 | 16,168 | -12,524 |
| Product C901 findings above 10 | 37 | 0 | -37 |
| `vellis/ + tools/` C901 findings above 10 | 53 | 11 | -42 |
| Persistent application tables | 39 | 25 | -14 |
| Named temporary relations | 38 | 20 | -18 |
| Product private FastMCP/MCP references | 4 | 0 | -4 |
| Tests directly accessing a product-owned connection | 17 files | 0 files | -17 files |
| Canonical definition resolvers | 4 | 1 | -3 |

The five remaining test files that mention a connection either open their own disposable connection
for declared-schema/audit corruption evidence or replace the connection factory to instrument
per-operation ownership; none reaches a connection owned by a running product object. The sole
canonical definition resolver is `definition_repository.load_definitions`; the bounded v1 staging
reader is explicitly named `load_candidate_definitions`. Every product function passes C901 at 10,
no product class has more than seven public methods, and no production module exceeds 800 logical
nonblank/noncomment lines. The catalog-like domain declaration is 815 physical and 657 such logical
lines; the largest logical production module is the schema declaration at 767.

The temporary-relation measurement counts every explicitly named product `TEMP TABLE`, `TEMP VIEW`,
and `VIRTUAL TABLE temp.*` declaration, rather than tables alone. The 20 successor names are:
`activation_change`, `activation_descriptor`, `audit_actual_vocab`, `audit_descriptor`,
`audit_expected_fts`, `audit_expected_vocab`, `direct_association_version`, `draft_selector_fts`,
`graph_object_identity`, `graph_object_version`, `property_version`, `restore_definition_key`,
`restore_descriptor`, `restore_graph_key`, `search_document`, `search_fts`, `search_scope`,
`validation_work`, `vellis_query_tokens`, and `vellis_query_vocab`.

Reproduce the successor count from literal declarations with:

```sh
uv run python - <<'PY'
import re
from pathlib import Path

pattern = re.compile(
    r"CREATE\s+(?:TEMP(?:ORARY)?\s+(?:TABLE|VIEW)(?:\s+IF\s+NOT\s+EXISTS)?\s+"
    r"(?:temp\.)?|VIRTUAL\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+temp\.)"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
names = sorted({
    name
    for path in Path("vellis").glob("*.py")
    for name in pattern.findall(path.read_text(encoding="utf-8"))
})
print(len(names))
print("\n".join(names))
PY
```

All 25 predecessor modules and 31 superseded test/support files named in the deletion inventory are
gone. The installed entry's static import closure contains every remaining product module except the
package metadata `__init__`, so no orphaned alternate runtime remains. The VEL2 schema stays at 25
application relations and has no compatibility relation or migration placeholder.

## Documentation synchronization

README, contributor guidance, security guidance, HTTP operation, backup/restore, v1 initialization,
vision, package metadata, command recipes, and MCP realization now describe only the runnable
successor. The stale locality handoff was removed. `just check` covers the current product/evolution
gates and no longer runs the completed campaign; the inactive portable engine and every explicit
campaign recipe remain unchanged. V1 export guidance intentionally names the old checkout's
documented command while making clear that v2 never opens v1 storage.

Owner guidance now gives exact backup, setup-from-backup, revision/time restore, confirmation, and
no-overwrite behavior; names database content and excluded sidecars; provides explicitly external
systemd, launchd, Tailscale, SSH, and TLS-proxy examples; and gives a current-revision plus
canonical/activity-history procedure for reconciling a lost post-commit response without a blind
retry.

## Black-box scenarios

Fresh context-isolated agents run the ten closure scenarios without implementation access or expected
conclusions. Only scenario, finding, and disposition are retained here; prompts and transcripts stay
outside the repository.

1. Cold discovery, UUID/type narrowing, selected hydration — clean. Public STDIO summary and focused
   inspection discovered the starter; mismatched UUID/type narrowing rejected with `kindMismatch`;
   matching identity hydration returned only the requested properties.
2. Literal, regex, and FTS long-text choice — clean after correction. One draft created six long
   document bodies, validated, and activated atomically. Literal, regex, all-term, and phrase queries
   retained their distinct meanings; an over-bound match rejected with `resultLimitExceeded` rather
   than truncating.
3. One-field patch preserving unseen data — clean. An identity read hydrated only one requested
   property; a patch changed that property without supplying the object's type, other properties, or
   associations. A subsequent complete read preserved both unseen properties and both associations,
   and current validation remained clean.
4. Multi-object removal/repoint with no cascade — clean after correction. Endpoint-only removal
   rejected atomically and identified every surviving associated-data and link dependent. One
   final-state batch then explicitly removed or repointed all affected dependents, committed once,
   and preserved unrelated graph objects unchanged.
5. Definition/data draft with an intervening live write — clean. One draft replaced a lexically
   earlier dependent definition and its later anchor definition while patching related graph data.
   An intervening live property write advanced the canonical revision; draft inspection and query
   composed that unstaged live field with the staged field. One activation published both definitions
   and both objects in one revision, preserving the live field and staged wins.
6. Repeated validation and invalid/valid/redundant activation — clean. A two-page invalid assessment
   was repeatable; invalid activation preserved revision zero and the draft. Staging the missing
   definition repaired it and one activation created revision one. A later raw but ineffective entry
   activated by clearing the draft without creating revision two.
7. V1 converted text, legacy inspection, and remodeling guidance — clean after correction. Public
   tagged-v1 export, preview, digest confirmation, and revision-zero import preserved a starter and a
   bounded repeated/nested fixture. Inspection/query returned canonical JSON scalar text and exact
   canonical `legacyV1`; guidance keeps identity-bearing remodeling in a later owner-approved draft.
8. STDIO onboarding — clean. Disposable starter setup, real STDIO initialize/list/call, and type
   summary returned revision zero and exactly the ten selected tools. An uninitialized target failed
   before protocol startup with actionable setup/audit guidance and no client mutation.
9. Token-protected remote HTTP onboarding — clean. The exact `/mcp` endpoint protected initialize,
   list, and call with `401` plus `WWW-Authenticate` for missing/invalid credentials and successful
   structured responses for the valid bearer. Non-loopback serving refused absent or non-private
   tokens, warned about plaintext HTTP, and never exposed the token value.
10. Post-commit response loss and revision/history reconciliation — clean. A raw HTTP client sent one
    effective change and closed without reading its response. Reconnection found exactly one new
    revision: current/revision reads, canonical history, and activity all agreed on the accepted
    change. No retry was needed and no surface claimed rollback.

The first fresh run of scenario 2 exposed an integration defect: draft validation was clean while
activation inserted new graph objects one UUID at a time, allowing an associated-data or link UUID
to sort before the identities it referenced and hit a foreign-key failure. Activation now composes
all proposed objects first, closes the affected versions together, reserves every new identity, and
then publishes the combined graph set. A focused adversarial UUID-order test covers anchors,
associated data, and a link in one activation; the fresh scenario rerun is clean. This correction
changes no draft or canonical meaning and introduces no new state.

The first fresh run of scenario 4 exposed the same incomplete-closure defect in active validation:
local cardinality peers were loaded without their otherwise-unaffected endpoints, so a fully resolved
remove/repoint batch could report an unrelated intact pair as dangling. The selected local closure now
expands only through the structural referents of objects already selected for validation. A focused
test retains an unrelated cardinality peer with an otherwise-unselected endpoint; the fresh rerun
accepts the resolved batch while preserving endpoint-only rejection and no cascade.

That rerun also exposed the definition counterpart of scenario 2's publication ordering defect:
definition activation inserted each type-key reservation and version together, so a lexically earlier
dependent definition could precede its newly staged anchor type. Activation now composes all changed
definitions, closes them together, reserves every type key, and publishes the combined set. A focused
adversarial type-key-order test covers the correction; scenario 5 rechecks it through the public draft
workflow. These corrections preserve the accepted final-state semantics and add no durable state.

The first fresh run of scenario 7 found that a standard public v1 starter exported empty property
descriptions that its own schema API could not populate, while v2 correctly requires nonempty
descriptions. Import now supplies the deterministic owner-visible text `Imported v1 property
<name>.` only for an absent or empty v1 description and records `property-description-filled` as a
conversion at the exact source pointer. Wrong-kind descriptions still block. Focused evidence covers
both absent and empty inputs; the fresh tagged-v1 rerun imported the starter and a public repeated
value with zero blocking dispositions.

## Final gates

| Gate | Exact candidate result |
|---|---|
| `just lint` | passed; Ruff checks clean and 145 files formatted |
| `just typecheck` | passed; 0 errors, 0 warnings, 0 notes |
| `just skills-check` | passed; 8 skills and 8 Claude links validated |
| `just system-evolution-check` | passed for `vellis-2-simplification-rebaseline` |
| `just model-check` | passed for all 6 files with official Java pilot 0.60.1 |
| `just model-reference-check` | passed; pinned corpus current |
| `just test` | passed; 789 tests |
| `just package-check` | passed for wheel and sdist installed-command paths |
| `just check` | passed, including the same 789-test suite; it did not run the inactive campaign gate |
| `git diff --check` | passed |

Mechanical closure inventories also pass: zero product C901 findings above 10, zero production
private FastMCP/MCP references, zero tests accessing a product-owned connection, one canonical
definition resolver, per-operation connection acquisition with explicit close on every exit, 25
persistent application relations, and 20 named temporary relations. The 11 findings counted across
`vellis/ + tools/` are unchanged portable workflow/reference tooling; two additional test functions
exceed 10 when tests are included. None violates the production constraint, and the inactive
campaign engine was deliberately not redesigned.
