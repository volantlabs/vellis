# Modeling Quality

## Contents

- [Meaning, identity, and state](#meaning-identity-and-state)
- [Behavior, interaction, and time](#behavior-interaction-and-time)
- [Structure and responsibility](#structure-and-responsibility)
- [Definitions and expressions](#definitions-and-expressions)
- [Requirements and evidence](#requirements-and-evidence)
- [Implementation-facing quality](#implementation-facing-quality)
- [Reasoning demonstrations](#reasoning-demonstrations)

## Meaning, identity, and state

- Use an owned feature when the subject governs an occurrence or value as part of itself.
- Use a derived feature when other modeled facts determine the value.
- When multiple derived values are jointly determined by one behavior occurrence, state transition,
  snapshot, revision, or other authority, first check whether existing owning behavior or structure
  already preserves that joint context. If not, derive one structured projection or bind the
  projections to their common authority; do not invent a wrapper solely to group outputs. The
  `derived` modifier alone does not establish the relationship. Preserve independently progressing
  state while naming the authority and equality or compatibility rule that makes its values
  applicable. Exercise a mixed-source counterexample that combines otherwise valid values.
- Use a reference feature for an independently existing occurrence that the subject does not own.
- Audit repeated appearances of the same conceptual occurrence. Reference one independently existing
  occurrence unless a distinct copy, sample, estimate, plan, or observation has its own intended
  identity and semantics.
- Reify a relationship only when the relationship itself needs identity, attributes, direction,
  lifecycle, behavior, or independent reference.
- Prefer identity already meaningful in the domain before introducing surrogate identifiers. Do not
  make every modeled thing addressable merely because source code or persistence often does.
- Derive a value from its authority when storing it separately would permit contradiction. Avoid
  duplicate flags, statuses, counts, totals, and classifications that another relationship or
  calculation already determines.
- Distinguish a thing from a description, measurement, command, plan, observation, or copy of that
  thing. Similar payloads do not establish shared identity.
- Distinguish absent, empty, unknown, not applicable, invalid, and not yet decided. Encode each only
  when it is system meaning; do not store modeling uncertainty as optionality or status.
- Define collection semantics when behavior depends on them: multiplicity, ordering, uniqueness,
  equality, duplicate treatment, completeness, and the meaning of an absent member.
- Keep storage keys, memory addresses, rows, documents, event records, serialized associations, and
  wire encodings out of domain meaning unless the system intentionally exposes them.
- Ensure each governed state has behavior that creates, observes, changes, or retires it, together
  with failure rules and discriminating evidence.
- Test ownership with instances: may the same occurrence appear in two contexts, may it outlive
  either, and which subject governs its invariants? Use reference semantics when the answers reveal
  independent existence.
- Review nested composites recursively. A container may imply ownership or complete-state copying
  through a nested payload even when its top-level declaration appears referential.
- Treat quantity kind, unit, dimension, tolerance, precision, uncertainty, and conservation as
  separate commitments. Add only those needed to decide system behavior.

## Behavior, interaction, and time

- Give each contextual use case a stakeholder-valued objective, nominal outcome, applicable alternate
  or failure outcomes, effects and non-effects, and evidence.
- Refine behavior only when actions, states, calculations, constraints, flows, or interactions add
  ordering, transformation, mode, event, timing, concurrency, state, failure, or evidence meaning.
- Connect inputs, outputs, matter, energy, data, and control when those connections justify
  decomposition. Labels and succession alone do not explain a transformation.
- Multiplicity states permitted occurrence count; it does not encode a guard, trigger, scheduling
  rule, or acceptance decision.
- Remove a behavior tree whose stages exchange no meaningful information or control and exclude no
  invalid behavior. Keep the behavior black-box until a meaningful refinement is known.
- Use state behavior for modes or conditions that affect behavior over time. A value having several
  allowed literals does not by itself require a state machine.
- State the events, guards, transitions, entry or exit effects, and invalid transitions needed by the
  claim. Do not invent a complete lifecycle where only one state-dependent distinction matters.
- Model concurrency, deadlines, rates, latency, jitter, ordering, loss, retry, or synchronization
  only when they change an outcome, safety property, resource obligation, or selected boundary.
- Add ports, interfaces, connections, flows, or messages only for intentional interaction meaning.
  Define direction, carried item or value, cardinality, and temporal or reliability semantics only
  to the precision required by the current behavior.
- Keep an actor protocol-neutral unless protocol participation is inherent to its modeled role.
- Treat a platform, framework, device, or protocol affordance as feasibility evidence. It becomes
  system authority only when its consequence is observable or intentionally selected.
- Do not convert human judgment, environmental uncertainty, or external responsibility into an
  automatic system guard unless the system has the information and authority to evaluate it.
- Qualify non-effects by subject. Behavior can preserve governed product state while changing
  diagnostics, telemetry, cache state, physical energy, or another authority when the model permits
  it.

## Structure and responsibility

- Add a logical part for independently meaningful lifecycle, identity, governed state, invariant,
  failure, safety, security, resource, external-interaction, substitution, physical, or selected
  realization responsibility, or for an internal boundary the project selects as binding and states
  a prohibition for.
- Use performed behavior when a part carries out referenced behavior during its lifetime.
- Use allocations only to relate genuinely distinct source and target responsibility structures.
  Do not allocate behavior back to the element already performing it.
- A code module, class, function family, process, service, table, pipeline stage, or test fixture is
  not evidence of a system part by discovery alone; it becomes one when the project selects it as
  binding, and the model then states what that selection forbids.
- A system part does not prescribe one code component: one modeled responsibility may be realized by
  several software components, and one software mechanism may support several modeled elements
  within one modeled part, never across two.
- Model an interface or port where the project means to fix what one part may assume about another.
  A private code call is not an interface by itself; a boundary the project intends to hold across
  independent implementation work is, and code may not reach around one the model declares.
- Keep packages as intentional namespaces or viewpoints, not automatic architecture layers; a
  package is a selected architectural boundary only where the project means to govern it.
- Avoid part hierarchies that merely reproduce documents, teams, process phases, screens, or source
  directories.

## Definitions and expressions

- Add definitions and supertypes only for current reuse, substitution, or shared semantics.
- Prefer native SysML semantics to annotations or prose-shaped pseudo-language.
- Define a calculation only when it returns an evaluable result with sufficiently clear inputs and,
  when relevant, units and numerical expectations.
- Define a constraint usage only when it has a complete predicate or deliberately bound expression.
- When replacing subtype structure with a kind, mode, or status value, define the valid feature
  combinations and behavior for each value. Representation simplification must not erase distinct
  system states.
- Do not add a generic superclass, envelope, predicate, identifier, extension point, lifecycle,
  strategy, or variant merely because several names or implementation shapes look similar.
- Do not model a deferred realization decision as runtime variability. Open design space is not a
  configurable system responsibility.
- Keep one authority for each rule. Split a rule only when the distinctions have independent
  stakeholder meaning, responsibility, or evidence.
- Treat an apparent no-op according to system semantics before adding deduplication keys, lineage,
  compensating behavior, or version machinery.

## Requirements and evidence

- Give each requirement a clear obligation and compatible subject.
- Reuse or refine an existing requirement when it already governs the changed claim. Do not create a
  requirement and verification pair merely to mirror every use case, action, interface, or type.
- Keep a requirement, its satisfaction assertion, and evidence distinct.
- Identify a logical satisfier when the model selects one; satisfaction is a claim, not proof.
- Give each verification or analysis case a compatible subject and evidence that discriminates the
  intended result from its nearest plausible wrong result.
- Navigate from stakeholder outcomes through contextual behavior, logical responsibility,
  requirements, satisfiers, and evidence without demanding identical element counts.
- For numerical behavior, make evidence sensitive to units, ranges, boundary values, precision, and
  tolerances that the model actually promises.
- For temporal or concurrent behavior, make evidence sensitive to ordering, deadlines, interleavings,
  rates, and non-effects that the model actually promises.
- For safety, security, privacy, or resource claims, identify the unsafe, unauthorized, disclosed, or
  exhausted counterexample the evidence must exclude.
- Keep model-authoring checks focused on language conformance, generated-artifact freshness, and
  project safety. Do not let tests freeze generic model vocabulary, package layout, exact element
  counts, or a living architecture.
- Parser acceptance proves syntax and baseline conformance, not model adequacy or product correctness.
- Implementation tests may verify software against current model authority. They must not become a
  duplicate inventory that prevents intentional model evolution.

Before retaining any new element, answer:

1. What current claim does it express that was otherwise missing?
2. Which nominal, alternate, failed, or invalid example depends on it?
3. What invalid model instance does it exclude?
4. Why is it the least committal native construct for that claim?
5. Is it system authority, decisive evidence, or merely implementation-shaped precision?

Use the reference skill to ground ownership, occurrence, multiplicity, behavior, allocation,
satisfaction, and verification decisions in the active official baseline.

## Implementation-facing quality

- Produce handoffs from qualified model authority and decisive cases, not a copied declaration
  inventory.
- State implementation cohesion cues without relabeling them as modeled subsystems, and without
  offering one that crosses a boundary the model has already drawn. Examples include a family of
  pure calculations, one group of invariants, a state-transition boundary, a timing concern, or an
  interaction adapter.
- State which system boundary finer code must preserve: identity, lifecycle, state ownership,
  atomicity, timing, safety, failure responsibility, physical interaction, or selected external
  behavior.
- Allow a task-local many-to-many realization map inside each modeled boundary; it explains software
  design without becoming a second system model, and it may not span a boundary the model draws.
- Translate implementation feedback upward. Replace “this class needs another field” with the
  system-level distinction, smallest failing instance, and differing observable consequences before
  editing the model.
- A new helper, module, class, process, or deployment unit requires model change only when it creates
  or selects new system meaning; one that crosses a boundary the model has already drawn is a defect
  to fix in code.

## Reasoning demonstrations

These are questions to ask, not templates or prescribed architecture.

- **Composite versus reference:** if two controllers use the same independently maintained
  calibration profile, they reference one occurrence. If each controller owns a private calibrated
  copy with a separate lifecycle, composition may be correct.
- **Optional multiplicity versus conditional behavior:** zero-or-one permits absence; it does not say
  when behavior occurs. Use a guard, event, state transition, or black-box requirement when the
  condition matters.
- **Logical part versus software component:** one transformation system may be implemented with
  parser, analyzer, optimizer, and emitter modules. Those modules do not become subsystems by being
  modules; they become subsystems when the project decides those boundaries must hold and the model
  states what crossing one would break.
- **State versus value:** an operating mode that changes permitted behavior and transitions on events
  may need state semantics. A display color selected from an enumeration usually remains a value.
- **Flow versus storage:** modeled transfer of samples from a sensor to an estimator does not select
  a queue, database, message broker, or buffer. Add those only when their behavior or boundary is
  selected.
- **Requirement versus constraint:** “the controller shall reach a safe condition within the selected
  interval” is an obligation with a subject and evidence. The mathematical predicate defining the
  safe region is a constraint; neither substitutes for the other.
- **Open choice versus configurable design:** if persistence, deployment, or algorithm choice is
  undecided, leave it open. Modeling interchangeable strategies would falsely claim runtime
  variability.
- **Implementation feedback versus model transcription:** a retry implementation that duplicates an
  effect may expose missing idempotence, ordering, or failure non-effect meaning. Model that
  consequence if required; do not model a retry class.
