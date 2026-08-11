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

## Execution loop

Follow [Execution and resume](references/execution-and-resume.md):

1. Restore the last validated checkpoint and reconcile any interrupted active-slice changes.
2. Select the lowest-ordered dependency-ready slice and mark it active before implementation,
   evidence, or documentation mutation begins. Retain the preceding campaign checkpoint and leave
   the active slice without a new checkpoint. Permit one active slice and one writer.
3. Reread its qualified authority and transitive semantic dependencies from the current model.
4. Invoke `$sysml-implementation` with the campaign slice contract. Let it choose the simplest
   conforming realization that respects project constraints and intentional deferrals.
5. Run focused evidence and project checks.
6. Obtain independent authority/conformance and engineering/evidence reviews. Collect their complete
   in-scope findings, batch remediation, then run one final independent review pair against the
   resulting slice. Repeat only when that final pair finds a plausible defect within the project's
   declared authority, safety, evidence, or ordinary recovery boundary.
7. Mark the slice complete only when its bounded obligations conform, evidence discriminates the
   nearest plausible wrong implementation, dependencies remain valid, and a checkpoint can include
   implementation, tests, evidence, documentation truth, and record state together.
8. Create that checkpoint, then continue to the next ready slice without waiting for routine human
   code review.

Treat implementation defects and bounded realization decisions as autonomous campaign work. An
approved record's selected realization constraints need not enumerate every bounded choice the
executor later makes. Preserve task-time choices in the realization, evidence, and handoff; add one
to the record only when project approval semantics permit it without rewriting the accepted plan.
Replan only when the choice changes stakeholder-visible meaning or an intentionally selected
boundary, and do not block merely because several code structures are semantically equivalent.

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
- [System closure](references/system-closure.md): full coverage, integration, runnable evidence, and
  cold reconstruction.
- [Campaign schema](assets/implementation-campaign.schema.json): portable machine contract.
- [Campaign template](assets/implementation-campaign.template.yaml): neutral starting artifact to
  populate from accepted model authority.
