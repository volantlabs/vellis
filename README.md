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
- [`tools/`](tools/): the pinned validator, reference search, skill checks, and campaign validation.

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
`$sysml-implementation-campaign`. Together they define a domain-neutral evidence, modeling,
whole-model decomposition, bounded realization, conformance, resumable execution, and closure loop.
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
closure paused at the selected external boundary because Codex's existing approval policy cancelled
the required bounded read-only MCP invocation. A
continuation harness may then invoke
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

A useful handoff answers the question, states the changed or reviewed meaning, gives decisive evidence and checks, and names only the remaining decision or follow-up work. An agent unfamiliar with an RTG begins with the modeled definition summary for current or selected historical state, then inspects only the active anchor neighborhoods needed for its query or proposed change. It retrieves the sole proposed definition set separately when continuing current definition work.

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
- `just implementation-campaign-worker-result-check <path>`: validate a compact worker handoff that
  contains counts and checkpoint state rather than review transcripts.
- `just implementation-campaign-baseline`: print the currently observed model, language, and
  validator digests without changing files.
- `just implementation-campaign-checkpoint-check`: after a checkpoint commit, verify clean tracked
  state, the committed campaign, approved plan projection, current checkpoint, and current evidence.
- `just check`: run the complete repository gate.

## Implementation status

All seventeen original campaign slices and corrective slice S018 are complete. Whole-system closure
had found that selected decisions D004 and D005 were never realized; S018 now implements their
setup-program/public-CLI behavior with fake-client evidence. The authorized live transition remains
closure decision D006. Its exact dry run and registrations succeeded, but the required Codex
read-only invocation was cancelled by the client's existing approval policy; closure may not change
that policy. Therefore `A017` and runnable closure remain `partial` while the already-established
cross-slice integration evidence remains `conforming`. See
[MCP realization](docs/mcp-realization.md#client-configuration) for the selected boundary and manual
fallback. `just implementation-campaign-status` reports the remaining closure decision.
Use these words precisely:

- **Implemented and verified.** Canonical graph, definition, and constraint meaning; canonical
  semantic equality over JSON, graphs, definitions, and canonical states; whole-string RE2 property
  patterns evaluated by RE2 itself; assessment of a graph against a definition set; fresh
  initialization from a supplied initial definition set at revision 0 with one initial-state
  record, no transitions, and an empty activity ledger; a
  durable local store that recovers identical memory across an ordinary restart, commits the
  canonical record and the current projection as one effect, and refuses a database holding
  anything else; a current-state projection reached without traversing canonical history;
  explicit graph changes committed atomically as contiguous canonical transitions, with the
  complete resulting graph validated first and replay reconstructing the same state from the
  ledger alone; the typed graph-conformance report; and current definition discovery — the complete
  shallow anchor vocabulary and the complete focused neighborhood of each selected anchor, each
  carrying the revision it was evaluated at so a caller can tell that the ground moved;
  governance of the one prospective definition set — stage, edit, review, activate, discard —
  where a working proposal may carry findings and activation is what they gate; and the optional
  Everyday Life starter vocabulary as an ordinary, owner-governable definition set; and bounded
  semantic query over current state — named anchor and associated-data groups, required directed
  links, structured property comparisons, and a shaped result refused whole rather than truncated
  when it would exceed the caller's row bound; and a separated observational ledger — reads,
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
  boundary that realizes them; of those, only preserving a snapshot has an owner-facing command,
  because that document is one of the inputs setup takes. Support for incremental
  owner-visible improvement analysis is verified the same way: an externally scheduled agent reads
  explicit bounded intervals of both ledgers, discovers the vocabulary those states had, asks
  bounded current and historical questions, and continues a later run from the interval it already
  processed. Vellis supplies no scheduler, job registry, worker, or inference of its own — nothing
  happens that the agent did not ask for, and where to continue from is the agent's own state
  rather than anything Vellis stores. Before proposing either a definition delta or a graph
  change, the agent rediscovers current definitions — a delta replaces the whole vocabulary, and a
  change is written in concepts that may have been retired since — and rechecks current facts,
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
  record accesses, along each dimension separately: current summary, inspection, query, conformance
  assessment, delta retrieval, and change validation read no record of either ledger however long
  the history behind them; a commit appends one record at the end without reading or rewriting the
  prefix, and observing is observational; a bounded interval of either ledger costs the interval
  and seeks to it rather than walking what precedes it; a historical vocabulary costs its
  definition-changing records rather than the graph transitions between them, while a historical
  graph is charged the replay the model exempts; replay costs its required tail while an ordinary
  restart does not; restoring a past state costs the tail it has to replay and not the records
  after it; and storage grows with both ledgers, including the observational one that every read
  adds to. Forgetting activity removes those records and bounds what comes next, but the file keeps
  the size it reached rather than returning pages to the disk. No numerical latency, startup, or
  storage budget is claimed or met: choosing one needs a runtime, a hardware profile, and a
  representative owner's data that do not exist yet.
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
- **Implemented but not live-closed.** Closure ran the exact authorized dry run and registration,
  then reread both matching entries. The bounded Codex invocation was cancelled under the client's
  existing approval policy, so closure paused without changing that policy and D006 remains open.
  [MCP realization](docs/mcp-realization.md#client-configuration) carries manual
  fallback commands for unavailable clients. FastMCP and FastMCP Slim are pinned at 4.0.0b1 and
  installed.

Deployment and migration realization remain open. The initial contract assumes one trusted
owner-configured client; its tools do not implement per-call authorization or decide owner approval.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.
