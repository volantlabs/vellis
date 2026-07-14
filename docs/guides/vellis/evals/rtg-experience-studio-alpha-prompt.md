# RTG Experience Studio Alpha Prompt

You are recreating the `experience_studio` alpha schema domain in Vellis RTG.

The goal is to model durable product planning for graph-backed public games, visual explorations,
and interactive experiences without turning Personal Ops into a product database or mixing
planning facts into source-authoritative runtime graphs. The alpha run uses Ocean Signal Atlas as
the first planning seed.

## Start State

Use a fresh explicit RTG storage root. First call `rtg_validate_graph`, then
`rtg_get_system_state`. If the graph is not empty, stop and confirm that `experience_studio` is the
explicit target before changing schema or data.

## Reviewable Fixtures

Inspect these files before calling mutation tools:

- `docs/prototypes/experience-studio/data/experience-studio-schema-v0.json`
- `docs/prototypes/experience-studio/data/ocean-signal-atlas-planning-records.json`
- `docs/prototypes/experience-studio/data/queries/experience-portfolio-query.json`
- `docs/prototypes/experience-studio/data/queries/source-readiness-query.json`
- `docs/prototypes/experience-studio/data/queries/publication-check-query.json`

The fixtures are inspectable alpha inputs, not hidden installation payloads.

## Ownership Boundary

- Personal Ops owns operator goals, commitments, routines, reviews, and attention.
- Experience Studio owns product intent, audience, questions, scenes, interactions, source
  assessments, claims, graph-model proposals, builds, publication checks, and design decisions.
- A domain graph such as `ocean_signal_atlas` owns source-grounded regions, observations,
  snapshots, caveats, and reading trails used by the published experience.

An app is not automatically a graph root. Split graph roots by authority, schema, write policy, and
lifecycle. When a cross-graph reference is needed, carry `(graph_id, local_uuid)` through a governed
bridge or explicit reference record; never use a raw foreign UUID.

## Modeling Rules

- Links are pure triples and have no properties.
- `SourceAssessment` and `PublicationCheck` are event anchors because the relationship outcome,
  reviewer, confidence, and time need their own identity and history.
- `PrototypeBuild` and `Decision` are append-only events.
- `ExperienceQuestionFacts`, `SceneFacts`, `InteractionFacts`, `ClaimFacts`, `GraphModelFacts`, and
  `PublicationCriterionFacts` use `state_as_of` intervals.
- Long design narratives stay in repository documents or a content store; graph facts use compact
  summaries and locators.
- Commercial-use assessments are planning evidence, not legal advice or certification.
- Use useful links rather than exhaustive links.

## Candidate Identity Rules

The current MCP schema-staging facade does not expose identity criteria, so enforce these as review
rules for the alpha and encode them when the facade supports them:

- `Experience`: unique by slug.
- `Scene`, `Interaction`, `Claim`, `GraphModel`, and `PublicationCriterion`: unique by stable key
  within one experience.
- `SourceCandidate`: unique by provider plus product identifier.
- Event anchors: unique by event kind, owning experience, and event timestamp.

## Run Sequence

1. Validate the fresh graph and inspect system state.
2. Stage `experience-studio-schema-v0` using the schema fixture.
3. Cut over the migration only after strict validation succeeds.
4. Apply the Ocean Signal Atlas planning records.
5. Validate the populated graph.
6. Run the portfolio, source-readiness, and publication-check query fixtures.
7. Persist `snapshots/experience-studio-alpha.json`.
8. Verify replay from the ledger.

## Expected Alpha Shape

- 13 live anchor types.
- 13 live data-object types.
- 16 live link types.
- 27 live anchors and 27 associated data objects.
- Portfolio query: 1 row.
- Source-readiness query: 1 row.
- Publication-check query: 6 rows, including one pending human-review gate.
- No graph-validation findings.

Report exact observed counts and limitations. Do not describe the Ocean planning seed as a live
NOAA feed or as a legal publication clearance.
