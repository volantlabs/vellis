# AGENTS.md

## Authority

Vellis is one individually owned application and an open demonstration of model-first software
engineering. Textual SysML v2 under `model/` is the product and system authority on each branch.
Pull requests propose changes to that authority; Markdown explains the work without restating its
contracts.

## Safety

At the start of work, run `pwd`, `git status --short --branch`, and `git worktree list`. Do not switch
branches in a worktree without human confirmation.

The ignored `.data/` directory may contain user-owned graphs and databases. Do not inspect, move,
rewrite, migrate, or delete it unless the human explicitly requests that exact operation. Never run
broad ignored-file cleanup commands here.

Do not mine v1 history for current requirements or design patterns unless the human requests a
historical comparison or recovery task.

## Skill routing

- `$sysml-modeling`: owner needs, use cases, behavior, logical responsibility, requirements,
  verification, adequacy, and simplification.
- `$sysml-reference`: official language semantics, construct comparison, citations, and validator
  diagnosis. Use it for every consequential SysML or KerML choice.
- `$rtg-schema-design`: RTG meaning, queries, definitions, validation, revision, history, recovery,
  and compatibility.
- `$documentation-sync`: repository authority, commands, skills, templates, and public guidance.

## Non-negotiable modeling rules

- Begin with owner value and observable behavior. Do not infer architecture from requested nouns,
  familiar names, predecessor code, framework examples, popular repository patterns, training-data
  priors, or incidental tests. Treat familiar architecture as a hypothesis, not a default.
- Close one changed semantic path at a time. Reuse existing behavior, domain meaning, requirements,
  satisfiers, and verification where they already carry the claim; add an element only at a layer
  whose meaning is missing. Semantic completeness does not require a new artifact in every layer.
- Prefer native SysML semantics. Comments and names cannot repair incorrect ownership, multiplicity,
  control, reference, satisfaction, or verification semantics.
- Review permitted instances recursively, not only declaration names. Inspect nested composites for
  accidental full-state ownership and define the joint tuple, projection, duplicate, absence, and
  null semantics of row-shaped results.
- Add actions only when functional refinement adds meaning. Group capabilities before parts, and add
  a part only for an independent lifecycle, state owner, failure responsibility, external
  interaction, or current realization decision.
- Keep persistence, transport, runtime, language, deployment, algorithms, and migration machinery
  open until intentionally selected. Do not add speculative services, controllers, adapters,
  managers, envelopes, extension seams, or duplicate authority.
- Prefer natural keys, derived meaning, one relationship authority, and one current prospective
  overlay before adding surrogate identity, stored flags, parallel rules, intent logs, or lifecycle
  machinery.
- Preserve explicit owner decisions and selected model meaning within the task's scope. Do not treat
  incidental tests, familiar patterns, explanatory comments, or mere element presence as owner
  decisions. An explicit review request may reassess them; otherwise reopen a decision only when new
  evidence creates a named contradiction and changed consequence.
- Do not use optional multiplicity to represent uncertainty, or configurable structure to represent
  a realization choice that is merely deferred. Absence, unknown, not applicable, and not yet decided
  are different meanings.
- Treat tool, protocol, and framework affordances as feasibility constraints, not a use-case or
  action inventory. Reflect them in the system model only when they change observable behavior or a
  selected realization boundary. The selected RTG MCP inventory is an intentional public contract,
  not evidence for services, adapters, ports, or matching internal decomposition. Its trusted-client
  assumption does not establish per-call authorization or owner approval.
- For agent-facing RTG work, begin cold: summarize the complete current anchor vocabulary, inspect
  only the relevant active-definition neighborhoods at that evaluated revision,
  and retrieve the sole current proposed definition set separately when continuing definition work.
  Do not assume predecessor schema knowledge or imply that current discovery reveals retired
  historical vocabulary.
- Preserve independently valuable outcomes, state governance, failure non-effects, recovery meaning,
  and verification while subtracting unsupported structure.
- Tests may observe tooling, repository safety, or an implementation against the current model; they
  do not choose or freeze the living model's constructs, vocabulary, inventory, topology, or prose.
- Never hand-edit future generated product source; regenerate it and check freshness when generation
  exists.

Before model edits, read `model/README.md`, every current `model/*.sysml` file, affected dependencies,
and the current diff. Follow the operative workflow and handoff in `$sysml-modeling`.

## Resources and checks

`just model-setup` downloads and checksum-verifies every reference artifact into the ignored
`.cache/`, then generates the searchable corpus. Nothing derived from upstream is committed, so the
corpus cannot drift from its pin. What setup provides:

| Artifact | Answers | Where |
| --- | --- | --- |
| Specification corpus | what a construct *means* | `just model-reference-find` |
| Standard model library | what exists and what it specializes | same finder, hits labelled `[library]` |
| Example and training models | what a construct looks like in working SysML (309 models) | same finder, hits labelled `[example]` |
| Construct inventory | which SysML name a question maps to | `just model-reference-concepts` |
| Pinned validator | what the parser actually accepts | `just model-probe`, `just model-check` |

SysML v2 names concepts differently from ordinary systems-engineering usage, so a search that returns
nothing convincing usually means the wrong word, not a missing capability. Consult the construct
inventory, then search again.

Begin with `just model-reference-find`, follow normative cross-references, inspect extraction
warnings, and never edit the generated corpus by hand. Cite the specification version and release
tag with the clause and page; the pinned beta documents carry no OMG document number.

Use `uv` and `just`. Run `just setup` and `just model-setup` after cloning. Before completion, run the
relevant narrow checks and normally `just check`. Keep `.data/` untouched.

The model selects an MCP tool contract but the repository has no runnable MCP server. Use modeled,
selected, implemented, and runnable precisely.
