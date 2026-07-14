# RTG broad-beta evaluation gates

Run three separate scenarios; no single scenario substitutes for another. Use only synthetic or
explicitly authorized data and temporary storage in automated tests.

## Repo-blind construction

Start an intentionally empty app with manual recovery. Design schema from prose, stage and cut it
over, ingest the full fixture, answer planning questions through queries, dry-run invalid writes,
submit an incompatible strict schema proposal, persist/list/load a snapshot, and verify replay.
This scenario exercises advanced general-purpose RTG behavior, including rejected proposal history.

## Ordinary onboarding

Use default setup and the installed Everyday Life ontology with no user facts. Capture incomplete
truthful statements without inventing dates, status, priority, contact details, or other optional
values. Review large initial writes with the human, then apply compact anchor records and use
returned generated IDs for follow-up links and reads. Do not expose migration or replay mechanics
unless recovery or schema evolution actually requires them.

## Existing private-beta upgrade

Seed a synthetic legacy flat storage root and exact SQLite path with a custom schema whose `Person`,
`Area`, `Project`, `Task`, `Event`, `Note`, `Resource`, fact, and link type keys overlap Everyday Life
keys but use different UUIDs. Reconstruct it from its ledger, then exercise setup, doctor, ordinary
startup, `--empty`, manual recovery, stdio, and localhost HTTP. Assert custom classification, exact
schema/object/link counts, no ontology overlay, validation success, representative queries, and
exact replay-to-live domain-state equivalence. Separately prove deterministic Everyday Life UUID
misuse and partial installation fail without mutation.

## Recorded metrics and gates

Record serialized `tools/list` and description bytes, MCP call and retry counts, request/response
bytes, generated IDs versus local refs, invented placeholder facts, reconciled graph/schema counts,
rejected migration-history visibility, replay accounting/digests/equivalence, and reconnect outcome.

Broad beta is blocked unless legacy custom graphs reconnect, ordinary onboarding invents no facts,
tool metadata is at most 16 KiB with descriptions at most 5 KiB, compact beta-scale mutations are at
least 60% smaller than full responses, invalid writes remain non-polluting, rejected migration
evidence is visible, replay explicitly proves or disproves exact live equivalence, and `just check`
passes.
