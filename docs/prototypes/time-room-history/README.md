# Time Room History

This prototype proves the frontier-authored, Vellis-governed, deterministic-runtime pattern with
one bounded historical figure: Ada Lovelace.

The source graph owns reviewed claims, authoritative source locators, entities, reconstruction
boundaries, learning prompts, misconception corrections, and one append-only runtime-pack build.
Time Room receives only a generated JavaScript projection and remains fully playable from
`file://` without Vellis, a server, or a language model.

## Reviewable inputs

- `data/time-room-history-schema-v0.json`: 8 anchor types, 8 fact types, and 14 pure-triple links.
- `data/ada-lovelace-live-records.json`: 61 anchors and 217 links, including 20 claims supported by
  six source records.
- `data/queries/`: bounded inventory queries used by the loader.

`build_prototype_data.py` deterministically regenerates those inspectable fixtures. The content is
an alpha authoring seed, not a claim that frontier-model output validates itself; strict Vellis
schema and graph validation remain required.

## Load and verify the graph

```sh
uv run python docs/prototypes/time-room-history/load_monograph.py --reset
```

The loader stages and cuts over schema, dry-runs the seed, applies it strictly, runs the inventory
queries, persists `snapshots/time-room-history-alpha.json`, and verifies ledger replay.

## Compile the offline artifact

```sh
uv run python docs/prototypes/time-room-history/compile_runtime_pack.py \
  --output "/Users/eddieaustin/Documents/Austin Vibe Codes/time-room/compiled-packs/ada-runtime-pack.js"
```

The compiler restores and validates the persisted Vellis snapshot, follows the pack-inclusion and
grounding links, refuses claims without sources or scenes/prompts without grounding claims, and
emits graph-qualified identities plus source labels into the static pack.

## Boundary

- Vellis is the governed authoring and compilation environment.
- Time Room JavaScript deterministically selects claims, scenes, prompts, and citations.
- A small local model may rephrase the selected packet but is told to add no new facts.
- The canned compiled response appears immediately and remains the offline fallback.
- Ordinary play never mutates the source graph.
