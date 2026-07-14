# RTG Personal Operating Graph Beta Prompt

Use this prompt manually with an agent after the `rtg_knowledge_graph` MCP server is connected.
This prompt extends the individual life-graph beta into a governed personal operating graph: a
local graph for commitments, decisions, goals, reviews, evidence, relationship context, and
routines.

## Prompt To Give The Agent

You are helping one person build a local Vellis RTG personal operating graph. Use only the
connected Vellis RTG MCP tools. Do not read the source repo, run shell commands, inspect git, or
use filesystem/browser access.

Treat the graph as governed local working memory for deciding what needs attention next and why the
answer is trustworthy. Record why the answer is trustworthy. Prefer explicit schema,
validation-before-mutation, sparse useful links,
snapshot/replay evidence, and clear modeling limitations over fuzzy recall or exhaustive capture.

Start by calling `rtg_validate_graph`, then `rtg_get_system_state`. Follow MCP-provided guidance
when useful. If the app is empty, bootstrap the schema from the model below. If a compatible
individual life graph already exists, stage a schema evolution that adds the operating graph model
without deleting live data. Treat this as a compatible individual life graph already exists path.
Do not look for or use a prebuilt beta schema or seed payload.

Use stable `snake_case` property keys. If exact date-like values are missing, choose reasonable
ISO-8601 placeholder strings and report the assumptions. Do not leave required date-like strings
empty. Preserve supplied domain, status, priority, confidence, and cadence facts.

Completion bar for this run:

- Build or evolve schema from the plain-English model; do not use a prebuilt beta schema or seed
  payload.
- Ingest all supplied initial facts, including 3 people, 5 areas, 5 goals, 6 commitments, 4
  decisions, 2 reviews, 6 evidence records, 3 relationship contexts, and 4 routines.
- Use useful links rather than exhaustive links. Every commitment and decision should have at
  least one meaningful link to a goal, area, person, review, or evidence record.
- Answer the operating questions with graph queries, then reconcile object counts by type and
  domain.
- Exercise at least two well-formed but semantically invalid write attempts without polluting the
  durable operating graph, and explain what the validation findings taught you.
- Try one schema evolution that should fail against current data, verify live state is preserved,
  and clean up or report staged work appropriately.
- Persist a compact snapshot, prove it can be found and loaded through MCP, and verify replay or
  replay-readiness.
- Finish with a concise human-facing brief covering schema, property-key mapping, placeholder
  assumptions, domain summary, counts, attention recommendations, trust/evidence gaps, recovery
  evidence, durability evidence, and modeling limitations.

Initial model to create or add:

- Anchor types: `Person`, `Area`, `Goal`, `Commitment`, `Decision`, `Review`, `Evidence`,
  `RelationshipContext`, `Routine`.
- Optional compatibility anchors when the graph already has them: `Project`, `Task`, `Event`,
  `Note`, `Resource`.
- Required associated data types:
  - `PersonFacts`: name, relationship, domain, preferred contact.
  - `AreaFacts`: title, domain, focus, active.
  - `GoalFacts`: title, domain, horizon, status, confidence, success signal, review date.
  - `CommitmentFacts`: title, domain, status, priority, due, made to, source, confidence.
  - `DecisionFacts`: title, domain, status, decided at, rationale, reversibility, review date.
  - `ReviewFacts`: title, domain, cadence, period start, period end, summary.
  - `EvidenceFacts`: title, domain, kind, locator, observed at, confidence.
  - `RelationshipContextFacts`: person name, relationship, domain, last contact, preference, open
    loop.
  - `RoutineFacts`: title, domain, cadence, status, next due, blocker.
- Link types:
  - `belongs_to`: goals, commitments, decisions, reviews, evidence, relationship contexts, or
    routines belong to areas.
  - `supports`: commitments, evidence, reviews, or routines support goals.
  - `owns`: people own or are responsible for goals, commitments, decisions, reviews, or routines.
  - `justifies`: evidence justifies commitments, decisions, or goals.
  - `reviewed_in`: goals, commitments, decisions, routines, or evidence are reviewed in reviews.
  - `involves`: relationship contexts involve people.
  - `informs`: relationship contexts or evidence inform decisions, goals, or commitments.

Initial facts to ingest:

- People: Self, Morgan the mentor, Jordan the partner.
- Areas:
  - Open source product work, professional.
  - Career development, professional.
  - Home and household, personal.
  - Health, personal.
  - Personal finance, personal.
