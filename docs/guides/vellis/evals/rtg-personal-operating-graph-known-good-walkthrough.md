# RTG Personal Operating Graph Known-Good Walkthrough

Use this walkthrough to recognize a successful run of
`docs/guides/vellis/evals/rtg-personal-operating-graph-beta-prompt.md`. It is not a script. It records the
expected shape and one captured run against the RTG MCP tools.

Captured run: 2026-07-08, through callable `rtg_knowledge_graph` MCP tools in Codex.
A manual localhost HTTP server was not needed. The MCP tools were already connected. If tools are
not connected in a future run, use the generated metadata from `just rtg-eval-info <storage-root>`
or start localhost HTTP with `just rtg-mcp-http <storage-root> 127.0.0.1 8765 /mcp`.

Note: during the captured run, an empty live anchor-record write was accidentally submitted while
loading the cutover tool. It recorded a no-op ledger entry at position 4, mutated no graph or
schema state, and does not affect the counts below.

## 1. Connection And Empty State

First call:

```json
{"tool": "rtg_validate_graph", "arguments": {}}
```

Expected result: `ok: true`, `result.accepted: true`, and no findings.

Then call:

```json
{"tool": "rtg_get_system_state", "arguments": {}}
```

Expected fresh state:

- `state_classification: "empty"`
- zero live schema definitions
- zero live graph objects
- `recommended_workflows` includes `schema_bootstrap`

## 2. Bootstrap Schema

Stage a schema migration named `personal-operating-graph-v1` with:

- 9 anchor types: `Person`, `Area`, `Goal`, `Commitment`, `Decision`, `Review`, `Evidence`,
  `RelationshipContext`, `Routine`
- 9 required fact types: `PersonFacts`, `AreaFacts`, `GoalFacts`, `CommitmentFacts`,
  `DecisionFacts`, `ReviewFacts`, `EvidenceFacts`, `RelationshipContextFacts`, `RoutineFacts`
- 7 link types: `belongs_to`, `supports`, `owns`, `justifies`, `reviewed_in`, `involves`,
  `informs`

Captured staging evidence:

- transaction: `0fb0141f-fa24-4561-b29c-5b766a2094ac`
- ledger position: `2`
- schema writes: `25`
- validation findings: none

Apply cutover:

```json
{"tool": "rtg_apply_migration_cutover", "arguments": {"migration_id": "personal-operating-graph-v1"}}
```

Captured cutover evidence:

- transaction: `ddf2fd83-b58f-48d9-a1db-e4fc6a40e99f`
- ledger position: `6`
- 25 live status changes
- validation findings: none

After cutover, `rtg_get_system_state` should report `state_classification: "schema_only"` and 25
live schema definitions.

## 3. Ingest Seed Graph

Use `rtg_apply_live_anchor_records` to ingest:

- 3 people
- 5 areas
- 5 goals
- 6 commitments
- 4 decisions
- 2 reviews
- 6 evidence records
- 3 relationship contexts
- 4 routines

Use sparse useful links rather than exhaustive links. In the captured run, every commitment and
decision had at least one meaningful area, support, ownership, review, evidence, or context link.

Captured ingestion evidence:

- transaction: `674e98bb-91b1-458c-94bd-3f815af39439`
- ledger position: `8`
- graph writes: `169`
- validation findings: none

Date-like placeholder assumptions used in the captured run:

- today: `2026-07-08`
- next Friday: `2026-07-10`
- tomorrow: `2026-07-09`
- Sunday: `2026-07-12`
- month end: `2026-07-31`
- next mentor agenda due: `2026-07-14`
- insurance expiration placeholder: `2026-08-15`
- tax prep window placeholder: `2027-02-15`

## 4. Query Outcomes

Expected live object counts after ingestion:

| Kind | Counts |
| --- | --- |
| anchors | `Area:5`, `Commitment:6`, `Decision:4`, `Evidence:6`, `Goal:5`, `Person:3`, `RelationshipContext:3`, `Review:2`, `Routine:4` |
| data objects | one matching required facts object for each anchor |
| links | `belongs_to:30`, `supports:18`, `owns:17`, `justifies:7`, `reviewed_in:11`, `informs:7`, `involves:3` |

Attention this week:

- commitment due this week: `Invite first beta testers`, professional, high priority,
  due `2026-07-10`
- routines due this week: `Weekday health baseline` on `2026-07-09`, `Friday Vellis review` on
  `2026-07-10`, `Sunday household reset` on `2026-07-12`

High-priority commitment evidence:

- `Invite first beta testers` has no direct `justifies` evidence link. This is a useful evidence
  gap.
