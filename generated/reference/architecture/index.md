# Architecture projections

Generated non-normative reading projection from the parser-backed SysML architecture graph; do not edit by hand.

These stable projections answer common architecture-review questions. On-demand views are
generated under `build/model-views/` with `just model-view`.

## Graphical views

| View | SVG | PlantUML |
|---|---|---|
| Model product and package layers | [diagram](package-layers.svg) | [source](package-layers.puml) |
| Bibliotek component dependency context | [diagram](bibliotek-component-context.svg) | [source](bibliotek-component-context.puml) |
| Vellis logical composition | [diagram](vellis-logical-composition.svg) | [source](vellis-logical-composition.puml) |
| Vellis runtime topology | [diagram](vellis-runtime-topology.svg) | [source](vellis-runtime-topology.puml) |

## Dense relationship views

- [Vellis operation ownership](operation-ownership.md)
- [Requirement and verification coverage](verification-coverage.md)
- [State-transfer boundary matrix](state-transfer-boundaries.md)

Model source digest: `941db7a140e95514ab99eea1667775fc044720c0d0f07b3890881cbae1a6973c`.
