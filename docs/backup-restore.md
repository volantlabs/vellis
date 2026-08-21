# Backup and restore

Create an audited online SQLite backup while Vellis may be serving requests:

```sh
mkdir -p /absolute/path/to/backups
vellis backup \
  --data-dir /absolute/path/to/vellis-data \
  --out /absolute/path/to/backups/vellis-2026-08-21.sqlite3
```

The output parent must already exist, and Vellis refuses to replace an existing output file. It
validates that the source has a supported Vellis database and schema, copies it through SQLite's
online backup API, completely audits the copied temporary snapshot, and then publishes an
owner-private file atomically. It appends no source activity. The database copy includes its lineage,
draft, activity, settings, and retained validation backing. Adjacent files are not backup content:
the HTTP token, v1 import report, and SQLite WAL/SHM sidecars are not copied. Protect the backup as
plaintext personal context.

Initialize a separate, empty data directory from that backup with:

```sh
vellis setup \
  --from-backup /absolute/path/to/backups/vellis-2026-08-21.sqlite3 \
  --data-dir /absolute/path/to/restored-vellis-data \
  --no-connect
```

This preserves the copied lineage rather than creating a new revision. Vellis refuses a nonempty
destination and never overwrites an existing database. Client connection, if wanted, is a separate
later `vellis connect` operation.

Restore historical meaning inside the current lineage by revision or canonical time:

```sh
vellis restore --data-dir /absolute/path/to/vellis-data --revision 42
vellis restore --data-dir /absolute/path/to/vellis-data --time '2026-08-21T18:30:00Z'
```

The command asks for confirmation; use `--yes` only when that exact selection has already been
approved. A time selects the greatest canonical revision recorded at or before it. Restore requires
no draft, validates the selected state, and publishes the historical definitions and graph as one
new canonical revision. It does not replace the database file or rewrite earlier history. If the
selected meaning already equals current state, restore is accepted without a new revision.

Run `vellis audit --data-dir /absolute/path/to/vellis-data` after copying backup files through any
external storage or transfer system and before relying on the copy.
