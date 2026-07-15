# Gothic Ambient Archive Graph Handoff

The Gothic Ambient Archive alpha is now a runnable RTG schema domain. Its schema, Lucy Westenra
planning seed, bounded queries, repeatable loader, snapshot, and replay checks are retained here as
one reviewable package.

## Current boundary

- The graph owns the source-grounded literature model, conservative verification status, ordered
  reading trails, and presentation-only style-pack records.
- `TrailStop` anchors own trail order and curation notes; pure-triple links carry no properties.
- Source spans and edition/license metadata remain explicitly unverified where the seed says so.
- A future UI, docent, or visual style system consumes this graph and must not become factual
  authority.

## Runtime evidence

`load_monograph.py` recreates the domain through strict schema staging and cutover, ingests 53
anchors and 88 links, executes the cluster, blood-trail, and threshold-motif queries, validates the
graph, persists a snapshot, and verifies replay from the ledger.

## Publication stop conditions

Do not promote this alpha seed to publication authority until a chosen public-domain edition has
verified source spans, jurisdiction-appropriate rights review, and reviewed event labels and
ordering. Style packs must remain presentation-only, and generated imagery must avoid actor
likenesses, protected trade dress, and unsupported license claims.
