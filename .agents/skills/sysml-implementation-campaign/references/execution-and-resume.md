# Execution and Resume

## Start or resume safely

1. Apply project safety rules and identify the working state, writer, current baseline, campaign
   record, and last checkpoint.
2. Validate the record structurally and semantically before trusting lifecycle or coverage.
3. If uncommitted work exists, compare it with the record's active slice and last checkpoint. Resume
   it only when the changes form one explainable continuation of that slice. Otherwise stop for
   project-directed recovery; never discard or absorb unexplained work.
4. If the baseline is stale, activate no slice. Replan and obtain human approval.
5. If no slice is active, select the lowest-order `ready` slice whose dependencies are complete.

The record must be sufficient after conversation loss. Do not depend on hidden notes, a previous
agent's memory, or a harness-specific task transcript.

## Execute one slice

Pass the slice executor:

- model baseline and slice ID;
- bounded outcome and qualified authority references;
- full or partial coverage contributions and remaining slice IDs;
- completed semantic dependencies;
- applicable verification or analysis references;
- selected project constraints, explicit non-goals, and intentionally open realization choices.

Require it to return implementation status, evidence references, realization decisions, classified
feedback, remaining authority, and checkpoint readiness. Verify the returned references against the
current model and record rather than copying the executor's prose.

## Review to a bounded clean result

Use two independent, context-isolated reviews after focused evidence passes:

1. **Authority and conformance:** verify baseline, slice scope, model meaning, partial/full coverage,
   dependencies, acceptance and failure non-effects, and absence of a model or plan gap.
2. **Engineering and evidence:** inspect implementation correctness, failure handling, numerical or
   temporal behavior where applicable, tests and other evidence, simplicity, realization leakage,
   project truth, and the nearest plausible wrong implementation.

Give reviewers the current branch or workspace, model, slice record, and evidence—not prior findings
or expected conclusions. A material finding must identify a plausible consequence for accepted
authority, implementation correctness, discriminating evidence, declared safety, or ordinary
project recovery under the project's stated assumptions. Do not expand the threat model or
recursively review campaign machinery unless the selected slice changes it.

Collect the complete findings from both reviews, batch remediation, and then run one final
independent review pair against the resulting slice. Repeat only if that final pair finds another
in-scope material defect. Read-only reviewers may work concurrently; one writer owns remediation and
the record.

## Checkpoint and continue

When both reviews produce no material finding:

- update the slice and affected aggregate authority status;
- run required focused and whole-project checks;
- ensure documentation claims distinguish modeled, selected, implemented, verified, and runnable;
- checkpoint implementation, evidence, and record state as one recoverable effect;
- record the checkpoint identifier and select the next dependency-ready slice.

If interruption occurs before the checkpoint, leave the slice active and resume it from inspected
working state. If interruption occurs after the checkpoint, the committed record selects the next
work. Never mark a slice complete before its checkpoint exists.
