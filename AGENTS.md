# AGENTS.md

## Purpose

Vellis is one individually owned application and an open demonstration of model-first software
engineering. It is not a component library or an enterprise platform.

Textual SysML v2 under `model/` is the current engineering authority. The model is a working draft;
implementation begins only after a human approves a vertical slice and its verification objectives.

## Startup and safety

At the start of work, run `pwd`, `git status --short --branch`, and `git worktree list`. Do not switch
branches in a worktree without human confirmation.

The ignored `.data/` directory may contain user-owned graphs and databases. Do not inspect, move,
rewrite, migrate, or delete it unless the human explicitly requests that exact data operation. Never
use broad ignored-file cleanup commands in this repository.

Do not mine v1 Git history for current requirements or design patterns unless the human explicitly
requests historical comparison or recovery work.

## Model-first workflow

1. Begin with the owner, external participants, Vellis boundary, and valued outcome.
2. Model black-box use cases before internal structure.
3. Add domain vocabulary, state, requirements, and white-box elements only when current intent needs
   them.
4. Use `sysml-reference` before consequential SysML/KerML syntax or semantics decisions.
5. Run `just model-check`; parser success is evidence, not architectural acceptance.
6. Obtain human approval before treating a slice as implementation-authorizing.
7. Define verification objectives before generation or implementation.
8. Keep model, future generated source, verification, and public guidance synchronized.

Use the repo-local skills as follows:

- `sysml-modeling`: model design, revision, review, and simplification.
- `sysml-reference`: language semantics, citations, and validator diagnosis.
- `rtg-schema-design`: anchors, associated data, links, associations, schemas, and compatibility.
- `documentation-sync`: authority, commands, skills, and public-document alignment.

## Modeling rules

- Prefer native SysML constructs over custom annotations or pseudo-language.
- Model owner value and observable behavior, not source-code structure.
- Distinguish owned, derived, and independently existing state.
- Use ports and interfaces only for intentional connections and transfers.
- Use states only for activated or event-driven behavior.
- Define a calculation only when it returns a result and a constraint only when it is a complete
  predicate.
- Keep persistence, transport, runtime, language, deployment, and algorithms open until intentionally
  selected or externally meaningful.
- Do not create placeholder services, adapters, managers, request/response types, extension seams,
  or duplicate representations.
- Ask what becomes false or unrealizable if a proposed element is removed. If nothing does, defer it.
- Keep one product-behavior authority. Markdown explains method, vision, operation, or open questions;
  it does not restate the model as a parallel contract.
- Never hand-edit future generated source. When generation exists, commit it and check freshness.

## RTG domain boundary

Preserve anchors, associated data objects, directed identity-bearing links, and identity-free direct
anchor/data associations as distinct concepts. Links may address anchors or associated data objects,
never links. Do not infer compatibility for former schemas, constraints, ledgers, storage layouts,
or transport encodings.

## Language resources

The committed Markdown under `reference/specifications/` is a searchable projection of pinned
official PDFs. The PDFs are authoritative. Begin retrieval with `just model-reference-find`, follow
normative cross-references, inspect extraction warnings, and cite specification section plus printed
or physical page. Never edit the corpus by hand.

## Repository commands

Use `uv` for Python and `just` for workflows. Run `just setup` and `just model-setup` after cloning.
Before completion, run the narrow relevant commands and normally `just check`. Do not add build,
runtime, packaging, or generation machinery before a real modeled slice needs it.
