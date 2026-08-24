# Model-to-implementation agentic development

This method treats implementation as a realization of current textual SysML v2 system authority,
not as a translation of model nouns into code nouns. It preserves system meaning while leaving
ordinary software engineering choices to the implementation work that first needs them.

Vellis is the first proving ground, not the template. The method is intended to move to software
projects with different domains, architectures, languages, runtimes, quality concerns, and evidence
needs.

## Portable core, project binding, domain extensions

The workflow has three deliberately separate layers:

1. **Portable core:** `$sysml-reference`, `$sysml-modeling`,
   `$sysml-implementation` and `$sysml-evolution` define the evidence, modeling,
   whole-model decomposition, bounded realization, conformance, resumable execution, post-build
   evolution, and feedback method.
2. **Project binding:** local instructions identify model entry points and reading order, the active
   language baseline, reference and validation tooling, source and generated-artifact ownership,
   implementation constraints, checks, and change-control workflow.
3. **Optional domain extensions:** a project may add skills for domain semantics and specialized
   evidence. Those extensions compose with the core; the core never requires one particular domain.

The core therefore assumes neither a directory layout nor Git, Python, a server, an interface style,
persistence, networking, code generation, or a test framework. It conditionally handles state,
quantities, time, concurrency, interaction, safety, security, resources, physical effects,
durability, and recovery only when the modeled system uses them.

This repository does not yet package those capabilities as a standalone plugin. The skills are
written around the portable boundary so they can be moved or packaged later without carrying Vellis
commands or RTG meaning into another project.

## One authority, two-way evidence

The model owns stakeholder outcomes, system boundaries, domain meaning, logical responsibility, and
any requirements, satisfiers, verification intent, analysis, or deliberately selected external
boundaries present in the project. Implementation source owns the concrete realization decisions
needed to make those commitments run. Tests, analyses, simulations, inspections, and demonstrations
provide evidence from implementation toward the model; they do not freeze the model's declaration
inventory or become a second requirements system.

Information moves in both directions:

1. Model work hands implementation a current, qualified semantic slice with observable obligations,
   full or partial authority coverage, remaining obligations, decisive cases, non-effects, and
   explicit realization deferrals.
2. Implementation work chooses the smallest sufficient realization, builds the slice, and produces
   discriminating conformance evidence and a separate implementation status.
3. Review and checkpoint that slice together, then take the next dependency-ready work.
4. Implementation defects remain implementation work. A reproducible model gap returns to the model.
   A feasibility limit reaches the model only when its demonstrated consequence changes
   stakeholder-visible system behavior or an intentionally selected realization boundary.

This asymmetry keeps the model authoritative without pretending it can or should predict every
class, function, module, process, algorithm, data structure, framework, device adapter, or deployment
choice.

## Systems authority and software design

SysML is systems-flavored authority. A logical part exists for independently meaningful lifecycle,
state, invariant, failure, safety, physical, external-interaction, substitution, or selected
realization responsibility—not merely because maintainable software benefits from another class.
What the model does decompose is authority; what it leaves unmodeled is free.

The asymmetry is directional. Inside a modeled boundary, software design may be much finer-grained
than the modeled system decomposition and needs no permission to be. Across modeled boundaries, code
may not merge, re-cut, or reassign governed state: a code unit spanning two modeled parts is an
implementation defect, not a realization decision.

Implementation agents use semantic neighborhoods as cohesion cues wherever the model is silent about
structure. Values and units, calculations,
validation rules, transformations, state transitions, interactions, numerical kernels, timing,
protocol adaptation, and evidence support may each motivate focused software components while
remaining inside one modeled system responsibility.

That relationship is a task-local, many-to-many **software realization projection**:

- one modeled responsibility may use several software components;
- one software mechanism may realize several model elements inside one modeled part; across two
  modeled parts it is an implementation defect;
- a software boundary may improve invariant enforcement, dependency direction, testability, platform
  isolation, or change isolation without becoming system authority;
- finer software structure must preserve the modeled identity, lifecycle, state, timing, safety,
  failure, physical, and external boundaries that remain unified.

A useful code component is not evidence for a SysML subsystem. Conversely, a modeled part does not
require one same-named class, service, process, or deployable—but it does require that no code
unit straddle it and its neighbor, and that its governed state stay where the model put it.

## Semantic handoff

A handoff is a task-local navigation and evidence aid that can be rebuilt from the current model. It
identifies:

- active baseline, change set, and scope read;
- stakeholder or engineering outcome and observable distinction;
- qualified model elements that jointly carry each obligation;
- full or partial authority coverage for every cited element and any remaining obligations;
- smallest nominal, applicable alternate or failed, boundary, and invalid cases;
- relevant identity, ownership, values, units, state, interaction, timing, resource, safety,
  compatibility, and non-effect boundaries;
- intended analysis, verification, simulation, inspection, or demonstration;
- intentionally selected external behavior;
- exact realization decisions and unrelated concerns left open.

Not every project or slice has every field. The handoff reuses the strongest existing authority and
does not create an artifact merely to fill each layer. It must not turn open choices into
configurable product architecture or a speculative list of interchangeable components.

