# RTG Agent Memory Spine Beta Prompt

Use this prompt with an agent after the `rtg_knowledge_graph` MCP server is connected. It recreates
the reference memory spine from inspectable instructions and exercises kernel time-shape, identity,
and link-kind behavior end to end.

## Prompt To Give The Agent

Build a fresh Vellis RTG agent-memory-spine graph using only the connected RTG MCP tools. Do not
read the source repository, use a hidden install payload, or bypass validation-before-mutation.

Start with `rtg_validate_graph` and `rtg_get_system_state`. Translate the model below into
`schema_definitions`, stage it with `rtg_stage_schema_migration` using migration ID
`agent-memory-spine-v1`, and apply it with `rtg_apply_migration_cutover` in strict mode. Every
anchor and data-object definition must declare its listed `time_shape`; every link must declare its
listed `link_kind`.

`Session` is included because this reference domain queries bounded working context across time.
Do not introduce Session as a required kernel type in domains that do not query it.

### Anchor and data-object model

| Anchor | Anchor time-shape | Required data type | Data time-shape | Required string fields |
| --- | --- | --- | --- | --- |
| `Actor` | `state_now` | `ActorFacts` | `state_now` | `name`, `actor_kind` |
| `Session` | `event` | `SessionFacts` | `event` | `started_at`, `scope`, `status` |
| `Trace` | `event` | `TraceFacts` | `event` | `intent`, `outcome`, `completed_at`, `ledger_position` |
| `Fact` | `state_now` | `FactBody` | `state_now` | `statement`, `status`, `observed_at` |
| `Assessment` | `event` | `AssessmentFacts` | `event` | `subject`, `judgment`, `assessed_at`, `status` |
| `Decision` | `event` | `DecisionFacts` | `event` | `title`, `rationale`, `decided_at`, `status` |
| `Skill` | `state_now` | `SkillFacts` | `state_as_of` | `name`, `description`, `status`, `effective_from`; required `valid_from`, `valid_to` datetimes |
| `Taxonomy` | `state_now` | `TaxonomyFacts` | `state_now` | `name`, `scheme`, `status` |
| `Media` | `event` | `MediaFacts` | `event` | `media_type`, `locator`, `checksum`, `captured_at` |
| `Domain` | `state_now` | `DomainFacts` | `state_now` | `name`, `description`, `status` |

An Assessment is append-only: its required `AssessmentFacts` cannot be updated, so a changed
judgment is a new Assessment anchor and facts record, optionally connected with `supersedes`.

The Actor anchor has a normalized same-type identity criterion on `display_name` using criterion
key `actor_display_name`. The identity-criterion fields are `criterion_key`, `property_paths`,
`match_strategy`, and `scope`.

### Link model

| Link type | Allowed source types | Allowed target types | Link kind |
| --- | --- | --- | --- |
| `ClassifiedAs` | `Fact`, `Assessment`, `Decision`, `Skill`, `Media` | `Taxonomy` | `semantic` |
| `derived_from` | `Fact`, `Assessment`, `Decision` | `Trace`, `Media` | `provenance` |
| `supersedes` | `Assessment`, `Decision`, `Skill` | same three types | `versioning` |
| `belongs_to_domain` | every spine anchor plus `Assessment` | `Domain` | `structural` |

### Required kernel probes

After cutover, create an Actor named `Ada Lovelace`, a Trace with a ledger-position string, a Fact,
an Assessment with `AssessmentFacts`, and a `derived_from` link from the Assessment to the Trace.
Then run these no-mutation validations:

1. **Append-only Assessment:** propose a write against the existing AssessmentFacts UUID. Expect
   `schema_object.event_update_rejected`. Append a new Assessment instead when judgment changes.
2. **Actor merge candidate:** propose a new Actor whose display name is `ada lovelace`. Expect
   `merge_candidate.identity_match` with the existing Actor UUID.
3. **Protected provenance:** propose direct deletion of the `derived_from` link. Expect
   `schema_object.provenance_link_delete_rejected` and confirm the graph is unchanged.

Finally run `rtg_validate_graph`, persist a compact snapshot, and verify replay or replay-readiness.
Report schema counts, each probe's finding and mutation state, graph validation, and durability
evidence.
