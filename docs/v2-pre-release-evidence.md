# Vellis v2 pre-release closure-correction evidence

This is the non-authoritative evidence narrative for completed evolution
`vellis-2-pre-release-closure-corrections` and its bounded pull-request follow-up
`vellis-2-pr-review-corrections`. Product authority remains the textual SysML under `model/`; this
document records correction outcomes, independent owner narratives, and reproduced simplicity
measurements against original source baseline
`7d007fd0b7e2ac6e8671bc297400f1490dd03a62`.

## Bounded correction outcome

The correction does not reopen the v2 design. It makes the already-selected public finding shape
repairable, consolidates the already-fixed public item bound, strengthens one predicate
discriminator and the ordinary complexity gate, removes one forwarding-only private module, and
corrects one evidence label. It adds no public operation, finding code or field, configuration,
schema relation, database version, compatibility layer, resolver, or alternate query engine.

| Finding | Disposition and evidence |
|---|---|
| F001 | Accepted model authority now derives starter completeness from the named definitions and selected date properties rather than redundant aggregate totals; runtime starter content is unchanged. |
| F002 | Accepted finding authority now requires exact RFC 6901 request or affected-state locations, keyed definition subjects, and retained referent identities. |
| F003 | Effective draft validation uses keyed definition paths. Removing `life.person` independently identifies all six current dependents while every finding retains `life.person` in `typeKeys`; `/` and `~` subject segments are escaped. |
| F004 | Active and draft duplicate findings point to the later real request member, command-limit findings use `""` for the whole request, and property-predicate refusal points to the node's actual `typeKeys`. Test-local pointer resolution confirms the request paths resolve. |
| F005 | `vellis.domain.PUBLIC_ITEM_LIMIT` is the sole production definition. Public schemas, validation, audit, discovery, draft, history, MCP annotations, summaries, and the rendered unchanged SQLite constraint use it. Existing schema checks and 1,000/1,001 behavior remain green. |
| F006 | A behavior-level test computes distinct strict and inclusive numeric result sets and confirms the public query returns the strict set. The independent oracle remains topology-only. |
| F007 | Accepted historical deviation. Phases 2–7 deferred production deletion to Phase 8. Git is unchanged; the future lesson is to make phase-local predecessor reachability a checkpoint condition, not to add generic campaign machinery here. |
| F008 | Phase 8 now labels the measurement as ``vellis/ + tools/`` C901 findings and separately records the two test findings. |
| F009 | The forwarding-only `vellis/v1_pointer.py` is deleted; v1 callers import the canonical JSON-pointer functions directly. |
| F010 | `just lint`, and therefore ordinary `just check`, now runs `uv run ruff check vellis --select C901`. |
| F011 | Accepted explicit glue. Effective-definition composition remains local and stateless; no second resolver or helper layer was added. |
| F012 | Backup initialization now reports the preserved lineage head rather than an unconditional revision zero. |
| F013 | Successful backup publication removes audit-created sidecars belonging to its private temporary database, and setup reads its static input backup immutably so the source gains none. |
| F014 | Public MCP guidance now explains that scalar property selection/predicates apply to associated-data nodes while anchor names and link endpoints are structural. |
| F015 | Public setup guidance now states Python 3.14+ installation and the absent-or-empty-`0700` POSIX directory prerequisite. |

Focused evidence is in the revised existing tests rather than a parallel contract suite:

- `tests/vellis/test_storage_v2.py` retains the starter projection digest, named date-property set,
  local bounds, optionality, empty graph, and state-derived initialization summary.
- `tests/vellis/test_change_draft_v2.py` discriminates keyed affected definitions, escaped dynamic
  subjects, resolvable duplicate locations, and the whole-request pointer.
- `tests/vellis/test_query_v2_successor.py` discriminates node-level predicate locations and a
  strict-boundary result from an inclusive mutant.
- Existing MCP schemas and 1,000/1,001 behavior remain the public-boundary evidence for the one
  fixed item limit.

## Pull-request review follow-up

Codex reviewed pre-release head `6da7985aae97a01c13468d1ec4a4f77bc6c7d5bc` and reported five
implementation defects already decided by current model authority. Each was independently
reproduced before correction; no model, public operation, wire shape, finding taxonomy, relation, or
database-version change was required.

