# AGENTS.md

## Authority

Vellis is one individually owned application and an open demonstration of model-first software
engineering. Textual SysML v2 under `model/` is the product and system authority on each branch.
Pull requests propose changes to that authority; Markdown explains the work without restating its
contracts. Implementation source realizes the current model and may select choices the model
intentionally leaves open; tests provide evidence of conformance. Neither source nor tests become a
parallel product authority.

## Safety

At the start of work, run `pwd`, `git status --short --branch`, and `git worktree list`. Do not switch
branches in a worktree without human confirmation.

The ignored `.data/` directory may contain user-owned graphs and databases. Do not inspect, move,
rewrite, migrate, or delete it unless the human explicitly requests that exact operation. Never run
broad ignored-file cleanup commands here.

Do not mine v1 history for current requirements or design patterns unless the human requests a
historical comparison or recovery task.

## Skill routing

`$sysml-reference`, `$sysml-modeling`, `$sysml-implementation-planning`,
`$sysml-implementation`, `$sysml-implementation-campaign`, and `$sysml-evolution` are the portable
MBSwE core.
The paths, commands, reading scope, checks, and review rules in this file bind that core to Vellis.
`$rtg-schema-design` and `$documentation-sync` are optional Vellis domain and repository extensions,
not dependencies that another project must carry.

- `$sysml-modeling`: owner needs, use cases, behavior, logical responsibility, requirements,
  verification, adequacy, and simplification.
- `$sysml-reference`: official language semantics, construct comparison, citations, and validator
  diagnosis. Use it for every consequential SysML or KerML choice.
- `$rtg-schema-design`: RTG meaning, queries, definitions, validation, revision, history, recovery,
  and compatibility.
- `$sysml-implementation-planning`: consume the complete accepted model and derive a
  coverage-complete, dependency-ordered campaign of semantic, integration, and closure slices.
- `$sysml-implementation`: consume one selected semantic slice, select bounded realization
  decisions, implement it, and review conformance evidence.
- `$sysml-implementation-campaign`: execute or resume the human-approved multi-slice campaign,
  coordinate independent review and remediation, checkpoint each slice, and prove system closure.
- `$sysml-evolution`: classify and coordinate evidence-backed changes to an already implemented
  system across accepted authority, realization, evidence, compatibility, and rebaselining.
- `$documentation-sync`: repository authority, commands, skills, templates, and public guidance.

## Portable-method boundary

Keep the six core skills reusable as written outside Vellis. They may require abstract capabilities
such as model entry-point discovery, pinned reference search, official validation, project checks,
and change review, but must not hard-code Vellis paths, `just` commands, RTG or MCP vocabulary,
Python, Git, persistence, networking, code generation, or a particular application architecture.
Bind those concerns in project instructions or optional domain skills.

When changing the portable core, exercise its guidance against at least these distinct archetypes:
a stateless transformation, an interactive stateful workflow, a distributed message-driven system,
an embedded or real-time cyber-physical controller, and numerical or safety/security-relevant
software. The method must expose units, timing, concurrency, physical, safety, security, durability,
or recovery semantics when consequential without demanding them from every project. Vellis and RTG
may demonstrate the method but must not become its implicit template. Do not claim a packaged plugin
until one exists.

Run those forward tests manually with fresh agents and do not disclose expected conclusions or prior
diagnoses. Keep prompts, transcripts, and expected-answer fixtures out of the repository; summarize
only the scenarios, material findings, and disposition in the task handoff or PR discussion.

For a complete-system implementation, derive or refresh `implementation-campaign.yaml` with
`$sysml-implementation-planning` and run `just implementation-campaign-check`. Human approval of the
complete current-baseline plan is required before `$sysml-implementation-campaign` activates a
slice. Use one thin manager, one fresh worker per slice, one writer, and one active slice. The manager
uses `just implementation-campaign-dispatch`, waits for the worker, consumes only its compact result,
and independently validates its checkpoint; it never implements, reviews, or reads reviewer
transcripts. After implementation, run independent read-only
authority/conformance and engineering/evidence reviews, batch in-scope remediation, run one final
review pair, then commit the slice and campaign update together. A model or material plan gap, stale baseline, or
stakeholder-visible feasibility consequence invalidates approval; implementation defects and
model-preserving realization choices remain campaign work.

