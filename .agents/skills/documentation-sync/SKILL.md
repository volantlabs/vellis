---
name: documentation-sync
description: Keep repository documentation synchronized with the SysML v2 model-as-code authority, modeling workflow, validation and reference tooling, repo-local skills, contributor guidance, public capability claims, commands, templates, and UI metadata. Use after model, tool, command, skill, workflow, README, AGENTS, CONTRIBUTING, SECURITY, template, or product-status changes.
---

# Documentation Sync

Keep each claim in the narrowest authoritative place and delete obsolete claims instead of preserving historical narrative.

Bias toward small, claim-driven documentation changes. Do not turn a model edit into a broad rewrite, duplicate model contracts for readability, preserve superseded terminology as narrative, or advertise plausible future capabilities. Prefer deleting an obsolete sentence to explaining its history.

## Authority map

- `model/*.sysml` on the current branch is that branch's product and system authority.
- Handwritten Markdown explains vision, method, contribution, operation, or tooling without restating model contracts.
- GitHub issues and PR discussion carry unresolved design work and review decisions.
- Reference corpora are generated from checksum-pinned upstream sources into the ignored `.cache/`; they are never committed and must not be hand-edited.
- `.agents/skills/` is the repo-local skill source; `.claude/skills/` contains managed links.
- `$sysml-reference`, `$sysml-modeling`, `$sysml-implementation-planning`,
  `$sysml-implementation`, `$sysml-implementation-campaign`, and `$sysml-evolution` are a portable
  core. Vellis paths,
  commands, RTG vocabulary, and repository workflow belong in project bindings or optional domain
  skills rather than those core instructions.
- Vellis product runtime source under `vellis/` is authored rather than generated. There are no
  generated Vellis product views or runtime sources; current implementation artifacts and tests must
  remain subordinate to the model authority.

Keep detailed workflow heuristics and agent failure patterns in the applicable skills. Keep
`AGENTS.md` to safety, routing, authority, and short non-negotiable rules; keep public method documents
conceptual. Do not copy the same anti-pattern catalog across the portable core.

Do not create placeholders to satisfy an imagined workflow. When product generation exists later, regenerate rather than hand-edit and add freshness checks at that time.

## Workflow

1. Review tracked and untracked changes without traversing protected ignored user data.
2. Update the canonical model first when product behavior, requirements, architecture, or verification changed.
3. Align `model/README.md`, `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/`, issue and PR templates, commands, skills, and skill UI metadata as applicable.
4. Route unresolved work to an issue or the active PR discussion; do not maintain a parallel open-questions document or status taxonomy.
5. Keep command examples limited to recipes that currently exist.
6. Remove claims for runtime, generated product, CLI, MCP, migration, packaging, or deployment capabilities that do not exist.
   A selected MCP contract may be documented as modeled while the repository still has no runnable
   MCP server; use the words modeled, selected, implemented, and runnable precisely.
7. Confirm a fresh agent can find the authority, current model map, applicable skills, validation path, and PR expectations without Git history or prior conversation.
8. Search guidance, tests, templates, commands, and metadata for stale terms and inverse claims after deletions.
   When a portable core skill changes, also check that it has not acquired a hard dependency on
   Vellis, RTG, MCP, local paths, local commands, a programming language, or a particular software
   architecture. Keep concrete bindings in repository guidance and domain extensions. Confirm that
   modeling, domain, and implementation skills use the same handoff fields and divergence taxonomy;
   documentation and PR claims must not present partial authority coverage as complete requirement
   satisfaction or verification.
9. If explanatory guidance compares candidate realizations, label it non-normative and keep the model's selected semantics distinct from unselected technology examples.
   For an intentionally selected agent workflow, explain the smallest invocation path without copying
   the full model contract or implying the future framework is already installed.
10. Re-read changed documentation as a new contributor. Remove claims that require prior conversation, Git archaeology, implied future work, or knowledge of deleted architecture.
11. When a review changes a settled decision, make the new evidence and changed consequence visible
    in the PR rather than silently rewriting the rationale or asking future contributors to infer it.
12. Run `just skills-sync` after skill inventory or metadata changes, then relevant checks and `git diff --check`.

Avoid duplicating normative SysML semantics in Markdown; route language questions to `$sysml-reference` and the pinned corpus.