| Review finding | Correction and discriminating evidence |
|---|---|
| Intermediate query bindings were materialized without the public result bound. | Pattern evaluation now streams candidates through an iterative depth-first traversal and retains only `maximumMatches + 1` complete tuples. Relationship constraints are evaluated as bounded traversal steps as soon as their endpoints are bound rather than as one expression per relationship. A dense synthetic stream proves early termination; the public topology/oracle matrix and a 65-node pattern preserve query meaning, while a real maximum-width population returns one exact 1,000-binding match and rejects an unfiltered second match without SQLite's flat-join or expression-depth limits. |
| Client enumeration treated every nonzero result as absence. | Codex and Claude each require their own complete missing-entry diagnostic. Mixed, cross-client, and other nonzero diagnostics raise on uncertain external state before remove or add. |
| A lone Unicode surrogate reached canonical UTF-8 encoding. | The strict wire-model boundary recursively rejects strings that are not UTF-8 encodable. A real MCP request carrying an escaped surrogate produces the Unicode-scalar validation error before the domain change operation is invoked and appends no activity. |
| Version interval audit omitted overlap detection. | Every version relation is checked by its family identity for intersecting intervals. The focused counterexample has individually valid bounds but two active versions at revision 2 and now produces an overlap finding. |
| FTS audit compared only aggregate token counts. | Independent rebuilt and live vocabularies are compared by term, document, column, and offset. Reversing indexed token order while retaining source content changes phrase results and now fails audit. |

The affected query, MCP lifecycle, history, audit, backup, and recovery suites passed 204 tests after
the correction. The final gate and review results below are refreshed at the frozen closure token.

## Installed owner narratives

The wheel and source distribution were built from the correction candidate. Five fresh,
context-isolated agents received only the installed artifact, public operating documentation, one
owner narrative, and disposable paths. They did not receive source, tests, expected conclusions,
prior findings, or implementation architecture. All state and helper programs stayed outside the
repository; no narrative used direct SQLite mutation.

### Everyday owner — CLI and MCP STDIO

- Scale and state: 33 starter definitions and 160 objects across six dated weeks: 41 anchors, 41
  details, and 78 links spanning people, areas, goals, projects, tasks, events, notes, and
  resources. The original lineage reached revision 3 after restore; its backup retained revision 2.
- Outcomes: cold discovery, mixed capture, connected questions, whole-result refusal, sparse field
  update without prior unrelated hydration, canonical and verbose history, restart, backup,
  backup initialization, audit, and historical restore all completed without lost unrelated data.
- Findings and disposition: the first run found ambiguous property-selection guidance, a false
  revision-zero setup message, leaked hidden temporary SQLite sidecars, and missing Python-runtime
  installation guidance. Product and documentation corrections addressed all four. A fresh
  installed rerun constructed the query from the clarified public guidance, reported the preserved
  revision, left no internal temporary sidecar, installed explicitly on Python 3.14, and passed
  recovered audit/MCP checks. Clean after affected rerun.

### High-volume owner — CLI and MCP STDIO

- Scale and state: one simple schema followed by 1,205 anchors, 1,205 associated-data objects, and
  1,204 links in six legal batches; canonical head revision 7.
- Outcomes: a 1,205-match result refused whole delivery at the 1,000 bound; property and identity
  narrowing succeeded; complete validation, canonical/activity history, restart, audit, online
  backup, backup initialization, and recovered identity reads completed. Observed end-to-end
  population/query/validation/history time was 2.46 seconds; this is not a threshold.
- Findings and disposition: the initial backup-initialization message falsely reported revision 0
  while preserving revision 7. After the root correction, a fresh installed recovery slice reported
  revision 7, audited cleanly, and returned representative anchor/data/link identities. A later
  recovery-boundary correction moved head discovery before publication and opened the static input
  immutably; the final installed rerun left both source and destination as single files. Clean after
  affected reruns.

### Frequently evolving schema steward — CLI and MCP STDIO

- Scale and state: 20 definitions (six anchor, six associated-data, eight link), 20 representative
  objects, five canonical revisions, and no final draft.
- Outcomes: a property addition preserved an intervening live write; an integer-to-text property
  change activated with explicitly remodeled values; removal of one shared definition returned
  eight separately repairable definition/object paths. Unstaging only the removal retained an
  unrelated schedule update, and activation caused no cascade or data loss.
- Findings and disposition: the same revision-zero backup message was reproduced against revision
  5. The fresh corrected slice reported revision 5, preserved revisions 0–5, matched current MCP
  discovery/history, and audited cleanly. Clean after affected rerun.

### V1 adopter — tagged-v1 export, v2 CLI, and MCP STDIO

- Scale and state: three v1 definitions and five live objects covering Boolean, integer/number,
  null, repeated and nested values, directed relationship, and legacy metadata. Preview recorded 10
  preserved, eight converted, zero omitted, and zero blocking dispositions. V2 initialized at
  revision 0 and an ordinary six-change remodel draft activated as revision 1.