- Goals:
  - Launch a trustworthy Vellis beta, professional, active, high confidence, review next Friday.
  - Clarify the next career narrative, professional, active, medium confidence.
  - Keep household administration calm, personal, active, medium confidence.
  - Rebuild a sustainable health rhythm, personal, active, medium confidence.
  - Complete 2026 tax planning with low scramble, personal, waiting, low confidence.
- Commitments:
  - Invite first beta testers, professional, next, high priority, due next Friday, made to Self,
    source planning session, high confidence.
  - Prepare mentor agenda, professional, next, medium priority, due before next mentor meeting,
    made to Morgan, source mentor thread, medium confidence.
  - Renew home insurance, personal, next, high priority, due before policy expiration, made to
    Jordan, source renewal notice, high confidence.
  - Schedule annual physical, personal, next, medium priority, due this month, made to Self,
    source health reminder, medium confidence.
  - Gather tax documents, personal, waiting, medium priority, due by tax prep window, made to
    Self, source finance review, low confidence.
  - Review monthly budget, personal, next, medium priority, due month end, made to Jordan, source
    household planning, medium confidence.
- Decisions:
  - Treat the life graph as a substrate hardening harness, professional, decided, reversible,
    review after beta feedback.
  - Keep personal operating data local unless explicitly exported, personal, decided, hard to
    reverse, review quarterly.
  - Use Friday review as the primary Vellis operating cadence, professional, decided, reversible,
    review in four weeks.
  - Keep tax planning waiting until document evidence arrives, personal, decided, reversible,
    review at next finance review.
- Reviews:
  - Weekly operating review, cross-domain, weekly cadence, current week.
  - Monthly finance review, personal, monthly cadence, current month.
- Evidence:
  - Vellis repository, professional, resource, `https://github.com/volantlabs/vellis`, observed
    today, high confidence.
  - Beta feedback themes note, professional, note, placeholder local note, observed this week,
    medium confidence.
  - Insurance renewal notice, personal, document, placeholder local file, observed this month,
    high confidence.
  - Doctor portal reminder, personal, message, placeholder local message, observed this month,
    medium confidence.
  - Budget export, personal, spreadsheet, placeholder local file, observed this month, medium
    confidence.
  - Mentor conversation note, professional, note, placeholder local note, observed this week,
    medium confidence.
- Relationship contexts:
  - Morgan, mentor, professional, last contact placeholder date, prefers concise agendas, open
    loop: send agenda before next meeting.
  - Jordan, partner, personal, last contact placeholder date, prefers shared household context,
    open loop: align budget and insurance tasks.
  - Self, operator, cross-domain, last review placeholder date, prefers attention lists with
    evidence gaps, open loop: protect focus from stale obligations.
- Routines:
  - Friday Vellis review, professional, weekly, active, next due next Friday, blocker none.
  - Sunday household reset, personal, weekly, active, next due Sunday, blocker unclear shared list.
  - Weekday health baseline, personal, weekday, active, next due tomorrow, blocker scheduling.
  - Monthly budget review, personal, monthly, active, next due month end, blocker waiting for
    latest budget export.

Use useful links, not exhaustive links. Goals should belong to one primary area where reasonable.
Commitments, evidence, reviews, routines, and relationship contexts should support or inform other
objects only when useful for planning or trust. Ownership should represent real responsibility.
`justifies` links should connect evidence to the facts or choices it actually supports.

After building or evolving the graph:

- Answer what needs attention this week across domains, ordered by priority and due date.
- Answer which high-priority commitments lack strong evidence.
- List active goals and the routines or commitments that support them.
- Find decisions due for review soon.
- Find relationship contexts with open loops.
- Find commitments made to someone other than Self.
- Confirm all initial anchors were created, including all six commitments, four decisions, six
  evidence records, and four routines.
- Reconcile global counts and counts by domain.
- Exercise at least two well-formed but semantically invalid write attempts without mutating live
  state. Prefer domain-relevant validation probes such as a `Commitment` without required
  `CommitmentFacts`, a non-string commitment `due` value, an invalid `confidence` enum if you
  modeled confidence as an enum, or a `justifies` link between unsupported endpoint types. Do not
  count a malformed tool call as a graph validation probe.
- Try one schema evolution that should fail against current data, such as requiring a new
  `risk_level` field on `DecisionFacts` without backfill. Verify that live state is preserved.
- Persist a compact snapshot, prove it can be found and loaded through MCP, and verify replay or
  replay-readiness.
- Produce a concise final brief with schema summary, property-key mapping, date-like placeholder
  assumptions, operating summary, reconciled counts, next attention list, evidence gaps, rejected
  writes, failed schema evolution, snapshot/ledger/replay evidence, and modeling limitations.
