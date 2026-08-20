# Vellis model

The textual SysML v2 files here are product and system authority for Vellis:

1. `10-rtg-domain.sysml` defines scalar values, graph objects, definitions, local cardinality,
   state selection, unified query, field-level changes, the draft, outcomes, ledgers, and v1
   compatibility meaning.
2. `15-everyday-life-starter.sysml` defines the optional recommended fresh vocabulary. It contains
   definitions only.
3. `20-rtg-system.sysml` defines one cohesive RTG boundary, owner-visible behavior, and the selected
   MCP operations.
4. `30-vellis.sysml` places that boundary in the one-owner product and covers initialization,
   connection, ordinary use, governance, history, restore, audit, backup, and v1 adoption.
5. `40-requirements.sysml` states cross-cutting obligations and selected satisfiers.
6. `50-verification.sysml` states decisive conformance evidence and nearest wrong systems.

The model deliberately describes a small compositional product. Anchors identify durable concepts;
associated-data objects hold sparse typed scalar facts and identity-free anchor associations; links
are directed identity-bearing relationships. Definitions are small owner-described contracts with
local bounds. UUID and type-key kind reservations persist through the lineage.

A cold agent discovers the shallow anchor vocabulary, inspects focused neighborhoods, and uses one
bounded query. Known UUIDs are selected directly. Connected graph questions use a pattern, and the
system establishes the bounded identity rows before hydrating requested values. There is no separate
get step, projection language, aggregation server, hidden variable, or disconnected product.

Active graph changes are atomic field upserts and explicit removals. Unmentioned fields survive,
absence differs from null, no cascade is inferred, and the batch is judged against its final state
independent of command order. One durable noncanonical draft composes complete definition
replacements and the same field-level graph patches over changing live state. Agents inspect raw
deltas, query effective draft state, validate current findings, and activate or discard. The draft
has no public version, status, assessment identity, or activation token.

Current and historical state are indexed directly. The canonical ledger is corruption-evident
owner-readable history, not public replay; the separate activity ledger is observational. Restore
creates a new revision, backup preserves complete database meaning, and first-use v1 adoption streams
into an explicitly reported revision-zero candidate. Snapshot, tail, replay, relationship-rule
identities, arbitrary nested user JSON, server aggregation, and public assessment objects are absent.

The model selects observable STDIO/HTTP and owner-lifecycle consequences but does not prescribe
Python modules, tables, SQL, FastMCP internals, deployment units, or service machinery. Ordinary
current discovery, query, and change must remain independent of excluded history and unrelated
populations. Full validation, activation, restore, audit, import, and backup may legitimately scan
relevant state with bounded working memory. Numerical performance targets remain deferred until
representative hardware and owner data exist.

Run `just model-check` for the pinned official validator and repository policy checks. Use
`$sysml-reference` for consequential language choices, `$sysml-modeling` for system meaning and
simplification, `$rtg-schema-design` for RTG governance, `$sysml-evolution` for post-build changes,
and `$documentation-sync` after model or public workflow changes.