- Outcomes: documented v1 public export, preview/report review, both digest confirmations,
  different-directory initialization, report-digest identity, audit, focused meaning inspection,
  effective-draft query, validation, activation, and post-activation query all completed. Imported
  history was not claimed or synthesized.
- Findings and disposition: no material finding; no rerun required.

### Operational recovery owner — CLI, MCP STDIO, and bearer-protected HTTP

- Scale and state: three definitions, four initial objects, revisions 1–5, one live-draft interval,
  and a 339,968-byte owner-private online backup.
- Outcomes: unauthenticated HTTP returned 401; authenticated reads and mutation worked. Backup ran
  during reads and preserved revision 3 plus the live draft. A deliberately abandoned revision-4
  response was reconciled through current state and both ledgers without retry. Restore correctly
  refused while the draft existed, then revision-1 meaning was published as revision 5 after
  discard; audit remained clean. Semantic/verbose activity and bounded history retained their
  distinctions.
- Findings and disposition: the initial run found that public setup guidance omitted the
  absent-or-empty-`0700` POSIX directory prerequisite and, independently, the Python 3.14 runtime.
  Revised guidance was followed successfully for absent and pre-created owner-private blank and
  backup destinations; all four databases audited cleanly. Clean after documentation rerun.

## Simplicity and scope reassessment

The broader simplification remains successful after the correction. Current measurements reproduce
the Phase 0 rules; line counts are diagnostic, not design targets.

| Measure | Phase 0 | Correction candidate | Change |
|---|---:|---:|---:|
| Authored SysML lines | 4,750 | 2,483 | -2,267 |
| Product Python lines under `vellis/` | 23,854 | 20,791 | -3,063 |
| Test Python lines | 28,692 | 16,740 | -11,952 |
| Product C901 findings above 10 | 37 | 0 | -37 |
| `vellis/ + tools/` C901 findings above 10 | 53 | 11 | -42 |
| Persistent application relations | 39 | 25 | -14 |
| Named temporary relations | 38 | 20 | -18 |
| Product private FastMCP/MCP references | 4 | 0 | -4 |
| Canonical definition resolvers | 4 | 1 | -3 |

The product has 65 Python modules after deleting the forwarding alias and isolating bounded pattern
evaluation, averaging about 320 physical lines. The largest logical production module is the
773-line schema declaration; the next is the 763-line query validator. No class has more than seven
public methods. The ten MCP tools, seven CLI
commands, 25 persistent relations, 20 named temporary relations, one canonical resolver, and
database version are unchanged.

The remaining breadth corresponds to accepted draft composition, current and historical query,
canonical/activity history, audit, backup and restore, search, and conservative v1 initialization.
There is no evidence that another subtraction campaign would improve owner outcomes before the
pre-release. In particular, reducing module, table, line, or test counts now would optimize the
measurements rather than remove an authority or runtime concept.

The correction itself stays inside the simplicity constraints: path-aware duplicate detection is a
small local helper in each of the two operation modules; the limit imports one existing constant;
the predicate mutant exists only as a focused behavior test; and deletion removes an alias rather
than replacing it. The accepted residuals are deliberate: topology-only independent oracle,
repeated effective-definition glue, portable-tool and test complexity outside the production gate,
and the historical deletion-sequencing lesson. None is a material pre-release product gap.

## Verification

The earlier affected domain, starter/storage, change/draft, query, MCP lifecycle, v1 import,
history/recovery, and repository-policy selection passed 561 tests. The pull-request follow-up's
focused selection passed 204 tests. The complete candidate passed 806 tests through ordinary
`just check`.

| Gate | Candidate result |
|---|---|
| `uv run ruff check vellis --select C901` | passed; zero product findings |
| `just lint` | passed; includes the product C901 gate |
| `just typecheck` | passed; zero errors, warnings, or notes |
| `just model-check` | passed for all six model files with the official Java pilot 0.60.1 |
| `just model-reference-check` | passed; pinned corpus current |
| `just system-evolution-check` | passed for this active correction record |
| `just package-check` | passed for wheel and source-distribution installed-command paths |
| `just check` | passed; 806 tests |
| `git diff --check` | passed |

The regenerated SQLite schema text is byte-identical to baseline and retains database version 1.
Mechanical closure inventories report 25 persistent and 20 temporary relations, one production
item-limit definition, no `v1_pointer.py`, no generated double-slash or synthetic-parent finding
path, zero product C901 findings, zero private MCP references, one canonical definition resolver,
ten tools, and seven CLI commands. The installed entry reaches all 64 non-metadata product modules,
so no orphan predecessor path remains. No command in this correction accessed the protected
`.data/` directory.

Final independent-review identities and the shared frozen token are applied only in deterministic
closure bookkeeping after the clean pair.
