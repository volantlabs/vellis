# Generated Artifacts

Everything in this directory is derived and committed for review, navigation, and downstream use.
Do not edit these files directly.

- [`reference/bibliotek/`](reference/bibliotek/) contains human-readable Bibliotek component and
  dependency views generated from the normative SysML model.
- [`reference/vellis/`](reference/vellis/) contains human-readable Vellis composition, façade,
  use-case, verification, and realization views generated from the normative SysML model.
- [`model/`](model/) contains machine-readable parser inventory, conformance objectives, and
  verification-evidence projections.

Run `just model-render` after changing the authored model under `../model/`. Review the resulting
changes with `just model-diff`; `just model-check` rejects missing or stale projections.
