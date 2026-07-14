# Schema Domain Catalog

This catalog lists repo-bundled schema-domain instructions. A descriptor and its prompt may be
available even when the domain is not compatible with the current RTG kernel. Check each
descriptor's `runtime_compatibility.status` before attempting it. Domain entries are instructions,
not hidden install payloads: agents should still stage schema through `rtg_stage_schema_migration`,
cut over with `rtg_apply_migration_cutover`, run strict validation, and preserve snapshot or replay
evidence.

The MCP app exposes this catalog through:

```json
{"tool": "rtg_get_usage_guide", "arguments": {"topic": "schema_domains"}}
```

Use the returned `domain_id`, `prompt_path`, and `walkthrough_path` to choose a domain and run it
from a downloaded repo checkout.

Launch metadata exposes `available` for the three instructional files and `runtime_ready` for
current-kernel compatibility. This directory remains the repository authority for the descriptor
inventory.

## Available Domains

Currently runnable on the harmonized kernel:

- [`individual-life-graph`](individual-life-graph/domain.yaml): initial personal/professional
  planning graph for one operator.
- [`personal-operating-graph`](personal-operating-graph/domain.yaml): governed operating graph for
  commitments, decisions, reviews, evidence, routines, and attention planning.

Cataloged but blocked pending kernel or fixture harmonization:

- [`governance-core`](governance-core/domain.yaml): kernel-adjacent principles, decisions,
  conventions, policies, versioning, and authorship provenance.
- [`agent-memory-spine`](agent-memory-spine/domain.yaml): flagship reference vocabulary for
  actors, working context, traces, facts, assessments, decisions, capabilities, classification,
  media, and graph domains.
- [`experience-studio`](experience-studio/domain.yaml): governed product-planning graph for
  graph-backed public games, visual explorations, and interactive experiences.
- [`gothic-ambient-archive`](gothic-ambient-archive/domain.yaml): alpha public-domain Gothic
  literature graph for ambient visual exploration and LLM docent navigation.
- [`time-room-history`](time-room-history/domain.yaml): source-grounded historical claims compiled
  into deterministic offline packs for kid-safe historical-figure experiences.

## Catalog Rules

- Keep domain descriptors small and human-readable.
- Keep runtime compatibility, requirements, and blockers explicit.
- Point to prompts and walkthroughs instead of duplicating full schemas.
- Do not auto-install opaque schema payloads from the catalog.
- Prefer validated recreate instructions over prebuilt schema blobs.
- Add a known-good walkthrough once a domain has been exercised through MCP.
