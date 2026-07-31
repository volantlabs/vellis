---
name: documentation-sync
description: Keep repository documentation synchronized with the canonical SysML v2 model, modeling workflow, validation and reference tooling, repo-local skills, contributor guidance, public status, and UI metadata. Use after model, tool, command, skill, workflow, README, AGENTS, CONTRIBUTING, SECURITY, template, or product-status changes.
---

# Documentation Sync

Keep each claim in the narrowest authoritative place and remove obsolete claims rather than preserving historical narrative.

## Current Authority Map

- `model/*.sysml` is the current product-behavior authority.
- Handwritten Markdown explains vision, method, operation, contribution, or unresolved questions without restating model contracts.
- `reference/specifications/` is generated from checksum-pinned official PDFs and must not be hand-edited.
- `.agents/skills/` is the repo-local skill source of truth; `.claude/skills/` contains managed links.
- There are currently no generated Vellis views, implementation sources, runtime sources, or freshness contracts for them.

Do not create placeholder generated artifacts merely to satisfy a workflow. When product generation exists later, regenerate instead of hand-editing and add freshness checks at that time.

## Workflow

1. Review both tracked and untracked changes and identify affected public claims.
2. Update the canonical model first when product behavior or intent changed.
3. Align `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/`, issue and pull-request templates, commands, skills, and skill UI metadata as applicable.
4. Keep command examples limited to recipes that currently exist.
5. Keep status language explicit about what is draft, approved, implemented, generated, or absent.
6. Remove component-library, runtime, packaging, migration-utility, or generated-view claims that are no longer true.
7. Run `just skills-sync` after skill inventory changes, then the narrowest relevant checks and `git diff --check`.

Avoid duplicating normative SysML semantics in documentation; route language questions to `$sysml-reference`.
