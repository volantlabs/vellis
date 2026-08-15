# Vellis

Vellis is an individually owned personal AI system and an open demonstration of model-first software engineering with textual SysML v2.

The repository contains the Vellis system model, its development tooling, and the application that realizes it; see [Implementation status](#implementation-status) for what is built and what is not. The model covers owner-facing behavior, Reified Type Graph (RTG) graph and query meaning, ledger-authoritative state and scalable history access, canonical equality and string-shape constraints, cold-agent current or historical definition discovery, definition governance, blank or recommended Everyday Life initialization, confirmed first-use import from a Vellis v1 JSON snapshot, snapshots and replay, proactive owner-visible analysis support, a selected ten-tool MCP contract, cohesive system responsibility, requirements, satisfiers, analysis, and verification cases.

## What is here

- [`model/`](model/): the textual SysML packages forming the current system authority.
- [`docs/vision.md`](docs/vision.md): the human/agent engineering vision.
- [`docs/modeling-method.md`](docs/modeling-method.md): the use-case-first model-as-code method.
- [`docs/implementation-method.md`](docs/implementation-method.md): the bidirectional path from
  accepted model meaning to code and conformance evidence.
- [`docs/mcp-realization.md`](docs/mcp-realization.md): non-normative guidance for the FastMCP realization.
- [`model/config/`](model/config/): checksum pins for the specifications, model libraries, and validator. The searchable corpus is generated from them into an ignored cache, never committed.
- [`.agents/skills/`](.agents/skills/): a portable SysML v2 MBSwE core plus Vellis-specific domain
  and repository extensions.
- [`implementation-campaign.yaml`](implementation-campaign.yaml): the baseline-bound current plan
  and execution/evidence index for the application build; it is not product authority.
- [`system-evolution.yaml`](system-evolution.yaml): the baseline-bound active post-build finding,
  decision, work, and rebaseline index; it is not product authority.
- [`tools/`](tools/): the pinned validator, reference search, skill checks, campaign validation, and
  evolution-record validation.

`just model-setup` builds a searchable SysML v2 reference layer into an ignored cache: the pinned
specifications, the normative model libraries, and 309 validated example models, all searched
together with each result labelled by source. The `$sysml-reference` skill carries a map from
ordinary engineering intent to SysML construct names, so an agent can name what it needs before
searching.

The SysML on a branch is that branch's system definition. A pull request proposes changes to behavior, requirements, system responsibility, and verification; review and merge are the acceptance mechanism. Markdown explains the work without duplicating the model as a parallel contract.

## Agent-assisted engineering

Begin with [`AGENTS.md`](AGENTS.md), then read the [model map](model/README.md), every current `model/*.sysml` file, and the current diff. Use `$sysml-modeling` for the engineering workflow, `$sysml-reference` for language decisions, `$rtg-schema-design` for RTG domain and governance meaning, and `$documentation-sync` after model or workflow changes.

The reusable core is `$sysml-reference`, `$sysml-modeling`,
`$sysml-implementation-planning`, `$sysml-implementation`, and
`$sysml-implementation-campaign`, plus `$sysml-evolution` for changes to an already implemented
system. Together they define a domain-neutral evidence, modeling, whole-model decomposition,
bounded realization, conformance, resumable execution, evolution, and closure loop.
They deliberately do not assume Vellis, RTG, this repository's paths or commands, Git, Python, MCP,
persistence, networking, code generation, or a test framework.

`AGENTS.md`, the model map, the pinned tooling, and the `just` commands bind that portable method
to this repository. `$rtg-schema-design` adds Vellis's RTG semantics, while
`$documentation-sync` maintains this repository's public and contributor guidance. Those are
optional project and domain extensions, not dependencies of the portable core. No standalone plugin
is packaged yet; the core skills are written so they can be moved or packaged later without carrying
the Vellis binding into another project.

For a complete-system build, `$sysml-implementation-planning` reads the complete accepted model and
derives dependency-ordered, evidence-bearing semantic slices. The committed campaign record stays
awaiting human approval until that complete plan is accepted. Vellis completed its seventeen
original slices, then closure exposed an unimplemented selected realization decision. A reviewed
candidate preserved that choice and added corrective slice S018. After renewed approval and S018,
closure confirmed both matching registrations and completed bounded invocations through Codex and
Claude Code. The implementation campaign is complete. A continuation harness may invoke
`$sysml-implementation-campaign` through a thin manager. The manager reads one machine disposition,
launches a fresh worker for exactly that slice, waits, and independently validates its checkpoint.
The worker uses `$sysml-implementation`, runs both bounded review lenses, batches remediation, runs
one final review pair, returns a compact result without reviewer transcripts, and stops. The manager
then repeats through whole-system runnable closure. The complete campaign receives one human
approval; reviewed routine slice checkpoints continue autonomously unless a model, plan, baseline,
feasibility, or external-authority boundary requires renewed human direction. The committed campaign
record, rather than any manager conversation, remains the resume authority.

When an accepted semantic slice is ready for code, model work emits a compact handoff of qualified
authority, in-scope obligations, authority coverage, remaining obligations, decisive examples,
conformance-evidence intent, and deliberately open realization decisions. `$sysml-implementation`
verifies or reconstructs that frame, selects the simplest evidence-backed realization, implements one
end-to-end slice, and returns conformance evidence or precisely classified feedback. The handoff is a
navigation aid, not another contract; the branch's SysML remains authoritative.

A useful handoff answers the question, states the changed or reviewed meaning, gives decisive evidence
and checks, and names only the remaining decision or follow-up work. An agent unfamiliar with an RTG
begins with the modeled definition summary for current, prospective, or selected historical state,
then inspects only the evaluated anchor neighborhoods needed for its query or proposed change. When
continuing definition work it retrieves the sole proposal's identities, overlay counts, and assessment
status, then uses prospective summary and inspection for its focused definition meaning.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/). `git` is also required, since `model-setup` fetches the pinned upstream release as a sparse checkout. Then run:

