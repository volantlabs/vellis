# AGENTS.md

## Authority

Vellis is one individually owned application and an open demonstration of model-first software
engineering. Textual SysML v2 under `model/` is product and system authority on each branch.
Markdown explains the work without restating its contracts. Implementation realizes the current
model and may select choices the model intentionally leaves open; tests are conformance evidence,
not parallel product authority.

## Safety

At the start of work, run `pwd`, `git status --short --branch`, and `git worktree list`. Do not switch
branches in a worktree without human confirmation. Preserve unexplained changes and stop when they
cannot be reconciled with the active work.

The ignored `.data/` directory may contain user-owned graphs and databases. Do not inspect, move,
rewrite, migrate, or delete it unless the human explicitly requests that exact operation. Never run
broad ignored-file cleanup commands here.

Do not mine v1 history for current requirements or design patterns unless the human requests a
historical comparison or recovery task. Do not mutate external client configuration except during an
explicitly authorized closure step; use public client CLIs and stop on conflicting or unparseable
state.

## Running Vellis

Check for an existing install before assuming one is needed: `command -v vellis`. If absent, install
with `uv tool install git+https://github.com/volantlabs/vellis`; see
[`docs/install.md`](docs/install.md) for the full command set and troubleshooting.

For a throwaway test instance that touches no global state — the recommended shape for unattended
work — use a scratch data directory and skip client registration:

```sh
uv run vellis setup --starter --no-connect --data-dir "$(mktemp -d)/vellis-data"
uv run vellis serve --transport stdio --data-dir <that same directory>
```

`uv run` works from a clone without a separate install step. Rules that apply at this scope:

- Every invocation needs a subcommand; bare `vellis` or `python -m vellis` is a usage error, not a
  server.
- Never point a throwaway `--data-dir` at `.data/` or any existing owner destination.
- Pass `--no-connect` in unattended use; `vellis connect` mutates external client configuration and
  is covered by the `## Safety` restriction above.
- One initialization mode must be given explicitly on a noninteractive `setup` — `--starter` (the
  recommended Everyday Life vocabulary), `--blank`, `--from-v1`, or `--from-backup`. There is no
  default when no terminal is present to confirm one.

## Skill routing

The portable MBSwE core is `$sysml-reference`, `$sysml-modeling`,
`$sysml-implementation-planning`, `$sysml-implementation`,
`$sysml-implementation-campaign`, and `$sysml-evolution`. Use `$rtg-schema-design` for RTG meaning
and governance and `$documentation-sync` after model, workflow, tool, skill, template, or public-
guidance changes.

- Use `$sysml-reference` for every consequential SysML or KerML choice.
- Use `$sysml-modeling` for system meaning, requirements, satisfiers, verification, adequacy, and
  simplification.
- Use `$sysml-implementation-planning` and `$sysml-implementation-campaign` for a complete-system
  build; use `$sysml-implementation` for one accepted semantic slice.
- Use `$sysml-evolution` for post-build findings or changes spanning accepted authority,
  realization, evidence, compatibility, and rebaselining.

Keep the portable core independent of Vellis paths, commands, RTG or MCP vocabulary, Python, Git,
persistence, networking, and any one architecture. Bind those concerns here, in `CONTRIBUTING.md`,
or in optional domain skills.

## Reading scope

Read `model/README.md`, every current `model/*.sysml` file, affected dependencies, and the current
diff before model edits, complete-system planning, or whole-system closure review.

For a bounded implementation, evolution item, or slice review, read `model/README.md`, the qualified
authority, its enclosing declarations, transitive semantic dependencies, applicable verification or
analysis intent, and the current diff. Record which model scope remains unread and expand only when a
reference, inherited constraint, or consequential effect cannot be resolved. Do not claim complete-
system readiness from a partial read.

For ordinary post-build evolution, use the current `system-evolution.yaml` authority closure and
baseline. Do not read the stale completed `implementation-campaign.yaml` unless reconstructing
campaign history, checking a preserved campaign decision, or replanning the complete system.

Read existing implementation only after the first authority pass; never infer architecture from
source layout, framework examples, familiar names, or incidental tests.

## Non-negotiable engineering rules

- Begin with owner value and observable behavior. Close one changed semantic path at a time and add
  model elements only where meaning is missing.
- Prefer native SysML ownership, reference, multiplicity, control, binding, satisfaction, and
  verification semantics. Comments and names cannot repair incorrect semantics.
- Review permitted instances recursively, including nested ownership, joint tuples, projections,
  duplicates, absence, null, state effects, failure non-effects, and recovery where applicable.
- Model at any depth the project means to govern, including software structure and internal
  interfaces. What is modeled binds implementation and what is unmodeled is the implementer's to
  choose, so leave persistence, transport, runtime, language, deployment, algorithms, migration, and
  internal decomposition unmodeled until the project means to govern them. A class or module found
  in code is not thereby a modeled part.
