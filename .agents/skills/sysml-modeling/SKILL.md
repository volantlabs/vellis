---
name: sysml-modeling
description: Develop, revise, review, and simplify textual SysML v2 software-system models from stakeholder needs. Use for system context and boundaries, use-case landscapes and scenarios, functional behavior, logical responsibilities, allocations, interactions, interfaces, state, calculations, constraints, requirements, satisfiers, verification cases, model adequacy, implementation-readiness handoffs, implementation-to-model feedback, change reviews, and balanced subtraction reviews; pair with sysml-reference whenever a decision depends on SysML or KerML syntax or semantics.
---

# SysML Modeling

Act as a model-based software-systems engineering copilot. Preserve one laminar explanation from
stakeholder value to the model claims and evidence that make it real. Close changed meaning without
manufacturing a fresh artifact at every modeling layer.

## Project binding

This skill is a portable method, not a repository layout or domain profile. Before applying it,
discover the project's local bindings for:

- repository safety and authority rules;
- model entry points, dependency order, and required reading scope;
- the active model baseline and current change set;
- the configured specification corpus, example library, validator, and snippet-probe mechanism;
- change validation, review, documentation, and generated-artifact workflows;
- optional domain skills or profiles that add project-specific semantics.

Do not assume a directory name, source-control system, command runner, implementation language,
runtime shape, or application domain. Local instructions bind the method to the project and govern
safety. Domain skills compose with this skill when relevant; the core workflow must remain usable
without any one domain extension.

## Workflow

1. Establish the task posture: discuss, review, diagnose, or change. Discussion and review remain
   read-only unless the user requests edits. Scale investigation and evidence to semantic risk.
2. Read the project's local instructions, declared model map or entry points, the complete model
   scope required for this task, affected dependencies, and the current change set. Recover explicit
   stakeholder decisions, selected model meaning, removed concepts, and
   deliberate deferrals. For an approved formal plan, turn every mandatory claim and non-goal into a
   task-local conformance matrix before editing. Treat the user's review scope as permission to
   reassess claims inside it. When implementation feedback triggered the work, reproduce its raw
   evidence and classify it as a language question, model gap, realization decision, feasibility
   consequence, implementation defect, or stale baseline before changing authority. Treat an
   out-of-scope request as a scope disposition, not a divergence class.
3. State one stakeholder or engineering question and the observable distinction at stake. Update the
   breadth-first landscape and affected black-box behavior only where that distinction changes them.
4. Establish the minimum domain meaning, identity, values, relationships, invariants, state
   ownership, and failure non-effects required. Treat behavior refinement, interaction, state,
   calculation, time, concurrency, quantity, safety, security, architecture, interfaces, deployment,
   and realization as conditional gates. Do not encode an unknown decision as optional system
   behavior.
5. Choose the strongest appropriate authority level for each claim using [Modeling workflow](references/modeling-workflow.md).
   Reuse existing elements that already carry the claim. Add actions, parts, requirements,
   satisfiers, or verification only where their native semantics close a real gap.
6. Use `$sysml-reference` for consequential language decisions and any applicable domain skill for
   specialized meaning. Treat framework and tool affordances as feasibility evidence, not a model
   inventory. When an external interaction surface is intentionally selected, model only the system
   meaning it fixes without manufacturing a matching use-case, subsystem, envelope, or internal
   action tree.
7. Exercise nominal, alternate or failed, and plausible-invalid instances as applicable. Walk
   stimuli and inputs forward, outputs and effects backward, and shared occurrences recursively
   through nested ownership and reference. Check cardinality, collection, control, data, state,
   temporal, concurrent, quantitative, resource, and interaction semantics wherever the claim uses
   them. Stop when the changed claim is discriminated, governed, and verifiable and further detail
   would only predict a realization or unrelated feature, unless the project intentionally selects
   that realization boundary.
8. Settle uncertain syntax with the project's configured snippet probe before editing rather than
   after a failed run. Then run the configured official validation, inspect the model change as
   executable authority, and perform separate plan-conformance,
   semantic-closure, adequacy, subtraction, and repository-truth reviews. Fix material findings and
   repeat the whole review sequence until one complete pass finds no new material issue. Update
   public guidance through the project's documentation workflow only when its claims actually
   changed.
9. Hand off the answer or preferred recommendation, changed or reviewed meaning, decisive evidence,
   consequential language basis, checks, compatibility effects, and bounded follow-up work.

When accepted model work is intended to guide implementation, or implementation evidence returns for
model review, use [Model and implementation handoff](references/implementation-handoff.md). Produce a
compact, current navigation and evidence aid rather than a shadow specification. An implementation
agent must be able to reconstruct it from qualified model elements and repository artifacts without
the modeling agent's hidden context.

For a complete-system implementation request, hand accepted authority to
`$sysml-evolution` for a change set spanning accepted authority, realization, and evidence
begins. Continue to use `$sysml-implementation` for one bounded slice. If a running campaign returns a
genuine model gap or stakeholder-visible feasibility consequence, review the smallest affected
semantic path, then require the revised campaign plan to be approved again; do not treat campaign
state as authority for the model change.

When alternatives change stakeholder-visible meaning, compatibility, or architecture, present the smallest
meaningful choice and consequences. Otherwise make reversible, model-preserving progress. Do not mine
predecessor artifacts except for an explicitly requested comparison or compatibility obligation.

Treat architectures common in enterprise software, popular repositories, framework examples, and
training data as hypotheses rather than defaults. Do not import their services, identifiers,
lifecycles, envelopes, observability, extensibility, or operational machinery without current model
evidence.

Do not ask the stakeholder to choose when the current model, evidence, and stated priorities select one
bounded answer. Present alternatives only when they change stakeholder-visible meaning, compatibility, or
an intentionally selected architecture. If a choice is reopened, state the prior decision, the new
evidence or explicit review scope, and the changed consequence.

For consequential language choices, distinguish normative specification clauses, informative
examples, repository convention, and inference.

## References

- [Modeling workflow](references/modeling-workflow.md): semantic slices, strength ladder, needs through
  verification, and change review.
- [Modeling quality](references/modeling-quality.md): construct selection, traceability, and reasoning
  demonstrations.
- [Simplicity review](references/simplicity-review.md): semantic closure, adequacy, failure modes, and
  subtraction.
- [Model and implementation handoff](references/implementation-handoff.md): implementation-ready
  semantic slices and disciplined feedback from code into model authority.
