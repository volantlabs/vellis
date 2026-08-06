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

`$sysml-reference`, `$sysml-modeling`, and `$sysml-implementation` are maintained as a portable
SysML v2 MBSwE core. Keep Vellis paths, commands, RTG and MCP semantics, implementation language,
and repository-specific review rules in local guidance or optional extensions. When changing the
core, apply the cross-domain portability review in `AGENTS.md`; do not use Vellis as the only test
case or claim that a standalone plugin already exists.

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
5. Cite official sections and pages for consequential language choices and run `just check`.
6. In the PR, report changed meaning, evidence, compatibility effects, unsupported architecture
   removed or deferred, any decision reopened by the review scope or new contradictory evidence, and
   bounded follow-up work.

## Implementation workflow

1. Read the current model and diff before taking architecture from existing source. Use a current
   model-work semantic handoff when available and verify it against the branch; otherwise reconstruct
   the affected authority directly.
2. Separate required model meaning, already selected realization constraints, realization decisions
   still open to implementation, genuine model gaps, and deliberate non-goals. Return to model work
   before coding across a gap in stakeholder-visible behavior, state, responsibility, failure,
   compatibility, or verification.
3. Plan one end-to-end semantic slice. For every cited authority, record the in-scope obligation,
   full or partial coverage, any remaining obligations, decisive conformance evidence, and required
   non-effects. Keep implementation status—`not evaluated`, `absent`, `partial`, `conforming`, or
   `conflicting`—separate from authority coverage. When software needs finer structure than the
   systems model, record a many-to-many realization against semantic neighborhoods and preserve the
   modeled lifecycle, state, transaction, failure, and external boundaries.
4. Implement the simplest sufficient realization and derive conformance evidence from verification
   intent rather than mirroring model declarations. Use tests, analysis, simulation, inspection,
   demonstration, numerical references, timing measurements, or hardware evidence as appropriate.
   Exercise accepted behavior, semantic rejection or failure, and the nearest invalid counterexample.
5. Review plan conformance, model meaning in code, evidence adequacy, realization leakage,
   subtraction, and repository truth separately. Repeat the complete review after material fixes until
   one pass finds no new issue.
6. In the PR, distinguish modeled, selected, implemented, verified, and runnable. Do not claim an
   entire requirement satisfied or verification case passed from a partially covered slice. Return
   reproducible implementation evidence to model work only for a model gap or demonstrated
   feasibility consequence; keep unselected implementation mechanics in realization work.

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
