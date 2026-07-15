# Documentation

Documentation is organized by audience and authority:

- [`../generated/reference/bibliotek/`](../generated/reference/bibliotek/) contains generated human views of the Bibliotek
  library, its components, shared semantics, and dependency topology.
- [`../generated/reference/vellis/`](../generated/reference/vellis/) contains the generated Vellis application composition,
  use cases, façade, verification, and realization mappings.
- [`engineering/sysml-modeling.md`](engineering/sysml-modeling.md) explains the repository's SysML
  profile, model workflow, validation, and packaging rules.
- [`guides/vellis/getting-started.md`](guides/vellis/getting-started.md) is the human first-run,
  local-data, backup, reset, and troubleshooting guide.
- [`guides/vellis/snapshot-transfer.md`](guides/vellis/snapshot-transfer.md) is the agent-facing
  procedure for transferring managed state from an earlier Vellis installation without importing
  its ledger.
- [`guides/vellis/evals/`](guides/vellis/evals/) contains developer-only evaluation prompts and
  walkthroughs.
- [`design/open-design-questions.md`](design/open-design-questions.md) is a non-normative backlog of
  unresolved model-design questions.
- [`design/component-runtime-architecture.md`](design/component-runtime-architecture.md) records the
  accepted cross-component runtime rules, current Vellis realization, and future review triggers.
- [`vision/agentic-mbse-engineering-system.md`](vision/agentic-mbse-engineering-system.md) states the
  durable human-and-agent model-based engineering vision.

For model work, start with the [SysML modeling guide](engineering/sysml-modeling.md). To understand
an existing boundary without reading raw SysML, use the generated [Bibliotek](../generated/reference/bibliotek/)
or [Vellis](../generated/reference/vellis/) reference. To operate the application, use the
[getting-started guide](guides/vellis/getting-started.md) or the
[application README](../apps/rtg_knowledge_graph/README.md).
Textual SysML under `../model/` is the normative design. Human references under
`../generated/reference/` and machine projections under `../generated/model/` are produced by
`just model-render` and must not be edited as alternate specifications. The `docs/` tree contains
only maintained guidance, rationale, tutorials, and current design questions.

Do not commit task plans, review scratchpads, generated analysis, or historical decision narratives
as durable documentation. Keep temporary work in its task context; place lasting component meaning
in SysML and add hand-authored prose only for current rationale, operations, tutorials, or concise
unresolved questions.
