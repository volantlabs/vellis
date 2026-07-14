---
twin:
  role: hypothesis
  concerns:
    - component.rtg.graph
    - component.rtg.schema
    - component.rtg.change_validation
    - component.rtg.controller
    - component.rtg.migration
    - component.rtg.query
---

# Agent-First Graph Modeling — The Opinionated Kernel

Status: design position, captured 2026-07-08. Synthesized from the volant_base production graph
(410 Principles, 184 DecisionRecords, 21 Conventions, 33 SchemaDomains, ~15 months of operating
scar tissue) against the Vellis RTG component library as it stands today. Graph citations use
`volant_base:<uuid-prefix>`; they resolve in the Volant Kesher graph, not this repo.

---

## Thesis

Vellis should not ship a neutral graph substrate and let every operator rediscover graph modeling
from scratch. It should ship an **opinionated kernel meta-model** — a small set of structural
invariants about how any agent-first memory graph must be shaped — and enforce them at the write
boundary, not in prose.

The single most important lesson from volant_base is not any one modeling rule. It is the
meta-pattern behind all of them: **almost every battle scar is a rule that was enforced by agent
discipline (bootloader prose, conventions, per-session vigilance) when it should have been
enforced by the substrate.** The graph accumulated 500+ duplicate-edge groups because link dedupe
was caller-side (`volant_base:d5e9f3b7`). It taught a frontier model that link properties persist
because the write path silently dropped them (`volant_base:8465e357`). It needed a Principle
telling agents to re-count inventory mid-backfill because the graph was live and unversioned
under them (`volant_base:c75932d0`). Kesher's own DecisionRecord names the canary: "Bootloader
Length Is the Canary for Governance Still in Prose" (`volant_base:154bc1b6`), and its Principle
states the target: "Deterministic rituals belong in code, not prose" (`volant_base:c636cf91`).

Vellis is positioned to be the system where those rituals *are* code. Its durable value —
"governed state for AI agent systems" (team briefing, 2026-07) — is exactly the promise that the
kernel, not the agent, carries the discipline.

The design below is in two layers:

1. **The kernel meta-model** — invariants Vellis enforces structurally for every graph.
2. **The reference memory spine** — the canonical schema for agent memory specifically, shipped
   as a schema domain, not hardcoded.

---

## 1. The kernel meta-model

### 1.1 Links are pure triples with structural identity

A link is `(type, source, target)` and nothing else. No properties, ever, and — the part Kesher
got wrong for a year — **rejected loudly at the write boundary, not silently dropped**
(`volant_base:8465e357`, decided 2026-06-18 after a frontier model was actively misled by
silent-success writes).

Go one step further than Kesher's fix: make `(type, source, target)` the link's *identity*.
A second write of the same triple is an idempotent no-op, not a duplicate. This deletes the
entire caller-side dedupe discipline (`volant_base:d5e9f3b7`, §B.8.a of the Kesher bootloader,
and the 500+ duplicate-edge groups it failed to prevent) from the operator's cognitive load.
RTG links currently carry their own UUIDs; keep the UUID as a handle, but derive uniqueness
from the triple.

Consequences the schema layer must then support well, because they are the pressure valves:

- **Relationship variance → distinct link types**, never a `kind` property
  (`volant_base:fc01c000`, `volant_base:ba0602dd`).
