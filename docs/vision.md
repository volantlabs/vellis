# Model-first engineering vision

Vellis is both a useful, individually owned application and the first proving ground for a reusable
model-first software engineering method for the agentic era.

The textual SysML on each branch is that branch's current system definition. Humans and agents collaborate through the same code-like loop used for source: change the model, validate it, inspect the diff, review the engineering consequences in a pull request, and merge the accepted change.

Agents help turn owner needs into use-case landscapes, domain meaning, necessary functional refinement, cohesive responsibility, requirements, and verification cases. Humans provide product judgment and review consequential tradeoffs. The model remains an engineering definition rather than a transcription of code or prediction of code modules.

Algorithms, storage layouts, transports, protocols, frameworks, deployment choices, and migration machinery remain absent until the product needs or deliberately selects them. Simplicity means both subtracting unsupported machinery and retaining enough explicit behavior, responsibility, history, and verification to make the system understandable and buildable.

Vellis treats one durable canonical ledger as the authority for personal memory while keeping current
work independent of accumulated history and bounded historical selection efficient. Materialized
projections, indexes, caches, checkpoints, snapshot cadence, and persistence technology remain
implementation choices rather than modeled subsystems. Vellis currently selects one SQLite-owned
live and historical state: immutable object and definition values, membership intervals, the sole
prospective overlay, complete assessments, canonical events, and activity history are normalized and
addressable through identity and semantic indexes. Maintained semantic summaries make ordinary
transition identity proportional to the change rather than the stored population. No production operation constructs or retains a
complete graph, definition set, canonical state, or canonical change. Ordinary work uses affected
neighborhoods, complete checks use bounded set-based scans, and lifecycle work streams. The
realization is characterized along each of those dimensions — what its work
responds to and what it ignores — and that
characterization deliberately sets no numerical latency, startup, or storage budget, because there
is not yet a representative benchmark environment, hardware profile, or owner's data to set one
against.

The central experiment is whether a sufficiently specified model in a standard language can replace
a pile of tickets and informal prose as the stable source of truth for autonomous agentic
engineering. The measure of success is a turnkey personal application and a repository whose path
from owner outcome through a human-approved whole-model plan, implementation source, and evidence is
easy to inspect, resume, understand, and trust. The future is model-first, agent-assisted, and plain.

That path is bidirectional without making its authorities symmetrical. Model agents expose
implementation-ready semantic neighborhoods and the system boundaries they must preserve. Software
agents may realize those concerns through finer-grained classes and modules, then return failing cases
or feasibility evidence translated back into stakeholder-visible systems meaning. Code structure informs
engineering judgment but does not become the model by transcription.

The reference, modeling, whole-model planning, bounded implementation, campaign-management, and
implemented-system evolution skills form a portable SysML v2 MBSwE core. A project
binds that core to its model layout, language baseline, validator, engineering checks, source rules,
and change workflow; optional domain skills add specialized meaning. Vellis contributes RTG as one
such extension, not as the assumed shape of the method. The repository does not yet ship a standalone
plugin, but the core should move to stateless, interactive, distributed, embedded, numerical, and
safety-relevant software projects without inheriting Vellis commands or vocabulary.

A first-time owner is offered a blank personal vocabulary or the modeled, recommended Everyday Life
starter, and explicitly confirms whichever they choose. The starter accelerates a useful beginning without becoming a
universal platform ontology: selected definitions become ordinary owner-governed meaning, and an
existing or restored system is never silently overlaid.

A first-time v2 owner may also preview and explicitly confirm compatible data and definitions from a
complete Vellis v1 JSON snapshot. Graph identities, kinds, stored values, and relationships are
preserved when they can conform; missing `system.live` uses its compatibility default and an unnamed
anchor receives the disclosed deterministic display name. Definition simplifications and omissions
are visible before acceptance. The result begins a new revision-zero v2 lineage rather than importing
enterprise-era history or creating an existing-system merge path. Export may happen after a v2
upgrade by running tagged v1.0 separately against the untouched old directory; v2 consumes only the
complete JSON snapshot at a separate destination and never adopts or converts raw v1 storage.

That includes agents arriving without hidden project memory. Vellis should let them discover the
owner-described concepts in one personal graph, inspect only the relevant meaning, and act through a
small portable contract without importing enterprise architecture or predecessor assumptions.

That same bounded history can support owner-configured external agents that periodically surface
stale data, repeated failures, unused vocabulary, or cleanup opportunities. Vellis supplies visible,
incremental evidence; scheduling, inference, and recommendation generation stay outside the product,
and no inferred change bypasses owner approval.
