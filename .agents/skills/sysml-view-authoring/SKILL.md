---
name: sysml-view-authoring
description: Author, revise, split, review, or diagnose canonical textual SysML v2 view definitions and usages, including repository-native PlantUML and SVG diagrams. Use for view filters, exposure scope, rendering selection, stable diagram identities, traversal-limit failures, diagram completeness, and generated view artifacts.
---

# SysML View Authoring

Author canonical SysML view usages under `model/`; treat committed PlantUML, SVG, and Markdown as generated projections. Keep every graphical projection focused enough to render completely with the pinned official pilot.

## Required grounding

1. Read `.agents/skills/sysml-reference/SKILL.md` completely and follow it before deciding view or rendering semantics.
2. Search the checksum-pinned specification pages for the exact construct in question. For view work, begin with SysML 2.0 sections 7.26.2 and 7.26.4–5 and KerML 1.0 sections 7.4.14 and 8.3.4.13.4, then follow relevant cross-references.
3. Distinguish official semantics from repository conventions and pilot limitations in the final explanation.
4. Read [references/view-patterns.md](references/view-patterns.md) before editing a graphical view or diagnosing a render failure.

## Workflow

### 1. Select one concern

Identify the stakeholder question and the smallest model root that answers it. Prefer a focused component contract, behavior, requirement, or interconnection projection over a broad package traversal. Do not introduce a viewpoint unless an explicit stakeholder concern and its framing are part of the model.
Use `architecture-projection` first when an on-demand context, impact, composition, operation,
action-flow, or requirement slice can test the concern without changing the canonical model. Promote
only a recurring, reviewed concern.

### 2. Author the canonical view

- Put authored views in the appropriate `model/<product>/views/` package.
- Use targeted `expose` memberships. Avoid `Package::**` for registered graphical views unless completeness has been demonstrated.
- Express alternative types in one `filter` statement joined with `or`. Separate filter statements are conjunctive and normally exclude the intended union.
- Keep table-oriented usages rendered `asElementTable`; the current pilot diagram command does not render them.
- Give every generated graphical view a unique native short name shaped as `diagram.<product>.<name>`.
- Register only usages rendered exactly once as `asTreeDiagram` or `asInterconnectionDiagram`.
- Do not hand-author a parallel component contract or duplicate normative behavior in the view.
- Use the repository's compact compartment style for a component contract overview. When
  relationships or flow are the concern, author a separate focused interconnection or behavior
  view rather than expanding every component action into a wide node-and-edge graph.

### 3. Validate and render

Run, in order:

```text
just model-check-formal
just model-diagrams
just model-check
```

Use `uv run python tools/sysml_diagrams.py render --backend pilot` only when the official parser inventory has already been refreshed. Generated `.puml` and `.svg` files live under `generated/reference/<product>/diagrams/` and must never be edited by hand.

### 4. Check completeness and presentation

- Treat `EXCEEDS THE LIMIT`, empty output, `ERROR:`, unsupported output, or invalid SVG as a failed projection. Never commit partial output.
- Compare visible nodes and relationships to the intended exposed root. Split an oversized view by concern or owned subtree; do not hide a missing primary contract to make the renderer pass.
- Visually inspect the SVG for readable labels, complete boundaries, clipping, and overlap.
- Run `just model-render` twice and require the second run to produce no generated diff when changing generator behavior or registrations.

### 5. Synchronize documentation

Use `.agents/skills/documentation-sync/SKILL.md` whenever view conventions, commands, generated locations, or supported rendering boundaries change. Generated component pages and indexes must be produced by `just model-render`, not edited directly.

## Completion report

State the specification sections consulted, the canonical view IDs changed, the renderer and completeness result, the generated artifacts affected, visual inspection result, and exact checks run. If a broad view remains unregistered, say which boundary prevented complete rendering and how it should be split.
