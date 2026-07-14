# RTG Governance Core Beta Prompt

Use this prompt with an agent after the `rtg_knowledge_graph` MCP server is connected. It recreates
the kernel-adjacent governance vocabulary through governed RTG operations; it is not an install
payload.

## Prompt To Give The Agent

Build a fresh Vellis RTG governance-core graph using only the connected RTG MCP tools. Do not read
the source repository, use a hidden schema payload, or bypass validation-before-mutation.

Start with `rtg_validate_graph` and `rtg_get_system_state`. On an empty graph, translate the model
below into `schema_definitions`, stage it with `rtg_stage_schema_migration` using migration ID
`governance-core-v1`, and apply it with `rtg_apply_migration_cutover` in strict mode. Every anchor
and data-object definition must declare its listed `time_shape`; every link must declare its listed
`link_kind`.

### Schema model

| Kind | Type | Time-shape | Required fields or associated data |
| --- | --- | --- | --- |
| anchor | `Actor` | `state_now` | `ActorFacts`; normalized same-type identity on `display_name` |
| data object | `ActorFacts` | `state_now` | `name`, `actor_kind` strings |
| anchor | `Principle` | `state_now` | `PrincipleFacts`; the identity anchor is current while its facts are time-bounded |
| data object | `PrincipleFacts` | `state_as_of` | `statement`, `rationale`, `status`, `effective_from` strings; required `valid_from`, `valid_to` datetimes |
| anchor | `Decision` | `event` | `DecisionFacts` |
| data object | `DecisionFacts` | `event` | `title`, `rationale`, `decided_at`, `status` strings |
| anchor | `Convention` | `state_now` | `ConventionFacts`; the identity anchor is current while its facts are time-bounded |
| data object | `ConventionFacts` | `state_as_of` | `title`, `rule`, `status`, `effective_from` strings; required `valid_from`, `valid_to` datetimes |
| anchor | `Policy` | `state_now` | `PolicyFacts`; the identity anchor is current while its facts are time-bounded |
| data object | `PolicyFacts` | `state_as_of` | `title`, `rule`, `status`, `effective_from` strings; required `valid_from`, `valid_to` datetimes |

Identity criterion fields are `criterion_key`, `property_paths`, `match_strategy`, and `scope`.
Use criterion key `actor_display_name`, path `display_name`, strategy `normalized`, and scope
`same_type`.

| Link type | Allowed source types | Allowed target types | Link kind |
| --- | --- | --- | --- |
| `authored_by` | `Principle`, `Decision`, `Convention`, `Policy` | `Actor` | `provenance` |
| `supersedes` | `Principle`, `Decision`, `Convention`, `Policy` | same four governance types | `versioning` |

After cutover:

1. Create an Actor named `Eddie Austin`, one active Principle, one accepted Decision, one active
   Convention, and one active Policy with their required data objects.
2. Link each governance artifact to the Actor through `authored_by`.
3. Validate and apply the batch in strict mode, then run `rtg_validate_graph`.
4. Validate a direct deletion of one `authored_by` link. It must be rejected with
   `schema_object.provenance_link_delete_rejected` and must not mutate the graph.
5. Persist a compact snapshot and verify replay or replay-readiness.

Finish with a short report containing the migration and cutover result, live schema counts,
governance object counts, provenance-deletion finding, graph validation result, and durability
evidence.
