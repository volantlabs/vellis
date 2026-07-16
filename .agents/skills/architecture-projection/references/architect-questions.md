# Architectural questions and projection choices

Use the live preset registry for exact parameters:

```text
uv run python tools/model_views.py presets --json
uv run python tools/model_views.py explain <preset>
```

| Question | Preset | Useful parameters |
|---|---|---|
| What does this component promise? | `contract` | Increase `depth` only when owned public members are missing. |
| What surrounds this element? | `context` | `direction=both`, normally one hop. |
| What might a change affect? | `impact` | Start inbound at depth one; expand to two only when necessary. |
| How is this system assembled? | `composition` | Keep parts, typing, bindings, and allocations in scope. |
| What runs and connects at runtime? | `runtime-topology` | Target a concrete realization rather than a logical contract. |
| Where does an operation go? | `operation` | Include performed actions, dependencies, flows, and successions. |
| How does modeled behavior proceed? | `action-flow` | Do not use when the model has no flow or succession facts. |
| Which obligations cover this subject? | `requirements` | Review satisfaction and verification separately. |
| Where are coverage gaps? | `verification-coverage` | Prefer Markdown because the relationship set is dense. |
| Are package dependencies correctly layered? | `package-layers` | Model-wide; no target is needed. |

## Failure interpretation

- **Unknown or ambiguous target:** list targets and use the stable or qualified identity.
- **Unsupported target kind:** select a preset whose architectural concern accepts that kind.
- **Node limit exceeded:** reduce depth, direction, or relationship kinds. Output is never partial.
- **No relationships:** confirm the chosen fact is modeled; do not manufacture an edge for a nicer
  picture.
- **Missing or stale architecture graph:** run `just model-render` before an on-demand query.
- **Renderer failure:** keep the request and manifest as evidence, then diagnose with
  `sysml-view-authoring`; do not edit generated PlantUML or SVG.

## Promotion rule

Promote only recurring stakeholder concerns. A promotion candidate supplies exposure identity and
a supported rendering, but canonical authoring still requires targeted exposure, valid filters,
formal validation, completeness review, and visual inspection.
