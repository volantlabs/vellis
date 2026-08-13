# Contributing

Vellis is developed model-first. Textual SysML v2 under `model/` is the current system authority;
handwritten documentation remains explanatory.

## Setup

Requires `uv`, `just`, and `git`.

```sh
just setup
just model-setup
just check
```

## Skill portability

`$sysml-reference`, `$sysml-modeling`, `$sysml-implementation-planning`,
`$sysml-implementation`, `$sysml-implementation-campaign`, and `$sysml-evolution` are maintained as
a portable SysML v2 MBSwE core. Keep Vellis paths, commands, RTG and MCP semantics, implementation language, and
repository-specific review rules in local guidance or optional extensions. When changing the core,
apply the risk tier in `AGENTS.md`: repository checks for editorial changes, two contrasting fresh-
agent archetypes for bounded orchestration or review-method changes, and all five archetypes for
cross-domain semantic or readiness changes. Do not use Vellis as the only semantic test case or claim
that a standalone plugin already exists.

## Change workflow

1. Create a branch and read `AGENTS.md`, `model/README.md`, relevant skills, and the current diff.
   Read the complete model for model edits, complete-system planning, and whole-system closure. For
   bounded implementation, evolution, or slice review, read the qualified authority, enclosing
   declarations, transitive semantic dependencies, and verification intent; record unread scope and
   expand only when a consequential reference cannot be resolved.
2. State one primary owner or engineering question, the observable change, and the explicit owner
   decisions, selected model meaning, or deliberate deferrals the change must preserve.
3. Trace the smallest affected semantic slice through the existing behavior, domain meaning, native
   representation, responsibility, requirements, satisfiers, and verification. Add only the elements
   needed to close a missing claim; do not populate layers for symmetry.
4. For a formal plan, map every mandatory claim and non-goal to authority and evidence. Review
   decisive examples, then repeat plan-conformance, closure, adequacy, subtraction, and repository-
   truth reviews until one full cycle finds no new material issue.
5. Run a task-local semantic consistency audit before validation. For each changed claim, compare
   native ownership, reference, multiplicity, binding, and derivation with observable effects and
   non-effects, requirement wording, satisfiers, verification evidence, and explanatory documentation.
   Record a temporary state-effect vector for every governed state the behavior may preserve or change
   (for RTG: graph, active definitions, delta, revision, canonical ledger, and activity ledger), then
   exercise the nearest wrong permitted instance. Search for stale and inverse claims. Do not commit
   the audit matrix; after a material fix, repeat the audit from the current diff to a clean fixed point.
6. Cite official sections and pages for consequential language choices and run `just check`.
7. In the PR, report changed meaning, evidence, compatibility effects, unsupported architecture
   removed or deferred, any decision reopened by the review scope or new contradictory evidence, and
   bounded follow-up work.

For a post-build audit or cohesive change set that spans model and implementation, use
`$sysml-evolution`. Bind raw evidence and classifications to `system-evolution.yaml`, route model
gaps through `$sysml-modeling`, route bounded realization work through `$sysml-implementation`, and
run `just system-evolution-check`. A code defect under sufficient accepted authority does not require
a model edit; changed system meaning must be accepted before implementation relies on it.

Vellis derives the evolution record's observed model, language, lockfile environment, Git
implementation, and checkpoint identities from the checked repository. A ready or active work item
binds one named dimension to that observed identity. Accepted approvals use the Git commit containing
the accepted record transition. Evidence commands are limited to repository checks and focused test
commands; path evidence resolves a Python test node or Markdown heading. Final reviews name the
independent reviewer and reviewed Git checkpoint and cover every lens declared in scope. The final
record-only commit may follow the reviewed implementation checkpoint, but no other tracked change may
sit between that checkpoint and closure.

## Implementation workflow

1. For a complete-system request, use `$sysml-implementation-planning` to read the complete model,
   derive full aggregate authority coverage and a dependency-ordered campaign, validate
   `implementation-campaign.yaml`, and obtain explicit human approval. Use
   `$sysml-implementation-campaign` only after approval. For one already selected slice, start with
   `$sysml-implementation`.
2. Read the scope required by `AGENTS.md` and the current diff before taking architecture from
   existing source. Use a current model-work semantic handoff when available and verify it against
   the branch; otherwise reconstruct the affected authority directly. Ordinary post-build evolution
   starts from `system-evolution.yaml`; read the stale completed campaign only for campaign-history
   reconstruction, a preserved campaign decision, or complete-system replanning.
