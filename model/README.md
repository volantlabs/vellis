# Model

This directory contains the authored textual SysML v2 design products for the repository.

- `foundation/` is the reusable software-component modeling foundation.
- `bibliotek/` is the reusable component library and its shared values and views.
- `vellis/` is the application composition, façade, use cases, views, and realizations.
- `config/` pins the allowed language profile, formal libraries, and validator runtime.

Foundation and Bibliotek are independently packageable `library package` products. Vellis is an
application package that consumes Bibliotek. Bibliotek must never import Vellis. KPARs are derived
distribution artifacts written to `build/model/packages/`; validator downloads and formal source
artifacts live under the ignored `.cache/sysml/` tree.

The modeling-pattern fixture lives under `tests/model/fixtures/`. It is validated against the
packaged Foundation but is not part of any authored product, formal product index, or KPAR.

Run `just model-render` to refresh human references under `generated/reference/` and machine
projections under `generated/model/`. Do not edit those projections by hand. Run `just model-check` to validate
the packaged products, repository profile, architecture, realizations, and generated artifacts.

Vellis application content belongs under `model/vellis/`. `EverydayLifeOntology.sysml` is the
authored starter schema; `model-render` derives the packaged
`apps/rtg_knowledge_graph/resources/everyday_life_schema.json` bootstrap bundle. That bundle
contains schema and migration material only—not user facts or a hand-authored snapshot.

The normal edit loop is `just model-render`, review with `just model-diff`, then
`just model-check`. Run `just check` before handing off the repository change. Detailed artifact,
command, authoring, review, and troubleshooting guidance lives in
[`docs/engineering/sysml-modeling.md`](../docs/engineering/sysml-modeling.md).

The model is the normative design authority. Git history retains superseded transition material;
the current tree contains only active model, configuration, generated projection, and verification
artifacts.
