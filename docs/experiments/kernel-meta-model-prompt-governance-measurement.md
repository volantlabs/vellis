# Kernel Meta-Model Prompt-Governance Measurement

This artifact closes the measurement requirement in the kernel meta-model program and provides an
input to WP-2. It measures only standing, KM-specific normative prose returned by
`rtg_get_usage_guide`; machine-readable tool shapes, domain catalog entries, and task-specific
recreate prompts are not standing prompt-governance.

## Method

- **Before:** commit `dca948d`, immediately before KM-1.
- **After:** commit `ad09922`, after KM-1 through KM-6.
- Inspect generic `rtg_get_usage_guide` topics and the source changes to their returned prose.
- For each KM rule, count one standing rule only if the guide tells an agent to preserve that
  invariant through behavior the kernel does not enforce.
- Do not count required payload fields such as `time_shape`, `link_kind`, or `mode`; those are
  machine-checked interface shape, not behavioral promises delegated to the prompt.

## Result

| Kernel rule | Before standing rules | After standing rules | After enforcement |
| --- | ---: | ---: | --- |
| KM-1 link structural identity and property rejection | 0 | 0 | graph and validation invariants |
| KM-2 required node time-shape and event immutability | 0 | 0 | schema and validation invariants |
| KM-3 schema-owned identity criteria and merge candidates | 0 | 0 | schema and validation invariants |
| KM-4 link-kind lifecycle policy | 0 | 0 | schema and validation invariants |
| KM-5 reviewed schema-evolution operations | 0 | 0 | migration and controller preconditions |
| KM-6 explicit write mode and optimistic replace | 0 | 0 | MCP decoding, validation, and controller concurrency |
| **Total** | **0** | **0** | **6 of 6 enforced** |

KM-specific standing rules deleted from usage-guide prose: **0**.

## Interpretation

The implementation successfully promoted all six behaviors into machine-enforced contracts, but
this repository's pre-KM usage guide did not carry equivalent safety rules in prose. The proposed
before/after measure therefore shows no prompt reduction and cannot support the stronger
order-of-magnitude claim by itself; the baseline was under-governed rather than equivalently safe.

WP-2 should compare the governed RTG against an equivalent ungoverned control whose safety
bootloader explicitly carries these six rules, while holding task success and error rates constant.
That controlled comparison—not this repository-history comparison—is the valid test of the
standing prompt-governance claim.
