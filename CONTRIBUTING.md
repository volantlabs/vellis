# Contributing

Vellis is developed model-first. Textual SysML v2 under `model/` is the current engineering source;
handwritten documentation must not become a parallel behavior specification.

## Setup

```sh
just setup
just model-setup
just check
```

`model-setup` downloads and checksum-verifies the pinned language PDFs, validator, and Java runtime.

## Change workflow

1. Read `AGENTS.md` and the relevant repo-local skills.
2. Express the smallest owner-valued change in the SysML model.
3. Use `sysml-reference` for consequential language decisions.
4. Run `just model-check` and review the result as language evidence, not design approval.
5. Obtain human approval before authorizing an implementation slice.
6. Update only the public guidance affected by the change.
7. Run `just check` before opening a pull request.

Prefer subtraction and one clear representation. Do not introduce internal structure, frameworks,
transports, generators, or extension points without a current modeled need.

The repository is model-only at present. Future generated source will be committed, clearly marked,
and regenerated rather than edited by hand.
