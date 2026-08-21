# Vellis v1 first-use initialization

Vellis v2 does not open a v1 data directory, migrate it in place, or import its
history. Export one complete JSON snapshot from a separate tagged v1 checkout, stop
that process, review the deterministic v2 conversion report, and initialize a different
empty owner-private v2 directory.

## Export without exposing v1 storage to v2

Keep the original v1 directory untouched. In a separate checkout and environment:

```sh
git clone --branch v1.0 --single-branch \
  https://github.com/volantlabs/vellis.git /tmp/vellis-v1
uv --directory /tmp/vellis-v1 sync --locked
uv --directory /tmp/vellis-v1 run vellis serve-mcp \
  --data-dir /absolute/path/to/old-v1-data
```

Connect an MCP client to that foreground v1 process, call its documented
`rtg_export_system_snapshot` tool with `{"summary": false}`, and save the returned
`result` object—the object containing `graph`, `schema`, `constraints`, and
`migration`—as one JSON file. Then stop v1. V2 consumes only that file; it never opens
the old directory.

Run `vellis setup --from-v1 SNAPSHOT --preview --report-out REPORT` to preview without a
destination. Publish only after reviewing the report, using the exact displayed source and report
SHA-256 values with `--confirm-source-digest` and `--confirm-report-digest`.

## What the report means

The machine report is complete and deterministic. Each disposition is one of:

- `preserved`: live identity or definition meaning reached the candidate;
- `converted`: UUID spelling, a whole property, or one exactly reducible local bound
  changed representation without being silent;
- `omitted`: non-live content, v1 history, or meaning v2 cannot exactly express did
  not enter the candidate;
- `blocking`: the candidate would lose identity, reference, type, property, or graph
  conformance and cannot be published.

Confirmation binds both the exact source bytes and exact machine report. A changed
source or report requires a new preview. Successful publication creates revision zero,
one initialization record, no imported predecessor transition, no draft, empty
activity, and the exact `v1-import-report.json` beside the database. The report is not
canonical state and is not included in SQLite backups.

The database and report become ready together through one atomic data-directory rename.
Before that boundary neither final artifact is visible. If the later directory-durability
flush fails, Vellis reports that both artifacts are published but durability is
unconfirmed; it does not claim that publication rolled back.

The snapshot, report, database, activity, and backups are plaintext at rest. Retain the
original snapshot and report under owner-private filesystem controls until the imported
graph has been reviewed and backed up.

## Review and remodel deliberately

After import, use ordinary v2 definition discovery and selected graph queries to inspect
converted text and request `system.legacyV1` only where the predecessor metadata is
needed. Do not interpret converted JSON text as a new nested property system:

- scalar properties hold atomic values;
- a nested or repeated identity-bearing concept becomes an associated-data object;
- a directed identity-bearing relationship becomes a link;
- different cardinality meaning usually deserves a distinct data or link type.

Any remodeling is a later owner-approved v2 definition/data draft. Initialization does
not silently invent those decisions.
