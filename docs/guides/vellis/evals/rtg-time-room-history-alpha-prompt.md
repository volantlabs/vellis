# RTG Time Room History Alpha Prompt

Recreate the `time_room_history` alpha graph in a fresh, explicitly targeted Vellis RTG root.
The goal is to compile frontier-authored, human-reviewable historical material into a bounded offline Time Room pack,
not to make a browser chat depend on a live graph service.

## Review first

- `docs/prototypes/time-room-history/data/time-room-history-schema-v0.json`
- `docs/prototypes/time-room-history/data/ada-lovelace-live-records.json`
- all query fixtures under `docs/prototypes/time-room-history/data/queries/`

The fixtures are reviewable inputs, not opaque installation payloads. The current alpha contains
paraphrased claims and source locators from the Science Museum, Computer History Museum, Project
Gutenberg's 1843 text, and the Bodleian archival finding aid.

## Required sequence

1. Validate the fresh graph and inspect system state.
2. Stage `time-room-history-schema-v0` with strict validation.
3. Cut over the migration.
4. Dry-run the Ada anchor records and pure-triple links.
5. Apply them only when the dry-run is accepted.
6. Validate the populated graph and run all seven inventory queries.
7. Persist `snapshots/time-room-history-alpha.json`.
8. Verify replay from that snapshot.
9. Run `compile_runtime_pack.py` and inspect the generated Time Room artifact.

## Expected shape

- 8 live anchor types, 8 live fact types, and 14 live link types.
- 61 anchors, 61 associated fact records, and 217 links.
- 20 historical claims and 6 source records.
- 6 reconstruction scenes, 12 learning prompts, and 5 misconception guards.
- Every claim has a `claim_supported_by` link.
- Every scene, prompt, and misconception has a grounding or correction claim.
- No graph-validation findings and successful replay verification.

Do not silently broaden this alpha to other figures. Do not describe reconstruction text as a
quotation, diary entry, or recovered memory. Do not describe the generated pack as proof that a
frontier model's historical output is self-validating.
