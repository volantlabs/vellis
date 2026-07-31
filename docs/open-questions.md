# Open Modeling Questions

These are intentionally unresolved. They should be answered through use-case refinement rather than speculative architecture.

## Applications

- How does the owner install, create, update, disable, and remove a hosted application?
- Are applications trusted code, sandboxed code, generated artifacts, or some combination?
- Does Vellis serve application assets directly or merely supervise external processes?

## Automations

- How does the owner define and schedule an automation?
- What triggers are required initially: manual, time-based, event-based?
- What execution limits and failure reporting are necessary for a single-owner host?
- How are automation source, configuration, and execution history related?

## Owner and agent trust

- What is the minimum client-registration mechanism needed to distinguish the owner's agents and tools?
- Is owner approval required per client, per capability, or only at installation?
- What provenance can be obtained reliably from external clients?

## RTG activity history

- Which read-only operations must be retained durably?
- Are query payloads retained, summarized, redacted, or omitted?
- What retention policy applies to non-state-changing activity?
- How are snapshots related to the authoritative state-change history?
- What owner outcome and acceptance evidence should define a future agent-assisted recovery path from an older RTG graph file?

## Constraint-model lifecycle

- Is editing a staged constraint model a specialized graph change or a separate privileged operation?
- What exact activation effects are permitted on existing graph data?
- How are assessment results tied to specific staged-model and graph revisions?

## Model-to-code workflow

- How will code elements declare the SysML elements they realize?
- Which verification cases should be executable in the first vertical slice?
