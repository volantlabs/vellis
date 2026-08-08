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
`$sysml-implementation`, and `$sysml-implementation-campaign` are the portable MBSwE core.
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
- `$documentation-sync`: repository authority, commands, skills, templates, and public guidance.

## Portable-method boundary

Keep the five core skills reusable as written outside Vellis. They may require abstract capabilities
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
slice. Use one writer and one active slice. After implementation, run independent read-only
authority/conformance and engineering/evidence reviews, remediate to a fixed point, then commit the
slice and campaign update together. A model or material plan gap, stale baseline, or
stakeholder-visible feasibility consequence invalidates approval; implementation defects and
model-preserving realization choices remain campaign work.

For Codex, an accepted campaign may be launched as a long-running goal with campaign completion as
its stopping condition. Any equivalent continuation harness is acceptable, but it must resume from
the validated committed campaign and project checkpoint rather than relying on conversation memory.

The current candidate campaign selects `fastmcp==4.0.0b1`, local STDIO, and a future documented
Python setup path that configures user-scoped Codex or Claude Code only through their public CLIs.
These are selected realization constraints, not model structure or implemented capability. Do not
upgrade the pre-release pin, add another transport, or edit client configuration files directly
without renewed review of the selected plan.

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
next slice, blocker, and closure state. These tools do not resolve SysML semantics and the ledger does
not replace rereading qualified model authority.

The model selects an MCP tool contract but the repository has no runnable MCP server. Use modeled,
selected, implemented, and runnable precisely.