- Preserve explicit owner decisions and accepted model meaning. Treat implementation feedback as a
  language question, model gap, realization decision, feasibility consequence, implementation
  defect, stale baseline, or out-of-scope request before mutation.
- Fix an **acceptance set** before dispatching a work item: a numbered list of specific wrong
  behaviors the change must make impossible, each stated as an observable outcome, plus the
  non-effects it must leave untouched. The set closes at dispatch. The agent doing the work does
  not extend it.
- A work item is **done** when every acceptance entry names one piece of evidence that fails if
  that wrong behavior is present, the declared non-effects hold, and the project gate passes.
  Nothing further is required for done.
- A reviewer extends a closed acceptance set only by reporting a defect the artifact actually
  exhibits, with a reproduction. A merely conceivable wrong behavior is a recorded, non-blocking
  observation and a candidate for a new finding and a new dispatch. Growing the acceptance set is
  never a reason to run another review pair.
- Tests do not freeze model vocabulary, structure, inventory, or prose.
- Never hand-edit generated product source when generation exists; regenerate and check freshness.
- Distinguish modeled, selected, implemented, verified, and runnable. Partial authority coverage
  never establishes whole-requirement satisfaction or whole-verification completion.

Before approving implementation plans for consequential stateful operations, identify permitted
scale drivers, forbidden unrelated-population dependencies, retained and transient materialization
shape, and operations whose meaning legitimately requires state-wide work. Defer numerical latency,
throughput, startup, or storage targets until representative runtime, hardware, and owner data exist.

## Review and checkpoint rules

Use one writer and two fresh, context-isolated read-only reviewers for a review pair: one
authority/conformance lens and one engineering/evidence lens. Pause mutation while both inspect the
same state token. Before freezing it, put all evidence references and intended completion statuses in
the review frame. A pair closes review when both lenses report no material finding and substantive
tracked or evidence state remains unchanged afterward. The compact result must name both distinct
reviewer identifiers and lenses, their clean dispositions, and the exact shared token; validate it against the
frozen token, recomputed current durable state, current campaign/work item, intended checkpoint, and
reported passed checks before bookkeeping. Fresh-agent independence remains an operational manager
obligation, and the manager independently runs required project gates rather than treating reported
check rows as proof of execution or completeness. The only permitted post-review mutation is
the deterministic atomic bookkeeping transition that applies those already-reviewed statuses and
checkpoint identifiers. Any implementation, test, documentation, evidence-reference, decision-
content, or plan-bearing mutation invalidates the clean pair; batch corrections, sweep the root
cause, rerun affected evidence, and obtain another clean pair. After three consecutive non-clean
pairs, perform one bounded root-cause audit before another pair.

For a complete implementation campaign, require a current validated human-approved plan, one active
slice, one fresh worker per slice, and atomic checkpoints containing implementation, evidence,
documentation truth, and campaign state. The manager consumes compact validated results and never
implements or reads reviewer transcripts. Model or plan gaps, stale baselines, and stakeholder-
visible feasibility consequences stop execution; implementation defects and model-preserving
realization decisions remain campaign work. Detailed checkpoint and harness rules are in
`CONTRIBUTING.md` and the campaign skill.
Candidate-result validation occurs before deterministic bookkeeping. After the commit changes the
state token, the manager validates the checkpoint independently rather than rerunning that check.

For post-build evolution, validate `system-evolution.yaml`. It is an execution and evidence index,
never product authority. Changed system meaning requires acceptance before implementation relies on
it; a defect already decided by accepted authority is ordinary implementation work.

## Portable-core validation

Choose validation by the consequence of a portable-core change:

- Editorial, link, or metadata-only: repository and skill checks.
- Bounded orchestration, context, or review-method behavior: fresh-agent forward tests on two
  contrasting archetypes selected for the affected concern.
- Cross-domain semantic, construct-selection, readiness, or evidence-method behavior: fresh-agent
  forward tests on a stateless transformation, interactive stateful workflow, distributed message-
  driven system, embedded or real-time controller, and numerical or safety/security-relevant system.

Run required forward tests without disclosing expected conclusions or prior diagnoses. Keep prompts,
transcripts, and expected-answer fixtures out of the repository; summarize scenarios, material
findings, and disposition in the task handoff or PR discussion.

## Resources and checks

Use `uv` and `just`. `just model-setup` fetches checksum-pinned language references into ignored
`.cache/`; begin language research with `just model-reference-find` and validate authored models with
`just model-check`. Do not edit generated reference corpora.

Run focused checks during work and normally `just check` before completion. Use
`just implementation-campaign-check` plus the post-commit
`just implementation-campaign-checkpoint-check` for campaign work, and
`just system-evolution-check` for evolution work. Keep `.data/` untouched.
