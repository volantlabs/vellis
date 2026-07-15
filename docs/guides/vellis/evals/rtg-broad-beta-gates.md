# RTG broad-beta evaluation gates

Run three separate scenarios; no single scenario substitutes for another. Use only synthetic or
explicitly authorized data and temporary storage in automated tests.

## Repo-blind construction

Start an intentionally empty current Vellis data root. Design schema from prose, stage and cut it
over, ingest the full fixture, answer planning questions through queries, dry-run invalid writes,
submit an incompatible strict schema proposal, and persist/list/load a snapshot. Restart against
the same root and verify that automatic latest reconstruction produces the same validated managed
state. This scenario exercises advanced general-purpose RTG behavior, including runtime-backed
migration trace history.

## Ordinary onboarding

Use default setup and the installed Everyday Life ontology with no user facts. Capture incomplete
truthful statements without inventing dates, status, priority, contact details, or other optional
values. Review large initial writes with the human, then apply compact anchor records and use
returned generated IDs for follow-up links and reads. Do not expose migration, trace, or
reconstruction mechanics unless recovery or schema evolution actually requires them.

## Earlier-version snapshot transfer

Seed a synthetic earlier-version flat storage root with a custom schema whose `Person`, `Area`,
`Project`, `Task`, `Event`, `Note`, `Resource`, fact, and link type keys overlap Everyday Life keys
but use different UUIDs. Open that root only with its source Vellis version, validate it, and export
one full coordinated system snapshot. Initialize a separate empty current data root and restore the
snapshot through the current application interface. Do not copy, merge, import, or reconstruct the
source controller ledger.

Assert custom classification, exact schema/object/link counts, no ontology overlay, validation
success, representative queries, the committed restore as the destination's first authoritative
state-changing trace, and automatic reconstruction of equivalent managed state after a destination
restart.
Preserve the source root throughout the evaluation. Follow
[`snapshot-transfer.md`](../snapshot-transfer.md) for the complete operator procedure.

## Recorded metrics and gates

Record serialized `tools/list` and description bytes, MCP call and retry counts, request/response
bytes, generated IDs versus local refs, invented placeholder facts, reconciled graph/schema counts,
rejected migration trace visibility, terminal trace dispositions, runtime positions, reconstruction
counts/digests/limitations, restart outcome, and snapshot-transfer verification.

Broad beta is blocked unless snapshot-transferred custom graphs validate and reconstruct after a
destination restart, ordinary onboarding invents no facts, tool metadata is at most 16 KiB with
descriptions at most 5 KiB, compact beta-scale mutations are at least 60% smaller than full
responses, invalid writes remain non-polluting, rejected migration evidence is visible through
runtime traces, latest reconstruction explicitly proves or disproves managed-state equivalence,
and `just check` passes.
