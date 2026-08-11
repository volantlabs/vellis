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
`$sysml-implementation`, and `$sysml-implementation-campaign` are maintained as a portable SysML v2
MBSwE core. Keep Vellis paths, commands, RTG and MCP semantics, implementation language, and
repository-specific review rules in local guidance or optional extensions. When changing the core,
apply the cross-domain portability review in `AGENTS.md`; do not use Vellis as the only test case or
claim that a standalone plugin already exists.

## Change workflow

1. Create a branch and read `AGENTS.md`, `model/README.md`, the complete model, relevant skills, and
   current diff.
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

## Implementation workflow

1. For a complete-system request, use `$sysml-implementation-planning` to read the complete model,
   derive full aggregate authority coverage and a dependency-ordered campaign, validate
   `implementation-campaign.yaml`, and obtain explicit human approval. Use
   `$sysml-implementation-campaign` only after approval. For one already selected slice, start with
   `$sysml-implementation`.
2. Read the current model and diff before taking architecture from existing source. Use a current
   model-work semantic handoff when available and verify it against the branch; otherwise reconstruct
   the affected authority directly.
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
5. Implement the simplest sufficient realization and derive conformance evidence from verification
   intent rather than mirroring model declarations. Use tests, analysis, simulation, inspection,
   demonstration, numerical references, timing measurements, or hardware evidence as appropriate.
   Exercise accepted behavior, semantic rejection or failure, and the nearest invalid counterexample.
   For modeled history scaling, instrument semantic record accesses or equivalent traces before using
   wall-clock measurements. Materialized current projections, revision/time indexes, definition
   checkpoints, caches, and snapshot cadence are possible realization choices, not model-selected
   architecture; do not claim numerical performance satisfaction before representative budgets exist.
   Treat Vellis v1 compatibility as confirmed first-use initialization from one complete JSON snapshot,
   never as an existing-system merge or adoption of v1 ledger history.
6. After focused evidence passes, use fresh read-only agents for separate authority/conformance and
   engineering/evidence reviews. One writer collects both sets of findings and batches all in-scope
   corrections, then obtains one final independent review pair. Repeat only if that pair finds a
   plausible failure under the declared project assumptions. Commit the slice's implementation,
   tests, evidence, documentation truth, and campaign update together; then continue to the next
   ready slice.
7. In the PR, distinguish modeled, selected, implemented, verified, and runnable. Do not claim an
   entire requirement satisfied or verification case passed from a partially covered slice. Return
   reproducible implementation evidence to model work only for a model gap or demonstrated
   feasibility consequence; keep unselected implementation mechanics in realization work.

A model or material plan gap, changed baseline, or stakeholder-visible feasibility consequence
invalidates campaign approval and requires human review before work resumes. Ordinary code defects
and model-preserving realization choices remain autonomous implementation work. Use
`just implementation-campaign-check` before any campaign checkpoint and
`just implementation-campaign-status` to inspect resumable state.
After approval, Codex contributors may launch the campaign as a long-running goal; use campaign
completion as the stopping condition and the modeled human-authority boundary as the pause condition.
One accepted complete plan authorizes the dependency-ordered campaign; routine slice completion does
not create 17 additional human approval gates. Each slice still requires its two independent review
lenses. Collect both sets of findings, batch all in-scope corrections, then run one final independent
review pair. Repeat only for a plausible failure under the declared project assumptions; do not
recursively red-team the campaign process unless the selected slice changes it.
The approved plan directly pins FastMCP and FastMCP Slim 4.0.0b1, selects local STDIO, and reserves
clean macOS onboarding through a documented Python setup path for runnable closure. The pins, the
STDIO boundary, and the setup path's fresh start and v1 recovery are implemented; starting from a
v2 snapshot, and configuring a client to launch the server, remain for later slices.

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

Do not introduce realization machinery without a current modeled need. The repository has no product
runtime or generated product source today. The model selects an MCP tool contract, but no MCP server
is implemented or runnable.
