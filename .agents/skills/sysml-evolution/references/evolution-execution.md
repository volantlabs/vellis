# Evolution Execution

## Contents

- [Operating mode](#operating-mode)
- [Approval gates](#approval-gates)
- [Planning and execution](#planning-and-execution)
- [Review and remediation](#review-and-remediation)
- [Interruption and change](#interruption-and-change)
- [Closure and rebaseline](#closure-and-rebaseline)

## Operating mode

Fix the mode at the start and record it. It decides how much has to be written down.

**Copilot.** The correction loop is seconds long, so ask rather than assume. The human confirms the
acceptance set at dispatch. Stop and report after each work item. Use one fresh reviewer and let the
human be the second lens. Use ordinary project checkpoints; do not mint state tokens and do not
re-stamp reviewed state.

**Autonomous.** Write the objective, the observable distinction, the non-goals, the acceptance sets,
and the stop conditions before dispatch, and do not let the working agent amend them. Use two fresh,
context-isolated reviewers. Stop mechanically on any of:

- changed accepted system meaning;
- a finding whose consequence falls outside the declared scope;
- an acceptance entry still without evidence after two review pairs;
- two review pairs that were not clean;
- an unexplained dirty working state.

Spend budgets rather than escalating. Never widen scope alone.

## Approval gates

Determine approval from consequence, not artifact count:

- Accept changed textual model authority before implementation relies on it.
- Require stakeholder or project approval for a changed selected external boundary, compatibility
  promise, safety/security posture, or project-designated material realization decision.
- Do not require a model edit, complete campaign, or exceptional approval for an implementation
  defect already decided by accepted authority.
- Do not infer approval from record existence, prior implementation, passing tests, or an agent's
  assertion.
- Scope approval to affected work. An independent implementation defect whose authority and normal
  change authorization are sufficient need not wait for an unrelated pending model or boundary
  decision in the same evolution set.

When target authority changes during execution, stop model-dependent mutation, mark affected work
stale, refresh the impact and evidence plan, and satisfy the new approval gate.

## Planning and execution

For each work item:

1. Confirm source and target baselines, dependency completion, writer ownership, and recoverable
   checkpoint state.
2. Reread qualified authority and transitive semantic dependencies. Reproduce each owned finding.
3. Build a bounded conformance matrix: authority, in-scope obligation, full or partial coverage,
   remaining obligations, implementation status, decisive evidence, non-effects, and open
   realization. When numerical meaning is material, include dimensions and units, conversions,
   precision or error budgets when authority supplies them, rounding and tie behavior, threshold
   neighborhoods, monotonicity, exceptional values, and a justified independent oracle.
4. Use `$sysml-modeling` for modeling work and `$sysml-implementation` for implementation work.
   Use applicable domain and reference skills. A modeling item ends with accepted model authority and
   an implementation-ready handoff; it does not silently continue into source changes.
5. Implement the smallest coherent change. Preserve unrelated accepted meaning, public boundaries,
   compatibility, user data, generated-source ownership, and project safety.
6. Run focused evidence and project truth checks. Update the durable record only with attributable,
   reproducible evidence.
7. Checkpoint the work item and record together when the project supports it. Stop after one work
   item when a manager or continuation harness owns sequence.

## Review and remediation

Review two lenses independently:

- **Authority/conformance:** accepted meaning, coverage, state and failure effects, compatibility,
  selected boundaries, and absence of realization leakage into authority.
- **Engineering/evidence:** correctness, data structures, resource behavior, concurrency, recovery,
  maintainability, evidence discrimination, explicit units, numerical error, timing basis, actual
  physical effects, execution-environment identity, and public/project truth where consequential.

A finding is material only if it names a behavior the current artifact exhibits, with the input that
produces it. "The evidence would not catch X" is not a finding unless X is present. Do not propose
additional evidence for behaviors outside the work item's acceptance set.

Collect complete findings from both lenses against the same state. Batch in-scope corrections, sweep
the same root cause, rerun relevant evidence, then run the second pair. Two review pairs is the
budget for one work item. If the second pair is not clean, stop: in copilot mode hand the findings to
the human; in autonomous mode pause the work item with its findings recorded and take the next
dependency-ready item. Never run a third pair. Do not prolong review by inventing inputs, threat
models, performance targets, or architecture outside declared authority and ordinary project
assumptions.

Bind each review result to its independent reviewer, exact reviewed-state checkpoint, lens, final
disposition, and reproducible evidence. Every lens declared in the evolution scope participates in
the clean final pass; do not substitute an unevidenced label or an earlier superseded review.

An audit finding is not closed by adding a test that observes the existing behavior. Evidence must
fail for the wrong implementation and the implementation or authority must actually change when the
finding requires it.

## Interruption and change

Resume from durable baselines and checkpoints, never conversation memory. Inspect uncommitted work
against the last checkpoint; continue only changes that explainably belong to the recorded active
work item. Stop on unexplained mutation or conflicting writer state.

New evidence during evolution follows the same intake path:

- add a separately classified finding when it has an independently actionable consequence;
- widen an existing work item only when its semantic outcome, dependencies, approval, and review
  surface remain unchanged;
- add and order a new work item when another completion owner is needed;
- route complete-system replanning to the campaign skills rather than recursively enlarging this
  record.

## Closure and rebaseline

Close only when:

- every finding is resolved, accepted with explicit authority, or dispositioned out of scope;
- accepted target authority is valid, current, and sufficient for every implemented change;
- each implementation work item and selected realization decision is conforming with attributable
  evidence;
- cross-item state, transaction, timing, safety, security, failure, interaction, and external
  boundaries remain coherent where applicable, including the actual physical or numerical effect
  rather than only a software-side proxy;
- compatibility and migration consequences are demonstrated or explicitly accepted;
- generated artifacts are fresh, public claims are truthful, and protected data remained outside
  the work;
- the complete project gate and applicable runnable-boundary checks pass;
- a cold agent can reconstruct source evidence, decisions, changed authority, implementation mapping,
  remaining non-goals, and the target baseline from durable artifacts.

Record the accepted target model and implementation checkpoints, closure evidence, and compatibility
disposition. The new target becomes the source baseline for later evolution. Archiving, retaining, or
removing the closed record is a project convention; its durable history must remain recoverable.
