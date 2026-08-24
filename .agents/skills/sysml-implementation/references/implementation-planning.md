# Implementation Planning

## Contents

- [Choose a semantic slice](#choose-a-semantic-slice)
- [Separate authority from realization](#separate-authority-from-realization)
- [Design the software realization projection](#design-the-software-realization-projection)
- [Build the conformance matrix](#build-the-conformance-matrix)
- [Write an executable plan](#write-an-executable-plan)
- [Keep the plan current](#keep-the-plan-current)

## Choose a semantic slice

Plan the smallest end-to-end result that preserves a meaningful modeled distinction and can produce
decisive evidence. A good slice:

- serves one stakeholder or engineering outcome;
- includes the minimum domain, behavior, interaction, and quality semantics it depends on;
- makes its nominal and applicable alternate or failed behavior observable;
- reaches a real selected software, user, device, physical, or environmental boundary when that
  boundary is in scope;
- can be verified without first implementing unrelated capabilities;
- leaves explicitly deferred behavior and architecture untouched.

Do not implement the model declaration by declaration. A value definition, calculation, state
boundary, interaction, platform adapter, and scenario may belong to one slice when none is useful or
verifiable alone. Conversely, a large use case may need several slices if each preserves a coherent
intermediate outcome.

Sequence prerequisites by semantic dependency, not model file order or a familiar layered
architecture. Units and numerical types may precede calculations; identity and equality may precede
state changes; event semantics may precede concurrent handling; safety constraints may precede
actuation. Introduce a layer, service, repository, adapter, process, or device abstraction only when
the current realization needs that separation.

## Separate authority from realization

Maintain three visibly different sources of decisions:

1. **Model authority:** applicable system behavior, domain meaning, responsibility, requirements,
   satisfiers, analysis or verification intent, and intentionally selected boundaries.
2. **Project- or user-selected realization:** language, supported platform, existing generation,
   dependency policy, framework, compatibility baseline, hardware, or deployment constraints already
   chosen.
3. **Task realization decisions:** the smallest concrete choices needed to make this slice work.

For a consequential task decision, record in the task-local plan or handoff:

- model constraints it must preserve;
- project facts and measured scale that make the decision necessary;
- smallest plausible alternatives;
- selected option and why it is sufficient now;
- reversibility and consequence of changing it;
- whether it changes model meaning. Usually it should not.

Keep this reasoning in the task-local plan, realization, evidence, or configured handoff. Do not
assume that an accepted campaign record is an exhaustive decision log: a project may freeze its
plan-selected decision projection at approval. In that case, do not rewrite it for an ordinary
bounded choice made during execution. Replan only if the choice changes stakeholder-visible meaning
or an intentionally selected boundary. Do not create speculative interfaces or configuration to
preserve every alternative at runtime. An open engineering choice is not a product variability
requirement.

Check current primary documentation before selecting a dependency or coding against a framework,
language, device, or platform. Treat affordances as feasibility constraints. If the easiest
technology shape conflicts with the model, adapt or reject that shape; do not silently change system
semantics.

## Design the software realization projection

The projection applies where the model is silent about structure. There, SysML system decomposition
and software decomposition answer different questions: the model may keep one cohesive system or
part because it owns one lifecycle, state, invariant, timing, safety, failure, physical, or
interaction boundary, while a maintainable implementation realizes that responsibility through
several classes, modules, functions, processes, generated types, tasks, or device-facing components.
Conversely, several model elements may need one software mechanism when they sit inside one part.

Where the model does decompose, the map is a conformance obligation rather than an explanatory aid.
Subdivide freely inside a modeled boundary; never merge, re-cut, or reassign governed state across
two of them.

Use semantic neighborhoods as cohesion cues without promoting them to system parts. Introduce a
software boundary when current code benefits from one or more of:

- a cohesive invariant, calculation, transformation, or transition family;
- stable dependency direction;
- isolation of pure computation from state, effects, platform code, or physical interaction;
- focused testing, analysis, simulation, or fault injection;
- coordinated access to one modeled state, time, safety, or resource authority;
- an implementation change boundary demonstrated by the slice;
- selected runtime, hardware, generation, or deployment constraints.

A validation component, for example, may isolate conformance algorithms while owning no independent
authoritative state and remaining inside one modeled system responsibility. A numerical kernel may
isolate unit-sensitive calculations without becoming a modeled subsystem. A protocol adapter may
isolate an external encoding without creating a new stakeholder outcome.

Keep a task-local many-to-many realization map when the decomposition is consequential, and always
when the model decomposes the area being implemented:

| Software responsibility | Modeled semantic neighborhood | Reason for separation | Modeled boundary that remains unified |
| --- | --- | --- | --- |
| Class, module, function group, process, task, generated family, or device-facing component | Qualified elements and obligations | Cohesion, dependency, evidence, platform, or deployment reason | Identity, lifecycle, state, time, safety, failure, physical, or external boundary |

Where the model is silent, this map explains code design, does not become model authority, and need
not be committed by default. Where the model decomposes, it is required: each row must name the one
modeled part it stays inside, and a row spanning two modeled parts is an implementation defect. Do
not demand a modeled allocation for every code component. Add or revise model structure
only when the system intentionally acquires a distinct lifecycle, state owner, failure or safety
responsibility, external interaction, physical boundary, substitutability, or selected realization
architecture.

Private code interfaces, dependency injection, helper protocols, synchronization primitives,
buffers, and collaboration objects may be useful realization structure without corresponding SysML
ports or interfaces, unless the model declares that boundary; a declared port or interface must be
realized as one. Keep the rest in the realization unless the system intentionally exposes or selects
that interaction boundary.

## Build the conformance matrix

Turn the implementation frame into a compact task-local matrix:

| Model obligation and authority | Authority coverage | Remaining obligation | Implementation status | Planned realization | Decisive conformance evidence | Required non-effect or non-goal |
| --- | --- | --- | --- | --- | --- | --- |
| Qualified element plus concise claim | `full` or `partial` | Qualified remainder, or `none` for full coverage | Start `not evaluated`; update to `absent`, `partial`, `conforming`, or `conflicting` from evidence | Source or behavior to add or change | Test, analysis, simulation, inspection, demonstration, numerical reference, timing measurement, hardware evidence, or other discriminating observation | Preserved authority or excluded scope |

Use one row per independently reviewable obligation, not per declaration. One row may cite several
requirements or verification cases; one model element may contribute to several rows. Include exact
external names, cardinality, units, ranges, timing, ordering, completeness, or payload rules only
when the model intentionally selects them.

Authority coverage and implementation status answer different questions. Coverage says whether the
slice claims all or only part of the cited authority. Status says whether the in-scope obligation is
`not evaluated`, `absent`, `partial`, `conforming`, or `conflicting`. A bounded slice may be complete
while citing a requirement partially, but the plan and final handoff must name the remaining
obligations and must not claim the whole requirement satisfied or verification case passed.

Judge coverage against each cited accepted authority element's complete meaning, never only the task
prompt or the concise row text. A row with any remaining obligation is necessarily `partial`; a
`full` row necessarily records `none`. Keep the remainder in its own column. List unresolved model
gaps outside the conformance matrix as blockers rather than assigning coverage to prospective
authority.

Map every mandatory user instruction and model claim in scope. Also map negative commitments that a
plausible implementation could violate. Examples, only when modeled, include:

- no state or physical effect after a rejected or invalid command;
- no unsafe actuation after a failed interlock;
- no result outside the promised tolerance or time bound;
- no partial output when completeness is required;
- no unmodeled retry, fallback, disclosure, or cascade;
- no fracture of one modeled identity, lifecycle, state, safety, or failure authority across code
  components.

The matrix is a conformance aid, not generated authority. Refresh it from the model when the model
changes and remove it when the task no longer needs it.

## Write an executable plan

For each plan item state:

1. **Outcome:** runnable, analyzable, simulatable, inspectable, or demonstrable result produced.
2. **Authority:** implementation-frame rows and qualified model elements it closes.
3. **Source work:** narrow files, realization-map responsibilities, generated artifacts, or
   environment-facing elements expected to change.
4. **Evidence:** nominal, applicable alternate or failed, boundary, and counterexample checks.
5. **Exit condition:** what must be true before the next semantic dependency begins.

Include explicit steps for:

- project and dependency setup only when not already present;
- model-gap resolution before dependent code;
- generated-source regeneration and freshness checks when generation is selected;
- focused evidence during each slice and the project's broader gate at the end;
- documentation truth and implementation status;
- a full conformance and subtraction review after the last material correction.

Do not add placeholder packages, empty abstractions, future adapters, broad error taxonomies, or
configuration merely to make the plan look architecturally complete. Plan only work needed by the
current slice and evidence.

For a planning-only request, stop after delivering the validated matrix, realization decisions,
sequence, risks, and model gaps. Do not create source or mutate external systems.

## Keep the plan current

Before each material implementation step, check whether model authority, dependencies, environment,
and earlier assumptions still hold. If the model changes:

1. reread the affected semantic closure and change set;
2. update the implementation frame and conformance matrix;
3. reclassify divergence;
4. revise later plan items and evidence;
5. rerun completed checks whose meaning changed.

Never mark a plan item complete merely because a same-named class, function, task, interface, or test
exists. Completion requires the modeled distinction and its decisive evidence.
