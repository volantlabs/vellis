---
name: sysml-implementation-planning
description: Consume a complete accepted textual SysML v2 model and derive a baseline-bound, coverage-complete, dependency-ordered implementation campaign made of evidence-bearing semantic slices. Use when planning implementation of a whole modeled system, decomposing all accepted authority into buildable slices, assessing whether a model is ready for autonomous implementation, or replanning after model authority changes; use sysml-implementation only after this skill has selected one bounded slice.
---

# SysML Implementation Planning

Turn a complete accepted model into an implementation campaign without translating declarations into
tasks or choosing familiar architecture in place of modeled meaning. Keep the model authoritative;
the plan is a baseline-bound execution index.

## Project binding

Discover the project's local bindings for:

- safety rules, model entry points, dependency order, and complete authored scope;
- active model and language baselines and the mechanism that identifies them;
- official validation and consequential language-reference capabilities;
- existing implementation, selected realization constraints, and project evidence gates;
- campaign-record location, validation, approval, checkpoint, and continuation mechanisms;
- optional domain skills that add specialized engineering semantics.

Do not assume a directory, source-control system, command runner, programming language, framework,
runtime, deployment, persistence, networking, user interface, or application domain. Read model
authority before existing source structure.

## Workflow

1. Confirm that the request covers the complete accepted model rather than one bounded semantic
   slice. For a slice, route directly to `$sysml-implementation`.
2. Record the active model and language baselines. Read the complete project-declared model scope,
   imports, and current change set. Use `$sysml-reference` for consequential language meaning and
   `$sysml-modeling` plus applicable domain skills for genuine authority gaps.
3. Build the implementation-bearing authority universe and obligation graph with
   [Complete-model decomposition](references/complete-model-decomposition.md). Follow behavioral,
   state, interaction, requirement, satisfaction, and verification meaning rather than files or
   declaration counts.
4. Add semantic dependencies. Collapse cycles or jointly governed meaning that cannot be split
   without fracturing identity, state, transaction, timing, safety, failure, physical, or external
   boundaries.
5. Cut the graph into the smallest end-to-end `semantic`, `integration`, and `closure` slices that
   produce discriminating evidence. Toolchain or realization setup belongs inside the first slice
   that needs it; do not create an architecture-only slice. For each slice, expose the consequential
   input and failure boundary, state or recovery obligations, declared assumptions, and review risks
   that evidence must discriminate so execution does not discover its contract incrementally.
6. Order dependency-ready slices by modeled prerequisites, then by risk retirement and reversible
   learning. Record an explicit order so a campaign manager does not improvise priority later.
7. Map every implementation-bearing authority reference to one or more slices. A slice may cover an
   authority element partially, but the accepted whole plan must cover its complete meaning across
   the campaign and identify where the remainder closes.
8. Only after the model-derived plan exists, inspect current source and evidence to set the existing
   implementation status and impact. Do not reshape slices to mirror accidental source topology.
9. Run [Campaign-plan review](references/campaign-plan-review.md), fix material findings, and repeat
   the complete review. Present every model or material plan gap for human review. Do not authorize
   campaign execution yourself.

## Output contract

Produce or refresh the project's configured campaign record with:

- model and language baseline identity;
- campaign objective and approval state;
- qualified implementation-bearing authority references and source locations;
- full or partial per-slice coverage contributions and complete aggregate planned coverage;
- stable slice IDs, kind, order, dependencies, verification references, lifecycle, and status;
- concise consequential realization decisions, blockers, evidence references, and checkpoints;
- whole-system integration, runnable-boundary, and cold-reconstruction closure intent.

Use only enough labels to navigate back to authority. Do not copy requirement prose, acceptance
criteria, scenarios, design descriptions, stories, estimates, assignees, or source inventories into
the record. Treat a schema or template bundled by the campaign skill as an interchange format, not
as product authority.

## Human authority gate

Set a newly derived or materially revised plan to awaiting approval. A human accepts the complete
plan before implementation begins or resumes. If decomposition exposes behavior that the model
cannot decide, record a model gap and stop. If review finds missing coverage, dependency, or closure
inside the plan, repair it and require renewed approval. Intentionally deferred realization remains
an implementation decision unless its demonstrated consequence changes stakeholder-visible meaning
or a selected boundary.

## References

- [Complete-model decomposition](references/complete-model-decomposition.md): authority universe,
  obligation graph, dependencies, cohesive slicing, and ordering.
- [Campaign-plan review](references/campaign-plan-review.md): coverage, readiness, human approval,
  subtraction, and cold-agent reconstruction.
