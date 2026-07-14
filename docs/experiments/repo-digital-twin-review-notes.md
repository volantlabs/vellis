# Repo Digital Twin Review Notes

Status: active evaluation record. This is non-normative operational commentary; textual SysML,
its realization bindings, repository files, and tests remain authoritative.

## Current experiment

The repo twin tests whether a deterministic local RTG projection can reduce repeated source-tree
reconstruction and catch model/realization/evidence drift that ordinary unit tests do not expose.
It is ignored under `.data/repo-twin`, disposable, and may never write back into the authored model
or implementation.

The predecessor experiment indexed the former hand-authored Markdown component-contract tree. During SysML
harmonization on 2026-07-14, the importer was changed to consume the current official
parser-backed inventory plus the authored component models and Python realization bindings. A
missing or stale formal inventory now stops synchronization before changing an existing twin.
This deliberately removes the old Markdown authority instead of recreating it.

The gate runs in this order: model validation and projection freshness, evidence-wrapped tests,
then repo-twin synchronization and drift checking. `changed_contract` evidence is keyed to the
modeled public-contract blocks and realized Python root, not generated Markdown.

## Evaluation trigger

The original phase-one experiment began on 2026-07-07. Evaluate it on or around 2026-07-28. Keep
the gate only if it has either caught at least one real drift issue or demonstrably replaced
meaningful source re-reading. Continuing after a failed criterion requires a new human decision.

## Evidence log

Real drift catches:

- 2026-07-08: `just graph-verify` found the declared but missing RTG discovery realization root;
  the component was subsequently implemented and verified.

Query-instead-of-re-reading uses:

- 2026-07-08: component inventory and implementation/evidence coverage.
- 2026-07-10: confirmation that no component yet owned graph-qualified citation resolution.
- 2026-07-10: bridge blast-radius inspection before isolating bridge traversal.
- 2026-07-10: federated-synthesis blast-radius inspection before separating semantic synthesis.
- 2026-07-14: `graph-query components` verified all 20 SysML component authorities, Python
  realization roots, and populated test suites with no orphan traversal through the source tree.

Add future entries as dated one-line observations with the command and what source reconstruction
or drift it replaced.

## Standing anomalies and recovery

- Evidence is local and not reconstructable from repository files. Preserve `.data/repo-twin`
  snapshots and ledgers before destructive recovery when its history matters.
- Reverting a modeled contract or implementation after a test run still changes the current hash;
  refresh evidence with a wrapped test run after reviewing the revert.
- A failing wrapped test is recorded as failed evidence and does not clear a drift warning.
- Exact timestamp ties are resolved deterministically by record UUID; new evidence uses
  microsecond timestamps.

Stress a change with: clean sync/check, modeled-contract edit plus refreshed model inventory,
implementation edit, orphan realization root, stale formal inventory, idempotent second sync,
and rebuild from a preserved or disposable storage root. The stale-inventory case must fail without
mutating the prior snapshot.
