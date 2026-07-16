# Generated Artifacts

Everything in this directory is derived and committed for review, navigation, and downstream use.
Do not edit these files directly.

- [`reference/bibliotek/`](reference/bibliotek/) contains human-readable Bibliotek component and
  dependency views plus normalized PlantUML and SVG diagrams generated from canonical SysML view
  usages. Diagram artifacts live in `reference/<product>/diagrams/` and are never edited directly.
- [`reference/vellis/`](reference/vellis/) contains human-readable Vellis composition, façade,
  use-case, verification, and realization views generated from the normative SysML model.
- [`reference/architecture/`](reference/architecture/) contains the stable cross-model architecture
  dashboard, including graphical topology, dense relationship matrices, and the generated
  state-transfer boundary matrix that distinguishes whole-state actions from ordinary batches.
- [`model/`](model/) contains machine-readable parser inventory, architecture graph, conformance
  objectives, and verification-evidence projections.

Run `just model-render` after changing the authored model under `../model/`. Review the resulting
changes with `just model-diff`; `just model-check` rejects missing or stale projections.
Use `just model-diagrams` when only the parser inventory and graphical projections need refreshing.
Use `just model-dashboard` for the stable architecture projections. On-demand projections and
changed-model review bundles are intentionally ignored under `../build/`.
