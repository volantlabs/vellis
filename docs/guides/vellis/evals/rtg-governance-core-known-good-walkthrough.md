# RTG Governance Core Known-Good Walkthrough

Use this walkthrough to recognize a successful run of
`docs/guides/vellis/evals/rtg-governance-core-beta-prompt.md`. It records contract-level expected evidence, not a
hidden schema or seed payload.

## 1. Fresh state and cutover

Call `rtg_validate_graph`, then `rtg_get_system_state`. A fresh graph reports an accepted
validation and `state_classification: "empty"`.

Stage `governance-core-v1` with strict validation, then call:

```json
{"tool":"rtg_apply_migration_cutover","arguments":{"migration_id":"governance-core-v1"}}
```

Expected schema after cutover:

- 5 anchors: `Actor`, `Principle`, `Decision`, `Convention`, `Policy`
- 5 data-object types: `ActorFacts`, `PrincipleFacts`, `DecisionFacts`, `ConventionFacts`,
  `PolicyFacts`
- 2 link types: `authored_by` (`provenance`) and `supersedes` (`versioning`)
- all 12 definitions live and strict graph validation accepted

## 2. Governance records

A representative batch creates one author and one record of each governance type, including every
required facts object. Four `authored_by` links connect the artifacts to the author. The batch is
accepted without force-create identity overrides.

The Actor definition exposes normalized same-type identity on `display_name`. Repeating the Actor
with case or spacing differences should therefore produce `merge_candidate.identity_match`
instead of silently creating a duplicate.

## 3. Provenance protection

Validate direct deletion of any live `authored_by` link. Expected result:

- `accepted: false`
- `mutation_state: "not_mutated"`
- finding code: `schema_object.provenance_link_delete_rejected`
- finding diagnostic: `link_kind: "provenance"`

The link remains live after the rejected proposal.

## 4. Completion evidence

Run `rtg_validate_graph`, persist a compact snapshot, and verify replay or replay-readiness. A run
is complete only when schema cutover, graph validation, provenance protection, and durability
evidence all succeed.
