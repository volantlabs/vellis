---
name: rtg-knowledge-graph-mcp
description: Operate the Vellis RTG Knowledge Graph MCP server for agent-driven graph work. Use when an agent has RTG MCP tools such as rtg_validate_graph, rtg_apply_live_graph_changes, rtg_stage_knowledge_changes, rtg_apply_migration_cutover, rtg_execute_query, snapshots, or runtime reconstruction, especially for schema evolution, validation recovery, and query authoring.
---

# RTG Knowledge Graph MCP

Use the RTG MCP server as a curated Vellis application façade, not as a loose JSON store or an arbitrary component invoker. Start by validating the connection and reading system state, discover live schema before writing, use the correct mutation lane, and query through `rtg_execute_query` instead of manually scanning objects.

## Operator Card

1. Validate the connection with `rtg_validate_graph({})`.
2. Read `rtg_get_system_state({})` to classify the domain as empty, schema-only, populated, or staged and confirm `runtime.health` is `ready`.
3. If examples are needed, call `rtg_get_usage_guide` with `everyday_life_schema`, `schema_design`, `capabilities`, `workflow_patterns`, `request_patterns`, `mcp_bootstrap_checklist`, `operator_card`, `schema_staging_minimal`, `tool_call_shapes`, `live_write`, `lookup_examples`, `query_examples`, `recovery_and_replay`, `migration_history`, or `migration_abandonment`.
4. Discover available anchor types with `rtg_discover_anchor_types`, then read details with `rtg_get_schema_pack`.
5. Stage initial schema or schema evolution with `rtg_stage_schema_migration` unless you need the advanced normalized-batch surface.
6. Make staged schema live with `rtg_apply_migration_cutover`.
7. Resolve existing object UUIDs with `rtg_resolve_anchor_by_fact` or `rtg_execute_query` lookup examples before link writes; dry-run risky graph changes with `rtg_validate_live_graph_changes` or repeated anchor-with-facts records with `rtg_validate_live_anchor_records`.
8. Write live graph data with `rtg_apply_live_graph_changes`; for repeated anchor plus required-facts ingestion, use `rtg_apply_live_anchor_records`.
9. Preserve recovery evidence with coordinated snapshots, runtime reconstruction verification, and runtime-backed migration history.

## First Calls

If the RTG MCP tools are not already connected, use the repo-generated MCP metadata before writing
custom scripts. Prefer the focused `mcp-config` CLI output, which is the complete client block and
launches the stdio server from absolute paths. The larger diagnostic metadata exposes the same
block as `mcp.client_config`. For a Vellis app
that is already running locally, use `mcp.transports.localhost_http.client_config` and connect to
`http://127.0.0.1:8765/mcp` by default. The localhost HTTP transport is unauthenticated and should
remain bound to `127.0.0.1`.

1. Call `rtg_validate_graph` with `{}`.
2. Expect `ok: true`, `result.accepted: true`, and no findings for a fresh graph.
3. Call `rtg_get_system_state` with `{}` and follow `recommended_next_steps`.
4. Call `rtg_get_usage_guide` with `topic: "workflow_patterns"` when you need common RTG operating sequences, or `topic: "request_patterns"` when the user prompt gives a goal but not a tool sequence.
5. Call `rtg_get_usage_guide` with `topic: "mcp_bootstrap_checklist"` when you need the full repo-blind workflow through MCP.
6. Call `rtg_discover_anchor_types` or `rtg_get_schema_pack` before inventing type keys or property names.

If the graph has no live schema, create schema with `rtg_stage_schema_migration`, then make it live with `rtg_apply_migration_cutover`. When repository skills are available, use `$rtg-schema-design` before authoring or evolving a consequential schema.

## Mutation Lanes

