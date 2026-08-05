# Contributing

Vellis is developed model-first. Textual SysML v2 under `model/` is the current system authority;
handwritten documentation remains explanatory.

## Setup

```sh
just setup
just model-setup
just check
```

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

Do not introduce realization machinery without a current modeled need. The repository has no product
runtime or generated product source today. The model selects an MCP tool contract, but no MCP server
is implemented or runnable.
