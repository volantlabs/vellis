# RTG Time Room History Alpha Walkthrough

Validated locally on July 10, 2026 against a fresh `time_room_history` RTG root.

## Observed evidence

- Schema cutover: accepted, with 30 live definitions.
- Live records: 61 anchors, 61 associated data objects, and 217 pure-triple links.
- Claims: 20.
- Sources: 6.
- Reconstruction scenes: 6.
- Learning prompts: 12.
- Misconception guards: 5.
- Runtime packs: 1 append-only build record.
- Graph validation: accepted with zero findings.
- Snapshot: `snapshots/time-room-history-alpha.json`.
- Replay verification: `replay_verified` from `start_snapshot_path`.

The first schema attempt was correctly rejected because `state_as_of` anchors are invalid and
versioned fact records require `valid_from` and `valid_to` datetime fields. The corrected model uses
stable state-now anchors with state-as-of claim, scene, prompt, and misconception facts.

## Compilation evidence

`compile_runtime_pack.py` restored and validated the snapshot, traversed pack-inclusion and
grounding links, and emitted an offline JavaScript pack containing:

- graph-qualified identity for every compiled claim and source
- source keys for every claim
- grounding claim keys for every scene, prompt, and misconception
- runtime guardrails forbidding unsupported factual additions

The generated pack is consumed by Time Room from `file://`. Deterministic JavaScript chooses the
bounded context and immediately renders a sourced fallback. Ollama, when enabled, may rephrase that
packet but is not the source of canonical history.

## Limitations

- One figure does not prove cross-figure comparison or a portfolio-scale history graph.
- Source review is an alpha editorial pass, not a professional historical peer review.
- The local model prompt constrains additions but cannot mathematically prove that generated prose
  contains no unsupported implication; the deterministic fallback remains authoritative.
- The graph compiler currently reads the validated snapshot projection directly rather than a
  descriptor-declared federated canned query.