- Use `rtg_apply_live_graph_changes` for normal live graph CRUD after schema exists.
- Use `rtg_validate_live_graph_changes` before risky imports or recovery probes; it returns generated IDs and validation findings without component-state mutation. The runtime still records the request and response.
- Use `rtg_validate_live_anchor_records` and `rtg_apply_live_anchor_records` when the payload is mostly anchors with associated required facts. Both compile to canonical `graph_changes`. Validation returns the submitted low-level payload for audit; successful apply defaults to a compact result with durable generated IDs and fact-position correlation.
- `rtg_apply_live_graph_changes` returns the full canonical low-level mutation result and does not accept `response_options`. Compact mutation response shaping belongs to `rtg_apply_live_anchor_records` and `rtg_stage_schema_migration`.
- Use `rtg_resolve_anchor_by_fact` for common exact anchor lookups before link writes. It compiles to `rtg_execute_query` and returns the submitted query, matches, count, and guidance.
- Use `rtg_stage_schema_migration` for ordinary schema bootstrap or schema evolution. It accepts type-key-oriented schema definitions, generates candidate UUIDs, and fills migration membership. Keep every `(kind, type_key)` pair unique within the request. Compact responses are the default and correlate durable candidate UUIDs through `generated_schema_ids["kind:type_key"]`; request `response_options.format: "full"` only when the submitted low-level payload is needed for debugging.
- Use `rtg_stage_knowledge_changes` only for advanced schema, constraint, migration, and non-live candidate graph changes; staged candidates must be referenced by a migration record in the same request.
- Use `rtg_apply_migration_cutover` to make staged candidates live and retire replaced records.
- Use `rtg_abandon_migration` to retire accidental draft, ready, or failed staged work; the runtime records its causal trace.
- Use `rtg_validate_graph` before and after risky changes.
- Use `rtg_export_system_snapshot`, `rtg_persist_system_snapshot`, `rtg_list_persisted_snapshots`, `rtg_load_persisted_snapshot`, `rtg_restore_from_snapshot`, `rtg_replay_ledger`, `rtg_verify_replay_from_ledger`, and `rtg_list_migration_history` for recovery, audit, and restart checks. Prefer `return_snapshot:false` for compact snapshot persistence/load. Snapshots are restored explicitly; they are not runtime-reconstruction seeds. Ordinary restart reconstructs the latest confirmed state automatically, and historical cursors must be evaluated in an isolated copy of the complete data root.

Always use `validation_mode: "strict"` unless the user explicitly asks to skip validation for a controlled recovery or debugging step. If a response has `ok: false`, inspect `error.message` and `error.diagnostic`; when `validation_report` is present, use its findings to repair the smallest payload problem and retry.

Structured diagnostics are a generic correction channel for agents. Read `diagnostic.path` for where the payload or operation failed, `diagnostic.remedy` for how to retry, `diagnostic.accepted_fields` and `diagnostic.minimal_example` for the valid shape, and `diagnostic.guide_topics` for MCP usage-guide topics to fetch. `diagnostic.mutation_state` says whether the failed operation was not mutated, live state was preserved, or another state outcome applies. Diagnostics must teach RTG contracts only; do not treat them as domain-specific schema answers.

Dry-run validation tools use `validation_options` with only `tracks` and `finding_limit`. Do not pass `validation_options.mode`; mutation tools use the separate `validation_mode` field.

When staging non-live graph candidates, include every candidate object ID in the migration's `graph_make_live` list: anchors, associated data objects, and links. Listing only anchors is insufficient. Strict staging validates migration records introduced in the same request against their projected cutover state, so invalid candidate data should return `validation_report` findings before the records are staged.

For validation exercises, prefer schema-required fields and link schema rules first. Use constraint definitions when the rule naturally matches the documented `query_pattern` or `cardinality` payload shapes below; do not invent new constraint kinds from prose alone.

## References

Every object reference is exactly one of:

```json
{"local_ref": "task-collect-feedback"}
```

```json
{"resource_id": "11111111-1111-1111-1111-111111111111"}
```

Use `local_ref` inside one request to connect newly written objects. Use `resource_id` for objects returned by earlier calls.

Do not reuse a `local_ref` from a previous request. Query or read the existing object and pass its returned UUID as `resource_id`.