```sh
just setup
just model-setup
just check
```

Useful commands:

- `just model-check`: validate every authored SysML file with the pinned validator.
- `just model-reference-find "<question>"`: search the specifications, model libraries, and example models; every hit is labelled with its source. Supply optional filters positionally, for example `just model-reference-find "<question>" sysml-2.1 8`.
- `just model-reference-concepts`: list every SysML v2 construct name, for turning a question into a searchable term.
- `just model-probe "<snippet>"`: check one SysML snippet against the pinned parser in about six seconds.
- `just model-reference-check`: prove the generated search corpus still matches its pin.
- `just skills-check`: validate the repo-local skills and their managed project links.
- `just implementation-campaign-check`: validate the campaign schema, baseline, qualified model
  references, dependency graph, approval, evidence, and closure invariants.
- `just implementation-campaign-status`: show campaign freshness, approval, active or next slice,
  blockers, closure status, and open realization-decision IDs with their owners.
- `just implementation-campaign-dispatch`: emit the manager's machine-readable action, selected work
  item, checkpoint, worktree condition, Git identity, reason codes, and state token without mutation.
- `just implementation-campaign-review-frame <work-item> <lens>`: generate one fixed, finding-free
  prompt for the `authority` or `engineering` review lens of the active slice, or of `closure`.
- `just implementation-campaign-worker-result-check <path> <review-state-token> <checkpoint>`:
  validate the candidate handoff against frozen pre-bookkeeping state. After commit, the manager uses
  checkpoint validation because bookkeeping intentionally changes the token.
- `just implementation-campaign-baseline`: print the currently observed model, language, and
  validator digests without changing files.
- `just implementation-campaign-checkpoint-check`: after a checkpoint commit, verify clean tracked
  state, the committed campaign, approved plan projection, current checkpoint, and current evidence.
- `just system-evolution-check`: validate the active post-build evolution record's schema,
  ownership, dependencies, approval, lifecycle, and evidence references.
- `just system-evolution-status`: show its lifecycle, approval, next work item, and open findings.
- `just check`: run the complete repository gate.

## Implementation status

