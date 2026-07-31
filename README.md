# Vellis

Vellis is an individually owned personal AI system and an open demonstration of model-first software
engineering with textual SysML v2.

The repository is currently at the **v2 model reset**: the former implementation and component-
library architecture have been removed, and the new Vellis model is the sole engineering source.
There is no supported runtime, CLI, package, server, or migration utility in this commit. The next
work is to simplify the draft model, approve the first vertical slice, and generate its source.

## What is here

- [`model/`](model/): the working Vellis SysML v2 model.
- [`docs/vision.md`](docs/vision.md): the human/agent engineering vision.
- [`docs/modeling-method.md`](docs/modeling-method.md): the use-case-first modeling method.
- [`docs/open-questions.md`](docs/open-questions.md): non-normative questions for the draft.
- [`reference/specifications/`](reference/specifications/): searchable projections of pinned SysML
  and KerML PDFs.
- [`.agents/skills/`](.agents/skills/): four focused modeling and synchronization skills.
- [`tools/`](tools/): the pinned validator, reference finder, and skill checks.

Markdown explains the work; it does not replace the SysML model as product authority. The generated
specification pages are retrieval aids, and their official PDFs remain authoritative.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/), then run:

```sh
just setup
just model-setup
just check
```

Useful commands:

- `just model-check`: validate every authored SysML file with the pinned validator.
- `just model-reference-find "<question>"`: find relevant specification pages.
- `just model-reference-find "<question>" sysml-2.0 5`: limit a search by specification and count.
- `just model-reference-check`: prove the committed search corpus matches the pinned PDFs.
- `just skills-check`: validate the four skills and their Claude Code exposure.
- `just check`: run the complete repository gate.

## Modeling stance

Start with the owner, external participants, system boundary, and valued outcomes. Introduce internal
parts, actions, services, ports, states, and other abstractions only when a current use case,
requirement, invariant, failure boundary, or verification need makes them necessary.

The RTG model preserves the domain distinction among anchors, associated data objects, directed
links, and identity-free anchor/data associations. It intentionally makes no compatibility promise
for the old runtime, schema lifecycle, ledger, storage, or protocol surfaces.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.