- **Relationships needing metadata (timestamp, actor, confidence, revocation) → reified nodes**
  (`volant_base:c8b3e7f2`, and DR `volant_base:c5151e09` — "AssetSlot classification via
  SlotClassifiedAs, not slot properties"). Reified junction types derive identity from what they
  connect and are validation-floor-exempt (`volant_base:66552be4`).
- **Cheap link types.** If minting a new link type is ceremony, people smuggle variance into
  properties. Link-type creation must be a one-op schema change.

### 1.2 Every node type declares its time-shape

Each node type is exactly one of: **state-now** (overwrite in place), **state-as-of** (validity
intervals), or **event** (append-only). Declared on the type definition, enforced by the write
path — an update to an `event` node is a rejected write, not a convention violation
(`volant_base:029c6021`: "Mixing shapes corrupts time queries").

This is the second-highest-leverage kernel opinion. volant_base has repeatedly converged on the
append-only assessment pattern by hand: re-scoring writes a NEW ICPFitAssessment node
(`volant_base:c2a1f9e0`), rubric scores are time-stamped composite nodes (`volant_base:27898e73`),
aerospace TestResults are append-only (the aerospace verification principle cluster). Each convergence cost a
DecisionRecord. In Vellis it should cost a schema field.

Corollary: `created_at`/`updated_at` are kernel-owned system fields, typed by the kernel
(volant_base spent a 40-node-type migration rebinding them from date to datetime,
`volant_base:6308711d`). Domain authors never model bookkeeping time; they only model
*domain* time (validity intervals, decision dates), where date-vs-datetime is a semantic choice
(`volant_base:90d5865b`).

### 1.3 Identity is architecture, not hygiene

Every node type declares its identity criteria — natural keys, match strategy, scope — as a
first-class schema object, not as tribal knowledge in a dedupe skill
(`volant_base:154f3498`, DR `volant_base:f3c6a31b`: identity criteria belong on a first-class
IdentityCriterion node, not flat properties).

The kernel uses it at write time: an insert matching an existing node's identity criteria is
surfaced as a merge candidate *by the substrate*. Kesher's `dedupe_check` is a separate tool the
agent must remember to call; Vellis's equivalent should be a mandatory phase of `apply` that
returns candidates instead of writing. Agent discipline → validation report.

Two identity rules ride along:

- **UUIDs are graph-local** (`volant_base:e9f93656`). Cross-graph references are an explicit
  reference type carrying `(graph_id, uuid)`, never a raw foreign UUID. Bake this in now, while
  Vellis is single-graph, because retrofitting it is what the Kesher Atlas program is still
  paying for.
- **One unambiguous identity accessor in the query language.** Kesher's `id(node)` returned the
  `id` *property*, not the node UUID (`volant_base:70e3e5fb`) — a pure footgun class. UUID is not
  a property; never let the two namespaces collide.

### 1.4 Link types carry a kind; the kind drives lifecycle

Every link type declares its kind: `semantic | structural | governance | provenance | versioning |
junction` (`volant_base:b6bfea72`). This is not documentation — it drives kernel behavior:
provenance links are append-only, structural links cascade on delete, semantic links are the
default traversal surface, versioning links get supersede semantics. Kesher declared this
principle but nothing consumes it; Vellis should make the kind load-bearing.

Deletion consults the kind: "check all connected links before deleting; assess the blast radius"
(`volant_base:520f1a2b`) becomes a kernel-computed impact report, and "orphan" audits enumerate
the full inbound link signature automatically (`volant_base:4b99776b`).

### 1.5 Property discipline is schema-enforced

- Constraints (enum, max-length, regex, typing) live on the attribute, once — no binding-level
  overrides (`volant_base:29ba36cd`, DR `volant_base:5fcd6b4a`).
- Indexed key must equal populated key; the kernel validates this instead of letting it become a
  "silent correctness bug" (`volant_base:a0a1b2c3-0001`).
- Naming rules (affordance prefixes, verb-phrase link names) are machine-checked at schema-op
  time. Kesher's DSV naming standard existed as a Principle while writes violated it freely
  (DR `volant_base:e4c6facb` — "hyphenation not enforced on writes"). A convention that isn't a
  validator is a wish.
- **Bodies live outside the graph.** Node properties stay short and indexable; anything over
  ~2KB goes to the content store, checksummed, linked via a media edge
  (`volant_base:3ee082d0`). The graph is the index of meaning, not the warehouse of bytes.
- Retire scalar properties when links model the relationship (`volant_base:e9a1c3f5`) — but the
  kernel should make the *link* the only way to say it on day one, so there is nothing to retire.
  Shared classifying vocabularies are taxonomy nodes + a universal `ClassifiedAs` primitive
  (`volant_base:d1a8c2f0`, `volant_base:90af8564` — Channel as taxonomy node, not per-type enum);
  enums are reserved for small closed sets owned by a single type.

### 1.6 Schema evolution is diffed, staged, and reversible — with real deletes

Vellis's staged-migration → validate → cutover pipeline is already ahead of where Kesher started.
Preserve it, and design out the specific scars:

- **Upsert-only schema ops are a trap.** Kesher has no `delete_property`; removal is "re-upsert
  the type with the key omitted," which has REPLACE semantics that have destroyed bindings
  (`volant_base:75b10b9b`, `volant_base:6fcb4f7e`). Vellis schema ops should be a closed set of
  explicit, first-class operations — add, rename, retype, delete — each with declared data
  implications (e.g., delete requires the strip-data-first sequence the kernel itself performs,
  per `volant_base:b2e80206`).
- **Publishing must be diff-scoped.** Kesher's publish "tags the entire staged HEAD," so stray
  ops become permanent (`volant_base:f186584f`); the mitigation is a human Convention to diff
  before publishing (`volant_base:7e99be43`). In Vellis, cutover should present the exact op-set diff
  and refuse to cut over anything unreviewed.
- **Wire-format strictness.** Half of Kesher's schema DRs are wire-format archaeology (`node`
  wrapper, `link` wrapper, `schema.` prefixes — `volant_base:f9c8b7a6`, `volant_base:d26562a3`,
  `volant_base:50a6530b`). Reject malformed ops at input with field-level errors; never record
  ops that compile to nothing.
