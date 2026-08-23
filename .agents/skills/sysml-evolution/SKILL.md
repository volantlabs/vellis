---
name: sysml-evolution
description: Assess, plan, execute, resume, review, and close principled changes to an already implemented textual SysML v2 system while keeping accepted model authority, implementation, evidence, realization decisions, and documentation synchronized. Use for post-build audits, implementation-to-model feedback, defects spanning model and code, stakeholder changes, dependency or platform consequences, performance or resource findings, incremental feature evolution, and rebaselining after accepted updates.
---

# SysML System Evolution

Evolve an implemented system without treating either its current source or its original build plan as
permanent authority. Preserve a reconstructible path from evidence through accepted model meaning,
bounded realization changes, conformance evidence, and a new synchronized baseline.

## Project binding

Discover the project's bindings for:

- safety, writer ownership, worktree coordination, and recoverable checkpoints;
- textual model entry points, accepted model and language baselines, and official validation;
- implementation baseline identity, authored or generated source ownership, and project checks;
- durable evolution-record location, schema validation, approval, and archival convention;
- implementation review, external-boundary, compatibility, and documentation workflows;
- optional domain skills and reference tooling.

Do not assume paths, version control, implementation language, persistence, deployment, runtime,
framework, product domain, or a prior campaign. A project may bind the durable record to a committed
file, issue, change request, or equivalent system of record.

## Workflow

1. Establish one evolution objective and its observable distinction. Identify the accepted model,
   implementation, language, and project checkpoints before reading current source as design intent.
   For a broad audit, record its declared lenses and limits rather than claiming exhaustive review.
2. Read current model authority cold and reproduce each trigger from raw evidence. Create or refresh
   the project's evolution record using [Evolution record](references/evolution-record.md). Keep the
   record an execution and evidence index, never a shadow specification.
3. Classify every finding independently as a language question, model gap, plan gap, feasibility
   consequence, implementation defect, realization decision, stale baseline, external dependency,
   or out-of-scope disposition. Do not collapse several findings into a model change merely because
   one implementation mechanism could address all of them.
4. Build the smallest affected authority closure. For each finding, identify qualified current
   authority, observable consequence, current implementation status, nearest plausible wrong system,
   compatibility effect, and whether accepted authority can already decide conformance. Preserve
   explicit quantities and units, timing basis, physical cause-to-effect boundary, safety or security
   consequence, numerical semantics and tolerated error, and execution-environment identity whenever
   any is consequential. For numerical thresholds, inspect cancellation, precision, rounding and tie
   rules, monotonicity, exceptional values, conversions, and neighborhoods around discontinuities as
   applicable; do not infer a missing budget.
5. Route the finding before mutation:
   - resolve language questions with `$sysml-reference`;
   - change insufficient or contradictory authority with `$sysml-modeling` and applicable domain
     skills, then obtain the project's human acceptance of changed system meaning;
   - correct implementation defects and choose bounded model-preserving realization decisions with
     `$sysml-implementation`;
   - stop on stale baselines, unresolved external dependencies, or consequential feasibility choices
     requiring stakeholder direction.
6. Derive dependency-ordered work items from semantic effects, not files or architecture layers.
   Give every finding and consequential realization decision one completion owner. Require separate
   modeling, implementation, integration, or closure work only when each produces independently
   discriminating evidence.
7. Apply the approval rules in [Evolution execution](references/evolution-execution.md). Acceptance
   of changed model authority precedes implementation against it. An ordinary implementation defect
   under sufficient current authority does not require inventing a model change or whole-system plan.
8. Execute one dependency-ready work item with one writer. Reread its authority, use the applicable
   specialist skill, run focused evidence, review authority/conformance separately from
   engineering/evidence, batch corrections, and checkpoint implementation, tests, documentation
   truth, and record state together when the project supports atomic checkpoints.
9. Reassess only the findings this change could have affected. Sweep the same root cause and add a
   new finding rather than widening an existing work item.
10. Close with [Evolution execution](references/evolution-execution.md): every finding has a supported
    disposition, target authority is accepted and current, implementation and integration conform,
    selected external behavior is exercised where applicable, public claims are truthful, and a cold
    agent can reconstruct the new baseline without conversation history.

## Scale selection

Use the lightest durable coordination that preserves the change:

- **One bounded correction:** a task-local implementation frame may be enough; use no durable record
  when context loss, approval, or cross-authority coordination is immaterial.
- **One cohesive evolution set:** use this skill and one baseline-bound evolution record containing
  all related findings and work items.
- **Complete or long-running rebuild:** split it into independently valuable evolution sets rather
  than growing one record into a second execution engine.

## Portable boundary

Keep system semantics and evidence obligations portable. The skill may require abstract capabilities
such as baseline discovery, official validation, change-record validation, project checks, and
independent review, but it must not prescribe a repository layout, database, cache, event ledger,
snapshot cadence, process topology, programming language, framework, protocol, or deployment.

Treat implementation structure as evidence only when its observable consequence crosses the model
gap or feasibility gate. Performance, timing, resource, safety, security, durability, and recovery
findings become model authority only when the system must promise or expose their consequence. For a
physical or numerical boundary, require units and evidence at the actual modeled effect rather than
stopping at a convenient software proxy. Compare numerical results with an independent higher-
precision, analytic, or otherwise justified oracle when exact expected values are not self-evident.

## References and assets

- [Evolution record](references/evolution-record.md): authority boundary, lifecycle, classifications,
  work ownership, and durable evidence semantics.
- [Evolution execution](references/evolution-execution.md): approval, execution, review, interruption,
  closure, and rebaseline rules.
- [Evolution schema](assets/system-evolution.schema.json): neutral machine-readable record contract.
- [Evolution template](assets/system-evolution.template.yaml): minimal starting record to bind in a
  project without importing a product architecture.
