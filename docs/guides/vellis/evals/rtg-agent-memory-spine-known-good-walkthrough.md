# RTG Agent Memory Spine Known-Good Walkthrough

Use this walkthrough to recognize a successful run of
`docs/guides/vellis/evals/rtg-agent-memory-spine-beta-prompt.md`. It records expected contract evidence and does
not contain an opaque schema payload.

## 1. Fresh strict cutover

Call `rtg_validate_graph`, then `rtg_get_system_state`. Stage `agent-memory-spine-v1` through
`rtg_stage_schema_migration` and apply it through `rtg_apply_migration_cutover` with strict
validation.

Expected live schema:

- 10 anchors: `Actor`, `Session`, `Trace`, `Fact`, `Assessment`, `Decision`, `Skill`, `Taxonomy`,
  `Media`, `Domain`
- 10 required data-object types, including append-only `AssessmentFacts`
- 4 links: `ClassifiedAs`, `derived_from`, `supersedes`, `belongs_to_domain`
- 24 live definitions total
- `Actor` has normalized same-type identity on `display_name`
- `AssessmentFacts` has `time_shape: event`
- `derived_from` has `link_kind: provenance`

Strict cutover and the following `rtg_validate_graph` call must both be accepted.

## 2. Minimal evidence graph

Apply one strict batch containing:

- Actor `Ada Lovelace` with `ActorFacts`
- one Trace with immutable `TraceFacts` and a ledger-position string
- one Fact with `FactBody`
- one Assessment with immutable `AssessmentFacts`
- one `derived_from` link from the Assessment to the Trace

The write is accepted and leaves the graph valid.

## 3. KM-2: append-only Assessment

Call `rtg_validate_live_graph_changes` with a data-object write targeting the existing
AssessmentFacts UUID. The write must declare `mode: "merge"`, but event immutability still rejects
it.

Expected evidence:

- `accepted: false`
- `mutation_state: "not_mutated"`
- finding code: `schema_object.event_update_rejected`
- finding diagnostic: `time_shape: "event"`

## 4. KM-3: Actor identity

Validate a new Actor with display name `ada lovelace`. Expected evidence:

- `accepted: false`
- finding code: `merge_candidate.identity_match`
- diagnostic identifies type `Actor`, criterion `actor_display_name`, and the existing Actor UUID

The caller must target the existing Actor, abort, or explicitly justify force creation.

## 5. KM-4: provenance lifecycle

Validate direct deletion of the live `derived_from` link. Expected evidence:

- `accepted: false`
- `mutation_state: "not_mutated"`
- finding code: `schema_object.provenance_link_delete_rejected`
- finding diagnostic: `link_kind: "provenance"`

The provenance link remains live.

## 6. Completion evidence

Run `rtg_validate_graph`, persist a compact snapshot, and verify replay or replay-readiness. The
domain is known-good only when strict cutover, all three kernel probes, graph validation, and
durability evidence succeed.
