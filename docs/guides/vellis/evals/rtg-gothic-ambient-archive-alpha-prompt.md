# RTG Gothic Ambient Archive Alpha Prompt

You are recreating the `gothic_ambient_archive` alpha schema domain in Vellis RTG.

The goal is to model a source-grounded public-domain Gothic literature graph for ambient visual
exploration and LLM docent navigation. The alpha run uses the Lucy Westenra transformation slice
from `Dracula` as planning-grade graph data. It is not authoritative literary ingestion yet.

## Start State

Start with a fresh explicit RTG storage root when possible. First calls:

```json
{"tool": "rtg_validate_graph", "arguments": {}}
```

```json
{"tool": "rtg_get_system_state", "arguments": {}}
```

If state is `needs_replay`, resolve replay or switch to a fresh explicit storage root before
writing. Do not layer this alpha domain into an ambiguous in-memory state.

## Source Files

Review these repo files before calling mutation tools:

- `docs/prototypes/nocturne-archive/graph-handoff.md`
- `docs/prototypes/nocturne-archive/data/gothic-ambient-schema-v0.json`
- `docs/prototypes/nocturne-archive/data/lucy-transformation-live-records.json`
- `docs/prototypes/nocturne-archive/data/queries/lucy-event-cluster-query.json`
- `docs/prototypes/nocturne-archive/data/queries/blood-trail-query.json`
- `docs/prototypes/nocturne-archive/data/queries/threshold-motif-query.json`

These JSON files are reviewable alpha fixtures, not hidden install blobs. Inspect them, then submit
their `arguments` through the named tool.

Do not auto-install opaque schema payloads. The point of these files is to make the alpha graph
model inspectable before mutation.

## Schema Modeling Rules

- Links are pure triples. Do not add link properties.
- Ordered reading-trail steps are `TrailStop` anchors with `TrailStopFacts.ordinal`, connected by
  `includes_stop`, `focuses_on`, and optional `follows` links.
- Event anchors and `EventFacts` use `time_shape: event`; corrections should append new event
  facts or new event anchors rather than editing source-grounded events in place.
- Long source text does not live in graph properties. Use `Passage` records with source markers and
  quote policy.
- Public-domain and license status are facts to verify, not assumptions.
- Style packs are presentation-only records. They may guide rendering and docent tone but cannot
  change graph claims.

## Run Sequence

1. Validate graph state.
2. Stage the schema using `rtg_stage_schema_migration` with the arguments from
   `gothic-ambient-schema-v0.json`.
3. Cut over the staged schema with `rtg_apply_migration_cutover`.
4. Validate graph state again.
5. Apply the Lucy planning seed using `rtg_apply_live_anchor_records` with the arguments from
   `lucy-transformation-live-records.json`.
6. Validate graph state again.
7. Run the three query fixtures with `rtg_execute_query`.
8. Persist a compact snapshot, preferably:

```json
{
  "tool": "rtg_persist_system_snapshot",
  "arguments": {
    "relative_path": "snapshots/gothic-ambient-archive-alpha-lucy.json",
    "return_snapshot": false
  }
}
```

## Expected Alpha Shape

After schema cutover and seed ingestion, a clean fresh run should have:

- 12 live anchor types.
- 12 live data-object types.
- 16 live link types.
- 53 live anchors.
- 53 live data objects.
- no validation findings.

Expected query row counts:

- `lucy-event-cluster-query.json`: 5 rows.
- `blood-trail-query.json`: 6 rows.
- `threshold-motif-query.json`: 3 rows.

## Final Brief

Report:

- whether schema staging, cutover, seed ingestion, graph validation, and queries passed
- exact live object counts
- query row counts
- snapshot or replay evidence
- remaining limitations, especially unverified source spans and license facts