3. Separate required model meaning, already selected realization constraints, realization decisions
   still open to implementation, genuine model gaps, and deliberate non-goals. Return to model work
   before coding across a gap in stakeholder-visible behavior, state, responsibility, failure,
   compatibility, or verification.
4. Plan one end-to-end semantic slice. For every cited authority, record the in-scope obligation,
   full or partial coverage, any remaining obligations, decisive conformance evidence, and required
   non-effects. Keep implementation status—`not evaluated`, `absent`, `partial`, `conforming`, or
   `conflicting`—separate from authority coverage. When software needs finer structure than the
   systems model, record a many-to-many realization against semantic neighborhoods and preserve the
   modeled lifecycle, state, transaction, failure, and external boundaries.
   For consequential stateful operations, also record permitted scale drivers, forbidden unrelated-
   population dependencies, retained and transient materialization shape, and any operation whose
   meaning legitimately requires state-wide work. This qualitative resource-shape check does not
   invent numerical budgets.
5. Implement the simplest sufficient realization and derive conformance evidence from verification
   intent rather than mirroring model declarations. Use tests, analysis, simulation, inspection,
   demonstration, numerical references, timing measurements, or hardware evidence as appropriate.
   Exercise accepted behavior, semantic rejection or failure, and the nearest invalid counterexample.
   For modeled history scaling, instrument semantic record accesses or equivalent traces before using
   wall-clock measurements. Current-state decomposition, revision/time and relationship indexes,
   definition checkpoints, caches that do not retain prohibited complete state, and snapshot cadence
   are possible realization choices, not model-selected architecture. For the selected Vellis SQLite
   realization, evidence must show that definition-only work materializes no graph, ordinary mutation
   work stays within the complete affected invariant closure, query candidates are narrowed by
   semantic identity joins before value filtering and stop at the modeled bound, explicit broad checks
   remain bounded-memory, and lifecycle work streams. Do not claim numerical performance satisfaction
   before representative budgets exist.
   Treat Vellis v1 compatibility as confirmed first-use initialization from one complete JSON snapshot,
   never as an existing-system merge or adoption of v1 ledger history.
6. After focused evidence passes, freeze one state token and use fresh read-only agents for separate
   authority/conformance and engineering/evidence reviews. Checkpoint after one pair in which both
   lenses are clean and no substantive tracked or evidence state changes afterward. Prepare all
   evidence references and intended completion statuses before freezing the review state. After a
   clean pair, permit only the deterministic atomic bookkeeping transition that applies those
   reviewed statuses and checkpoint identifiers. Any implementation, test, documentation, evidence-
   reference, decision-content, or plan-bearing mutation invalidates the pair. If either lens finds
   a material issue, one writer batches corrections, sweeps the root cause, reruns affected evidence,
   and obtains a new clean pair. After three consecutive non-clean pairs, perform one bounded root-
   cause audit before another pair; do not ask reviewers to invent mutants or speculative inputs
   merely to continue discovery. Commit the slice's
   implementation, tests, evidence, documentation truth, and campaign update together; return the
   compact worker result and stop without selecting the next slice.
7. In the PR, distinguish modeled, selected, implemented, verified, and runnable. Do not claim an
   entire requirement satisfied or verification case passed from a partially covered slice. Return
   reproducible implementation evidence to model work only for a model gap or demonstrated
   feasibility consequence; keep unselected implementation mechanics in realization work.

A model or material plan gap, changed baseline, or stakeholder-visible feasibility consequence
invalidates campaign approval and requires human review before work resumes. Ordinary code defects
and model-preserving realization choices remain autonomous implementation work. Use
`just implementation-campaign-check` before any campaign checkpoint and
`just implementation-campaign-status` to inspect resumable state.
After approval, use a thin long-running manager that runs
`just implementation-campaign-dispatch`, launches one fresh worker for the named slice or closure
item, waits for it, consumes only a compact validated result, and rechecks the committed checkpoint.
The manager never implements, reviews, or reads reviewer transcripts. One accepted complete plan
authorizes the dependency-ordered campaign; routine slice completion does not create 17 additional
human approval gates. Each worker stops after one checkpoint or declared pause. Any harness and
provider may realize these roles as long as durable state and the one-writer boundary remain intact.