- `Renew home insurance` is justified by `Insurance renewal notice` with high confidence.

Active goals and supporting work:

- `Clarify the next career narrative` is supported by `Prepare mentor agenda`.
- `Keep household administration calm` is supported by `Renew home insurance` and
  `Sunday household reset`.
- `Launch a trustworthy Vellis beta` is supported by `Invite first beta testers` and
  `Friday Vellis review`.
- `Rebuild a sustainable health rhythm` is supported by `Schedule annual physical` and
  `Weekday health baseline`.

Decisions due for review by `2026-08-05`:

- `Keep tax planning waiting until document evidence arrives`, review `2026-07-31`
- `Treat the life graph as a substrate hardening harness`, review `2026-07-31`
- `Use Friday review as the primary Vellis operating cadence`, review `2026-08-05`

Relationship open loops:

- Jordan: align budget and insurance tasks
- Morgan: send agenda before next meeting
- Self: protect focus from stale obligations

Commitments made to someone other than Self:

- `Prepare mentor agenda`, made to Morgan, due `2026-07-14`
- `Review monthly budget`, made to Jordan, due `2026-07-31`
- `Renew home insurance`, made to Jordan, due `2026-08-15`

## 5. Bad-Write Recovery Probes

Use no-mutation validation tools for recovery probes.

Probe 1: `Commitment` anchor with no `CommitmentFacts`.

Expected result:

- `accepted: false`
- `mutation_state: "not_mutated"`
- finding code: `schema_object.missing_required_associated_data`
- remedy: add the required associated data object or use the anchor-record facade

Probe 2: `CommitmentFacts.due` with a numeric value.

Expected result:

- `accepted: false`
- `mutation_state: "not_mutated"`
- finding code: `schema_object.property_kind_mismatch`
- path: `CommitmentFacts.properties.due`
- remedy: replace the value with an allowed string value

## 6. Failed Schema Evolution

Stage migration `decision-risk-level-required-v1` with `validation_mode: "skip"` to replace
`DecisionFacts` with a stricter schema that requires `risk_level`, without backfilling live
decision facts.

Captured staging evidence:

- transaction: `d80aea84-c1be-4a25-a349-7235d227cccc`
- ledger position: `10`
- staged schema candidates: `1`

Attempt strict cutover. Expected failure:

- transaction: `9c85e3a1-69ad-4f1e-9836-e91272bbd486`
- ledger position: `12`
- error type: `RtgControllerValidationFailed`
- diagnostic mutation state: `live_state_preserved`
- finding codes include `migration_cutover.post_state_invalid` and
  `schema_object.missing_required_property`
- missing path: `DecisionFacts.properties.risk_level`

After failure, `rtg_validate_graph({})` should still return accepted current live state.

Then abandon the failed migration:

- transaction: `d5c3750f-22ff-42db-895f-fbfa5e5171dd`
- ledger position: `14`
- abandoned migration: `decision-risk-level-required-v1`
- pruned staged schema candidate count: `1`

## 7. Snapshot And Replay

Persist a compact snapshot:

```json
{
  "tool": "rtg_persist_system_snapshot",
  "arguments": {
    "relative_path": "snapshots/personal-operating-graph-v1.json",
    "return_snapshot": false
  }
}
```

Captured snapshot evidence:

- relative path: `snapshots/personal-operating-graph-v1.json`
- transaction: `d9d0ec16-c525-4066-87a7-fd5a177c3210`
- ledger position: `15`
- compact summary matches the live graph counts above

Then call `rtg_list_persisted_snapshots` and `rtg_load_persisted_snapshot` with
`return_snapshot:false`. Expected result: the persisted snapshot is listed and the loaded compact
summary matches the live graph counts.

Verify replay from ledger in scratch state:

```json
{"tool": "rtg_verify_replay_from_ledger", "arguments": {"replay_options": {}}}
```

Captured replay evidence:

- status: `replay_verified`
- ledger records seen: `15`
- mutating requests replayed: `7`
- replay start source: `empty`
- validation accepted: true
- replayed post-state counts match the live graph counts above

## 8. Modeling Limits To Report

- The model intentionally uses string fields for status, priority, confidence, cadence, and
  reversibility. Enum constraints are not modeled yet.
- Evidence locators are placeholders except for the Vellis repository URL.
- Relationship context is sparse and deliberately avoids exhaustive personal history.
- Link counts are useful for the beta path, but a future reference app may want stricter
  constraints for required evidence on high-priority commitments.
- The failed `risk_level` evolution proves cutover safety, not that `risk_level` is the right
  durable field.
