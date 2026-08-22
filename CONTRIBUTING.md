# Contributing

Vellis is developed model-first. Textual SysML v2 under `model/` is the current system authority;
handwritten documentation remains explanatory.

## Setup

Requires `uv`, `just`, and `git`.

```sh
just setup
just model-setup
just package-check
just check
```

`just build` produces the wheel and source distribution into `dist/` for local inspection; it is
independent of `just package-check`, which builds and smoke-tests its own disposable copies and
also proves the documented `uv tool install git+...` path against this checkout's committed HEAD
(see [`docs/install.md`](docs/install.md)).

### Version bump

The version is a static literal in four places, cross-checked by
`tests/test_repository_policy.py::test_version_is_consistent_across_metadata_runtime_and_lock`:

1. `pyproject.toml` (`project.version`)
2. `vellis/__init__.py` (`__version__`)
3. `tests/test_repository_policy.py` (the literal comparison)
4. Run `uv lock` to regenerate the matching `uv.lock` entry.

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
   Treat Vellis v1 compatibility as confirmed first-use initialization from one complete JSON snapshot
   into a separate v2 destination, never as an existing-system merge, raw-store adoption, same-directory
   replacement, in-place conversion, or adoption of v1 ledger history. A post-upgrade recovery may run
   tagged v1.0 in a separate environment against the untouched old directory to produce that snapshot.
6. After focused evidence passes, freeze one state token and use fresh read-only agents for separate
   authority/conformance and engineering/evidence reviews. Checkpoint after one pair in which both
   lenses are clean and no substantive tracked or evidence state changes afterward. Prepare all
   evidence references and intended completion statuses before freezing the review state. After a
   clean pair, record each distinct reviewer identifier, lens, clean disposition, and the exact shared token in
   the compact worker result, and validate it against the frozen token and recomputed current durable
   state. These identifiers record attribution; the manager still enforces fresh-agent independence
   and independently runs required project gates and validates the resulting checkpoint. Reported
   check rows are not proof of execution or completeness. Pair counts alone do not bind
   review state. Then permit only the deterministic atomic bookkeeping transition that applies those
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

The portable campaign engine and its explicit campaign recipes remain
available for a future approved complete-system campaign. They are intentionally separate from
ordinary `just check`; current post-build work is reconstructed from `system-evolution.yaml`.
Provider-specific harness trials and completed-campaign narratives do not belong in contributor
guidance. Repository work never reads or edits real client configuration files.

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
escape the repository through a symlink. Product tests use temporary data locations and never
inspect or write `.data/`.

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
local standard input/output and foreground HTTP. Tests exercise public Codex and Claude CLI
registration without claiming or mutating an owner's real client configuration.