Call `rtg_resolve_anchor_by_fact` for common exact fact predicates. Use `matches[0].resource_id` only when `match_count` is exactly 1. If the helper is unavailable or a broader lookup is needed, call `rtg_get_usage_guide` with `topic: "lookup_examples"` for copy-pastable queries and use the returned binding's anchor UUID as `resource_id`. Do not guess UUIDs.

## Live Graph Writes

For repeated anchor plus facts ingestion, prefer the compact anchor-record facade:

```json
{
  "anchor_records": [
    {
      "ref": {"local_ref": "item-alpha"},
      "type": "Item",
      "display_name": "Item alpha",
      "facts": [
        {
          "type": "ItemFacts",
          "properties": {
            "title": "Item alpha",
            "category": "example",
            "status": "active"
          }
        }
      ]
    }
  ],
  "validation_mode": "strict"
}
```

Use `rtg_validate_live_anchor_records` with the same `anchor_records` payload for no-mutation validation.

Successful anchor-record applies default to `response_options: {"format":"compact"}`. Read
durable identities from `result.generated_ids`; `result.generated_refs.facts` maps automatically
named fact refs back to anchor/fact positions. Use `format:"full"` only when inspecting the compiled
`submitted_graph_changes` is necessary.

After the Item schema example below has been cut over, this minimal live write should succeed:

```json
{
  "graph_changes": {
    "anchor_writes": [
      {
        "ref": {"local_ref": "item-alpha"},
        "type": "Item",
        "display_name": "Item alpha"
      }
    ],
    "data_object_writes": [
      {
        "ref": {"local_ref": "item-alpha-facts"},
        "type": "ItemFacts",
        "properties": {
          "title": "Item alpha",
          "category": "example",
          "status": "active",
          "priority": 1
        },
        "anchor_refs": [{"local_ref": "item-alpha"}]
      }
    ]
  },
  "validation_mode": "strict"
}
```

Do not send schema, constraint, migration, or non-live candidate work to `rtg_apply_live_graph_changes`.
Do not pass `response_options` to `rtg_apply_live_graph_changes`; use its full result or choose the anchor-record façade when a compact mutation response is important.

For dry-runs, use the same `graph_changes` payload with `rtg_validate_live_graph_changes`. It resolves `local_ref` values, returns `generated_ids` and `resolved_graph_changes`, and leaves component state unchanged. Its message trace remains part of runtime history.

For link writes, both endpoint anchors must exist or be written in the same request, and a live link schema must allow the source and target anchor types:

```json
{
  "ref": {"local_ref": "item-related"},
  "type": "related_to",
  "source_ref": {"local_ref": "item-alpha"},
  "target_ref": {"resource_id": "22222222-2222-2222-2222-222222222222"}
}
```

## Schema And Cutover

Prefer `rtg_stage_schema_migration` for schema-only work. Schema payload references use type keys such as `"ItemFacts"` inside fields like `required_data_types`; migration lifecycle membership uses generated candidate UUIDs in `schema_make_live` and `schema_make_non_live`.

Stage schema definitions as non-live candidates only when you need the advanced normalized-batch surface. Reference them from a ready migration in the same request:

```json
{
  "knowledge_changes": {
    "schema_changes": {
      "definition_writes": [
        {
          "ref": {"resource_id": "10000000-0000-0000-0000-000000000001"},
          "definition": {
            "uuid": "10000000-0000-0000-0000-000000000001",
            "kind": "anchor",
            "type_key": "Item",
            "description": "A durable item.",
            "payload": {"required_data_types": ["ItemFacts"]},
            "system": {"live": false}
          }
        },
        {
          "ref": {"resource_id": "10000000-0000-0000-0000-000000000002"},
          "definition": {
            "uuid": "10000000-0000-0000-0000-000000000002",
            "kind": "data_object",
            "type_key": "ItemFacts",
            "description": "Structured facts associated with an item anchor.",
            "payload": {
              "properties": {
                "title": {"required": true, "value_kinds": ["string"]},
                "category": {"required": true, "value_kinds": ["string"]},
                "status": {
                  "required": true,
                  "value_kinds": ["string"],
                  "allowed_values": ["active", "waiting", "done"]
                },
                "priority": {
                  "required": false,
                  "value_kinds": ["integer"],
                  "minimum": 0,
                  "maximum": 5
                }
              }
            },
            "system": {"live": false}
          }
        }
      ]
    },
    "migration_changes": {
      "migration_writes": [
        {
          "ref": {"resource_id": "10000000-0000-0000-0000-000000000010"},
          "migration": {
            "migration_id": "10000000-0000-0000-0000-000000000010",
            "description": "Introduce live item anchors with required item facts.",
            "status": "ready",
            "schema_make_live": [
              "10000000-0000-0000-0000-000000000001",
              "10000000-0000-0000-0000-000000000002"
            ]
          }
        }
      ]
    }
  },
  "validation_mode": "strict"
}
```