For this repository's initial harness trial, using Claude Sonnet at medium reasoning for the manager
and fresh Opus 5 Medium workers is a non-normative cost/conformance configuration; Opus 5 Low is an
acceptable manager substitute. Provider and model choice are not part of the portable method or the
approved implementation plan. Claude workers launch reviewer `Agent` calls once in foreground mode
with `run_in_background: false`. They may issue both calls in one turn only when the harness blocks
until both return; otherwise they run the lenses sequentially. They never poll reviewer work with
background shell commands, sleeps, monitors, or overlapping timers. Without a direct join, use at
most one foreground five-minute wait followed by one status check.

The manager passes the dispatch `state_token` to its worker. Before mutation, the worker reruns
`just implementation-campaign-dispatch 0 <state-token>`; a changed token stops stale or duplicate
work. After activation,
generate each fixed review prompt with
`just implementation-campaign-review-frame <work-item> <lens>`, naming the active slice or
`closure`.
Validate the compact handoff with `just implementation-campaign-worker-result-check <path>` and put
optional JSONL timing, review-count, check-count, and harness-usage telemetry under the ignored
`.cache/implementation-campaign/` directory. Wait ten minutes only after transient launcher or quota
failure when no child is live, and stop after three identical failures against one state token.
The completed campaign's plan directly pins FastMCP and FastMCP Slim 4.0.0b1, selects local STDIO,
and selected clean macOS onboarding through a documented Python setup path. The
pins, the STDIO boundary, and the setup path's three starting inputs — a confirmed fresh vocabulary,
a canonical snapshot document, and a confirmed v1 snapshot — are implemented, and a client launching
the server as a subprocess is exercised end to end, including the exact command an owner would
register. Closure configured and verified both supported clients on this machine; that effect changed
client-owned configuration rather than this repository.

That selected client-configuration behavior was not built by its original owners. Closure caught the
escaped implementation defect after all original slices had checkpointed, so the renewed approved
plan preserved the choice and allocated it to corrective slice S018, with the live dry run and
registration completed at closure. That campaign is now the completed-but-stale source baseline;
`system-evolution.yaml` and `just system-evolution-status` report the current post-build work.

Vellis checkpoint identifiers are navigation labels in the portable campaign record:

- approval: `approval:<full-approved-plan-commit-sha>`;
- slice: `slice:<slice-id>:<approved-plan-short-sha>:<attempt>`;
- closure: `closure:<approved-plan-short-sha>:<attempt>`.

Start an attempt at `1` and increment it only if a checkpoint for the same slice and approved plan
already committed. Attempt numbers are scoped to one slice under one approved plan, so a slice that
is still pending when a renewed plan is approved starts at `1` under that plan. A slice that was
already complete keeps its checkpoint untouched; re-running it means reopening it in the candidate
record before approval, not a second attempt. No special Git commit trailers are required.

The approval commit is a direct child of the reviewed plan commit and changes only
`implementation-campaign.yaml`: set campaign lifecycle to `ready`, approval to `accepted`, both
approval and campaign checkpoints to `approval:<reviewed-plan-sha>`, and only the lowest-ordered
dependency-ready slice to `ready`. It may not change authority, coverage, slices, dependencies,
verification, decisions, blockers, evidence, or any other plan-bearing content. A campaign or slice
blocker changes approval to `changes-required`, clears its approval checkpoint, and puts the campaign
in `blocked` or `stale`; execution does not continue through that state.
Every later slice and closure checkpoint preserves that approved plan-bearing projection exactly.

For the completed corrective plan, the approval transition readied only S018 while S001 through S017
retained their existing checkpoints. S018 owned the missing selected setup behavior; closure owned the
authorized live client transition. Approval did not itself authorize external client mutation: that
occurred only at the approved closure step after its dry run exactly matched expected state. The plan
preserved prior `integration_status: conforming` evidence across the seventeen completed slices while
keeping A017 and the runnable client boundary partial until S018 and fresh closure rechecked them.

Replanning after slices have completed ends at a renewed approval, which follows the same rule with
one difference: completed slices keep the checkpoints they earned, including the superseded approved
plan those labels name. A corrected plan narrows what those slices claimed and moves the remaining
obligations into later slices; it does not invalidate the work they committed, so re-minting their
labels would attest to a plan under which they were never reviewed. The renewed approval commit sets
both approval and campaign checkpoints to `approval:<reviewed-plan-sha>` exactly as a first approval
does, and readies only the next dependency-ready slice. Until a slice completes under the renewed
plan, that approval is the latest recoverable campaign checkpoint; the next completed slice then
takes its place, using the renewed plan's short sha and attempt `1`. A campaign that blocks before
that happens may keep the approval as its checkpoint rather than falling back across the replan; it
may also retain the last completed slice, whose label still names the superseded plan. Both are
recoverable states, so both are permitted — but a retained approval must be one granted after that
slice, never the approval the slice itself was completed under.

