# RTG Individual Life Graph Beta Prompt

Evaluation only: launch Vellis with `--empty --manual-recovery` before using this prompt. Ordinary
users receive the modeled Everyday Life ontology automatically and should not use this prompt.

Use this prompt manually with an agent after the `rtg_knowledge_graph` MCP server is
connected. The prompt exercises the initial individual open-source RTG use case: one person
using an AI assistant to organize personal and professional domains in a durable graph.

## Prompt To Give The Agent

You are helping one person build a local Vellis RTG life graph for personal and professional
planning. Use only the connected Vellis RTG MCP tools. Do not read the source repo, run shell
commands, inspect git, or use filesystem/browser access.

Treat the graph as durable working memory for cross-domain questions, next-action planning,
evidence, recovery, replay, and schema evolution.

Start by inspecting the available RTG system state and any MCP-provided guidance or tool
descriptions. If the app is empty, design and bootstrap an appropriate schema from the model below.
Do not look for or use a prebuilt beta schema or seed payload.

Use stable machine property keys, preferably `snake_case`. If exact date-like values are missing,
choose reasonable ISO-8601 placeholder strings and report those assumptions. Do not leave required
date-like strings empty.

Preserve supplied domain, status, and priority facts. If a required field is not supplied, choose a
reasonable placeholder and report it as an assumption rather than silently changing the user's
model.

Completion bar for this run:

- Build schema from the plain-English model; do not use a prebuilt beta schema or seed payload.
- Ingest all supplied initial facts, including 3 people, 5 areas, 5 projects, 8 tasks, 3 events,
  4 notes, and 1 resource.
- Use useful links rather than exhaustive links, and avoid inventing ownership, mentions, or
  dependencies that are not meaningful.
- Answer the planning questions with graph queries, then reconcile object counts and task status.
- Exercise invalid writes without polluting the durable planning graph, and explain what the
  validation findings taught you.
- Try a schema evolution that should fail against current data, verify live state is preserved,
  and clean up or report staged work appropriately.
- Persist a compact snapshot, prove it can be found and loaded through MCP, and verify replay or
  replay-readiness.
- Finish with a concise human-facing brief covering schema, property-key mapping, placeholder
  assumptions, domain summary, counts, next actions, recovery evidence, durability evidence, and
  modeling limitations.

Initial model to create:

- Anchor types: `Person`, `Area`, `Project`, `Task`, `Event`, `Note`, `Resource`.
- Required associated data types:
  - `PersonFacts`: name, relationship, domain, preferred contact.
  - `AreaFacts`: title, domain, focus, active.
  - `ProjectFacts`: title, domain, status, priority, desired outcome, next review.
  - `TaskFacts`: title, domain, status, priority, due, context.
  - `EventFacts`: title, domain, status, start, summary.
  - `NoteFacts`: title, domain, topic, summary.
  - `ResourceFacts`: title, domain, kind, locator.
- Link types:
  - `belongs_to`: projects, tasks, events, notes, or resources belong to areas.
  - `supports`: tasks, events, notes, or resources support projects.
  - `owns`: people own or are responsible for areas, projects, tasks, or events.
  - `mentions`: notes mention people.
  - `depends_on`: tasks depend on tasks.

Initial facts to ingest:

- People: Self, Morgan the mentor, Jordan the partner.
- Areas:
  - Open source product work, professional.
  - Career development, professional.
  - Home and household, personal.
  - Health, personal.
  - Personal finance, personal.
- Projects:
  - Vellis beta and open source launch, professional, active, high priority.
  - Career map refresh, professional, active.
  - Home systems cleanup, personal, active.
  - Health routine reset, personal, active.
  - 2026 tax planning, personal, waiting.
- Tasks:
  - Invite first beta testers, professional, next.
  - Collect eval feedback, professional, waiting.
  - Draft the Vellis public roadmap, professional, next.
  - Prepare mentor agenda, professional, next.
  - Renew home insurance, personal, next.
  - Schedule annual physical, personal, next.
  - Gather tax documents, personal, waiting.
  - Review monthly budget, personal, next.
- Events:
  - Vellis beta review.
  - Annual physical.
  - Household planning.
- Notes:
  - Beta feedback themes.
  - Open source positioning.
  - Household routine preferences.
  - Health baseline notes.
- Resource:
  - Vellis GitHub repository at `https://github.com/volantlabs/vellis`.

Use useful links, not exhaustive links. Projects should belong to one primary area where
reasonable. Tasks, events, notes, and resources should support relevant projects only when the
relationship is meaningful. Ownership should represent real responsibility. Mentions should only be
used when a note explicitly mentions a person. Dependencies should represent real sequencing or
blocking.

After building the graph:

- Answer next professional tasks.
- Answer next personal tasks.
- List active projects across personal and professional domains.
- Find tasks supporting the Vellis beta and open-source launch.
- Find notes or resources supporting active projects.
- Confirm all initial anchors were created, including all eight requested tasks.
- Exercise at least two well-formed but semantically invalid write attempts without polluting the
  durable planning graph. Prefer domain-relevant validation probes such as missing required task
  facts, a non-string task due value, or an invalid link endpoint; do not count a malformed tool
  call as a graph validation probe. For an invalid link endpoint probe, use real resolved endpoint
  anchors so the failure tests link schema compatibility rather than a missing reference. Explain
  the validation findings and recover appropriately.
- Try one schema evolution that should fail against current data, such as requiring a new sponsor
  field on `ProjectFacts` without backfill. Verify that live state is preserved.
- Persist a compact snapshot, prove it can be found and loaded through MCP, and verify replay or
  replay-readiness.
- Produce a concise final brief with schema summary, property-key mapping, date-like placeholder
  assumptions, domain summary, reconciled counts, next actions, recovery evidence,
  snapshot/ledger/replay evidence, and modeling limitations.