For each slice, collect complete findings from both review lenses, batch all in-scope corrections,
and sweep the same root cause before one final independent review pair against the resulting slice.
Repeat only when that final pair identifies a plausible failure under the project's declared
assumptions. After three consecutive non-clean final pairs, perform one bounded root-cause audit
before another pair. Reviewers do not invent mutants, fuzz spaces, threat models, or speculative
input boundaries merely to find something new. Reviewers evaluate the selected slice and its evidence;
they do not recursively red-team the campaign mechanism unless the slice intentionally changes it.
Malicious repository, Git, or checker manipulation is outside this trusted-local workflow.

An accepted campaign may use any continuation harness that keeps the manager context thin and
resumes from the validated committed campaign and project checkpoint rather than conversation
memory. Each fresh worker executes exactly one slice or closure item and stops. Plan approval is one
gate for the complete campaign, not one human gate per slice. Routine reviewed slice checkpoints
continue autonomously; only the campaign skill's explicit pause conditions return to the human.

The campaign selects direct pins for `fastmcp==4.0.0b1` and `fastmcp-slim==4.0.0b1`,
local STDIO, and a documented Python setup path that configures user-scoped Codex or Claude Code
only through their public CLIs. These are selected realization constraints, not model structure;
read current implementation and runnable status from `implementation-campaign.yaml` and the README.
Do not
upgrade the pre-release pin, add another transport, or edit client configuration files directly
without renewed review of the selected plan.

Closure exposed the client-configuration half of that selection as an escaped implementation defect
after its original owners had already checkpointed. The renewed approved campaign assigns the setup
behavior to corrective slice S018 and keeps the live client transition in closure.

## Implementation campaign binding

S001 selects the product package, source root, and product-test layout. In the same first
product-bearing checkpoint, extend Ruff, basedpyright, pytest, and `just check` to cover all product
source and tests. Do not create an architecture-only setup slice. Add a dependency and update the
lock only in the first slice that uses it; S009 directly pins both `fastmcp==4.0.0b1` and
`fastmcp-slim==4.0.0b1` without globally allowing prereleases.

Campaign evidence references are either `path:<repo-relative-path>#<test-or-section>` or
`command:<exact reproducible command>`. Do not record prose assertions, absolute paths, transcripts,
or transient files as evidence. Path references may not traverse symlinks outside the repository.
Path fragments resolve to Markdown heading anchors or Python test nodes. Tests use temporary data
directories. A runtime default uses the platform's user-data
convention, confirms a nonempty resolved destination, and never resolves to the repository's `.data/`
directory.

Use fresh context-isolated read-only agents for the two required slice reviews; the single writer
pauses mutation while they inspect the same working state and verifies the diff afterward. An active
slice has no new checkpoint: `campaign.checkpoint` remains the last committed recovery point until
the reviewed slice commits. The committed `HEAD` containing the current ledger is the recovery
state; checkpoint labels are navigation identifiers. Dirty tracked state, a ledger differing from
`HEAD`, missing current evidence, or approved-plan drift blocks checkpoint validation and automatic
advance. When a recorded active slice has uncommitted work, inspect it against the last checkpoint;
resume only changes that explainably continue that slice, and stop on unexplained work. Any campaign
or slice blocker invalidates approval and stops execution. Project checkpoint IDs and the exact approval
transition are documented in `CONTRIBUTING.md`. Run
`just implementation-campaign-checkpoint-check` after each checkpoint commit; it is intentionally
post-commit and therefore not part of `just check`.
After approval, every slice and closure checkpoint must preserve the exact approved plan-bearing
authority, coverage, dependency, verification, realization-decision, and baseline projection. Plan
changes require a new candidate plan, cold review, and renewed human approval.

Every selected realization decision has one evidence-bearing completion owner. Decision selection,
authority, ownership, and evidence intent are plan-bearing; its implementation status and evidence
references are execution state. A worker must close each decision it owns individually. If a selected decision was omitted
from an already-complete owner, preserve the choice and add a corrective work item through renewed
planning rather than asking the owner to choose again.

Generate each review prompt with `just implementation-campaign-review-frame <work-item> <lens>`
after the slice is active, or with `closure` once every slice is complete. The frame deliberately excludes prior findings. Workers validate their compact
result with `just implementation-campaign-worker-result-check <path>`; managers do not accept raw
review output. Store timing, review-count, check-count, and optional harness-usage telemetry only in
the ignored `.cache/implementation-campaign/` area. Telemetry never establishes conformance or
authorizes advancement.

