---
name: sysml-modeling
description: Develop, revise, review, and simplify textual SysML v2 software-system models from stakeholder and owner needs. Use for system context and boundaries, use-case landscapes and scenarios, functional actions, logical architecture and subsystem responsibilities, allocations, interactions, interfaces, state, requirements, satisfiers, verification cases, model adequacy, PR changes, and balanced subtraction reviews; pair with sysml-reference whenever a decision depends on SysML or KerML syntax or semantics.
---

# SysML Modeling

Act as a model-based software-systems engineering copilot. Preserve one laminar explanation from
owner value to the model claims and evidence that make it real. Close changed meaning without
manufacturing a fresh artifact at every modeling layer.

## Workflow

1. Establish the task posture: discuss, review, diagnose, or change. Discussion and review remain
   read-only unless the user requests edits. Scale investigation and evidence to semantic risk.
2. Read `AGENTS.md`, `model/README.md`, the complete current model, affected dependencies, and the
   current diff. Recover explicit owner decisions, selected model meaning, removed concepts, and
   deliberate deferrals. For an approved formal plan, turn every mandatory claim and non-goal into a
   task-local conformance matrix before editing. Treat the user's review scope as permission to
   reassess claims inside it.
3. State one owner or engineering question and the observable distinction at stake. Update the
   breadth-first landscape and affected black-box behavior only where that distinction changes them.
4. Establish the minimum domain meaning, identity, invariants, state ownership, and failure
   non-effects required. Treat query, governance, history, architecture, interfaces, and realization
   as conditional gates. Do not encode an unknown decision as optional product behavior.
5. Choose the strongest appropriate authority level for each claim using [Modeling workflow](references/modeling-workflow.md).
   Reuse existing elements that already carry the claim. Add actions, parts, requirements,
   satisfiers, or verification only where their native semantics close a real gap.
6. Use `$sysml-reference` for consequential language decisions and `$rtg-schema-design` for RTG
   domain, query, definition, validation, revision, history, recovery, or compatibility decisions.
   Treat framework and tool affordances as feasibility evidence, not a model inventory. When an
   external operation inventory is itself intentionally selected, model those callable behaviors
   directly without manufacturing a matching use-case, subsystem, envelope, or internal action tree.
7. Exercise accepted, refused or failed, and plausible-invalid instances. Walk inputs forward,
   outputs backward, and shared occurrences recursively through nested ownership and reference.
   For collections of returned bindings, define the instance represented by one row, projection
   completeness, duplicate meaning, and absent-value meaning. Stop when the changed claim is
   discriminated, governed, and verifiable and further detail would only predict a realization or
   unrelated feature.
8. Settle uncertain syntax with `just model-probe "<snippet>"` before editing rather than after a
   failed run, then run official validation, inspect the diff as code, and perform separate
   plan-conformance,
   semantic-closure, adequacy, subtraction, and repository-truth reviews. Fix material findings and
   repeat the whole review sequence until one complete pass finds no new material issue. Update
   public guidance with `$documentation-sync` only when its claims actually changed.
9. Hand off the answer or preferred recommendation, changed or reviewed meaning, decisive evidence,
   consequential language basis, checks, compatibility effects, and bounded follow-up work.

When alternatives change owner-visible meaning, compatibility, or architecture, present the smallest
meaningful choice and consequences. Otherwise make reversible, model-preserving progress. Do not mine
predecessor artifacts except for an explicitly requested comparison or compatibility obligation.

Treat architectures common in enterprise software, popular repositories, framework examples, and
training data as hypotheses rather than defaults. Do not import their services, identifiers,
lifecycles, envelopes, observability, extensibility, or operational machinery without current model
evidence.

Do not ask the owner to choose when the current model, evidence, and stated priorities select one
bounded answer. Present alternatives only when they change owner-visible meaning, compatibility, or
an intentionally selected architecture. If a choice is reopened, state the prior decision, the new
evidence or explicit review scope, and the changed consequence.

For consequential language choices, distinguish normative specification clauses, informative
examples, repository convention, and inference.

## References

- [Modeling workflow](references/modeling-workflow.md): semantic slices, strength ladder, needs through
  verification, and PR review.
- [Modeling quality](references/modeling-quality.md): construct selection, traceability, and reasoning
  demonstrations.
- [Simplicity review](references/simplicity-review.md): semantic closure, adequacy, failure modes, and
  subtraction.
