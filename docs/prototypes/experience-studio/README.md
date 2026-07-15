# Experience Studio

Experience Studio is the governed planning graph for graph-backed public games, visual
explorations, and interactive experiences. It is deliberately separate from Personal Ops and from
source-authoritative domain graphs.

The first seed is Ocean Signal Atlas. It records product intent, audience, framing question,
scenes, interactions, source assessment, public claim, graph-model proposal, prototype build,
publication criteria, checks, and the decision to preserve the three-layer graph boundary.

## Ownership

- Personal Ops: operator goals, commitments, routines, reviews, and attention.
- Experience Studio: reusable product planning and publication readiness.
- Domain graphs: source-grounded facts used by the published experience.

## Reviewable Inputs

- `data/experience-studio-schema-v0.json`: 13 anchor types, 13 fact types, and 16 pure-triple link
  types.
- `data/ocean-signal-atlas-planning-records.json`: 27 planning anchors and 39 links.
- `data/queries/experience-portfolio-query.json`: product, audience, question, model, and build.
- `data/queries/source-readiness-query.json`: source assessment with its owning experience.
- `data/queries/publication-check-query.json`: ordered publication checks and open gates.

The registered monograph exposes that final query as the descriptor-declared
`experience_publication_readiness` federated read. Use
`just rtg-federated-answer "Show Experience Studio publication readiness."` for the bounded
read-only summary and graph-qualified check citations.

## Load The Monograph

Run the repeatable loader against the registered local root:

```sh
uv run python docs/prototypes/experience-studio/load_monograph.py --reset
```

The loader validates the fresh graph, stages and cuts over schema, ingests the Ocean seed, runs the
three queries, persists `snapshots/experience-studio-alpha.json`, and verifies replay from the
ledger.

Use `--reset` only for an intentional clean rebuild of this alpha graph root.

## Current Boundary

Experience Studio stores a `GraphModel` locator for Ocean Signal Atlas, not reef regions,
heat-stress observations, NOAA dataset snapshots, or runtime caveats. Those records belong in a
future `ocean_signal_atlas` domain graph if the experience advances to governed runtime ingestion.
