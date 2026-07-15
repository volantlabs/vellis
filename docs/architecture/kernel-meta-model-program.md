---
twin:
  role: decision
  concerns:
    - component.rtg.graph
    - component.rtg.schema
    - component.rtg.change_validation
    - component.rtg.controller
    - component.rtg.migration
    - component.rtg.query
    - component.rtg.constraints
---

# Kernel Meta-Model Program (KM)

Status: program charter, captured 2026-07-08. Operationalizes the gap list in
[`agent-first-graph-modeling.md`](./agent-first-graph-modeling.md) §4 as seven trackable work
items, KM-1 through KM-7, ordered by leverage and dependency. Each item promotes one rule from
"agent discipline" to "kernel invariant."

Graph provenance: volant_base DecisionRecord `7c0c418d` ("Vellis Ships an Opinionated Kernel
Meta-Model for Agent-First Graph Memory") and Exploration `29a19618`. The design doc carries the
per-opinion scar citations; this program carries the execution state.

Status vocabulary matches the research program: `open | in_progress | done | killed`, updated by
ordinary file edit. This is an engineering program, not a research program — items produce spec
amendments, contract tests, and implementation, not RR reports.

Post-merge harmonization checkpoint (2026-07-14): KM-2 through KM-5 now conform to the
SysML-owned component tree, including MCP codecs, generated starter ontology, federation legacy
snapshot backfill, repo-twin schema, schema-domain readiness, reviewed schema-evolution operation
storage, diff-scoped cutover, kernel-sequenced property rename/delete effects, and replayable per-op
evidence. `just check` passed with 574 tests. KM-6 is the next kernel harmonization tranche.

## The per-item loop

Every KM item runs the same loop. Do not skip steps; the loop *is* the methodology this program
exists to prove.

1. **Spec amendment first.** Draft the contract/invariant delta against the affected
   `model/bibliotek/components/component.rtg.*.sysml` spec(s), using the proposed delta in the item as the
   starting point. Specs are human-owned black-box contracts — the human approves the amendment
   before any code changes (AGENTS.md: agents may not change accepted public contracts without
   explicit approval).
2. **Contract tests second.** Encode the new invariant as boundary tests before implementation.
   The acceptance criteria below are written to be directly translatable into contract tests.
3. **Implement** inside the spec's declared `code.roots` only.
4. **Verify:** `just check` green (lint, typecheck, skills-check, test-evidence, graph-verify).
5. **Checkpoint:** local commit (no push without explicit ask), evidence noted in the commit
   message.
6. **Flip the Status line** on the item and record the evidence pointer (test file, commit).

## Dependency order

```
KM-1 (link identity)      ── independent, do first, smallest surface
KM-2 (time-shape)         ── independent of KM-1; schema + change_validation
KM-3 (identity criteria)  ── after KM-2 (shares the schema-definition extension surface)
KM-4 (link kinds)         ── after KM-1 (extends the same link-definition surface)
KM-5 (schema ops)         ── independent; migration + schema
KM-6 (write modes)        ── after KM-1 (idempotency interacts with merge semantics)
KM-7 (governance domain + memory spine) ── last; consumes KM-2/3/4 vocabulary
```

---

### KM-1 — Links carry structural identity; properties rejected loudly

Status: done
Design source: §1.1
Affected specs: `component.rtg.graph` (invariant + provided contracts), `component.rtg.change_validation` (validation report shape)

Evidence:
- `components/rtg/graph/tests/test_rtg_graph_contract.py::test_reapplying_existing_link_triple_is_idempotent_noop`
- `components/rtg/graph/tests/test_rtg_graph_contract.py::test_link_payload_with_extra_keys_is_rejected_with_reified_node_guidance`
- `components/rtg/graph/tests/test_rtg_graph_contract.py::test_import_rejects_links_with_extra_payload_keys_and_duplicate_triples`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_reports_repeated_link_write_as_per_operation_noop`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_rejects_link_write_extra_keys_with_reified_node_guidance`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_graph_state_surfaces_existing_duplicate_link_triples`
- `just check` green on 2026-07-08.

Notes: Removing link `system` required narrow downstream cleanup in MCP decoding, controller apply/live-flip handling, query tests, and repo-twin sync. Repo-twin stored snapshots had legacy link `system` payloads, so the repo-twin boundary now strips that derived metadata before restore while the graph component still rejects link payload keys. Link schema validation also needed a separate pass because links no longer participate in `system.live` filtering.

Proposed contract delta: link identity derives from `(type_key, source_uuid, target_uuid)`. The
link UUID remains a stable handle, but a second apply of an existing triple is an idempotent
no-op reported as such — never a second link. Any link payload carrying keys beyond
uuid/type/source/target is rejected with an actionable, field-naming error.

Acceptance criteria:
- Applying the same triple twice yields exactly one link; the second apply's validation report
  identifies it as an idempotent no-op (not an error, not a silent success-with-duplicate).
- A link payload with a `properties` key (or any extra key) is rejected with an error that names
  the offending keys and points to reified-node modeling.
- Existing graphs containing duplicate triples surface them via a diagnostics query
  (`rtg_validate_graph` or equivalent) so operators can collapse them.
- Contract tests at the `component.rtg.graph` boundary cover all three; `just check` green.

### KM-2 — Every node type declares a time-shape, enforced on write

Status: done
Design source: §1.2
Affected specs: `component.rtg.schema` (type-definition shape), `component.rtg.change_validation` (write-path enforcement), `component.rtg.migration` (retrofit semantics)

Evidence:
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_node_definitions_require_time_shape_and_links_reject_it`
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_state_as_of_requires_interval_fields_and_reserved_system_fields_are_rejected`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_rejects_updates_to_event_data_objects_but_allows_new_events`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_rejects_caller_owned_kernel_timestamp_fields`
- `components/rtg/migration/tests/test_rtg_migration_contract.py::test_schema_time_shape_retrofit_defaults_and_enters_cutover_plan`
- `components/rtg/controller/tests/test_rtg_controller_contract.py::test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers`
- `just check` green on 2026-07-08.

Notes: Timestamp population had to land in the controller apply path even though the main
type-shape and validation contracts live in schema/change-validation/migration. The repo-twin
store also needed two compatibility adjustments: derived legacy schema snapshots are normalized
to `state_now` before restore, and sync diffing ignores kernel-owned `created_at`/`updated_at`
when deciding whether source-derived records changed.

Proposed contract delta: node type definitions carry a required `time_shape` field:
`state_now | state_as_of | event`. Writes updating an `event`-shaped node's data object are
rejected with guidance to append a new node. `state_as_of` types require validity-interval
fields declared. Kernel owns `created_at`/`updated_at` as datetime system fields on every
record; domain schemas cannot redeclare them.

Acceptance criteria:
- Schema staging without `time_shape` on a new node type fails validation with an actionable
  error; existing types get a migration path (default `state_now` with an explicit retrofit op).
- An update targeting an `event` node is rejected at validation; appending a new node of the
  same type succeeds.
- System timestamps are populated by the kernel on every mutation and are not writable by
  callers.
- Contract tests at schema + change_validation boundaries; `just check` green.

### KM-3 — Identity criteria are schema objects; apply detects merge candidates

Status: done
Design source: §1.3
Affected specs: `component.rtg.schema` (identity-criterion definitions), `component.rtg.change_validation` (merge-candidate track), `component.rtg.controller` (apply-phase wiring)

Evidence:
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_node_identity_criteria_are_stored_and_snapshotted`
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_identity_criteria_reject_invalid_shape_and_payload_paths`
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_link_definitions_reject_identity_criteria`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_reports_data_identity_merge_candidates_without_mutation`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_reports_force_create_override_as_informational_evidence`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_preserves_current_behavior_for_types_without_identity_criteria`
- `components/rtg/controller/tests/test_rtg_controller_contract.py::test_strict_live_graph_apply_blocks_identity_merge_candidate_before_mutation`
- `components/rtg/controller/tests/test_rtg_controller_contract.py::test_validate_live_graph_changes_reports_identity_merge_candidate_without_ledger`
- `components/rtg/controller/tests/test_rtg_controller_contract.py::test_force_create_identity_override_applies_and_is_preserved_in_request_ledger`
- `just check` green on 2026-07-08.

Notes: The controller already ledgers strict validation failures, so merge-candidate rejections
preserve graph/schema/constraint/migration state while audit metadata advances. This isolated
KM-3 branch intentionally excludes the later `component.rtg.discovery` implementation commit, so
`just check` still reports the pre-existing repo-twin discovery implementation warning even though
the gate exits green.

Proposed contract delta: a node type may declare identity criteria (property set + match
strategy: exact | normalized | composite). Validation of an insert whose criteria match an
existing live node returns the match as a merge candidate in the validation report instead of
writing. Caller resolves: merge (supply existing UUID), force-create (explicit flag, recorded),
or abort.

Acceptance criteria:
- Inserting a node matching an existing node's identity criteria yields a validation report
  naming the candidate UUID(s) and match basis; nothing is written.
- Force-create writes and records the override in the ledger entry.
- Types without identity criteria behave exactly as today (no behavior change).
- Contract tests; `just check` green.

### KM-4 — Link types declare a kind; the kind drives lifecycle

Status: done
Design source: §1.4
Affected specs: `component.rtg.schema` (link-definition field), `component.rtg.graph` (cascade/append-only behavior), `component.rtg.change_validation`

Evidence:
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_link_definitions_require_link_kind_and_validate_enum`
- `components/rtg/schema/tests/test_rtg_schema_contract.py::test_legacy_snapshot_link_kind_retrofit_defaults_missing_links`
- `components/rtg/graph/tests/test_rtg_graph_contract.py::test_delete_anchor_preview_exposes_complete_raw_link_blast_radius`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_rejects_staged_link_schema_without_link_kind`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_rejects_direct_provenance_link_delete_without_mutation`
- `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py::test_validation_reports_kind_grouped_delete_blast_radius_without_mutation`
- `just check` green on 2026-07-08.

Notes: `component.rtg.graph` already exposed the complete raw delete-preview set, so KM-4
kept graph schema-neutral and put lifecycle policy in change validation. The public schema
contract change also required updating MCP schema-staging examples/codecs and repo-twin legacy
snapshot normalization so existing persisted schema snapshots get the explicit `semantic`
retrofit before restore.

Proposed contract delta: link type definitions carry a required `link_kind`:
`semantic | structural | governance | provenance | versioning | junction`. Kernel behavior
consumes it: provenance links are append-only (no delete outside migration); structural links
cascade with their source; deletion of any node returns a kind-grouped impact report before
apply.

Acceptance criteria:
- Staging a link type without `link_kind` fails validation; retrofit op defaults existing types
  to `semantic` with a report.
- Deleting a provenance link outside a migration is rejected; deleting a node with structural
  links cascades them and the validation report enumerates the blast radius grouped by kind.
- Contract tests; `just check` green.

### KM-5 — Schema evolution ops are explicit, diff-scoped, and include real deletes

Status: done (evidence: `just check` on 2026-07-09 passed with 247 tests; component
evidence includes `test_schema_evolution_ops_round_trip_and_enter_cutover_plan`,
`test_malformed_schema_evolution_op_names_field_and_leaves_no_trace`,
`test_schema_evolution_rename_property_rewrites_live_data_and_replays`,
`test_schema_evolution_delete_property_strips_live_data_with_ledger_evidence`,
`test_cutover_rejects_injected_unstaged_schema_evolution_ops`, and
`test_cutover_rejects_unreviewed_schema_property_diff`.)
Design source: §1.6
Affected specs: `component.rtg.migration`, `component.rtg.schema`, `component.rtg.controller` (cutover surface)

Proposed contract delta: the schema-op vocabulary is a closed set of explicit operations —
add/rename/retype/delete for properties, types, and link types — each declaring its data
implications. `delete_property` on a populated type sequences the data strip itself
(kernel-ordered, ledgered). Cutover presents the exact op-set diff since the last live schema
and refuses to apply ops not in the reviewed set. Malformed ops are rejected at input with
field-level errors; nothing unparseable is ever recorded to the migration record.

Acceptance criteria:
- Renaming and deleting a populated property round-trips without manual data scrubbing, with
  ledger evidence of the kernel-sequenced strip.
- Cutover output includes the full op diff; injecting an unstaged op is impossible by
  construction (test attempts it and asserts rejection).
- A malformed op is rejected with the offending field named; the migration record contains no
  trace of it.
- Contract tests; `just check` green.

Surprises:
- Strict cutover validation has to validate against a temporary graph with reviewed property data
  effects applied; otherwise a valid `rename_property` or `delete_property` fails against the
  replacement schema before the kernel-sequenced rewrite can run.
- Existing MCP recovery coverage now treats a property schema diff without reviewed
  `schema_evolution_ops` as a controller precondition failure rather than a validation failure.

Post-merge harmonization evidence (2026-07-14): the accepted migration, schema, and controller
SysML contracts now own the KM-5 vocabulary and cutover obligations; generated projections and MCP
input codecs include the operation records; and `just check` passed with 574 tests.

### KM-6 — Writes declare merge-vs-replace and ride optimistic concurrency

Status: done (evidence: `just check` on 2026-07-10 passed with 255 tests; component
evidence includes
`test_validation_rejects_missing_invalid_and_conflicting_data_write_modes`,
`test_validation_projects_merge_and_replace_properties_without_comparing_tokens`,
`test_data_object_reads_issue_stable_tokens_and_merge_replace_are_explicit`,
`test_stale_replace_returns_winning_state_and_ledgers_conflict`, and
`test_interleaved_replace_writers_cannot_both_succeed`.)
Design source: §1.7
Affected specs: `component.rtg.controller` (apply contract), `component.rtg.change_validation`, `component.storage.sql` (ledger position exposure, read-only widening if needed)

Proposed contract delta: every data-object write declares `mode: merge | replace`. Replace-mode
requires proof of a fresh read: caller supplies the record's current version token (ledger
position or content checksum); mismatch rejects with the current state returned. Batch apply
remains all-or-nothing per existing controller semantics.

