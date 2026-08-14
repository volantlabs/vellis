---
name: sysml-implementation-campaign
description: Execute, resume, review, and close a human-approved, model-derived implementation campaign across multiple semantic slices while preserving a durable baseline-bound campaign record. Use for long-running autonomous implementation of an accepted textual SysML v2 system, continuing after context loss or interruption, coordinating independent slice reviews and checkpoints, reacting to model changes, or proving full-system implementation closure; use sysml-implementation-planning first when no complete approved campaign exists.
---

# SysML Implementation Campaign

Manage a long-running build as a sequence of model-conformant slices. Keep the accepted model as
product authority and the campaign record as resumable execution and evidence state.

## Project binding

Discover the project's local bindings for:

- safety, authored authority, baseline identity, and official model validation;
- campaign-record location, schema, freshness check, status reporting, and approval mechanism;
- continuation or recurring-task mechanism and its stopping condition;
- working-state inspection, single-writer ownership, checkpoint creation, and recovery;
- the project's trust and recovery boundary;
- implementation, evidence, documentation, and whole-project checks;
- independent review-agent availability and optional domain skills.

Do not assume a path, source-control system, command runner, programming language, framework,
runtime, architecture, or deployment. The project may use an external continuation harness; the
record must remain sufficient for a fresh agent when that harness loses context.

## Preconditions

Read [Campaign record](references/campaign-record.md). Do not implement unless:

- the record and current model baseline validate;
- the complete plan has explicit human approval;
- no model or plan blocker is open;
- the workspace has one identifiable writer and recoverable checkpoint state;
- the selected slice is dependency-ready and its qualified authority can be reread.

If no complete plan exists, invoke `$sysml-implementation-planning`. Never infer approval from a
file's existence, a prior agent's assertion, or partial implementation.

## Supervision and execution

For multi-slice autonomy, first read [Campaign supervision](references/campaign-supervision.md).
Keep a long-running manager context thin and dispatch each slice or closure attempt to a fresh
worker. The manager trusts validated durable state, not its transcript; it never implements,
reviews, or consumes reviewer transcripts. A worker executes exactly one selected work item,
returns a compact result, and stops.

The slice worker follows [Execution and resume](references/execution-and-resume.md):

1. Restore the last validated checkpoint and reconcile any interrupted active-slice changes.
2. Select the lowest-ordered dependency-ready slice and mark it active before implementation,
   evidence, or documentation mutation begins. Retain the preceding campaign checkpoint and leave
   the active slice without a new checkpoint. Permit one active slice and one writer.
3. Reread its qualified authority and transitive semantic dependencies from the current model.
4. Invoke `$sysml-implementation` with the campaign slice contract. Let it choose the simplest
   conforming realization that respects project constraints and intentional deferrals.
5. Run focused evidence and project checks. Prefer targeted checks during implementation and
   remediation; normally run the whole-project gate once against the state offered for review.
6. Freeze one review-state token and obtain independent authority/conformance and
   engineering/evidence reviews against that same state. Include all evidence references and
   intended completion statuses in the frame before freezing it. Each frame carries the exact state
   token; the compact result names both distinct reviewer identifiers, lenses, clean dispositions, and that same
   token. Validate the result against the frozen token, recomputed current durable state, current
   campaign/work item, intended checkpoint, and reported passed checks before bookkeeping. The manager
   still enforces fresh-agent independence, runs required project gates, and independently validates
   the checkpoint; reported rows do not prove execution or completeness. If both are clean and
   substantive tracked or evidence state has not changed, review is complete. The worker may then
   perform only the deterministic atomic bookkeeping transition that applies those reviewed statuses
   and checkpoint identifiers. Otherwise collect their complete in-scope findings,
   batch remediation, sweep the root cause, rerun affected evidence, freeze the new state, and obtain
   another pair. Any implementation, test, documentation, evidence-reference, decision-content, or
   plan-bearing mutation invalidates a prior clean pair. After three consecutive non-clean
   pairs, perform a bounded root-cause audit before requesting another pair. Launch each reviewer
   once and await it through a blocking join or serialized foreground execution; never keep the
   worker alive with timers, polling, or overlapping wait tasks.
7. Mark the slice complete only when its bounded obligations conform, evidence discriminates the
   nearest plausible wrong implementation, every realization decision it owns is individually
   conforming with attributable evidence, dependencies remain valid, and a checkpoint can include
   implementation, tests, evidence, documentation truth, and record state together.
8. Create that checkpoint, return the compact worker result, and terminate. The manager independently
   validates the checkpoint before it dispatches the next ready slice without routine human review.

Treat implementation defects and bounded realization decisions as autonomous campaign work. An
approved record's selected realization constraints need not enumerate every bounded choice the
executor later makes. Preserve task-time choices in the realization, evidence, and handoff; add one
to the record only when project approval semantics permit it without rewriting the accepted plan.
Replan only when the choice changes stakeholder-visible meaning or an intentionally selected
boundary, and do not block merely because several code structures are semantically equivalent.
An already-selected behavior found missing is an implementation defect, not an invitation to reopen
the choice. If its owner was incorrectly checkpointed complete, preserve the decision and add a
corrective work item through renewed planning, whether or not unrelated approved work remains.

## Pause and replan

Pause before further implementation when evidence establishes:

- a genuine model gap or contradiction;
- a material plan gap, including omitted authority, dependency, or closure;
- a stakeholder-visible feasibility consequence or intentionally selected boundary change;
- a stale model or language baseline;
- an external dependency that the project cannot safely resolve within its authority.

Invalidate plan approval, preserve reproducible evidence, and route model gaps to `$sysml-modeling`,
language questions to `$sysml-reference`, and plan gaps to `$sysml-implementation-planning`. Human
approval is required for the corrected model-derived plan before resuming. Do not reinterpret an
ordinary code defect, storage choice, module boundary, dependency choice, or framework mismatch as a
model gap.

## Completion

Run [System closure](references/system-closure.md) after all planned slices complete. Mark a campaign
complete only when the baseline is current, aggregate authority coverage is full, implementation and
integration evidence conform, the project-selected external boundary is runnable, a cold agent can
reconstruct the result, and no blocker remains. A completed model or completed slice is not by itself
a completed application.

## References and assets

- [Campaign record](references/campaign-record.md): authority boundary, lifecycle, consistency, and
  template use.
- [Execution and resume](references/execution-and-resume.md): slice selection, interruption recovery,
  review, remediation, and checkpointing.
- [Campaign supervision](references/campaign-supervision.md): context-light management, one-work-item
  workers, dispatch, retry, and compact handoffs.
- [System closure](references/system-closure.md): full coverage, integration, runnable evidence, and
  cold reconstruction.
- [Campaign schema](assets/implementation-campaign.schema.json): portable machine contract.
- [Campaign template](assets/implementation-campaign.template.yaml): neutral starting artifact to
  populate from accepted model authority.
- [Worker-result schema](assets/campaign-worker-result.schema.json): compact manager handoff without
  review transcripts.
