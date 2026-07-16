---
name: architecture-projection
description: Render, inspect, compare, or explain stable and on-demand architectural projections from canonical textual SysML v2. Use when an architect or agent asks for model context, dependency impact, composition, runtime topology, operation traces, action flow, requirement coverage, package layers, a changed-model review bundle, or guidance on which model-derived view answers an architecture question.
---

# Architecture Projection

Answer architecture questions from canonical SysML facts. Treat the parser-backed architecture
graph, PlantUML, SVG, matrices, and manifests as generated projections rather than a parallel model.

## Workflow

1. Run `just model-view-presets` or
   `uv run python tools/model_views.py presets --json`. Do not rely on a memorized parameter list.
2. Read [references/architect-questions.md](references/architect-questions.md) when selecting among
   similar presets or interpreting a failure.
3. Resolve targets with `just model-view-targets` and prefer a stable ID over a display name.
4. Render the smallest projection that answers the concern:

   ```text
   just model-view context component.example
   just model-view impact component.example --direction inbound --depth 2
   just model-view operation operation.example.execute
   just model-view requirements component.example
   ```

5. Inspect `manifest.json` before interpreting the diagram. Require `truncated: false`, an empty
   omissions list, the expected target, and a current model digest.
6. Distinguish modeled relationships from repository projection conventions. Never infer a
   sequence, state transition, dependency, satisfaction, or verification relationship that is not
   present in the parser-backed graph.
7. For a model change, run `just model-view-changed BASE=<git-ref>` and review the bundle index.
8. If a projection is repeatedly useful, run `just model-view-promote <preset> <target>` to produce
   a candidate snippet, then use `sysml-view-authoring` and `sysml-reference` before editing the
   canonical model. Never insert the candidate without formal and visual review.

## Boundaries

- Stable dashboard artifacts live under `generated/reference/architecture/` and are committed.
- On-demand and changed-model artifacts live under `build/` and are disposable.
- Fail when `max-nodes` is exceeded; narrow depth or relationships instead of accepting truncation.
- Use matrices for dense traceability and graph diagrams for topology or flow.
- Use `sysml-view-authoring` when the task changes canonical view definitions, filters, exposure,
  rendering selection, or registered `diagram.` identities.

## Completion report

State the architectural question, preset, stable target, non-default parameters, model digest,
artifact path, node and edge counts, completeness result, and any relationship that remains
unmodeled. State whether the output is stable, change-relative, exploratory, or a promotion
candidate.