Acceptance criteria:
- A write without a declared mode is rejected (or defaults to merge with an explicit report
  entry — decide in spec amendment and encode the choice in tests).
- Replace with a stale version token is rejected and returns the winning state; replace with a
  fresh token succeeds and omitted properties are removed.
- Two interleaved writers on the same record cannot both succeed in replace mode.
- Contract tests; `just check` green.

Surprises:
- Content-checksum version tokens keep optimistic-concurrency correctness independent of ledger
  persistence while object reads still expose the observed ledger position for audit and
  multi-phase coordination.
- Deterministic repo-twin synchronization must read current version tokens before replacing
  existing derived records; merge mode would preserve properties removed from repository source.

### KM-7 — Governance vocabulary as kernel-adjacent schema domain; memory spine as flagship catalog domain

Status: done (evidence: both catalog domains recreate through strict staged migration and cutover;
the agent-memory-spine contract test proves append-only Assessment facts, Actor merge-candidate
detection, and provenance-link deletion rejection; `just check` passed with 259 tests on
2026-07-10.)
Design source: §1.10, §2
Affected: `docs/schema-domains/` (two new domains), `apps/rtg_knowledge_graph` (catalog exposure); no kernel component contract changes expected

Proposed delta: author two schema domains per the existing catalog rules (prompts + walkthroughs,
not opaque payloads): (a) `governance-core` — principle, decision, convention, policy types with
provenance links, time-shapes assigned; (b) `agent-memory-spine` — the §2 spine table (Actor,
Session, Trace, Fact, Assessment, Decision, Skill, Taxonomy + ClassifiedAs, Media, Domain) with
time-shapes and link kinds declared, exercising KM-2/3/4 vocabulary end-to-end.

Acceptance criteria:
- Both domains recreate from prompt in a fresh graph via `rtg_stage_schema_migration` →
  `rtg_apply_migration_cutover` with strict validation, and each has a known-good walkthrough.
- The spine walkthrough demonstrates: an append-only Assessment (KM-2), a merge-candidate hit on
  Actor identity (KM-3), and a provenance link refusing deletion (KM-4).
- Catalog README updated; `just check` green.

---

## Program definition of done

All seven items `done`, plus one measurement artifact: a before/after count of standing
prompt-governance the MCP usage guide must carry for safe agent operation (the design doc's
falsifiable claim, feeding WP-2). When KM-1 through KM-6 land, each rule deleted from
`rtg_get_usage_guide` prose is the visible win.

Measurement: [`kernel-meta-model-prompt-governance-measurement.md`](../experiments/kernel-meta-model-prompt-governance-measurement.md).
The observed before/after count is `0 → 0`, with zero prose-rule deletions and all six behaviors
machine-enforced. The historical baseline was under-governed, so WP-2 still needs an equivalently
safe ungoverned control to test the order-of-magnitude claim.
