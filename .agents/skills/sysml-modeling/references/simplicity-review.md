# Simplicity Review

## Contents

- [Adequacy review](#adequacy-review)
- [Subtraction review](#subtraction-review)
- [Agent correction patterns](#agent-correction-patterns)
- [Final result](#final-result)

Perform two independent reviews. Adequacy catches missing authority; subtraction catches unjustified
complexity. Review adequacy first so simplification does not erase behavior, state governance,
interaction, safety, recovery, or evidence that the system actually needs.

## Adequacy review

Look for, as applicable:

- one omnibus use case hiding independently valuable stakeholder outcomes;
- missing actors, environmental assumptions, or system-boundary distinctions;
- governed state with no behavior that creates, observes, changes, or retires it;
- alternate, degraded, failed, unsafe, or unauthorized outcomes and required non-effects absent from
  black-box behavior;
- actions with no stakeholder-valued origin or no added refinement meaning;
- transformations with unclear inputs, outputs, control, or result;
- modes, events, guards, or invalid transitions too vague to judge;
- interactions whose source, destination, direction, carried item, or applicable timing is unknown;
- quantities without required units, dimensions, ranges, precision, tolerance, or uncertainty;
- concurrency, ordering, deadlines, capacity, resource, safety, security, privacy, durability, or
  recovery semantics too vague for a current obligation;
- logical parts with no independent lifecycle, state, invariant, failure, interaction, physical,
  substitution, or selected realization responsibility;
- requirements with an incompatible or missing subject, or consequential obligations with no
  selected satisfier or verification path where the project requires them;
- important responsibilities existing only in explanatory prose or comments;
- contextual use-case or behavior definitions absent from the actual system context;
- a conceptual occurrence compositionally owned by more than one container;
- nested composite content that quietly carries full state or a duplicate occurrence;
- optional usages whose multiplicity is mistaken for a condition;
- kind, mode, or status values with undefined valid feature combinations;
- collections whose ordering, equality, uniqueness, completeness, or absence meaning affects
  behavior but remains undefined;
- outputs or effects that cannot be traced to the input, event, decision, interaction, or requirement
  that authorizes them;
- a selected external interaction whose inputs, outputs, effects, or compatibility meaning remain
  placeholders;
- optional features or variants used to hide an unresolved design decision;
- implementation feedback exposing observable ambiguity that has not been translated into system
  meaning;
- excessive deletion that makes system authority unknowable.

Add the smallest native model element that closes each material gap. Do not add every listed
dimension; absence is a gap only when the current system claim depends on it.

## Subtraction review

Separate selected structure from transcribed structure before subtracting: structure the project
intentionally selected as binding architecture is not a subtraction candidate on shape alone, and a
selection that constrains nothing was not a selection.

For a part, port, interface, package, or allocation, ask what it forbids: name one implementation
it rules out that a competent engineer would otherwise plausibly choose. Rules out nothing is
decoration; remove it however architectural it looks. Rules out something is authority; keep it
however software-shaped it looks, and require the prohibition to be written into the model or the
handoff rather than implied or asserted in review. Transcription and deliberate architecture
declare the same shapes and differ only in origin and in what they forbid.

For every element ask:

1. Which stakeholder outcome, use case, requirement, invariant, interaction, failure, analysis, or
   verification needs it?
2. What becomes false, unrealizable, unsafe, or unverifiable if it is removed?
3. Is it the lowest-commitment native representation of that claim?

Remove or defer elements with no concrete answer.

Warning signs include:

- classes, functions, handlers, tables, processes, call graphs, screens, or source directories
  transcribed into the model;
- one same-named action, outcome, report, requirement, or verification wrapper for every use case;
- one use case, action, request, result, or test for every interface or protocol operation;
- action trees that name stages without connecting the information, matter, energy, state, or control
  that makes the stages meaningful;
- empty subtype families that differ only by label;
- capability groupings promoted to parts with no stated prohibition, solely to anticipate code
  modules or team boundaries;
- structure that rules out no plausible implementation, most often services, adapters, controllers,
  managers, repositories, runtimes, deployment units, devices, databases, or protocols;
- request or response envelopes and serialization shapes standing in for domain meaning;
- generic predicates, base types, identifiers, extension points, or configuration with no current
  semantic need;
- duplicate authoritative representations or independently stored derived values;
- persistence, events, checkpoints, caches, transport, retry, paging, synchronization, or migration
  machinery stronger than the selected system behavior;
- state machines or lifecycle machinery with no behavior that depends on state;
- variability or interchangeable parts representing a realization decision that is merely deferred;
- package structure that mirrors documents, process phases, teams, or code layers;
- a distinction retained only because predecessor code or a familiar architecture had it;
- broad error taxonomies, telemetry, correlation, audit, or operational machinery before a current
  stakeholder or engineering obligation needs them;
- precision, timing, resource, safety, or security detail copied from a technology without a modeled
  consequence;
- initialization behavior for a system that can simply begin in a valid state;
- tests or generated inventories used to freeze model vocabulary, topology, exact counts, or prose;
- a public assessment or duplicate result that restates information already supplied by the
  governing behavior;
- handoff artifacts promoted into permanent parallel requirements or architecture.

## Agent correction patterns

Use these groups to diagnose behavior, not as another checklist to satisfy:

- **Transcription:** noun substitution, familiar-name matching, interface mirroring, and symmetry
  completion create elements because source material contains matching names or columns. The defect
  is the origin, not the shape: the same declaration is authority when the project selected it and
  transcription when source material supplied it. Return to the stakeholder distinction and keep
  only elements that change its meaning.
- **Authority theater:** prose repair, parser theater, and citation theater substitute comments,
  successful parsing, or nearby references for correct native semantics and design evidence. State
  the instance-level commitment and exercise it.
- **Anticipation:** reference-architecture gravity, future-proofing, precision theater, contract
  inflation, and uncertainty encoding turn common or possible realizations into current system
  contracts. Keep open choices in the engineering work, not configurable in the system.
- **Mechanical closure:** layer completion and test-shaped modeling add mirrored actions,
  requirements, reports, or verification artifacts to satisfy an inventory. Close claims and
  invariants, not columns.
- **Destructive correction:** subtraction panic and local-patch blindness remove necessary authority
  or fix one declaration without following semantic consequences. Review adequacy first, then
  subtract.
- **Decision churn:** repeated reviews reopen explicit stakeholder decisions without new evidence or
  an explicit reassessment scope. Preserve continuity while still challenging incidental structure.
- **Decorative architecture:** parts, ports, and packages that look like an architectural
  commitment but rule nothing out, so the model grows while the implementer stays exactly as free.
  State the prohibition the element is meant to carry or delete the element.

For execution of a formal plan, also look for quiet omission: a plan item marked complete because a
nearby name exists, a negative commitment checked in only one artifact, or a later edit invalidating
an earlier review. A clean fixed point requires one full review cycle after the last material
correction.

## Final result

Prefer one laminar route from stakeholder outcome through behavior, domain meaning, logical
responsibility, requirements, satisfiers, evidence, and later implementation. Record unresolved
design work in the project's decision or review mechanism rather than modeling a speculative answer.

Prefer **semantic compression**: fewer elements with all necessary distinctions intact. Mere
deletion is not simplification when it leaves outcomes ambiguous, ownership contradictory,
interactions incomplete, or verification unable to distinguish the nearest wrong system.
