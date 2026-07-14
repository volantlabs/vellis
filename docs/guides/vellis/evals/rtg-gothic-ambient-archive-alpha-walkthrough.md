# RTG Gothic Ambient Archive Alpha Walkthrough

This walkthrough records the expected shape of the first Nocturne Archive graph-modeling run. It
is alpha evidence, not a literary source-verification certificate.

## Validation Evidence

Validated locally against a fresh in-process RTG controller on July 9, 2026.

Payloads:

- `docs/prototypes/nocturne-archive/data/gothic-ambient-schema-v0.json`
- `docs/prototypes/nocturne-archive/data/lucy-transformation-live-records.json`
- `docs/prototypes/nocturne-archive/data/queries/blood-trail-query.json`
- `docs/prototypes/nocturne-archive/data/queries/lucy-event-cluster-query.json`
- `docs/prototypes/nocturne-archive/data/queries/threshold-motif-query.json`

Observed sequence:

1. `rtg_validate_graph` on a fresh controller accepted with zero findings.
2. `rtg_stage_schema_migration` accepted `gothic-ambient-archive-schema-v0`.
3. `rtg_apply_migration_cutover` accepted the staged schema.
4. `rtg_apply_live_anchor_records` accepted the Lucy planning seed.
5. Final `rtg_validate_graph` accepted with zero findings.
6. The graph state classified as `populated`.

Observed live counts:

```json
{
  "anchor": {
    "Character": 6,
    "Event": 6,
    "Motif": 5,
    "Object": 3,
    "Passage": 1,
    "Place": 3,
    "ReadingTrail": 3,
    "Source": 1,
    "StylePack": 5,
    "Theme": 2,
    "TrailStop": 17,
    "Work": 1
  },
  "data_object": {
    "CharacterFacts": 6,
    "EventFacts": 6,
    "MotifFacts": 5,
    "ObjectFacts": 3,
    "PassageFacts": 1,
    "PlaceFacts": 3,
    "ReadingTrailFacts": 3,
    "SourceFacts": 1,
    "StylePackFacts": 5,
    "ThemeFacts": 2,
    "TrailStopFacts": 17,
    "WorkFacts": 1
  }
}
```

Observed query row counts:

- Blood Trail query: 6 rows.
- Lucy event cluster query: 5 rows.
- Threshold motif query: 3 rows.

## Why TrailStop Exists

The initial prose plan treated `ReadingTrail` as an ordered list. RTG links are pure triples and do
not carry properties, so order cannot live on an `includes_stop` link. The alpha graph reifies each
ordered step as a `TrailStop` anchor with `TrailStopFacts.ordinal`.

This preserves the graph-modeling rule:

- relationship metadata becomes a node
- links remain property-free
- ordering can be queried and validated as data

## Current Limitations

- Source spans are placeholders. The Lucy events and citations must be verified against a chosen
  public-domain edition before authoritative use.
- License facts are placeholders. Public-domain basis and provider policy must be checked before
  publication.
- The MCP schema staging facade accepts `identity_criteria`; the alpha payload has not declared
  natural-identity rules yet, so duplicate-domain identity remains a follow-up modeling decision.
- Link kinds are encoded in the alpha payload: `evidenced_by` is provenance, `includes_stop` and
  `follows` are structural, `variant_of` is versioning, and the remaining links are semantic.
- The connected desktop MCP graph may report `needs_replay`; use a fresh explicit storage root or
  resolve replay before mutating it.
