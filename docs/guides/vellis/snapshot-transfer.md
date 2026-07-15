# Transfer data from an earlier Vellis installation

Vellis does not migrate an earlier controller ledger into the component runtime. Transfer the
managed RTG state as one coordinated system snapshot and let the destination runtime record the
snapshot restore as the beginning of its own authoritative chronology.

This is an operational transfer procedure, not a compatibility contract between runtime-ledger
formats.

## Transfer procedure

1. Keep the source data root unchanged and run the Vellis version that already knows how to open
   it.
2. Call `rtg_validate_graph` and resolve any invalid live state before export.
3. Call `rtg_export_system_snapshot` with `summary: false` and save the snapshot object nested in
   the successful MCP response's `result` field as JSON. Do not save the outer `{ok, result}`
   response envelope as the snapshot. Record the source validation result and snapshot summary
   alongside it.
4. Start the current Vellis version with a new data root and starter-schema installation disabled
   (`--empty` on the CLI). Do not point it at the source JSON root, SQL database, or runtime
   database, and do not copy either ledger. The destination must have no state-changing runtime
   effects before restoration.
5. Call `rtg_restore_from_snapshot` once with that saved `result` snapshot object. The new runtime
   validates the coordinated graph, schema, constraints, and migration state before making it
   visible and records the committed restore in its own ledger.
6. Call `rtg_validate_graph`, `rtg_get_system_state`, and `rtg_export_system_snapshot`. Compare
   validation, object counts, migration counts, and the coordinated state digest or snapshot
   summary with the source evidence.
7. Keep the source data root and exported snapshot until the destination has restarted and
   reconstructed the same validated state from its runtime history.

If the source installation cannot start under current code, use a checkout or installed package of
the source version only long enough to validate and export the snapshot. Do not teach the current
runtime to interpret the earlier ledger.

## Agent rule

When asked to move data from an earlier Vellis installation:

- inspect and show the source and destination paths before changing anything;
- preserve the source data root;
- obtain or create a full coordinated snapshot with the source version;
- initialize a separate empty destination;
- keep starter-schema installation disabled until the transferred snapshot is restored and
  verified;
- restore through the current Vellis application interface so the runtime records the import;
- verify destination state and restart reconstruction before suggesting retirement of the source;
- never copy, merge, replay, or import the earlier controller ledger into the new runtime ledger.

Snapshot transfer preserves managed RTG state. It intentionally does not preserve the old
application's traffic chronology, queued audit failures, process identity, or runtime positions.
