---
name: documentation-sync
description: Keep human documentation synchronized with canonical SysML v2 models, generated component and application views, implementation realizations, repository tooling, skills, and workflow rules. Use after model, code, generated-view, README, AGENTS, skill, command, or public behavior changes.
---

# Documentation Sync

Keep each documentation projection useful without creating a second source of component truth.

## Source Direction

```text
textual SysML/KPAR -> generated component, application, and manifest views
```

Hand-authored Markdown may explain rationale, tutorials, operations, evolution, or unresolved
questions. It must not independently restate normative action signatures, state, dependencies, or
invariants.

## Workflow

1. Inventory canonical model, implementation, generated, documentation, and skill changes from
   version-control status and diffs. Include untracked files; an ordinary diff omits newly added
   documentation and can hide an incomplete sync.
2. Run `just model-render` for parser-backed inventories, the architecture graph and stable
   dashboard, model-derived views, conformance objectives, and manifests.
3. Review generated component pages for actions, signatures/defaults, typed failures, state access,
   required constraints, asserted satisfiers, native action calls, invariants, and subject-compatible
   verification objectives. A fresh but semantically incomplete projection fails sync.
4. When an accepted source or prior model exists, confirm the projection preserves its public
   meaning unless an explicit contract change was approved.
5. Before deleting predecessor documentation, classify its remaining content: contractual facts
   move to the model; rationale, tutorials, operations, evolution notes, and unresolved questions
   move to a clearly non-normative home; obsolete statements cite the current model decision that
   supersedes them. Confirm implementation discoveries are either modeled intentionally or recorded
   as realization drift.
6. When package ownership or imports change, update library/application indexes and confirm the
   generated dependency direction still matches the canonical model.
7. Update only hand-authored documents whose readers need new context or workflow guidance.
8. Update AGENTS when repository-wide authoring or realization rules change.
9. Update reusable skills only for generally applicable workflow improvements; keep product names,
   project findings, and repository-specific package maps in repository guidance.
10. Update skill UI metadata when a skill's purpose changes.
11. Confirm packaged products validate independently and downstream products consume packaged
    dependencies, then run `just skills-check`, `just model-check`, local-link and documentation-
    guidance checks when available, and the narrowest relevant repository checks.

## Documentation Roles

- Canonical textual model roots: normative component and application design when designated by the
  repository.
- Generated human-reference roots: non-normative projections; never edit them by hand.
- Generated machine-projection roots: parser indexes, conformance objectives, evidence indexes, or
  other derived data; regenerate rather than hand-edit.
- Project orientation and contributor guidance: architecture, links, setup, and workflow rules.
- Hand-authored documentation roots: rationale, tutorials, operations, evolution, and unresolved
  questions that do not restate the contract.
- Reusable skill roots: general authoring, realization, and maintenance workflows rather than
  product-specific findings or directory maps.

## Rules

- Change the model, not generated Markdown, when a public component contract changes.
- Keep generated-artifact freshness in ordinary `model-check`.
- Prefer projections built from a conformant parser's structured model inventory. When temporary
  text extraction remains, cross-check every projected public definition against that inventory.
- Freshness is insufficient: generated pages must expose every modeled public contract, including
  package-level constructors, failure mappings, defaults, and verification closure.
- Record unclear model/implementation behavior as compact drift rather than explanatory duplication.
- Do not create historical archives or ADRs when Git history and the current model are sufficient.
- Do not copy full model contracts into README or workflow documents.
