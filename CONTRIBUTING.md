# Contributing

Vellis is an early-stage component library. Contributions should preserve the repository's component-first design style: small boundaries, explicit invariant ownership, and black-box tests.

## Local Setup

Install `uv` and `just` first — see the Development Setup section of `README.md` for install commands and prerequisites (Python 3.14 is provisioned automatically by `uv`).

```sh
just setup
just model-setup
just check
```

`just model-setup` downloads and checksum-verifies the pinned model references and validator assets
that `just check` requires. Run it once after cloning and whenever the model lock files change.

Use `uv` for Python commands and `just` for project tasks.

## Submitting Changes

Fork the repository, create a topic branch, make your change, run `just check`, and open a pull
request against `main`. Keep pull requests focused on a single concern and describe any SysML
contract changes in the PR description.

## Before Opening A Change

- Read `AGENTS.md` for repository rules.
- Update the SysML component or application model when public behavior, owned state, dependencies,
  invariants, or verification expectations change.
- Prefer focused changes over broad refactors.
- Add or update boundary tests for component behavior.
- Run `just check` before submitting.

## Component Changes

Textual SysML under `model/bibliotek/` and `model/vellis/` is the normative design for component and
application work. Generated reference pages under `generated/reference/` are review aids, not alternate
contracts. Do not create or maintain parallel hand-authored component specifications.

Accepted model contracts are human-owned. If a change requires altering an accepted public
contract, surface the change and get maintainer approval before changing the model and its
realizations together.

For a model-affecting change, use this order:

```sh
just model-render      # regenerate committed human and machine projections
just model-diff        # review the model and every derived change together
just model-check       # run formal, profile, architecture, realization, and freshness gates
just check             # finish with all repository checks and tests
```

See [`docs/engineering/sysml-modeling.md`](docs/engineering/sysml-modeling.md) for artifact roles,
scoped checks, implementation handoffs, and troubleshooting.
