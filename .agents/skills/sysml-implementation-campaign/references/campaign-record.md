# Campaign Record

## Purpose and authority boundary

Use one baseline-bound record as the durable current state of planning, execution, evidence, and
closure. It is not product authority, a requirements document, a ticket backlog, an architecture, or
an event log. Versioned project checkpoints provide history; the record contains only current state.

Always reread qualified model references before acting. Labels distinguish entries but do not replace
model meaning. Do not add requirement prose, acceptance criteria, stories, tasks, estimates,
assignees, source inventories, module plans, serialized model payloads, or speculative architecture.

Copy and populate the bundled template only through the project's configured artifact workflow. Use
the bundled schema as the portable structural contract and project validation for baseline and
cross-record semantics.

## Baseline

Record the planned baseline and the currently observed baseline separately. Include authored model,
language-reference, and validator identities or digests when the project supplies them.

- `current`: planned and observed baselines agree.
- `stale`: they differ, the campaign is stale, approval is invalidated, and no slice may be active.

Do not update the planned baseline merely to make a freshness check pass. Re-read the changed model,
replan affected and remaining work, rerun plan review, and require human approval.

## Coverage and slices

Each top-level authority entry labels one independently reviewable obligation neighborhood and names
the qualified model references that jointly carry it, their sources, all contributing slice IDs,
aggregate planned coverage, and current implementation status. Each slice contribution names the
same authority ID, its `full` or `partial` contribution, and every slice that closes a partial
remainder. A partial contribution lists all other aggregate contributors, including completed
prerequisites; a full contribution is self-sufficient and therefore the sole contributor. Project
validation must check both directions. Do not split joint authority merely to obtain one reference
per row.

Use stable slice IDs and unique integer order. Dependencies form an acyclic semantic graph. Slice
kind is `semantic`, `integration`, or `closure`; lifecycle is `pending`, `ready`, `active`, `blocked`,
`stale`, or `complete`. Permit only one active slice.

Keep these dimensions separate:

- authority coverage: `full` or `partial`;
- implementation status: `not evaluated`, `absent`, `partial`, `conforming`, or `conflicting`;
- campaign lifecycle: planning and execution state;
- approval: human acceptance of the current complete plan.

## Evidence, decisions, blockers, and checkpoints

Use evidence references to point to project artifacts or commands; do not copy their payloads.
Evidence on an aggregate authority must remain attributable to one of its declared contributing
slices. An artifact may be created before the slice that ultimately cites it, but aggregate evidence
must not become a side channel for claiming authority omitted from the slice contract.

Distinguish realization constraints selected by the accepted campaign from bounded task-time choices
the model and plan intentionally leave open. Record only consequential decisions needed for later
conformance or resume, with the authority they preserve. When project approval freezes the record's
decision projection, preserve an ordinary task-time choice in code, evidence, and the slice handoff
rather than rewriting the accepted plan. Escalate only if its consequence changes stakeholder-visible
meaning or an intentionally selected boundary. Checkpoints are opaque project-bound identifiers.

Classify blockers as `language question`, `model gap`, `plan gap`, `feasibility consequence`, `stale
baseline`, or `external dependency`. Implementation defects and ordinary realization decisions are
campaign work, not blockers. An out-of-scope request is a disposition outside the blocker taxonomy.

A completed slice requires conforming bounded implementation, discriminating evidence, completed
dependencies, no blocker, and a checkpoint. Campaign completion additionally requires current
baseline, accepted plan, full aggregate authority coverage, all slices complete, conforming
integration and runnable-boundary status, closure evidence, and a final checkpoint.
