# SysML v2 Modeling

Textual SysML v2 under `model/` is the authored design for Bibliotek and Vellis. Generated pages
under `docs/model/generated/` explain that model for humans; they are projections, not a second
contract source.

`docs/model/generated/verification-evidence.json` resolves every modeled evidence group to the
exact test nodes currently available to evaluate it. Repository checks reject accepted component
evidence groups that resolve only to a path with no concrete tests.

The official Java pilot is pinned and qualified for headless syntax, linking, and semantic
validation. The model remains in `shadow` status until human acceptance completes the remaining
gates in `model/model-status.json`. The former Markdown component specifications are frozen as a
migration baseline during that interval. New design work belongs in SysML.

## Model products

- `model/foundation/SoftwareComponentModeling.sysml` defines minimal lifecycle, failure,
  realization, and evidence traceability vocabulary. Logical semantics stay in native SysML.
- `model/bibliotek/shared-values/` contains the deliberately narrow language-neutral value layer.
- `model/bibliotek/components/` contains ten reusable black-box component models.
- `model/bibliotek/views/` contains native reusable views for structure, behavior, requirements,
  satisfaction, and verification.
- `model/vellis/` contains the Vellis application composition, façade, use cases, and current
  Python/MCP realizations.
- `model/vellis/views/` contains native views for application composition, use cases, requirements,
  satisfaction, verification, and realization.
- `model/realizations/PythonImplementationDrift.sysml` relates known implementation disagreements
  from logical model elements to Python realizations without changing intended design.

Bibliotek imports the foundation and never imports Vellis. Vellis imports Bibliotek. Derived KPAR
packaging preserves this direction so the library and application can later move to separate
repositories.

## Package and library architecture

SysML uses namespaces and packages rather than a software-language `module` construct. A package is
a namespace and organizational owner. A `library package` identifies reusable definitions. The
KPAR is the independently versioned distribution container for those packages.

The repository uses the following ownership rule:

```text
SoftwareComponentModeling (library package; generic modeling vocabulary)
  <- Bibliotek (library package façade; reusable component library)
       <- Vellis (application package; roles, façade, use cases, app invariants)
            <- VellisLocalPython / VellisMcpPython (realization packages)
```

`Bibliotek.sysml` is the curated library façade. Its public imports expose supported component and
shared-value packages. Individual component library packages remain the semantic owners of their
contracts, so consumers may use the umbrella or a narrower package without moving ownership.
Private imports express authoring dependencies without adding them to the umbrella API.

The foundation contains only concepts intended to apply to software-component models generally.
Bibliotek contains reusable component contracts and the smallest shared semantic vocabulary needed
by multiple Bibliotek components. Vellis contains application-specific request shaping, workflows,
use cases, transport mapping, and response policy. A type is not promoted to a shared package merely
because two Python modules happen to use similar structures.

### Runtime evolution

The logical Bibliotek contracts remain invocation-topology neutral. A future reusable messaging
layer may be added under a separately packageable Bibliotek runtime library when its observable
delivery semantics are designed. Ports, interfaces, message items, flows, endpoint identities,
correlation, ordering, retry, and idempotency then belong to that runtime contract. A Vellis runtime
realization maps existing logical capabilities onto it; it does not redefine component behavior
just to replace constructor injection or direct calls.

Repository-specific names and migration gates live here and in `AGENTS.md`. The reusable authoring
skills contain only the generic package-layering and runtime-neutrality method, so they can guide
the next library or application without carrying Vellis/Bibliotek migration history.

## Right-sized modeling profile

Every component has a structural contract: identity, lifecycle, public values/items, typed actions,
defaults and multiplicities, principal failures, performed operations, and collaborator roles.
Invocation-scoped collaborators are action inputs. Collaborators retained for the component
occurrence are referential part roles with explicit multiplicity. Implementation bindings belong to
concrete realization packages, so the logical component may have multiple conforming realizations.

Stateful components additionally model abstract owned, derived, and externally referenced state,
which actions read or mutate it, concise effects, rejected-operation no-effects, and invariant
preservation.

Detailed behavior is selective. Model declarative matching rules, transition tables, observable
ordering, and rollback orchestration only when a consumer must predict them. Calculations are useful
for compact pure semantics such as query equality and ordering; successions are useful for
externally meaningful controller ordering. Do not model private helpers, call graphs,
implementation branches, storage layouts, Python exception inheritance, or algorithms where
equivalent implementations preserve the contract.

Stop when the model is sufficient for composition, substitution, design-level reasoning, and
black-box verification. It is intentionally not executable pseudocode.

Right-sized does not mean lossy. For an accepted component, the model must preserve its public
field names, multiplicities, defaults, construction actions, concrete failures, state categories,
observable effects, ordering promises, and invariant identities unless a human approves a contract
change. Concise requirements may replace several prose bullets only when they retain the same
meaning and do not admit incompatible black-box implementations.

