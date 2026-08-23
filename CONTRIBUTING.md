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

`just build` produces the wheel and source distribution into `dist/` for local inspection, through
the same purging entry point as the check below; it is independent of `just package-check`, which builds and smoke-tests its own disposable copies and
also proves the documented `uv tool install git+...` path against this checkout's committed HEAD
(see [`docs/install.md`](docs/install.md)). `just package-check` first deletes this checkout's
ignored `build/` directory, because the build backend reuses that tree and never removes files
deleted from source; it then compares every installed module against source by content, so a stale
artifact fails the check instead of passing it.

### Version bump

The version is a static literal in four places, cross-checked by
`tests/test_repository_policy.py::test_version_is_consistent_across_metadata_runtime_and_lock`:

1. `pyproject.toml` (`project.version`)
2. `vellis/__init__.py` (`__version__`)
3. `tests/test_repository_policy.py` (the literal comparison)
4. Run `uv lock` to regenerate the matching `uv.lock` entry.

## Skill portability

`$sysml-reference`, `$sysml-modeling`, `$sysml-implementation`, and `$sysml-evolution` are
maintained as
a portable SysML v2 MBSwE core. Keep Vellis paths, commands, RTG and MCP semantics, implementation language, and
repository-specific review rules in local guidance or optional extensions. When changing the core,
validate along the axis the change sits on; the axis list is in `AGENTS.md` under
`## Portable-core validation`. Do not use Vellis as the only semantic test case or claim that a
standalone plugin already exists.

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

1. For one already selected slice, start with `$sysml-implementation`. For a change set spanning
   accepted authority, realization, evidence, and baseline, use `$sysml-evolution`.
2. Read the scope required by `AGENTS.md` and the current diff before taking architecture from
   existing source. Classify every consequential statement as required model meaning, an
   already-selected realization constraint, an open realization decision, a model gap, or a
   deliberate non-goal.
3. Fix the acceptance set before dispatch and treat it as closed. The work is done when every entry
   names evidence that fails if that wrong behavior is present, the declared non-effects hold, and
   `just check` passes.
4. Commit implementation, tests, evidence, documentation truth, and the record update together as
   one checkpoint. Validate every record change with `just system-evolution-check`.
5. Evidence uses `path:<repo-relative-path>#<test-or-section>` or `command:<exact reproducible
   command>`. Never inspect or write `.data/`.

Review discipline — the lens split, materiality, the two-pair budget, and the stop conditions — is
normative in `$sysml-evolution` and bound to this repository in `AGENTS.md`.

## Testing authority

Automated tests may observe language tooling, repository safety, and future implementations. They do
not choose or freeze the living model's constructs, names, counts, topology, package layout, or prose.
A future implementation contract check may compare implemented behavior with the current model: the
implementation is constrained by the model, not the model by a duplicate test inventory. Such a
check may also compare implemented structure with a modeled decomposition—asserting that no code
unit spans two modeled parts—because it reads the current model rather than restating it as a
second inventory.

When tests and model structure were introduced together, review the model independently from owner
purpose, accepted and refused examples, state effects, and decisive evidence. Passing tests or parser
acceptance cannot substitute for that semantic review.

Do not introduce realization machinery without a current modeled need. Product source under
`vellis/` is authored, not generated. The selected MCP tool contract is implemented and runnable over
local standard input/output and foreground HTTP. Tests exercise public Codex and Claude CLI
registration without claiming or mutating an owner's real client configuration.
