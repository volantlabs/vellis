# Modeling Workflow

## Contents

- [Preserve the decision frame](#preserve-the-decision-frame)
- [One semantic slice per change](#one-semantic-slice-per-change)
- [Semantic-strength ladder](#semantic-strength-ladder)
- [Needs through verification](#1-frame-stakeholder-value-and-system-context)
- [Project change review](#7-review-through-the-project-workflow)

## Preserve the decision frame

Before expanding the model, identify the current question, explicit stakeholder decisions it
depends on, selected model meaning, concepts already removed, and choices intentionally deferred.
Treat them as constraints outside the requested review scope. Do not promote an incidental test,
familiar pattern, comment, diagram, or existing element into a stakeholder decision. Reopen an
explicit decision only when the stakeholder asks for reassessment or new evidence contradicts it,
and then state:

1. the prior decision;
2. the new evidence;
3. the consequence that can no longer be preserved.

Do not ask the same question again in architecture, interface, validation, or implementation
language. A review may strengthen the rationale for a decision without reopening it.

## One semantic slice per change

Start with one stakeholder or engineering question. Update the breadth-first landscape only where
that question changes it, then trace the changed claim through the applicable existing context,
behavior, domain meaning, logical responsibility, requirements, satisfiers, and verification. Add
an element only when that layer lacks meaning needed to close the claim. Exercise nominal,
alternate or failed, and plausible-invalid instances. Defer unrelated cleanup and realization
design.

The steps below are conditional gates, not a demand to elaborate every modeling dimension. A
calculation change need not invent a state machine. A user-interaction change need not select
deployment. A timing requirement need not create a service boundary. Stop when the changed
stakeholder outcome is semantically closed and further detail would only anticipate a realization or
hypothetical future use case, unless the project intentionally selects that realization boundary.

Semantic closure is not artifact completion. A use-case change does not automatically need a new
action, requirement, verification case, interface, result type, or part. Reuse or strengthen
existing authority when it already has the right subject and meaning. Add a new artifact only when
it makes a necessary distinction expressible or independently reviewable.

## Semantic-strength ladder

Place each claim at the strongest appropriate level:

1. Use native SysML structure, behavior, or relationship when it directly expresses the claim.
2. Use a complete constraint or calculation when formal evaluation is useful and the expression is
   known.
3. Use normative requirement text plus decisive verification when formalization would be premature.
4. Use explanatory documentation only for orientation, contribution, tooling, or operation.

Stronger is not automatically better: select the highest level justified by current knowledge and
engineering value. A deferred decision is not a product option and does not justify optional
multiplicity, variants, interfaces, or configuration. Keep one authority for each claim; do not
repeat it at weaker levels as a parallel contract. Names, comments, and prose may explain native
semantics but cannot replace or contradict them.

## 1. Frame stakeholder value and system context

Name the system of interest, its boundary, the stakeholders whose outcomes matter, external actors,
and the environment in which value appears. Actors may be people, organizations, software systems,
devices, physical processes, operators, maintainers, or regulators. Keep them outside the system
boundary unless the system intentionally owns or contains them.

Record only environmental assumptions that constrain system meaning. Do not turn every surrounding
technology, organization, or physical object into model structure.

## 2. Build the use-case landscape

Cover each independently valuable stakeholder objective with a distinct use case. Use an
encompassing journey only to compose genuinely included outcomes. For every use case, establish as
applicable:

- actors, objective, and relevant conditions;
- meaningful stimuli, inputs, or preconditions;
- nominal result;
- alternate, refusal, degradation, or failure outcomes;
- visible state, physical, informational, or temporal effect and guaranteed non-effects;
- evidence that discriminates the intended outcome from its nearest wrong result.

Do not create a use case for every screen, command, protocol message, framework hook, sensor signal,
or external operation. Those surfaces may realize stakeholder outcomes; they do not define the
outcome landscape. A platform or environmental limitation becomes system meaning only when it
changes an observable outcome or the project intentionally selects that realization boundary.

Do not infer responsibilities from a product name, acronym, known reference architecture, or
predecessor implementation. Establish current stakeholder meaning first. A familiar term remains
domain vocabulary until current behavior requires a particular architecture.

## 3. Establish domain meaning and governed state

Introduce the minimum identity, values, quantities, units, relationships, invariants, and state
ownership needed by the behavior. Keep conceptual meaning independent from storage, serialization,
transport, user-interface, runtime, and deployment choices. Ensure every governed state has behavior
that changes or observes it and consequences that can be verified.

Prefer identity already present in the domain before adding surrogate identifiers, names, versions,
statuses, or lineage. Prefer a derived feature when another authoritative fact determines the value.
A measurement, estimate, proposal, or captured copy is not automatically the same occurrence as its
subject; model the distinction only when behavior depends on it.

Distinguish absent, empty, unknown, not applicable, invalid, and undecided. Optional multiplicity
expresses permitted absence in system instances, not uncertainty in the design process. Keep an
unresolved engineering choice in the project's decision workflow unless the system itself must
represent that uncertainty.

Model precision, tolerance, units, uncertainty, conservation, spatial meaning, resource limits,
security classification, or safety integrity only when the current claim depends on them. Their
absence is not automatically a gap; their observable consequence may be.

## 4. Refine behavior when it adds meaning

Refine use cases or requirements into actions, states, calculations, constraints, interactions, or
flows only when decomposition reveals shared behavior, ordering, transformation, modes, events,
state effects, timing, concurrency, failures, or verification needs. Black-box behavior may remain
undecomposed. Do not create a same-named action merely to satisfy a traceability convention.

A behavior tree must add semantics, not only labels. Connect the information, material, energy, or
control that justifies the decomposition. Multiplicity states how many usages may occur; it does not
state the condition under which one occurs. If the condition, transformation, transition, or result
cannot yet be modeled clearly, retain the stronger black-box statement and decisive verification
instead of implying a partial algorithm.

Do not derive one action per external operation or framework capability. Introduce functional
refinement only when the system must explain behavior inside its boundary. When an external
interaction inventory is intentionally selected as a current contract, model its interaction
meaning directly without manufacturing equal-count use cases, subsystems, requests, reports, or
internal stages.

Use states for event- or condition-dependent behavior over time, calculations for evaluable results,
constraints for predicates that must hold, and flows or messages for intentional transfer. Do not
use one construct merely because an implementation mechanism with a similar name exists.

## 5. Group capabilities before structure

Group related behavior as functional capabilities without assuming code objects, processes, devices,
or deployment boundaries. Introduce a logical part only when at least one independently meaningful
commitment requires it:

- lifecycle, identity, or substitutability;
- governed state or invariant ownership;
- failure, safety, security, or resource responsibility;
- an external interaction or physical boundary;
- independent realization currently selected or under explicit trade study;
- an internal boundary the project selects to keep coherent across independent implementation work.

Selecting binding internal structure is a stakeholder decision, not an agent's convenience: present
it as an architectural selection and record what it forbids. Code maintainability alone does not
make that decision, and neither does the existence of a class, module, service, cache, handler,
pipeline, adapter, or user-interface grouping. Do not turn structure you found in an implementation
into structure the model commands; model the decomposition you intend to be obeyed and leave the
rest to the implementer. Use performed behavior when a part carries out referenced behavior. Use
allocations only when distinct source and target hierarchies need an explicit responsibility
mapping.

## 6. Close requirements and verification

Requirements state obligations and identify compatible subjects. Do not add a requirement merely to
restate a type, use case, action, or test. Satisfaction assertions identify selected satisfiers; they
do not prove satisfaction. Verification and analysis cases identify compatible subjects and
decisive evidence. One case may cover several compatible requirements, and one requirement may need
several discriminating cases.

Keep the applicable chain navigable without forcing equal counts:

stakeholder outcome → contextual use case → optional behavior refinement → system responsibility →
requirement → satisfier → verification or analysis

Not every slice needs every link. Trace the changed claim through the strongest authority that
exists, and add a layer only when its absence prevents the project from deciding conformance.

Walk consequential semantic chains in both directions:

- stimulus or input through behavior to output or effect;
- event, guard, transition, mode, and promised state or non-effect;
- flow or message source, destination, carried matter or information, and relevant ordering or time;
- calculation input, units, precision, and result;
- shared occurrence through ownership and reference;
- requirement through subject, satisfier, and discriminating evidence.

For each consequential claim, exercise:

1. the smallest nominal instance;
2. the smallest alternate or failed instance with promised non-effects;
3. the smallest counterexample that exposes ambiguous ownership, cardinality, control, transition,
   quantity, timing, interaction, or responsibility.

Use only the cases applicable to the claim; do not invent refusal, persistence, networking, or
physical behavior for systems that do not have it. If the cases require a distinction the model
cannot express, close that gap before adding deeper structure. If they make an element irrelevant,
remove it.

Use informal requirement documentation when an obligation is not expressed as a formal predicate.
Introduce a constraint usage only with a complete predicate.

## 7. Review through the project workflow

Treat model changes as executable authority:

1. map each mandatory plan claim and non-goal to its authority and evidence;
2. validate the complete required model scope with the configured official validator;
3. inspect the change set for altered system meaning and unintended consequences;
4. review requirements, satisfiers, analysis, and verification where applicable;
5. perform plan-conformance, semantic-closure, adequacy, subtraction, and project-truth reviews;
6. fix findings and repeat the full review sequence until one pass reaches a clean fixed point;
7. explain consequential tradeoffs in the project's normal review record;
8. integrate through the configured change-control workflow.

Do not duplicate review state inside model elements. Put unresolved work in the project's configured
issue, decision, or review mechanism.

## Historical material

Consult predecessor artifacts only when current work explicitly needs historical comparison,
compatibility, migration, or recovery. Preserve current system meaning rather than predecessor
architecture by default.
