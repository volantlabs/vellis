# Use-case-first model-as-code development

This method treats textual SysML v2 as versioned system authority: changes are validated, reviewed for
engineering meaning, and accepted through the project's normal change-control workflow. It is
designed for reuse across software systems rather than around one product, domain, repository layout,
or implementation style.

## Portable method and local binding

The portable modeling method begins with stakeholder value, closes one semantic slice, uses official
SysML and KerML evidence, and hands implementation system obligations without prescribing code.
Each project supplies local bindings for:

- model entry points, dependency order, and required reading scope;
- active specification, model-library, examples, and validator baseline;
- reference search, snippet probing, and complete-model validation;
- review, decision, documentation, and generated-artifact workflows;
- optional domain skills that add specialized semantics.

The method assumes no directory name, command runner, source-control system, application protocol,
runtime, persistence technology, or programming language. Vellis binds these capabilities locally;
another project can bind them differently without editing the core skills.

## Breadth before depth

Begin with stakeholders, external actors, system boundary, environment, and independently valuable
outcomes. Actors may be people, organizations, software systems, devices, or physical processes. An
encompassing journey may compose outcomes but should not erase their different nominal, alternate,
failure, state, physical, temporal, or evidence semantics.

Do not infer architecture from requested nouns, familiar names, reference architectures, framework
examples, predecessor code, or incidental tests. Establish the current system meaning first.

## One semantic slice

Start each change with one stakeholder or engineering question and the observable distinction at
stake. Update only the affected black-box behavior, then add the minimum domain meaning and native
representation needed to make the distinction decidable.

Elaborate conditionally:

- identity, values, quantities, units, relationships, invariants, and governed state;
- actions, calculations, constraints, modes, events, transitions, control, and data flow;
- interactions, ports, interfaces, connections, flows, and messages;
- timing, ordering, concurrency, resources, physical behavior, safety, security, and privacy;
- requirements, satisfiers, analysis, and verification;
- logical structure and selected realization boundaries.

Not every slice needs every dimension or a new artifact at every layer. Refine behavior when it adds
ordering, transformation, reuse, state, failure, interaction, timing, or evidence meaning. Group
capabilities before considering parts. Stop when the changed claim is governed and verifiable and
further detail would only anticipate implementation or unrelated features.

An undecided realization is not optional system behavior. Keep it open in the project's decision
record rather than modeling interchangeable parts, variants, interfaces, or configuration. Tool,
framework, protocol, and device affordances are feasibility constraints, not an automatic inventory
of use cases, actions, or subsystems.

## Systems structure is not code structure

A logical part needs independent system meaning: lifecycle, identity, governed state, invariant,
failure, safety, security, resource, physical, external-interaction, substitution, or selected
realization responsibility. Code maintainability alone does not establish one.

Implementation may still isolate semantic neighborhoods into classes, modules, functions, processes,
tasks, or generated types. One modeled responsibility may use several software components, and one
software mechanism may realize several model elements. Modeling work should expose those cohesion
cues and the system boundaries they must preserve, not manufacture a one-to-one architecture.

## Proportionality and continuity

Add an element only when it expresses a current system consequence, obligation, or
implementation-blocking ambiguity. Preserve explicit stakeholder decisions and deliberate deferrals
across review rounds. Reopen a decision only under explicit reassessment or when new evidence creates
a concrete contradiction; record the prior decision, evidence, and changed consequence.

Prefer existing domain identity, derived facts, one authority for each rule, and the least committal
native construct before adding surrogate identifiers, stored flags, parallel schemas, generic
envelopes, lifecycle machinery, or extension seams.

If tests and model structure were introduced together, reassess model adequacy independently.
Passing checks, matching names, and parser acceptance do not establish that the system meaning is
necessary or correct.

## Semantic closure

Exercise consequential claims with the smallest applicable:

1. nominal instance;
2. alternate, degraded, refused, or failed instance and promised non-effects;
3. boundary or plausible-invalid counterexample.

Walk semantic chains in both directions:

- stimulus or input through behavior to output or effect;
- event and guard through transition to state and non-effect;
- calculation input through units and precision to result;
- flow or message through source, destination, carried content, ordering, and timing;
- shared occurrence through ownership and reference;
- requirement through subject, satisfier, and discriminating evidence.

Check collection ordering, equality, uniqueness, completeness, and absence only where behavior
depends on them. Check time, concurrency, resources, physical behavior, safety, security, durability,
and recovery only where the current claim depends on them. Conditional depth is rigor; compulsory
elaboration is not.

## Adequacy and subtraction

Review adequacy before subtraction. Preserve independently valuable outcomes, state and invariant
authority, interactions, failure behavior, required non-effects, and evidence. Then remove elements
that express no necessary claim, exclude no invalid model instance, or merely transcribe an expected
implementation.

The goal is semantic compression: fewer elements with all consequential distinctions intact. Mere
deletion is not simplification when it makes ownership contradictory, behavior ambiguous, or evidence
unable to distinguish the nearest wrong system.

## Evidence and review

Use the active pinned official specifications for consequential language decisions and the selected
official validator for language conformance. Separate normative clauses, standard-library and example
evidence, project convention, stakeholder decision, and agent inference.

Review the complete required model scope, current change set, semantic closure, requirements and
evidence where applicable, unsupported commitments, and project truth separately. After the last
material correction, repeat the full review cycle; completion requires one pass that finds no new
material issue.

## Handoff to implementation

Accepted model work intended for code ends with a compact semantic handoff: active baseline and scope,
qualified authority, each in-scope obligation, full or partial authority coverage, any remaining
obligations, decisive cases, relevant system boundaries, conformance-evidence intent, compatibility
effects, and exact realization decisions left open. Partial coverage is valid for a bounded slice but
does not establish whole-requirement satisfaction or whole-verification completion.

The handoff may identify semantic neighborhoods that offer implementation cohesion while naming the
single identity, lifecycle, state, timing, safety, physical, failure, or external boundary they remain
inside. It is task-local and reconstructible from current model authority; it does not restate the
model as a parallel specification or predict software structure.

Implementation verifies or reconstructs the handoff before taking architecture from existing source.
Implementation defects are fixed in code. A missing consequential system distinction returns to the
affected semantic slice. A feasibility constraint changes the model only when its demonstrated
consequence changes stakeholder-visible behavior or an intentionally selected realization boundary.
Unselected storage, acknowledgement, process, transport, framework, and deployment mechanics remain
realization decisions unless their consequence crosses that gate. See the
[model-to-implementation method](implementation-method.md) and use `$sysml-implementation` for the
operational workflow.

## Vellis binding

Vellis uses branches and pull requests, the model under `model/`, checksum-pinned local reference
tooling, the official validator, and `just` checks as its project binding. `$rtg-schema-design`
supplies RTG-specific meaning as an optional domain extension. Those paths, commands, and domain
semantics are deliberately absent from the portable core.
