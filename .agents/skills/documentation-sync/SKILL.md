---
name: documentation-sync
description: Keep Vellis documentation synchronized with component specs, Python implementations, repo tooling, skills, and workflow rules. Use after changes to README.md, AGENTS.md, docs/components specs, .agents/skills, pyproject.toml, justfile, component directories, tests, or public behavior that should be reflected in docs.
---

# Documentation Sync

Use this skill when repository changes may make durable documentation stale. Keep documentation current without duplicating every detail across every file.

## Workflow

1. Identify the source of truth for the change.
2. List documentation surfaces that may reference that behavior, rule, tool, or component.
3. Update only the docs whose reader needs the changed information.
4. Preserve the role of each document.
5. Run the narrowest relevant checks.
6. Report what was updated and what was intentionally left unchanged.

## Documentation Roles

- `README.md`: human-facing project overview, setup, common workflows, and current status.
- `AGENTS.md`: repository-wide operating rules for agents and contributors.
- `docs/components/*.md`: component-local contracts, owned state, dependencies, invariants, verification, lifecycle, and open questions.
- `.agents/skills/*/SKILL.md`: reusable agent workflows for repeated repo tasks.
- `.agents/skills/*/agents/openai.yaml`: UI metadata for skills; keep it aligned with the skill purpose.
- `pyproject.toml`, `.python-version`, `uv.lock`, and `justfile`: executable project and tooling configuration, not prose documentation.

## Sync Rules

- When public component behavior changes, update the component spec in the same change.
- When repo-wide workflow changes, update `AGENTS.md` and only summarize in `README.md` if humans need it.
- When setup commands, Python version, dependencies, or task recipes change, update `README.md`, `AGENTS.md`, and executable config together when applicable.
- When adding or changing a repeated agent workflow, update or add a skill and mention it in `AGENTS.md` if agents must use it.
- When public affordance names or workflows change, check durable eval prompts, examples, and reference-app docs that teach agents or humans how to use those affordances.
- When implementation exposes unclear design, record the uncertainty under the affected component spec's `Open questions` instead of hiding it in README prose.
- Do not create ADRs by default; use component specs or `AGENTS.md` unless a durable cross-component rule cannot fit there.

## Avoid Over-Syncing

- Do not copy full component specs into `README.md`.
- Do not make `README.md` authoritative for agent rules.
- Do not document private helper structure unless it affects a public contract, owned state, invariant, dependency, verification, or runtime assumption.
- Do not update unrelated docs just because they are nearby.
- Do not add historical narratives when the current rule is enough.

## Checks

Prefer these checks when relevant:

- `just check` for repository lint, type checking, skill validation, and tests.
- `just skills-check` after changing repo-local skills.
- Link and path readback for changed Markdown files.
- Skill frontmatter readback for changed skills.
- `uv sync --dev` when Python dependency metadata changes.
