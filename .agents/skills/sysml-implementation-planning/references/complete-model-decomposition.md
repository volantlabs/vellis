# Complete-Model Decomposition

## Establish the authority universe

Read the complete accepted scope before creating slices. Collect only elements that carry or qualify
implementation meaning, including as applicable:

1. stakeholder outcomes, actors, system boundary, environment, use cases, and decisive scenarios;
2. domain identity, ownership, reference, multiplicity, equality, values, quantities, units,
   relationships, invariants, governed state, and absence semantics;
3. calculations, constraints, control, data flow, actions, modes, events, transitions, alternate
   outcomes, failure non-effects, and logical responsibility;
4. selected external interactions, names, inputs, outputs, interfaces, messages, physical effects,
   timing, concurrency, durability, recovery, safety, security, privacy, resources, and compatibility;
5. requirements, their subjects, selected satisfiers, analysis, and verification intent;
6. explicit realization selections, deferrals, and non-goals that constrain implementation.

Do not inventory every declaration. One implementation obligation may be jointly carried by several
elements, and one element may contribute to several obligations. Keep qualified references so every
claim can be reread from current authority.

## Form the obligation graph

Use independently reviewable system commitments as nodes. Add an edge when one commitment:

- produces identity, values, state, definitions, or configuration another consumes;
- establishes an invariant or validation boundary another assumes;
- must precede, guard, authorize, or atomically coincide with another effect;
- shares one lifecycle, state, transaction, timing, safety, failure, physical, or external owner;
- supplies a selected interaction needed to observe another outcome;
- supplies replay, restart, recovery, compatibility, or historical meaning another verifies;
- supplies evidence whose discrimination requires several behaviors to coexist.

Do not add a dependency merely because declarations, likely files, or familiar layers appear in an
order. Mark uncertain edges and resolve them from authority before using them to sequence work.

Collapse strongly connected or inseparable nodes into one semantic neighborhood when splitting them
would create duplicate authority, partial transaction meaning, contradictory outputs, or evidence
that cannot distinguish conformance. Keep independently valuable outcomes separate even if one code
component may later realize both.

## Cut semantic slices

Each slice must:

- make one modeled stakeholder or engineering outcome observable;
- include the minimum authority and prerequisites needed to preserve that outcome end to end;
- contain nominal and applicable alternate, failed, boundary, or counterexample evidence;
- reach a selected software, user, device, physical, or environmental boundary when one exists;
- preserve every unified identity, state, transaction, timing, safety, or recovery boundary it uses;
- leave unrelated and intentionally deferred meaning outside the slice.

Use `semantic` for an independently valuable behavior, `integration` only for modeled meaning that
crosses prior slices, and `closure` for evidence or runnable-system obligations that genuinely require
the assembled system. Do not create generic foundation, architecture, data, service, user-interface,
or testing layers. Put necessary setup inside the earliest semantic slice that proves it useful.

## Assign coverage and order

For every slice-to-authority contribution record:

- `full` only when the slice closes every obligation carried by that cited element;
- `partial` when the slice is not self-sufficient, with every other stable slice ID whose combined
  contribution closes the aggregate remainder, whether that slice executes earlier or later;
- the existing implementation status separately from authority coverage;
- the verification or analysis references capable of discriminating the contribution.

Require every implementation-bearing authority reference to have full aggregate planned coverage.
Order slices first by semantic dependency. Among independent ready slices, place earlier the slice
that retires the most consequential uncertainty or feasibility risk with the least irreversible
realization. Give each slice a stable identifier and unique integer order. Initial campaigns use a
single writer even when the graph contains independent branches.
