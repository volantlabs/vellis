# Conformance and Feedback

## Contents

- [Build evidence](#build-evidence)
- [Review conformance](#review-conformance)
- [Classify divergence](#classify-divergence)
- [Return implementation feedback](#return-implementation-feedback)

## Build evidence

Use modeled verification and analysis cases as intent and discrimination criteria, not as a
requirement for one generated test per case. Select the smallest applicable evidence mix that proves
the current slice:

- value, identity, equality, relationship, and invariant tests;
- calculation tests sensitive to ranges, units, precision, tolerance, and uncertainty;
- state, mode, event, transition, and failure-non-effect tests;
- property or generative tests for broad semantic spaces;
- interaction and contract tests for intentionally selected inputs, outputs, flows, messages, and
  external names;
- timing, rate, ordering, concurrency, load, resource, and fault tests when those are modeled;
- safety, security, privacy, and misuse evidence when those are modeled;
- scenario tests that demonstrate a stakeholder outcome end to end;
- simulation, numerical comparison, model-in-the-loop, software-in-the-loop, hardware-in-the-loop,
  physical demonstration, or inspection where appropriate;
- restart, replay, durability, recovery, migration, and compatibility tests only when the slice
  claims them;
- static analysis, generated-source freshness, or other inspection where runtime behavior cannot
  discriminate the claim.

One evidence artifact may cover several compatible requirements. One requirement may need several
forms of evidence. Prefer behavioral and quantitative assertions over model prose, declaration
counts, source layout, or copied inventories. Assert an exact external inventory only when exactness
is itself selected model meaning.

Exercise, as applicable:

1. the smallest nominal instance and complete promised effect;
2. the smallest alternate, degraded, refused, or safely reported failure and every promised
   non-effect;
3. boundary values and meaningful interleavings;
4. the smallest plausible-invalid instance that would pass if ownership, identity, multiplicity,
   equality, units, control, state, timing, interaction, safety, or external-boundary meaning were
   wrong.

Do not invent rejection, transactions, persistence, networking, or hardware evidence for a system
that does not claim them. Keep malformed external representation and unexpected execution failure
distinct from completed domain outcomes only when the model makes that distinction. Measure
non-effects against the correct system authority.

## Review conformance

Perform these reviews separately after focused evidence passes.

### Plan conformance

Map every mandatory implementation-frame row and non-goal to code and evidence. Confirm that full or
partial authority coverage, remaining obligations, and implementation status are reported
separately. Find quiet omissions, scope growth, whole-requirement claims based on partial coverage,
and steps marked complete by name rather than behavior.

### Semantic preservation

Walk stimuli and inputs forward through applicable calculations, decisions, state, interactions, and
effects. Walk every output, state change, physical effect, and failure backward to the stakeholder
outcome and qualified model authority that permits it. Inspect nested owned values and independently
shared occurrences.

Check, where applicable:

- identity, kind, ownership, references, multiplicity, ordering, uniqueness, and semantic equality;
- missing, empty, null, unknown, invalid, inapplicable, and undecided distinctions;
- values, units, dimensions, ranges, precision, tolerances, uncertainty, and numerical stability;
- calculations, constraints, control flow, data flow, transformations, and invariants;
- modes, events, guards, transitions, nominal outcomes, alternate outcomes, and required non-effects;
- timing, rates, deadlines, latency, jitter, concurrency, interleavings, synchronization, and
  resource bounds;
- interaction direction, ports, interfaces, flows, messages, carried items, loss, and ordering;
- safety, security, privacy, physical, environmental, durability, recovery, and compatibility
  consequences;
- completeness, duplicates, bounds, and absence semantics for collections where behavior depends on
  them;
- modeled decomposition boundaries, with no code unit spanning two modeled parts and no governed
  state reassigned across them;
- exact selected external behavior without invented external surfaces or leaked internal structure.

### Evidence adequacy

Confirm each consequential claim has a test, analysis, simulation, inspection, or demonstration that
would fail for the nearest plausible wrong implementation. Parsing, type-checking, compilation, and
nominal-path success alone do not prove model conformance.

### Realization subtraction

Remove or defer code that exists only for a familiar architecture, future provider, unused extension
seam, duplicate authority, universal envelope, speculative configuration, or unselected operational
machinery. Preserve software structure that demonstrably improves current invariant enforcement,
dependency direction, evidence, platform isolation, change isolation, or implementation complexity
without inventing system meaning. Code that exists to realize a modeled boundary is never a
subtraction candidate; if that boundary is wrong, return model feedback instead of deleting code.

### Project truth

Run the project's narrow and broad checks. Confirm generated artifacts are fresh, public claims match
what is implemented and runnable, and user-owned or out-of-scope data remained outside the work.

After any material correction, repeat the complete review sequence. Finish after one full pass finds
no new material issue, even if it offers non-blocking observations. Require every material finding to
name a plausible consequence within accepted authority, selected boundaries, declared assumptions,
or ordinary malformed-input and recovery behavior. Stylistic preferences, alternative truthful
wording, speculative inputs outside those boundaries, duplicated evidence, and extra hardening with
no such consequence do not block completion or trigger another pass.

Batch all findings from a pass and sweep once for the same root cause before repeating it. Do not ask
a review to build novel mutants, expand fuzz spaces, invent attack models, or search speculative
inputs solely to prolong discovery. Use those techniques when verification or declared risk selects
them, or when one concrete material finding needs a bounded reproducer. After three consecutive
non-clean final passes, perform one explicit root-cause audit before another fresh pass; the count
does not excuse a material defect or create a new human approval gate.

## Classify divergence

Do not resolve every discrepancy in code. Classify it first:

| Divergence | Correct response |
| --- | --- |
| Language question | Resolve the construct through the reference skill before changing model or code |
| Implementation defect | Fix code or implementation evidence that contradicts sufficient current authority |
| Model gap | Return to model work when authority cannot distinguish consequential required system behavior |
| Realization decision | Decide in the implementation plan when system meaning remains equivalent and the model is silent about structure; where the model decomposes, structurally different implementations are not equivalent even when behaviorally equivalent, and divergence from a modeled decomposition is an implementation defect |
| Feasibility consequence | Present demonstrated evidence and review the changed stakeholder-visible outcome or selected boundary |
| Stale baseline | Refresh the frame, plan, code impact, and evidence before deciding |

Treat requested behavior outside both the accepted model and task scope as an out-of-scope
disposition rather than a divergence class. Before returning anything to model work, confirm that the
affected behavior or boundary is represented or intentionally selected and that the evidence shows a
consequential stakeholder-visible distinction the current model cannot decide. Unselected storage,
acknowledgement, process, transport, framework, and deployment mechanics remain realization
decisions unless a demonstrated consequence crosses that gate.

Never weaken a model obligation solely to make an existing implementation, framework, device, or
platform convenient. Never add code architecture to the model solely to justify source already
written.

## Return implementation feedback

Hand model work a compact, reproducible feedback record when needed:

- active model baseline and implemented slice;
- qualified authority exercised;
- evidence that passed and the nearest invalid case it excludes;
- realization decisions made without changing model meaning;
- demonstrated feasibility constraints;
- exact model ambiguity or contradiction, with differing system consequences;
- compatibility or selected-boundary consequence;
- recommended disposition: code fix, model review, stakeholder decision, or bounded deferral.

Raw failing cases, traces, measurements, simulations, and primary platform documentation are
stronger feedback than architecture preferences. A modeling agent should be able to reproduce the
issue from current project artifacts without hidden implementation-agent context.

Translate a genuine gap upward before proposing SysML changes:

1. Capture the smallest failing stimulus, input, state, environment, operation, and observed result in
   implementation terms.
2. Remove class, function, table, framework, device-driver, task, and exception names from the
   problem statement.
3. State the system-level distinction the model cannot decide: stakeholder outcome, identity,
   ownership, invariant, quantity, calculation, state transition, timing, concurrency,
   responsibility, interaction, safety, security, external contract, failure non-effect,
   compatibility, or evidence.
4. Identify differing observable consequences and current qualified model authority that is silent
   or contradictory.
5. Route the issue to the modeling skill and any applicable domain skill. Add meaning only at the
   strongest necessary authority level; do not add a subsystem because the software fix uses a class,
   process, lock, buffer, or adapter.
6. Refresh the implementation frame, realization map, code, and evidence from the accepted model
   change.

In the final implementation handoff, distinguish modeled, selected, implemented, verified, and
runnable. State what remains unimplemented even when the model is complete.