- **Sandbox probing is legitimate; production probing is damage** (`volant_base:226b9d52`).
  Throwaway schema workspaces should be one call, free, and obviously the right place to
  experiment.

### 1.7 Writes are transactional proposals with explicit merge semantics

- **Merge vs replace is declared per write, never implied.** "Query the node before you write it;
  omission is deletion" (`volant_base:ab40cddf`) is a scar of ambiguous upsert semantics. The
  Vellis write op takes an explicit mode; replace-mode requires the caller to prove a fresh read
  (compare-and-set on version or checksum).
- **Staged proposals are a kernel primitive.** Kesher converged on `ProposedGraphWrite` nodes for
  bulk imports because "per-item confirmation does not scale; staged review preserves
  no-silent-writes at scale" (`volant_base:132a4240`). Vellis's change_validation component is the
  natural home: every batch is validate → (optionally) review → apply, and "propose, don't
  silently write" (`volant_base:2be35ef4`) becomes a policy toggle per actor, enforced by the
  controller rather than promised by the agent.
- **Concurrency by leasing, not hope.** Multi-phase writers lease the target entity and
  re-validate before each write (`volant_base:a1285c2b`); parallel-session HEAD-trampling is a
  documented Kesher failure mode. The RTG ledger's transaction positions give Vellis the
  substrate for optimistic concurrency; expose it.

### 1.8 Provenance is two-layered and non-optional

Ground truth and narrative are different records, and conflating them was worth a DecisionRecord:
"AgentTrace as Semantic Envelope; Runtime Trace as Ground Truth" (`volant_base:ecc251ab`,
`volant_base:738901af`).

- **Layer 1 — the ledger** (Vellis already has it): every mutation, transaction ID, validation
  report, replayable. Mechanical, kernel-owned, append-only by construction.