If the same migration stages non-live graph candidates, include all of their candidate UUIDs in `graph_make_live`. This includes anchors, associated data objects, and links.

Use field refinements only for stable semantics: `allowed_values` for a closed scalar set,
`format` values `date`, `date_time`, or `uri` for strings, inclusive `minimum`/`maximum` for numbers,
and RE2 `pattern` for strings. Refinements also apply recursively inside object properties and list
items; strict projected-cutover validation checks existing data against them.

Then call:

```json
{"migration_id": "10000000-0000-0000-0000-000000000010"}
```

with `rtg_apply_migration_cutover`. If cutover fails, the live graph should remain unchanged. When `validation_report` is present, repair the staged candidate or graph data from its findings; otherwise call `rtg_validate_graph` with the migration ID to get projected-state findings before retrying.

## Constraint Definitions

Stage constraints through `rtg_stage_knowledge_changes` and make them live through migration cutover. Constraint candidates must be non-live and listed in `constraint_make_live`.

A `query_pattern` constraint uses a normal RTG `query_spec` plus `expectation`:

```json
{
  "ref": {"resource_id": "20000000-0000-0000-0000-000000000001"},
  "constraint": {
    "uuid": "20000000-0000-0000-0000-000000000001",
    "kind": "query_pattern",
    "target_type_keys": ["Item"],
    "display_name": "At least one active item",
    "description": "The graph should contain at least one active item.",
    "payload": {
      "query_spec": {
        "anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}],
        "data_requirements": [
          {
            "name": "facts",
            "anchor_bucket": "item",
            "data_type_key": "ItemFacts",
            "predicates": [{"path": ["status"], "operator": "equals", "value": "active"}]
          }
        ]
      },
      "expectation": "must_match_at_least_one"
    },
    "system": {"live": false}
  }
}
```

A `cardinality` constraint uses a `query_spec`, `counted_binding`, and optional `minimum` or
`maximum`. An optional `group_by_bindings` list applies the bound independently to each unique tuple
of those query bindings; omit it for one global count. Use cardinality when the rule is about count
bounds rather than just whether a pattern exists.

## Queries

Use exact key names. The decoder rejects common aliases such as `types`, `fields`, and `property_predicates`.

```json
{
  "query_spec": {
    "anchor_buckets": [
      {"name": "item", "anchor_type_keys": ["Item"]}
    ],
    "data_requirements": [
      {
        "name": "facts",
        "anchor_bucket": "item",
        "data_type_key": "ItemFacts",
        "predicates": [
          {"path": ["category"], "operator": "equals", "value": "example"},
          {"path": ["status"], "operator": "equals", "value": "active"}
        ]
      }
    ],
    "return_spec": {
      "anchor_buckets": ["item"],
      "data_requirements": ["facts"],
      "properties": [
        ["facts", ["title"]],
        ["facts", ["priority"]]
      ]
    }
  },
  "query_options": {"live_filter": "live"},
  "response_options": {"format": "properties_only"}
}
```

For relationship questions, bind both endpoints and require a typed link:

```json
{
  "query_spec": {
    "anchor_buckets": [
      {"name": "source", "anchor_type_keys": ["Item"]},
      {"name": "target", "anchor_type_keys": ["Item"]}
    ],
    "link_requirements": [
      {
        "name": "relationship",
        "source_bucket": "source",
        "target_bucket": "target",
        "link_type_keys": ["related_to"]
      }
    ],
    "return_spec": {
      "anchor_buckets": ["source", "target"],
      "link_requirements": ["relationship"]
    }
  },
  "query_options": {"live_filter": "live"}
}
```

Supported predicate operators are `exists`, `equals`, `not_equals`, `lt`, `lte`, `gt`, `gte`, `contains`, `in`, `substring`, and `regex`.

When using `response_options.format: "properties_only"`, read non-aggregate compact rows from `result.rows[].properties`; aggregate compact rows retain `row_index`, `group_by`, and caller-named aggregation fields directly. Query responses identify themselves with `result.kind` (`full` or `properties_only`). Count returned rows with `result.row_count`, and use the full response when you need bindings or UUIDs. Give every anchor, link, and data requirement a name that is unique across the whole query.

For larger results, use `query_options.limit` and `offset`; deterministic ordering occurs before
slicing. `distinct_rows:true` deduplicates exact returned projections before pagination and must not
be combined with aggregation. For counts,
use `return_spec.group_by` paths that also appear in `return_spec.properties`, plus `aggregations`
with `function:"count"`; counts are distinct binding UUIDs. A link requirement may set
`required:false` when a source row must survive without a matching link.

## Recovery

- Missing required data: add the required associated data object named by the validation finding.
- Wrong property kind: fix the property path named by the finding, usually inside `data_object_writes.properties`.
- Invalid link endpoint type: first resolve or create real endpoint anchors, then write a link whose existing endpoint types violate the live link schema. If the finding is `schema_object.reference_missing`, repair the endpoint reference before treating the probe as an endpoint-type validation.
- Recovery probes: use `rtg_validate_live_graph_changes` or `rtg_validate_live_anchor_records` first. Corrected bad-write examples should not become live graph content unless the user explicitly wants them. Dry-run validation evidence can stay in the final brief; create a durable evidence record only when graph evidence is explicitly desired.
- Unknown type key: call `rtg_discover_anchor_types` and `rtg_get_schema_pack`; do not guess.
- Candidate not migration-scoped: add every staged candidate UUID to `schema_make_live`, `constraint_make_live`, or `graph_make_live` as appropriate.
- Failed cutover: inspect the failed migration status metadata, validate with `migration_ids`, repair staged candidates or live data, and retry or call `rtg_abandon_migration`.
- Intentional failed-cutover test: stage the invalid candidate with `validation_mode: "skip"`, then call cutover in strict mode and verify the live state is preserved.
- Restart or persistence check: persist a compact snapshot, list and load it with `return_snapshot:false`, restart the current app normally, then call `rtg_verify_replay_from_ledger` with empty options to inspect the verified startup reconstruction report. For an earlier runtime cursor, copy the complete data root and reconstruct the isolated copy; never rewind live state in place.
- Earlier-version transfer: open the source with the version that created it, validate and export one full coordinated snapshot, initialize a fresh current destination, and restore through `rtg_restore_from_snapshot`. Validate counts and restart reconstruction before retiring the source. Never import, merge, or replay an earlier controller ledger; follow `docs/guides/vellis/snapshot-transfer.md`.
- Migration audit: `rtg_get_system_state.migration_counts_by_status` describes only the current migration store. Use `rtg_list_migration_history` for runtime-trace projections named `knowledge_staged`, `cutover_requested`, and `migration_abandoned`; use each event's trace disposition and arguments, and inspect the causal trace through trusted developer APIs when deeper outcome evidence is required.

## Domain Graph Pattern

For a domain graph, a reasonable design often models durable nouns as anchors, mutable attributes as associated data objects, and traversable relationships as typed links.

Treat this as domain modeling guidance, not a prebuilt schema. The actual anchor types, fact types, required fields, and links should come from the user's prompt.
