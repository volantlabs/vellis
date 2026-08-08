---
name: sysml-implementation
description: Consume one bounded semantic slice of accepted textual SysML v2 system authority and turn it into model-conformant software, discriminating evidence, and conformance review. Use when planning or implementing a selected slice, continuing that slice after a model change, choosing realization details the model intentionally leaves open, mapping its requirements and verification cases to evidence, or diagnosing divergence between current model authority and source code; use sysml-implementation-planning for whole-model decomposition and sysml-implementation-campaign for long-running multi-slice execution.
---

# SysML Implementation

Turn the current model into working software without treating SysML as a class diagram or letting
source code become a competing system definition. Preserve one navigable path from stakeholder outcome and
modeled meaning through realization decisions, code, and evidence.

## Project binding

This skill is a portable implementation method. Before using it, discover the project's local
bindings for:

- safety rules and the location and reading order of model authority;
- active model baseline, current change set, and any model-to-implementation handoff;
- selected implementation language, platforms, dependency policy, and compatibility baseline;
- authored versus generated source ownership and regeneration rules;
- build, test, analysis, simulation, hardware, deployment, and documentation checks that apply;
- optional domain skills that add specialized engineering semantics.

Do not assume a model directory, source-control system, command runner, programming language,
framework, server, user interface, persistence layer, network, code generator, or test framework.
Local instructions bind the method to the project and govern safety. The core skill must remain usable
for stateless, stateful, interactive, batch, embedded, real-time, distributed, scientific, and
safety- or security-relevant software without requiring concerns those systems do not have.

## Workflow

1. Establish whether the task is bounded-slice planning, implementation, conformance review, or
   diagnosis. Keep a planning or review request read-only unless the user also requests changes. If
   the task covers the complete system or manages several slices over time, route it to
   `$sysml-implementation-planning` or `$sysml-implementation-campaign` before continuing.
2. Follow project safety and authority instructions. Read the model cold before taking cues from
   existing implementation structure. If the project supplies a semantic handoff from model work,
   verify it against the current model and change set rather than trusting prior conversation. Otherwise
   reconstruct the same task-local implementation frame with [Model consumption](references/model-consumption.md).
3. Classify every consequential statement as one of:
   - required model meaning;
   - an already selected realization constraint;
   - a realization decision still open to this task;
   - a model gap or contradiction;
   - a deliberate non-goal or unrelated concern.
4. Close a model gap before coding when it changes stakeholder-visible behavior, system responsibility,
   identity, ownership, state, failure non-effects, compatibility, a selected external contract, a
   requirement, or decisive verification. Use `$sysml-modeling` and `$sysml-reference`; use an
   applicable domain skill as well. Do not reopen intentionally deferred realization merely because
   code now needs a concrete choice.
5. Select one end-to-end semantic slice and form an executable plan with
   [Implementation planning](references/implementation-planning.md). Tie each plan item to qualified
   model authority, observable evidence, and explicit non-goals. Choose the simplest realization
   supported by current scale, project facts, user direction, and the slice's applicable failure,
   quality, timing, resource, safety, security, lifecycle, compatibility, and deployment needs.
6. Implement the slice. Preserve applicable modeled identity, ownership, multiplicity, equality,
   values, units, calculations, invariants, control and data flow, state, modes, events, timing,
   concurrency, interaction, nominal and alternate outcomes, required non-effects, and selected
   external boundary meaning.
   Use current primary documentation for selected libraries and runtimes. Keep framework payloads,
   storage forms, modules, and call graphs in the realization unless the model intentionally selects
   their observable consequences.
7. Derive conformance evidence from verification intent rather than mirroring model inventories.
   Exercise the smallest nominal case, applicable alternate or safely reported failure, and
   counterexample that exposes the slice's consequential distinction. Add boundary, numerical,
   temporal, concurrent, resource, security, safety, simulation, or hardware evidence only where
   required. Verify non-effects at the authority they promise to preserve.
8. Run [Conformance and feedback](references/conformance-review.md). Review plan conformance, model
   meaning in code, evidence strength, realization leakage, and subtraction separately. Fix material
   findings and repeat the whole review sequence until one full pass finds none.
9. Update explanatory documentation and status claims through the project's configured workflow only
   when they changed. Distinguish modeled,
   selected, implemented, verified, and runnable. Hand back implemented meaning, model references,
   realization decisions, checks, compatibility effects, and any bounded model feedback.

## Campaign composition contract

When a campaign manager invokes this skill, validate and consume:

- the active model baseline, stable slice ID, and bounded observable outcome;
- qualified authority and each slice contribution's `full` or `partial` coverage;
- the stable IDs that close every remaining partial obligation;
- completed semantic dependencies and applicable verification or analysis references;
- selected project constraints, explicit non-goals, and open realization decisions.

Return:

- the slice's implementation status using `not evaluated`, `absent`, `partial`, `conforming`, or
  `conflicting`;
- evidence references and the nearest plausible wrong implementation each excludes;
- consequential realization decisions and the authority they preserve;
- any language question, model gap, plan gap, feasibility consequence, implementation defect, stale
  baseline, or out-of-scope disposition;
- remaining authority and whether the slice is ready for an atomic project checkpoint.

Do not select another slice, approve a campaign plan, mark whole-system requirements satisfied from
partial coverage, or declare the application complete. The campaign manager owns sequence, durable
state, independent reviews, checkpoints, resume, and final system closure.

## Translation discipline

- Do not map a package to a code package, a part to a service or class, an item to a DTO or table, an
  action to a method, or a requirement to one test by name alone. Retrieve the construct's semantics
  and preserve its instance-level commitment in whatever implementation structure is simplest.
- Allow software structure to be finer-grained than the systems model. Use cohesive semantic
  neighborhoods as evidence for classes or modules when they improve invariant enforcement,
  dependency direction, testability, or change isolation, but record that many-to-many mapping as a
  realization projection. Do not turn an implementation component into an independent modeled
  lifecycle, state authority, failure boundary, or subsystem by accident.
- Treat definitions and usages, ownership and reference, specialization, subsetting, redefinition,
  binding, multiplicity, succession, satisfaction, and verification as semantic commitments rather
  than naming conventions. Use `$sysml-reference` when any of them affects the implementation.
- Let conformance evidence verify the current model from implementation toward authority. Do not make
  test names, counts, fixtures, schemas, golden files, or generated artifacts into a second inventory
  that freezes the living model.
- Treat implementation discoveries as evidence. Feed them back into the model only when they expose
  missing or contradictory product meaning or intentionally select a realization boundary; do not
  transcribe an accidental code structure into SysML.
- Never hand-edit generated product source when the repository has selected generation. Change its
  authority or generator, regenerate, and check freshness. Do not introduce generation merely
  because the source model is machine-readable.
- Refresh the implementation frame whenever the model or its relevant diff changes during the task.

## References

- [Model consumption](references/model-consumption.md): cold reading, semantic handoffs,
  implementation frames, and the model-gap gate.
- [Implementation planning](references/implementation-planning.md): vertical slices, realization
  decisions, conformance matrices, plans, and non-goals.
- [Conformance and feedback](references/conformance-review.md): conformance evidence, fixed-point
  review, divergence classification, and implementation-to-model feedback.