For Claude Code campaign workers, launch each reviewer `Agent` exactly once in foreground mode with
`run_in_background: false`. Submit both calls in one assistant turn only when the harness blocks until
both return; otherwise run them sequentially. Never await reviewers with background `Bash`, `sleep`,
`Monitor`, repeated status checks, or overlapping timers. If no direct join exists, permit at most
one foreground `sleep 300` at a time followed by one status check; start another only after the first
has completed. When the launcher can control the worker environment, prefer
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.

External client mutation is closure-only; S018 implements and tests the behavior with fake public
CLI executables and temporary Vellis destinations. Closure-owned D006 preserves the prior
authorization: after an exact matching dry run, closure may change only the named `vellis` entries
through public CLIs—replacing the disabled Codex HTTP entry with the selected STDIO entry and adding
the Claude Code user-scoped STDIO entry.
On a fresh attempt after interruption, either already-matching enabled user-scoped entry is an
idempotent no-op and only the remaining authorized transition may run. Conflicting or unparseable
state, another destination, unsupported behavior, or any approval-policy consequence pauses before
further mutation. Outside that closure step, reading configuration is fine but do not run `codex mcp
add`, `codex mcp remove`, `claude mcp add`, `claude mcp remove`, or any other mutating client command.

## Non-negotiable modeling rules

- Begin with owner value and observable behavior. Do not infer architecture from requested nouns,
  familiar names, predecessor code, framework examples, popular repository patterns, training-data
  priors, or incidental tests. Treat familiar architecture as a hypothesis, not a default.
- Close one changed semantic path at a time. Reuse existing behavior, domain meaning, requirements,
  satisfiers, and verification where they already carry the claim; add an element only at a layer
  whose meaning is missing. Semantic completeness does not require a new artifact in every layer.
- Prefer native SysML semantics. Comments and names cannot repair incorrect ownership, multiplicity,
  control, reference, satisfaction, or verification semantics.
- Review permitted instances recursively, not only declaration names. Inspect nested composites for
  accidental full-state ownership and define the joint tuple, projection, duplicate, absence, and
  null semantics of row-shaped results.
- Add actions only when functional refinement adds meaning. Group capabilities before parts, and add
  a part only for an independent lifecycle, state owner, failure responsibility, external
  interaction, or current realization decision.
- Keep persistence, transport, runtime, language, deployment, algorithms, and migration machinery
  open until intentionally selected. Do not add speculative services, controllers, adapters,
  managers, envelopes, extension seams, or duplicate authority.
- Prefer natural keys, derived meaning, one relationship authority, and one current prospective
  overlay before adding surrogate identity, stored flags, parallel rules, intent logs, or lifecycle
  machinery.
- Preserve explicit owner decisions and selected model meaning within the task's scope. Do not treat
  incidental tests, familiar patterns, explanatory comments, or mere element presence as owner
  decisions. An explicit review request may reassess them; otherwise reopen a decision only when new
  evidence creates a named contradiction and changed consequence.
- Do not use optional multiplicity to represent uncertainty, or configurable structure to represent
  a realization decision that is merely deferred. Absence, unknown, not applicable, and not yet decided
  are different meanings.
- Treat tool, protocol, and framework affordances as feasibility constraints, not a use-case or
  action inventory. Reflect them in the system model only when they change observable behavior or a
  selected realization boundary. The selected RTG MCP inventory is an intentional public contract,
  not evidence for services, adapters, ports, or matching internal decomposition. Its trusted-client
  assumption does not establish per-call authorization or owner approval.
- For agent-facing RTG work, begin cold: summarize the complete anchor vocabulary for current or
  explicitly selected historical state, inspect only the relevant active-definition neighborhoods at
  that evaluated revision, and reuse a time summary's resolved revision for historical inspection and
  query. Retrieve the sole current proposed definition set separately when continuing definition work,
  and rediscover current definitions before preparing a current mutation. Do not assume predecessor
  schema knowledge.
- Preserve independently valuable outcomes, state governance, failure non-effects, recovery meaning,
  and verification while subtracting unsupported structure.
- Tests may observe tooling, repository safety, or an implementation against the current model; they
  do not choose or freeze the living model's constructs, vocabulary, inventory, topology, or prose.
- Never hand-edit future generated product source; regenerate it and check freshness when generation
  exists.
