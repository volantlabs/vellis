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
   engineering/evidence reviews. One writer remediates findings and repeats both reviews after every
   material correction. When one full cycle finds no new issue, commit that slice's implementation,
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
not create 17 additional human approval gates. Each slice still requires its two independent clean
reviews before the writer checkpoints it and continues.
The current candidate plan directly pins FastMCP and FastMCP Slim 4.0.0b1, selects local STDIO, and
reserves clean macOS onboarding through a documented Python setup path for runnable closure; these
remain unimplemented until their campaign slices complete.

Vellis checkpoint identifiers bind the portable campaign record to Git without trying to embed a
commit's own hash:

- approval: `approval:<full-approved-plan-commit-sha>`;
- slice: `slice:<slice-id>:<approved-plan-short-sha>:<attempt>`;
- closure: `closure:<approved-plan-short-sha>:<attempt>`.

Start an attempt at `1` and increment it only if a checkpoint for the same slice and approved plan
already committed. Put the required lines together in the commit's final Git trailer block. Every
checkpoint carries `Campaign-Checkpoint: <identifier>`. Approval adds
`Campaign-Approval: accepted`; slice commits add `Campaign-Authority-Review: clean` and
`Campaign-Engineering-Review: clean`; final closure adds `Campaign-Closure-Review: clean`.
Each required campaign trailer occurs exactly once with the documented key spelling and value, and
checkpoint commits carry no campaign trailer belonging to another checkpoint kind. Missing,
case-variant, duplicate, contradictory, or extra `Campaign-*` trailers invalidate the checkpoint.

The approval commit is a direct child of the reviewed plan commit and changes only
`implementation-campaign.yaml`: set campaign lifecycle to `ready`, approval to `accepted`, both
approval and campaign checkpoints to `approval:<reviewed-plan-sha>`, and only the lowest-ordered
dependency-ready slice to `ready`. It may not change authority, coverage, slices, dependencies,
verification, decisions, blockers, evidence, or any other plan-bearing content. A campaign or slice
blocker changes approval to `changes-required`, clears its approval checkpoint, and puts the campaign
in `blocked` or `stale`; execution does not continue through that state.
Every later slice and closure checkpoint preserves that approved plan-bearing projection exactly.
Changing the baseline, authority map, coverage, slice graph, verification references, or selected
realization decisions requires replanning, a new cold review, and renewed human approval.

During uncommitted active work, retain the preceding campaign checkpoint and leave the active
slice's checkpoint null. After a checkpoint commit, the current campaign checkpoint must resolve to
`HEAD`; any later uncheckpointed commit is unexplained recovery state. Run
`just implementation-campaign-check` before committing and
`just implementation-campaign-checkpoint-check` afterward. If the post-commit binding fails, do not
advance; amend the sole unpublished checkpoint commit when safe, otherwise request recovery direction.

Campaign evidence uses `path:<repo-relative-path>#<test-or-section>` for committed artifacts or
`command:<exact reproducible command>` for rerunnable checks. A path fragment must resolve to a
Markdown heading anchor or a Python test node in both the working tree and checkpoint commit, and a
path may not escape the repository through a symlink. S001
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