- **Layer 2 — semantic provenance nodes**: traces narrate intent and outcome; decisions record
  why; both *link* to ledger positions rather than duplicating them. Every write carries actor
  identity as a system field ("Provenance Is the Product," `volant_base:a1b2c3d4`; "One Agent,
  Every Surface," `volant_base:d078cbc2` — salience 1.0, the highest in the graph).
- Lifecycle claims require backing: a node claiming a terminal status must carry the evidence
  that status implies, validated at write (`volant_base:69ed2a66`).

### 1.9 The graph describes itself, in the graph

Kesher's Architecture Domain — SchemaDomain nodes, `BelongsToDomain` edges, the "map of the
territory" — turned out to be what makes the graph *navigable by agents at all*: agents plan
traversals from the map before touching data. Two rulings to inherit directly:

- Domain membership is a graph edge, never a JSON blob (`volant_base:c3175b20`,
  ratified in DR `volant_base:f0a0d4f6`).
- The data catalog is the operability contract — a type declared in the compiled schema but
  absent from the catalog is not operable (`volant_base:8c000002`). In Vellis, schema store and
  graph store are already parallel structures; guarantee they cannot drift by deriving the
  catalog view from the schema store rather than maintaining it as data.

Domains are a queryable lens, not a containment hierarchy (Meta-Governance domain summary,
volant_base). Sparsity is signal: "the graph is a theory, not a database — node types are
hypotheses; falsification is expected" (`volant_base:2d612723`). The kernel should make it cheap
to see which types are unpopulated hypotheses (candidate for pruning) versus load-bearing.

### 1.10 Governance artifacts are kernel types, and schema changes are product decisions

"Governance lives in the graph, not in prose" (`volant_base:9169a83e`) — but in Kesher the
governance types themselves (Principle, DecisionRecord, Convention, OperationType,
BehavioralPolicy) were modeled ad hoc over months, complete with gaps like Convention missing
from `AuthoredBy`'s allowed sources (Convention `volant_base:0b0d0164` records the workaround in
its own description). Vellis should ship the governance vocabulary *in the kernel schema domain*:
principle, decision, convention, policy, with their provenance links, from the first boot.

And treat schema changes as what they are: "Schema Design Is Product Design"
(`volant_base:a7e1c3d0`) — the schema generates the capability surface agents can act on. When
authorship distributes beyond one hand, implicit structure must become explicit and queryable
(`volant_base:55555555`). That is the moment Vellis is being built for.

---

## 2. The reference memory spine (shipped as a schema domain)