- When accepted model work will guide implementation, hand off qualified authority, observable
  obligations, full or partial authority coverage, remaining obligations, decisive
  accepted/refused/failed cases, state and ownership boundaries, conformance-evidence intent, and
  exact realization deferrals. Keep that handoff reconstructible from the branch rather than
  creating a shadow specification. Implementation status is a separate value: not evaluated,
  absent, partial, conforming, or conflicting. Partial coverage never establishes whole-requirement
  satisfaction or whole-verification completion. Judge coverage against the complete cited accepted
  authority, not merely the task prompt or row summary; `full` always means no remaining obligation.
- Treat implementation feedback as evidence. Fix code that contradicts sufficient model authority;
  change the model only for a genuine model gap or a demonstrated feasibility consequence whose
  stakeholder-visible or intentionally selected realization-boundary consequence changes. Classify
  feedback as language question, model gap, realization decision, feasibility consequence,
  implementation defect, or stale baseline; treat an out-of-scope request separately. Unselected
  storage, acknowledgement, process, transport, framework, and deployment mechanics remain
  realization decisions unless their demonstrated consequence crosses that gate.
- Permit implementation classes and modules to be finer-grained than modeled parts. Record their
  many-to-many realization against semantic neighborhoods while preserving modeled lifecycle, state,
  transaction, failure, and external boundaries; a useful code component is not by itself a SysML
  subsystem.

Before model edits, read `model/README.md`, every current `model/*.sysml` file, affected dependencies,
and the current diff. Follow the operative workflow and handoff in `$sysml-modeling`.

Before implementation edits, first read the same current authority without taking architecture from
existing source. For complete-system work, follow `$sysml-implementation-planning` and
`$sysml-implementation-campaign`; for one accepted slice, follow `$sysml-implementation`. Use a
current model-work handoff when available and verify it against the branch; otherwise reconstruct its
task-local implementation frame directly from the model. Return to model work before coding across
an unresolved semantic gap.

For post-build audits or changes spanning model authority, implementation, evidence, and selected
realization, use `$sysml-evolution` and validate `system-evolution.yaml` with
`just system-evolution-check`. The record is an execution and evidence index, never product
authority. Changed system meaning still requires acceptance before implementation relies on it;
defects already decided by accepted authority remain ordinary implementation work.

## Resources and checks

`just model-setup` downloads and checksum-verifies every reference artifact into the ignored
`.cache/`, then generates the searchable corpus. Nothing derived from upstream is committed, so the
corpus cannot drift from its pin. What setup provides:

| Artifact | Answers | Where |
| --- | --- | --- |
| Specification corpus | what a construct *means* | `just model-reference-find` |
| Standard model library | what exists and what it specializes | same finder, hits labelled `[library]` |
| Example and training models | what a construct looks like in working SysML (309 models) | same finder, hits labelled `[example]` |
| Construct inventory | which SysML name a question maps to | `just model-reference-concepts` |
| Pinned validator | what the parser actually accepts | `just model-probe`, `just model-check` |

SysML v2 names concepts differently from ordinary systems-engineering usage, so a search that returns
nothing convincing usually means the wrong word, not a missing capability. Consult the construct
inventory, then search again.

Begin with `just model-reference-find`; optional specification and limit arguments are positional,
for example `just model-reference-find "<question>" sysml-2.1 8`. Follow normative cross-references, inspect extraction
warnings, and never edit the generated corpus by hand. Cite the specification version and release
tag with the clause and page; the pinned beta documents carry no OMG document number.

Use `uv` and `just`. Run `just setup` and `just model-setup` after cloning. Before completion, run the
relevant narrow checks and normally `just check`. Keep `.data/` untouched.

`just implementation-campaign-check` validates the committed execution index against the current
model and language baselines. `just implementation-campaign-status` reports its approval, active or
next slice, blocker, and closure state. `just implementation-campaign-dispatch` emits the manager's
machine-readable next action and durable state token without changing files. These tools do not
resolve SysML semantics and the ledger does not replace rereading qualified model authority.

`just system-evolution-check` validates the active evolution record's schema, exact ownership,
dependency order, approval checkpoints, lifecycle, repository-derived observed baselines,
project-bound evidence references, and attributable review invariants. `just
system-evolution-status` reports its approval, next work, and open-finding count.

The repository exposes the selected MCP tool contract over local standard input and output. Matching
user-scoped Codex and Claude Code entries are configured to launch it, and accepted bounded
invocations through both clients complete the selected live boundary. Use modeled, selected,
implemented, verified, and runnable precisely.
