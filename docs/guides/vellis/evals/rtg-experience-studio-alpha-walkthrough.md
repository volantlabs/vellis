# RTG Experience Studio Alpha Walkthrough

This walkthrough records the observed evidence for the first Experience Studio run. It is an alpha
product-planning model, not a legal review or a source-authoritative Ocean Signal Atlas graph.

## Validation Evidence

Validated locally against a fresh in-process RTG controller on July 10, 2026.

The checked-in fixture set is designed to run through a fresh in-process RTG controller:

- `docs/prototypes/experience-studio/data/experience-studio-schema-v0.json`
- `docs/prototypes/experience-studio/data/ocean-signal-atlas-planning-records.json`
- `docs/prototypes/experience-studio/data/queries/experience-portfolio-query.json`
- `docs/prototypes/experience-studio/data/queries/source-readiness-query.json`
- `docs/prototypes/experience-studio/data/queries/publication-check-query.json`

The repeatable loader is `docs/prototypes/experience-studio/load_monograph.py`.

## Observed Sequence

1. Validate a fresh controller with zero findings.
2. Stage and cut over `experience-studio-schema-v0`.
3. Ingest the Ocean Signal Atlas planning seed.
4. Validate the populated graph with zero findings.
5. Run the three bounded query fixtures.
6. Persist `snapshots/experience-studio-alpha.json`.
7. Verify replay from the ledger.

## Observed Counts

- 13 anchor schema definitions.
- 13 data-object schema definitions.
- 16 link schema definitions.
- 27 live anchors.
- 27 live data objects.
- 39 live links.
- Portfolio query: 1 row.
- Source-readiness query: 1 row.
- Publication-check query: 6 rows.

## Boundary Evidence

The seed records one product-level decision to keep operator planning, experience planning, and
source-authoritative runtime facts in separate graph roots. Personal commitments remain in
`personal_ops`; NOAA reef observations remain candidates for a future `ocean_signal_atlas`
monograph.

## Current Limitations

- The seed contains one experience and does not yet prove portfolio-scale query ergonomics.
- Source eligibility is a planning assessment based on recorded source policy and still requires
  human publication review.
- The MCP schema-staging facade accepts `identity_criteria`; candidate natural keys remain
  unencoded in this alpha payload pending a domain-specific identity review.
- Link kinds are encoded in the schema payload, including governance for publication checks,
  provenance for evidence, and structural lifecycle for scene composition.
- The Ocean Signal Atlas graph model remains a proposal locator, not a staged runtime schema.
