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

1. Identify the canonical model or implementation change.
2. Run `just model-render` for parser-backed inventories, model-derived views, conformance
   objectives, and manifests.
3. Review generated component pages for actions, signatures/defaults, typed failures, state access,
   required constraints, asserted satisfiers, native action calls, invariants, and subject-compatible
   verification objectives. A fresh but semantically incomplete projection fails sync.
4. When an accepted source or prior model exists, confirm the projection preserves its public
   meaning unless an explicit contract change was approved.
5. When package ownership or imports change, update library/application indexes and confirm the
   generated dependency direction still matches the canonical model.
6. Update only hand-authored documents whose readers need new context or workflow guidance.
7. Update AGENTS when repository-wide authoring or realization rules change.
8. Update reusable skills only for generally applicable workflow improvements; keep product names,
   project findings, and repository-specific package maps in repository guidance.
9. Update skill UI metadata when a skill's purpose changes.
10. Confirm packaged products validate independently and downstream products consume packaged
    dependencies, then run `just skills-check`, `just model-check`, and the narrowest relevant
    repository checks.

## Documentation Roles

- `model/**/*.sysml`: normative component and application design when designated canonical by the repository.
- `docs/model/generated/`: generated, non-normative human views; never edit by hand.
- `README.md`: project orientation, current architecture, links, setup, and common workflows.
- `AGENTS.md`: repository-wide contributor and agent rules.
- `docs/model/`: hand-authored modeling guidance and operational runbooks.
- `.agents/skills/`: reusable authoring, realization, and maintenance workflows.

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