All seventeen original campaign slices and corrective slice S018 are complete. S018 implements the
selected setup-program/public-CLI behavior with fake-client evidence. Closure confirmed both
matching user-scoped STDIO registrations, the exact no-op dry run, a full ten-tool Codex desktop
owner scenario, and a bounded Claude Code definition-summary invocation. `A017`, integration, and
the runnable boundary are conforming; closure decision D006 and the implementation campaign are
complete. See [MCP realization](docs/mcp-realization.md#client-configuration) for the selected
boundary and manual fallback.
Use these words precisely:

- **Implemented and verified.** Canonical graph, definition, and constraint meaning; canonical
  semantic equality over JSON, graphs, definitions, and canonical state meaning; whole-string RE2
  property patterns evaluated by RE2 itself; complete SQLite-backed assessment of graph conformance
  with bounded finding retrieval; fresh initialization from a streamed initial definition set at
  revision 0 with one initial-state
  record, no transitions, and an empty activity ledger; a
  schema-version-5 local SQLite store that owns normalized current, prospective, historical, and
  ledger state, recovers identical memory across an ordinary restart, commits the canonical record
  and its addressable graph, definition, and proposal projections as one effect, and refuses a
  foreign or unsupported-version database. Complete assessments are published and retained as
  observational state, separate from canonical replay authority. No production operation constructs a complete
  resident graph, definition-set document, canonical-state document, or canonical-change document.
  Explicit graph changes are committed atomically as contiguous canonical transitions after
  validating their complete affected invariant closure; unaffected valid state is not revalidated.
  Current graph and prospective-overlay semantic summaries are maintained in the same transaction
  as their normalized rows, so sealing an ordinary transition does not rescan either population.
  The typed graph-conformance report and current definition discovery provide the complete
  shallow anchor vocabulary and the complete focused neighborhood of each selected anchor, each
  carrying the revision it was evaluated at so a caller can tell that the ground moved;
  governance of the one prospective definition set and graph overlay — stage bounded keyed
  definition edits, stage complete-object upserts or tombstones, unstage, assess, activate, and
  discard — where a working proposal may temporarily carry findings and an exact non-stale clean
  assessment gates atomic activation; and the optional
  Everyday Life starter vocabulary as an ordinary, owner-governable definition set; and bounded
  semantic query over current state — named anchor and associated-data groups, required directed
  links, structured property comparisons, and a shaped result refused whole rather than truncated
  when it would exceed the caller's row bound, with indexed identity, type, direct-association, and
  directed-link joins constraining candidates before property filtering; and a separated
  observational ledger — reads,
  validation, and refused operations leave a bounded record carrying capability, outcome,
  provenance, evaluated revision and scope but no result rows, over which the owner may read a
  bounded interval of either ledger and forget activity without moving anything replay
  reconstructs; and canonical snapshots with the reconstruction that rebuilds state from a base and
  a later contiguous tail, where each record's identity is chained from the one before it and rooted
  in the ledger's own, so a tail cannot be grafted onto a history it does not belong to; and
  historical selection, where a revision or a time takes discovery and query back to a committed
  state and answers with the meaning that state had; and the selected ten-tool MCP boundary —
  exactly the modeled tool names, typed both ways, where a semantic refusal stays distinct from
  malformed input and from an unexpected failure and every promised non-effect holds on the far
  side; and restoration, which makes a past state current again as one new revision without
  rewriting anything earlier, and refuses while a proposal is in flight rather than discarding it;
  and beginning a new lineage from a snapshot and its tail, whose history starts at the revision
  that state reached rather than at zero, because renumbering it would claim transitions this
  ledger does not have. The confirmed first-use vocabulary choice — blank or the Everyday Life
  starter, both named, the starter recommended and preselected, and neither established until the
  owner confirms — is implemented and verified. Confirmed first use from a Vellis v1 snapshot —
  live v1 content arriving exactly as it was stored, every simplification and omission named
  before the owner agrees to it, and a new lineage at revision 0 that claims none of the v1
  system's history — is implemented and verified. These capabilities are also verified as the
  owner-governed workflows they compose into: nothing an agent uses to look at memory is capable
  of retaining anything, and a proposal the owner declines never becomes a call, so canonical
  memory afterwards is indistinguishable from memory that was never asked — Vellis does not decide
  approval, and a submitted change is retained if it conforms, whoever asked for it. Approved
  context outlives the session that wrote it, corrections and forgetting leave the state they
  changed reachable in history, a
  vocabulary proposal can be staged across other work and restarts and is gated at activation
  rather than at staging, forgetting activity moves nothing replay reads, and an established
  system reaches the Everyday Life vocabulary only through ordinary definition governance. Every
  refusal and every execution failure in those workflows reaches the caller and leaves graph,
  definitions, delta, revision, and canonical history where they were. The owner-only operations —
  activity retention, snapshots, the recovery check, and restoration — are verified at the system
  boundary that realizes them. Preserving a snapshot has the owner-facing
  `uv run python -m vellis.preserve --out FILE` command because that document is one of the inputs
  setup takes; restoration has `uv run python -m vellis restore --revision REVISION` (or `--time`)
  and confirms before committing the selected historical state forward. Support for incremental
  owner-visible improvement analysis is verified the same way: an externally scheduled agent reads
  explicit bounded intervals of both ledgers, discovers the vocabulary those states had, asks
  bounded current and historical questions, and continues a later run from the interval it already
  processed. Vellis supplies no scheduler, job registry, worker, or inference of its own — nothing
  happens that the agent did not ask for, and where to continue from is the agent's own state
  rather than anything Vellis stores. Before proposing either a definition delta or a graph
  change, the agent rediscovers current definitions — bounded keyed edits produce one complete
  proposed vocabulary meaning, and a graph change is written in concepts that may have been retired
  since — and rechecks current facts,
  because the owner may have fixed the thing already; and every finding is traceable to the
  bounded observations and exact evaluated revisions it came from. Finally, that these compose
  into one cohesive system an individual can run is itself verified end to end: each of the three
  starting inputs the model names — blank or the confirmed Everyday Life starter, a canonical
  snapshot with its later records, and a confirmed v1 snapshot — establishes its own system; a
  client launching the server as an ordinary subprocess discovers exactly the ten tools, learns the
  vocabulary cold, asks a bounded question and retains one approved change; and a later session in
  a new process finds that memory at the state replay reconstructs. A failed start, a second start
  over an established system, and a client that cannot connect each name the stage that failed,
  say that established memory is unchanged, and give an available next step, with graph,
  definitions, delta, revision, and canonical ledger identical either side of the failure.
- **Characterized, not budgeted.** What this realization's work responds to is measured in semantic
  row visits, decoded values, affected neighborhoods, streamed buffer sizes, and query candidates.
  Summary and focused inspection decode no graph and no unrelated definitions. A one-object mutation
  scales with its change, incident relationships, affected associations, and applicable rules; a
  high-degree mutation scales with that degree, not unrelated population or obsolete object
  versions. Current, prospective, and historical queries constrain candidates in SQL and stop after
  `maximumRows + 1`; only projected rows are hydrated. An ordinary mutation never invokes a full
  conformance check. A broad definition cutover or explicit full check may scan all applicable rows,
  but does so set-wise with bounded working memory and stores every finding once for paged retrieval.
  Snapshot, tail replay, import, verification, v1 translation, and restore stream or use temporary
  SQLite/set operations without constructing whole-state values. Storage grows with normalized
  history and the observational ledger. Forgetting activity removes those records but does not
  promise file-page reclamation. No numerical latency, startup, throughput, or storage budget is
  claimed without representative hardware and owner data.
- **Runnable.** `uv run python -m vellis.setup` prepares one local system. It previews the
  destination and, unless it can already see that the destination will not do, offers both starting
  vocabularies with the Everyday Life starter preselected. It asks for confirmation, and accepts
  `--data-dir`, `--vocabulary`, `--yes`, and a no-effect `--dry-run` that still reports a
  destination it can already see will not do. Repeating `--client codex` or `--client claude`
  selects either or both supported clients; omitting it selects neither, and
  `--replace-client CLIENT` is required before a differing entry can be replaced. `--from-v1`
  begins from a Vellis v1 JSON system
  snapshot instead, and `--from-snapshot` from a Vellis canonical snapshot document — a complete
  capture with an optional later ledger tail, which
  `uv run python -m vellis.preserve --out FILE` writes from an established system, leaving its
  canonical memory and revision where they were and recording the capture in its activity history.
  Each carries its own vocabulary, so passing `--vocabulary` as well
  is refused rather than ignored, and only one starting input may be given; each is read again at
  confirmation, so one that changed after it was previewed is not the one that was agreed to. A
  snapshot start says before it is confirmed which revision the new lineage will begin at, because
  that is the revision the captured state reached rather than zero. Setup stores memory under
  `VELLIS_DATA_DIR` when that is set and otherwise under the platform's user-data location, and
  never writes to this repository's ignored `.data/`.
  `uv run python -m vellis` then serves that memory over local standard input and output; pointed at
  a destination holding no established memory it refuses rather than creating one, and a client that
  cannot start it is told which stage failed, that established memory is unchanged, and what to do
  next, in the same shape setup uses. Both commands
  resolve the same destination, so a system established at a configured location is the one the
  server serves. An MCP client launching that command as a subprocess discovers exactly the
  selected ten tools and reaches the memory setup established, across separate sessions and
  processes — a real client library over the real transport. Setup inspects and configures selected
  user-scoped Codex and Claude Code
  entries only through their public CLIs. Matching entries are no-ops; differing entries require
  explicit replacement; and an unavailable client reports a platform-correct copyable fallback
  without undoing initialized memory.
- **Runnable and live-closed.** Closure reran the exact authorized no-op dry run and reread both
  matching entries. Codex desktop exercised all ten public tools in one owner scenario and restored
  the starter vocabulary with an empty conforming graph and no staged proposal. Claude Code
  completed the bounded `rtg_definition_summary` invocation at revision 8. These observations,
  together with reproducible project boundary, setup, persistence, and inventory evidence, close
  D006 and the campaign without changing client approval policy.
  [MCP realization](docs/mcp-realization.md#client-configuration) carries manual
  fallback commands for unavailable clients. FastMCP and FastMCP Slim are pinned at 4.0.0b1 and
  installed.

Deployment realization remains open. This unreleased build intentionally starts a fresh normalized
schema-version-5 store and refuses unsupported prototype schema versions rather than migrating them;
it never inspects or changes this repository's ignored `.data/` content during development. The
initial contract assumes one trusted
owner-configured client; its tools do not implement per-call authorization or decide owner approval.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.