The approved plan commit is the approval commit's direct parent, and its
`implementation-campaign.yaml` is the reviewed candidate record. Those are usually the same commit.
When review is followed by a commit that leaves the campaign record untouched — a checker or
documentation fix, say — that later commit carries the reviewed plan forward unchanged and is the
one to approve; naming the earlier commit instead fails the parent check.

Two gates divide this work, and the split matters:

- `just implementation-campaign-check` reads only the record. It cannot know when a slice completed,
  so it bounds the superseded region rather than locating it: every slice completed at or after the
  first one bearing the current approved plan must bear it too, and a campaign that is ready or
  active may never rest on a slice checkpoint naming a superseded plan. The bound is silent while no completed slice yet bears the
  current plan, so a slice mislabelled in that window passes this gate — and so does every later one
  until some slice adopts the current plan. Only the second gate closes that.
- `just implementation-campaign-checkpoint-check` reads the approved plan commit, whose own record
  says which slices were already complete when it was reviewed. That is the boundary: anything
  finished since must checkpoint against this plan, and anything finished before must keep its label
  byte for byte. It also resolves the approval a blocked campaign still rests on, and identifies the
  approval commit by what it changed rather than by what the record claims, so an ordinary commit
  landing while the campaign waits is not judged as one. Run it after every
  checkpoint commit, including the approval, before advancing; it is the only automated detector for
  a mislabelled slice, and it is not part of `just check`, so skipping it loses the check entirely.

Before granting approval, confirm that the candidate record's completed slices — which ones, and the
exact checkpoint each carries — are the work actually finished. That set becomes the permanent
boundary both gates consult, and no later check can question it.

Changing the baseline, authority map, coverage, slice graph, verification references, or selected
realization decisions requires replanning, a new cold review, and renewed human approval.

A selected realization decision records one completion owner and advances through explicit
implementation status and reproducible evidence. Ownership, the selected choice, and its evidence
intent are plan-bearing; status and evidence references may advance during execution. A completed slice may not leave one of its owned
decisions open, and closure may not complete with an open closure-owned decision. If an already
checkpointed owner omitted a selected decision, add a corrective work item through renewed planning;
do not reopen the choice unless new evidence changes its stakeholder-visible consequence.

During uncommitted active work, retain the preceding campaign checkpoint and leave the active
slice's checkpoint null. Each completed slice uses one ordinary commit containing implementation,
tests, evidence, documentation truth, and the ledger update. The committed `HEAD` containing the
current ledger is the recovery state; checkpoint labels help navigate it rather than attest to Git
history. The project trusts its owner, executing agent, Git implementation, and committed checker.
It detects accidental dirty state, stale authority, plan drift, missing evidence, and interruption;
it does not defend against malicious local history or checker rewriting.
Run `just implementation-campaign-check` before committing and
`just implementation-campaign-checkpoint-check` afterward. If the post-commit binding fails, do not
advance; amend the sole unpublished checkpoint commit when safe, otherwise request recovery direction.

Campaign evidence uses `path:<repo-relative-path>#<test-or-section>` for committed artifacts or
`command:<exact reproducible command>` for rerunnable checks. A path fragment must resolve to a
Markdown heading anchor or a Python test node in the current committed state, and a path may not
escape the repository through a symlink. S001
chooses the product source and test layout and extends all repository gates to cover it in that same
checkpoint. Product tests use temporary data locations and never inspect or write `.data/`.

## Testing authority

Automated tests may observe language tooling, repository safety, and future implementations. They do
not choose or freeze the living model's constructs, names, counts, topology, package layout, or prose.
A future implementation contract check may compare implemented behavior with the current model: the
implementation is constrained by the model, not the model by a duplicate test inventory.

When tests and model structure were introduced together, review the model independently from owner
purpose, accepted and refused examples, state effects, and decisive evidence. Passing tests or parser
acceptance cannot substitute for that semantic review.

Do not introduce realization machinery without a current modeled need. Product source under
`vellis/` is authored, not generated. The selected MCP tool contract is implemented and runnable over
local standard input and output, and a real client launching it over that transport is exercised.
Matching user-scoped Codex and Claude Code entries are configured to launch it. Whole-system live
closure is complete, with accepted bounded invocations through both named clients and reproducible
project evidence for the selected boundary.
