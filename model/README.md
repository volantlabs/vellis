# Model

This directory contains the authored textual SysML v2 design products for the repository.

- `foundation/` is the reusable software-component modeling foundation.
- `bibliotek/` is the reusable component library and its shared values and views.
- `vellis/` is the application composition, façade, use cases, views, and realizations.
- `config/` pins the allowed language profile, formal libraries, and validator runtime.
- `migration/` tracks temporary shadow-to-canonical cutover gates and identifier migration data.

Foundation and Bibliotek are independently packageable `library package` products. Vellis is an
application package that consumes Bibliotek. Bibliotek must never import Vellis. KPARs are derived
distribution artifacts written to `build/model/packages/`; validator downloads and formal source
artifacts live under the ignored `.cache/sysml/` tree.

The modeling-pattern fixture lives under `tests/model/fixtures/`. It is validated against the
packaged Foundation but is not part of any authored product, formal product index, or KPAR.

Run `just model-render` to refresh human references under `docs/reference/` and machine projections
under `generated/model/`. Do not edit those projections by hand. Run `just model-check` to validate
the packaged products, repository profile, architecture, realizations, and generated artifacts.

The model remains in shadow status while the human gates in `migration/cutover-status.json` remain
open. New design is nevertheless authored here; the former Markdown specifications are frozen
migration evidence, not an authoring surface.