Completeness is tested by behavioral substitutability, not source reconstruction. An independent
Rust, Python, or other realization may use entirely different algorithms and internal structures,
but the model must determine the same legal invocations, externally encoded values, abstract state
effects, ordering, failure/no-effect behavior, invariants, and dependency obligations. The same
rule applies at every modeled level: component, controller/subsystem, application façade, use case,
and transport realization. Deeper implementation or hardware modeling is selective rather than the
default mode.

## Native-first rules

- Use parts for active components and applications, attributes for values, and items for things
  whose identity or lifecycle matters.
- Give stable public identities with native SysML short names. Use the logical literal name when an
  enum value is itself a public encoding; otherwise define the encoding in a realization codec.
- Give every invocable action explicit multiplicity. `perform action` is the native
  provided-operation relationship and needs no duplicate role annotation.
- Use typed action inputs for invocation-scoped collaborators and multiplicited `ref part` features
  for collaborators retained by a component occurrence.
- In an application composition, bind a retained referential role to the actual application part
  usage when they denote the same occurrence. Binding is identity/equality, not a generic “calls”
  edge; never bind performed action usages to indicate invocation.
- Keep construction actions separate from actions performed by an existing component.
- Use ordinary owned features for component-owned state, `derived` features for projections, and
  `ref` features for independently existing durable resources or collaborators.
- Use typed dependencies for action-to-state access and allowed dependency topology. Model a call as
  a nested action performed by its provider. Explicitly redefine the typed action parameters and
  bind or flow every contract-significant input and output.
- Put every testable obligation in a requirement `require constraint`. A required constraint may be
  a complete Boolean predicate or normative text when exact formalization would reduce clarity.
  Top-level documentation is not a truth condition.
- Assert which part or action usage satisfies each accepted requirement. Verify it separately with a
  verification case whose subject is compatible with the requirement subject and whose evidence ID
  names a concrete evidence group.
- Use constraints only for complete predicates. Use an
  enum-valued status plus transition obligations for request-driven record lifecycle; use an
  exhibited state when activated behavior or event-triggered transitions are actually modeled.
- Use a calculation only when it defines a real reusable computation with an evaluable result.
  Never use hollow calculations, constraints, states, ports, or interfaces as prose containers.
- Use cases describe actor-visible value. Ports, interfaces, messages, and flows appear only when
  connection or transfer semantics are part of the current contract.
- A modeled interface has typed port ends and explicit contract-significant flows. Empty ports are
  not generic software API notation.
- Use view definitions for reusable projections. Define a viewpoint only when explicit stakeholders
  and concerns constrain the view; generated prose and diagrams remain projections.
- SysML names identify logical model features and literals; they do not implicitly define a wire
  encoding. When an external spelling is contract-significant, model it as an explicit logical
  literal or in a realization codec rather than deriving it from identifier style.

The JSON storage, query, and controller models are the representative patterns: respectively
durable state, declarative matching, and externally meaningful orchestration.

## Generated views and checks

`just model-render` produces one page per Bibliotek component, Bibliotek and Vellis indexes,
action/state/requirement/satisfaction/verification tables, composition and use-case projections,
and the static Vellis application manifest. `just model-check` rejects stale outputs, empty or semantically hollow public actions,
missing or signature-incompatible protocol operations, accepted Markdown fields/failures/invariants
that disappeared during shadow migration, requirements without required constraints, satisfiers, or
subject-compatible verification objectives, untyped state access, unresolved
implementation bindings, invalid referential-role bindings, the wrong Vellis role/tool surface, and
unrecorded drift. These shadow comparisons are repository migration gates, not part of the reusable
component-authoring skills.

```sh
just model-setup
just model-check-foundation
just model-check-bibliotek
just model-check-vellis
just model-render
just model-check
just model-package
just model-handoff TARGET=component.storage.json_file
```

The repository profile checker is not a substitute for formal validation. `just model-setup`
downloads checksum-pinned copies of the official 2025-06 Java pilot, its SysML 2.0/KerML 1.0
libraries, and a Java 21 runtime into the ignored `model/.cache/` directory. `just model-check`
then runs both the repository profile and the official validator; `just model-check-formal` runs
the latter directly. The published BNF is useful for syntax tooling, but it cannot replace the
pilot's linking, type, multiplicity, specialization, and other semantic diagnostics. KPAR outputs
remain shadow candidates and Markdown retirement remains blocked until human acceptance.

## Semantic discoveries

Changing representation does not authorize changing accepted boundaries. Record a genuine Python
disagreement in `model/realizations/PythonImplementationDrift.sysml`. Treat boundary, ownership, lifecycle,
dependency, and invariant changes as explicit proposals for human approval. Implementation-only
helpers and incidental behavior stay outside the model unless they acquire independent,
language-neutral contract meaning.