Authority coverage and implementation status are independent. Coverage says whether the slice
claims all or only part of cited model authority. Status says whether its in-scope implementation is
`not evaluated`, `absent`, `partial`, `conforming`, or `conflicting`. A bounded slice may close while
covering only part of a larger requirement, but the remainder must be explicit and the whole
requirement or verification case must not be reported complete. Coverage is judged against each
cited accepted authority element's complete meaning, not merely the task prompt or row summary;
`full` necessarily means that no obligation remains.

## Translate gaps back into system meaning

When implementation or its evidence exposes a gap, preserve the smallest failing case but translate
the problem before editing SysML:

1. record the failing stimulus, input, state, environment, operation, and observed consequence;
2. remove class, function, table, task, process, framework, driver, and exception vocabulary;
3. identify the unresolved system distinction—such as outcome, identity, ownership, quantity,
   invariant, transition, timing, concurrency, interaction, safety, responsibility, external
   contract, failure non-effect, compatibility, or evidence;
4. state the differing observable consequences the current model cannot decide;
5. reopen only the affected semantic slice at the strongest necessary authority level.

A new class, field, lock, buffer, adapter, or process may be the software fix without becoming a
modeled part or feature. Conversely, an ambiguity in system ownership, behavior, timing, safety, or
external meaning must be closed in the model before code silently selects one outcome. After an
accepted model change, rebuild the implementation frame and realization projection, then carry the
change back down into code and evidence.

Classify the feedback as a language question, model gap, realization decision, feasibility
consequence, implementation defect, or stale baseline. An out-of-scope request is a scope
disposition, not a divergence. Before escalating, confirm that the affected behavior or boundary is
represented or intentionally selected and that the evidence exposes a consequential distinction the
model cannot decide. Unselected storage, acknowledgement, process, transport, framework, and
deployment mechanics remain realization decisions unless their demonstrated consequence crosses
that gate.

## Plan and execute by semantic slice

Implementation proceeds through end-to-end semantic slices rather than declaration-by-declaration
generation. Each slice produces one meaningful modeled outcome, includes only the domain, behavior,
interaction, and quality semantics it depends on, and ends in evidence that would fail for the
nearest plausible wrong implementation.

The plan separates:

- required model meaning;
- project- or user-selected realization constraints;
- task realization decisions;
- genuine model gaps;
- explicit non-goals.

It records why a concrete dependency or software structure is sufficient for current facts without
feeding that structure back into SysML. Generated source is conditional: when generation is selected,
agents change its authority or generator, regenerate, and verify freshness. Machine-readable SysML
alone does not require generation.

Conformance evidence is equally domain-dependent. A stateless transformation may need properties and
boundary values; an interactive workflow may need scenario and state evidence; a distributed system
may need ordering and fault cases; a real-time controller may need simulation, timing, interlock, and
hardware evidence; scientific software may need units, tolerances, numerical references, and
reproducibility.

## Review to a bounded clean result

After a slice works, walk stimuli and inputs forward through calculations, decisions, state,
interactions, and effects. Walk each output, state change, physical effect, and failure backward to
the stakeholder outcome and qualified authority that permits it.

Review, wherever applicable:

- identity, ownership, multiplicity, equality, collections, and absence;
- values, units, ranges, precision, tolerance, and uncertainty;
- control, transformations, states, events, transitions, and non-effects;
- timing, ordering, concurrency, resources, and fault behavior;
- interactions, safety, security, physical effects, durability, recovery, and compatibility;
- evidence capable of rejecting the nearest plausible wrong implementation;
- realization machinery unsupported by the current slice.

Collect complete authority/conformance and engineering/evidence findings, then batch all in-scope
corrections and sweep the same root cause once. Run the second review pair against the
resulting slice. Reviewers receive fixed lens prompts without earlier findings or expected
conclusions; they do not invent new mutants, fuzz spaces, attack models, or speculative input
boundaries solely to prolong discovery. The two-pair budget and its stop conditions are normative in
`$sysml-evolution`.

Reviewers stay on the selected slice and its evidence unless that slice intentionally changes the
method itself. A slice is complete only when the final pair finds no material modeled-behavior,
authority-coverage, evidence, implementation, declared-safety, or ordinary-recovery issue. Its
compact handoff states the checkpoint, checks, review counts, elapsed time, and any pause reason;
reproducible project artifacts carry the technical detail instead of reviewer transcripts.

Use targeted checks while implementing and remediating. Normally run the full project gate once
before the initial pair and once against the remediated state before the final pair; rerun it sooner
only when the change or project binding makes that evidence necessary.

## Vellis as a proving case

Vellis binds the portable core through `AGENTS.md`, `model/README.md`, its pinned reference and
validator tooling, `system-evolution.yaml`, and its `just` checks.
Post-build evolution is inspectable with `just system-evolution-check` and
`just system-evolution-status`; its record indexes findings, decisions, work, and rebaselining but
does not become product authority or a second execution engine. Vellis derives observed
model, language, lockfile, Git implementation, and checkpoint identities from the repository and
binds completed independent reviews to their reviewer and reviewed checkpoint; those are project
bindings, not assumptions embedded in the portable skill.
`$rtg-schema-design` is an optional Vellis domain extension, not part of the portable core.

Within that extension, graph, definitions, validation, query, revision, and history may become
distinct Python responsibilities while RTG remains one modeled semantic and transactional boundary.
That is one demonstration of the systems/software seam, not a decomposition other projects should
copy. Another project supplies its own domain skill—or none—and its own local bindings.
