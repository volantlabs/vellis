# Model Consumption

## Contents

- [Begin cold](#begin-cold)
- [Read by meaning](#read-by-meaning)
- [Use a semantic handoff](#use-a-semantic-handoff)
- [Build the implementation frame](#build-the-implementation-frame)
- [Apply the model-gap gate](#apply-the-model-gap-gate)

## Begin cold

Start from current project authority rather than predecessor code, familiar architecture, prior
conversation, or framework conventions. Record the active model baseline and current change set.
Read local safety and authority instructions, the declared model map or entry points, the complete
authored scope required by the project, affected dependencies, and applicable domain skills before
treating source structure as design evidence.

For a large model, follow its declared reading and dependency rules. If no rule requires a complete
read, establish the smallest complete transitive semantic closure for the requested slice and list
which model scope remains unread. Do not claim full-system implementation readiness from a partial
read.

Read existing implementation only after the first model pass. Then compare it with the model instead
of using it to explain what the model must have meant. Consult deleted or predecessor source only
when the task explicitly concerns compatibility, migration, recovery, or historical comparison.

## Read by meaning

Follow imports, qualified references, and contextual usages rather than filename or declaration
counts. Locate, as applicable:

1. stakeholder outcomes, actors, system boundary, environment, and contextual use cases;
2. domain occurrences, values, quantities, units, relationships, multiplicity, equality, invariants,
   and governed state;
3. behavior, calculations, constraints, modes, events, state effects, alternate outcomes,
   non-effects, and logical responsibility;
4. interactions, flows, messages, timing, concurrency, resources, safety, security, privacy,
   durability, recovery, and physical effects that the slice actually uses;
5. intentionally selected external operations, signals, inputs, outputs, interfaces, and
   compatibility constraints;
6. requirements, their subjects, and selected satisfiers where present;
7. analysis and verification cases and the evidence that discriminates intended from invalid
   behavior;
8. explicit realization selections, deferrals, and non-goals.

Do not demand a separate artifact at every level. Reuse the strongest model element that already
carries a claim. Use the reference skill to resolve consequential construct meaning and state both
the instance-level commitment and what it does not imply about code structure.

Pay particular attention to information that code-first reading tends to erase:

- one occurrence owned in one place and referenced elsewhere;
- a thing versus its description, measurement, observation, command, plan, or copy;
- absent, empty, unknown, not applicable, invalid, undecided, and present-null distinctions;
- ordered versus unordered collections, uniqueness, completeness, and semantic equality;
- units, dimensions, range, precision, tolerance, and uncertainty;
- mode-dependent behavior, invalid transitions, and required non-effects;
- ordering, timing, concurrency, rate, capacity, and resource boundaries;
- physical, safety, security, privacy, and environmental consequences;
- intentionally selected versus merely convenient external shapes;
- requirements whose decisive evidence spans several implementation components.

## Use a semantic handoff

Model work may provide an implementation-ready semantic handoff. Treat it as a compact navigation and
evidence aid, never as a second contract. A useful handoff names:

- active model baseline, change set, scope read, and semantic-slice scope;
- the stakeholder or engineering outcome and observable distinction;
- qualified model elements carrying each consequential obligation;
- full or partial authority coverage for each cited element and any remaining obligations;
- smallest nominal, alternate or failed, and plausible-invalid cases as applicable;
- identity, ownership, state, quantity, temporal, interaction, failure, or non-effect boundaries that
  matter;
- relevant requirements, satisfiers, analysis, and verification intent;
- selected external contracts and compatibility obligations;
- realization decisions intentionally left open and interpretations intentionally excluded;
- any unresolved model gap that blocks honest implementation.

Validate every cited element against the active model baseline and change set. Drop stale claims. If
the handoff omits a consequential path, read the model and add it to the task-local frame rather than
silently assuming a default. A handoff from another agent must be reproducible without that agent's
hidden context.

## Build the implementation frame

Create a task-local frame for the selected slice. Keep it in the active plan, working notes, or the
project's normal review record; do not commit a parallel specification by default. Use stable
qualified element names and source locations, with only enough summary to distinguish the
implementation obligation.

| Field | Record |
| --- | --- |
| Baseline | Active model identity, current change set, and scope read |
| Outcome | Stakeholder or engineering result this slice makes observable |
| Authority | Qualified model elements that carry the claim |
| Obligation | Concrete behavior, value, state, relationship, quality, or boundary code must preserve |
| Authority coverage | `full` when the slice covers every obligation of each cited element; otherwise `partial` |
| Remaining obligation | Obligations outside the slice for every partially covered element; `none` only for full coverage |
| Implementation status | `not evaluated`, `absent`, `partial`, `conforming`, or `conflicting` for this obligation |
| Decisive cases | Smallest applicable nominal, alternate or failed, and invalid examples |
| Conformance evidence | Test, analysis, simulation, inspection, demonstration, numerical reference, timing measurement, hardware evidence, or another observation capable of discriminating the claim |
| Deferrals | Realization choices and unrelated behavior the model leaves open |

Add identity, units, timing, safety, compatibility, or external-contract detail only when the slice
depends on it. Link one obligation to several model elements when they jointly carry the claim; do
not create artificial one-to-one trace rows.

Evaluate coverage against the complete meaning of each cited accepted authority element, not merely
the task prompt or the obligation restated in one row. `full` requires `Remaining obligation` to be
`none`. If any obligation carried by a cited element is outside the slice, coverage is `partial` and
the remainder must stay in its own field. Do not assign coverage to a prospective element or
unresolved model gap; report the readiness blocker separately.

Initialize each obligation's status as `not evaluated`, then update it after reading source and
existing evidence. This implementation status is separate from authority coverage and never
describes the model. A slice may finish with partial authority coverage when its bounded obligations
are conforming and the remainder is explicit, but it may not claim the entire requirement satisfied
or verification case passed.

## Apply the model-gap gate

Classify uncertainty before choosing code:

- **Language question:** the model form is unfamiliar or ambiguous to the reader. Use the reference
  skill; do not edit model or code from memory.
- **Model gap:** current authority cannot distinguish consequential stakeholder-visible behavior,
  system responsibility, identity, relationship, state, quantity, timing, interaction, failure,
  safety, security, compatibility, or evidence. Return to model work before implementation.
- **Realization decision:** the model intentionally permits several semantically equivalent
  implementations. Choose from current evidence in the implementation plan; do not add optional
  architecture to the model.
- **Feasibility consequence:** a demonstrated language, runtime, platform, dependency, hardware, or
  environmental limit changes stakeholder-visible behavior or an intentionally selected realization
  boundary. Route that changed system consequence through model review. If system meaning does not
  change, keep the matter as a realization decision.
- **Implementation defect:** current code or evidence contradicts sufficient model authority. Fix
  the implementation without weakening the model.
- **Stale baseline:** the handoff, code review, or evidence uses superseded model authority. Refresh
  the frame before deciding.

Treat a requested behavior outside both the accepted model and task scope as an out-of-scope
disposition, not a divergence class.

Before escalating to model work, ask whether the affected behavior or boundary is represented or
intentionally selected in current authority and whether the evidence shows a consequential
stakeholder-visible distinction the model cannot decide. Unselected storage, acknowledgement,
process, transport, framework, and deployment mechanics remain realization decisions unless a
demonstrated consequence crosses that gate.

A crash between durable commit and delivery of a success response is not by itself a model gap. It
becomes one only when accepted authority promises response delivery, retry reconciliation, idempotent
result semantics, or another observable distinction that the model cannot decide. Durability or
restart continuity alone governs committed state, not an unselected acknowledgement channel.

A model need not decide algorithms, functions, modules, classes, data structures, storage,
serialization, framework, user-interface structure, deployment, or generated-source layout before
implementation. It must decide enough system meaning to distinguish conforming behavior from
nonconforming behavior. Declare the slice ready only when that distinction and its decisive evidence
are clear.