Everything above is kernel. The memory model itself ships as the flagship schema domain —
recreatable, inspectable, not hardcoded — consistent with the existing catalog rule ("prompts,
not hidden install payloads"). The spine, with time-shapes:

| Type | Time-shape | Role | Inherited scar |
|---|---|---|---|
| `Actor` (person/agent/service) | state-now | identity anchor; every write's provenance target | operator ≠ tenant (`volant_base:2a8b4c7e`); role as enum on the node, not separate types (`volant_base:d015488f`) |
| `Session` | event | bounded working context; **not** a heavyweight node type unless queried across time — Kesher ruled session identity can live as a property until proven otherwise (`volant_base:2a8f7c53`) | |
| `Trace` | event | semantic envelope per completed task; links to ledger positions, cited nodes, applied policies | `volant_base:ecc251ab` |
| `Fact` / domain nodes | state-now or state-as-of | the actual memory content, per-domain | time-shape declared, §1.2 |
| `Assessment` / `Observation` | event | anything scored, measured, or judged — never edited, always superseded | `volant_base:27898e73`, `volant_base:c2a1f9e0` |
| `Decision` | event | why state changed; the unit of institutional memory | `volant_base:` DR corpus is the proof this works |
| `Principle` / `Policy` | state-as-of | rules the controller enforces; versioned, salience-weighted | `volant_base:9169a83e` |
| `Skill` / `Capability` | state-as-of | what agents can do; portfolios are link-defined collections of pointers, never copies | "DRY at Scale", "Relational Taxonomy" |
| `Taxonomy` + `ClassifiedAs` | state-now | universal classification primitive | `volant_base:d1a8c2f0` |
| `Media` / body store | event (immutable versions) | heavy bodies, checksummed | `volant_base:3ee082d0` |
| `Domain` (map node) | state-now | the graph's self-description | §1.9 |

Session context assembly — Kesher's `session_init` — should be a **kernel query recipe over this
spine** (actor → scope → policies → relevant domains → open threads), not a bespoke server
composite. Discovery is a graph join, not flat search (`volant_base:b1d4e7a2`). And the memory
system must be self-maintaining: agents that consume context also produce, curate, and prune it
as a side effect of normal work (`volant_base:e9f0a1b2`) — which is only safe because §1.7 makes
every such write validated, proposed, and traced.

---

## 3. Anti-patterns (the paid-for list)

Modeling moves volant_base explicitly paid to learn *not* to do:

1. Link properties, in any form, including "documented but not persisted" (`volant_base:f8a9b0c1`).
2. Caller-side link dedupe as the integrity mechanism (§1.1).
3. Editing event-shaped nodes in place; status history as an overwritten enum (§1.2).
4. Foreign UUIDs crossing graph boundaries (`volant_base:e9f93656`).
5. Domain membership, type registries, or any structural fact serialized into JSON blob
   properties (`volant_base:92f96ae0` — "first-class nodes and edges, not core_components_json").
6. Per-type enums for shared vocabularies (channel, stage, medium) instead of taxonomy nodes.
7. Conventions without validators — every naming/shape rule either compiles to a check or it
   will drift (`volant_base:e4c6facb`).
8. Governance in prompt prose that the substrate could enforce (`volant_base:154bc1b6`). The
   Kesher bootloader at v3.7 is ~10k tokens of Tier-1 contract *after* aggressive migration of
   rules into tools; Vellis's target is a bootloader that fits in a tool description.
9. Sessions/scratch bundles without an authored governance record — "bundles are managed
   substrates, not session scratchpads" (Convention `volant_base:a103c0f1`; a 2-day forensic
   cleanup earned it).
10. Trusting a pre-campaign inventory of a live graph across a multi-batch operation
    (`volant_base:c75932d0`) — snapshot isolation for bulk ops is the kernel fix.

---

## 4. What this changes for Vellis

Execution state for this list lives in
[`kernel-meta-model-program.md`](./kernel-meta-model-program.md) (KM-1…KM-7, spec-first loop,
Status lines per item).

Concretely, gap-ordered against the current RTG components:

1. **Triple-identity links** (§1.1) — likely a `component.rtg.graph` invariant change; highest
   leverage, smallest surface.
2. **`time_shape` on schema type definitions** (§1.2) with write-path enforcement in
   change_validation.
3. **Identity criteria in `component.rtg.schema`** + merge-candidate detection as a validation
   track (§1.3).
4. **`link_kind` on link definitions** driving cascade/append-only behavior (§1.4).
5. **Explicit schema delete/rename ops with kernel-sequenced data implications** (§1.6).
6. **Declared merge-vs-replace write modes + optimistic concurrency on the ledger** (§1.7).
7. **Governance vocabulary as a kernel-adjacent schema domain**; memory spine as the flagship
   catalog domain (§1.10, §2).

None of these require abandoning the existing components — they are invariant promotions inside
boundaries Vellis already owns. That is the point: the scars are known, the enforcement points
exist, and moving each rule from "agent discipline" to "kernel invariant" is exactly the
generation-vs-stewardship bet the team briefing already made.

## Changes to the outlook

Strengthens Frame 1 (governed-graph substrate): differentiation is not "a graph with validation"
but "a graph whose kernel encodes the operating scars of a production agent-memory deployment."
Candidate new falsifiable claim for the register: *an agent operating a Vellis graph requires an
order of magnitude less standing prompt-governance (bootloader tokens) than the same agent
operating an equivalent ungoverned graph, at equal or lower error rates.* WP-2 (substrate
benchmark) is the natural home to test it.
