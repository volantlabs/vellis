# Nocturne Archive Graph Fixtures

This directory retains the governed RTG slice of the earlier Nocturne Archive prototype. The
static web experience and generated image assets are intentionally not part of the schema-domain
runtime package; they remain presentation consumers rather than graph authority.

The reviewable inputs are:

- `data/gothic-ambient-schema-v0.json`: 12 anchor types, 12 fact types, and 16 pure-triple link
  types.
- `data/lucy-transformation-live-records.json`: 53 planning anchors and 88 links.
- `data/queries/`: bounded cluster, trail, and motif queries.
- `graph-handoff.md`: readiness, evidence, and ownership boundaries for the alpha seed.

Load the graph with:

```sh
uv run python docs/prototypes/nocturne-archive/load_monograph.py --reset
```

The loader stages and cuts over the schema, ingests the Lucy planning seed, runs all three queries,
validates the populated graph, persists a snapshot, and verifies ledger replay. Use `--reset` only
for an intentional clean rebuild.

The seed remains alpha planning evidence: source spans, edition metadata, and publication rights
must be reviewed before treating the graph as authoritative source material.
