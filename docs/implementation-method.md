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
   `$sysml-implementation-planning`, `$sysml-implementation`, and
   `$sysml-implementation-campaign` define the evidence, modeling, whole-model decomposition,
   bounded realization, conformance, resumable execution, and feedback method.
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

1. Whole-model planning identifies every implementation-bearing authority neighborhood, forms its
   semantic dependency graph, and derives a complete campaign for human approval.
2. Model work hands implementation a current, qualified semantic slice with observable obligations,
   full or partial authority coverage, remaining obligations, decisive cases, non-effects, and
   explicit realization deferrals.
3. Implementation work chooses the smallest sufficient realization, builds the slice, and produces
   discriminating conformance evidence and a separate implementation status.
4. The campaign reviews and checkpoints that slice, resumes with the next dependency-ready slice,
   and closes only after full-system integration and runnable evidence.
5. Implementation defects remain implementation work. A reproducible model gap returns to the model.
   A feasibility limit reaches the model only when its demonstrated consequence changes
   stakeholder-visible system behavior or an intentionally selected realization boundary.

This asymmetry keeps the model authoritative without pretending it can or should predict every
class, function, module, process, algorithm, data structure, framework, device adapter, or deployment
choice.

## Systems authority and software design

SysML is systems-flavored authority. A logical part exists for independently meaningful lifecycle,
state, invariant, failure, safety, physical, external-interaction, substitution, or selected
realization responsibility—not merely because maintainable software benefits from another class.
Software design may therefore be much finer-grained than the modeled system decomposition.

Implementation agents use semantic neighborhoods as cohesion cues. Values and units, calculations,
validation rules, transformations, state transitions, interactions, numerical kernels, timing,
protocol adaptation, and evidence support may each motivate focused software components while
remaining inside one modeled system responsibility.

That relationship is a task-local, many-to-many **software realization projection**:

- one modeled responsibility may use several software components;
- one software mechanism may realize several model elements;
- a software boundary may improve invariant enforcement, dependency direction, testability, platform
  isolation, or change isolation without becoming system authority;
- finer software structure must preserve the modeled identity, lifecycle, state, timing, safety,
  failure, physical, and external boundaries that remain unified.

A useful code component is not evidence for a SysML subsystem. Conversely, a modeled part does not
require one same-named class, service, process, or deployable.

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

## Whole-model planning and durable campaign state

Whole-model planning begins cold from the complete accepted authority. It derives independently
reviewable obligation neighborhoods, semantic dependencies, inseparable cycles, and end-to-end
semantic slices before consulting existing source topology. Integration and closure slices appear
only when modeled meaning spans prior slices. Necessary toolchain setup belongs to the first semantic
slice that uses and proves it, not an architecture-only phase.

The resulting campaign record contains the current baseline, qualified authority references,
many-to-many slice coverage, dependencies, implementation status, evidence references, consequential
realization decisions, blockers, approval, and checkpoints. It contains no copied requirements,
stories, tasks, estimates, architecture, or serialized model. A fresh agent must reread the cited
model authority before acting.

The complete plan and every material replan require human approval. A stale baseline, genuine model
gap, material plan gap, or stakeholder-visible feasibility consequence pauses execution and
invalidates that approval. Code defects and bounded model-preserving realization choices remain
autonomous implementation work. Approval applies to the complete campaign: independently reviewed
routine slice checkpoints are recovery boundaries, not repeated human approval gates.

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

## Review to a fixed point

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

Material corrections restart the complete review. A slice is complete only after one full pass finds
no new conformance, evidence, simplicity, or project-truth issue. Its handoff states precisely what is
modeled, selected, implemented, verified, runnable, and still deferred.

## Long-running execution and closure

A continuation harness repeatedly invokes the campaign manager, but durable meaning does not depend
on one conversation. The validated campaign record and project checkpoints identify the exact
baseline, active or next slice, evidence, decisions, and blockers. One writer owns one active slice.
In Codex, the approved campaign is suitable for a
[long-running goal](https://learn.chatgpt.com/use-cases/follow-goals): completion is the verifiable
stopping condition, while model gaps, material plan gaps, stale baselines, and stakeholder-visible
feasibility consequences are explicit pause conditions. Other environments may provide an equivalent
continuation harness.

After focused evidence passes, independent agents review authority/conformance and
engineering/evidence. The writer remediates every material finding and repeats both reviews. Only a
clean fixed-point cycle permits the implementation, evidence, documentation truth, and campaign
state to checkpoint together. A project-bound checkpoint must resolve to that durable combined
state; an active slice retains the preceding recoverable checkpoint until the new one commits, and
the committed current checkpoint is the exact recovery head rather than an older reachable state.
Slice checkpoints form one direct single-parent chain from approval through the final slice and
closure, so merges, sibling history, or unexplained intermediate commits cannot be mistaken for
campaign recovery state. Historical authority resolution uses each checkpoint's committed validator
pin rather than the current checkout's pin. Project bindings must inspect raw object history and
reject local replacement or graft overlays that could rewrite the recovery view.
Project checkpoint validation also preserves the approved plan-bearing projection through every
slice and closure checkpoint. A changed baseline, authority map, coverage contribution, dependency,
verification reference, or consequential realization decision returns the campaign to planning and
human approval rather than silently changing the execution plan.

After the last planned slice, a separate closure cycle reconstructs complete model coverage, tests
cross-slice semantics, exercises the selected external boundary from a fresh environment, performs a
cold-agent reconstruction, and subtracts unsupported machinery. Application completion requires a
current baseline, full aggregate authority coverage, conforming integration evidence, a runnable
selected boundary, and no blocker.

## Vellis as a proving case

Vellis binds the portable core through `AGENTS.md`, `model/README.md`, its pinned reference and
validator tooling, `implementation-campaign.yaml`, and its `just` checks. The campaign is inspectable
with `just implementation-campaign-check` and `just implementation-campaign-status`; its observed
baseline is available with `just implementation-campaign-baseline`, and committed checkpoints are
resolved with `just implementation-campaign-checkpoint-check`.
`$rtg-schema-design` is an optional Vellis domain extension, not part of the portable core.

Within that extension, graph, definitions, validation, query, revision, and history may become
distinct Python responsibilities while RTG remains one modeled semantic and transactional boundary.
That is one demonstration of the systems/software seam, not a decomposition other projects should
copy. Another project supplies its own domain skill—or none—and its own local bindings.
