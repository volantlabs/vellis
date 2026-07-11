# SysML v2 Modeling

Textual SysML v2 under `model/` is the authored design for Bibliotek and Vellis. Generated pages
under `docs/model/generated/` explain that model for humans; they are projections, not a second
contract source.

The model remains in `shadow` status until a pinned formal validator and human acceptance complete
the gates in `model/model-status.json`. The former Markdown component specifications are frozen as
a migration baseline during that interval. New design work belongs in SysML.

## Model products

- `model/foundation/SoftwareComponentModeling.sysml` defines typed governance, contract, state
  access, implementation, and evidence metadata using ordinary SysML constructs.
- `model/bibliotek/shared-values/` contains the deliberately narrow language-neutral value layer.
- `model/bibliotek/components/` contains ten reusable black-box component models.
- `model/vellis/` contains the Vellis application composition, façade, use cases, and current
  Python/MCP realizations.
- `model/implementation-drift.yaml` records the small set of known implementation disagreements
  without promoting current Python behavior into intended design.

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

Every component has a structural contract: identity, lifecycle, public values/items, typed provided
and required actions, defaults and multiplicities, principal failures, and required provider
cardinality. Implementation bindings belong to concrete realization packages, so the logical
component may have multiple conforming realizations.

Stateful components additionally model abstract owned state, authority and lifetime, which actions
read or mutate it, concise effects, rejected-operation no-effects, and invariant preservation.

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
- Give every invocable action explicit multiplicity. Use performed actions for provided
  capabilities and referential action or part features for required capabilities.
- Do not duplicate the provided role in metadata: `perform action` already supplies that native
  meaning. Required-capability metadata adds only provider cardinality that the reference feature
  does not otherwise express.
- Relate required capabilities to providers with annotated dependencies. Binding means value equality; it
  is not a generic dependency-injection relation.
- Declare provider cardinality for every required capability.
- Keep construction actions separate from actions performed by an existing component.
- Record state authority, lifetime, and persistence independently. Durable external state is not
  automatically composition-owned by a process-lifetime component.
- Use requirements for testable obligations and constraints only for complete predicates. Use an
  enum-valued status plus transition obligations for request-driven record lifecycle; use an
  exhibited state when activated behavior or event-triggered transitions are actually modeled.
- Use cases describe actor-visible value. Ports, interfaces, messages, and flows appear only when
  connection or transfer semantics are part of the current contract.
- A modeled interface has typed port ends and explicit contract-significant flows. Empty ports are
  not generic software API notation.
- Bibliotek and Vellis public field names and enum literals encode as `lower_snake_case` by default.
  `@ExternalName` records exact exceptions such as abbreviated query operators. This mapping is
  part of the black-box contract and must not be inferred from an implementation language.

The JSON storage, query, and controller models are the representative patterns: respectively
durable state, declarative matching, and externally meaningful orchestration.

## Generated views and checks

`just model-render` produces one page per Bibliotek component, Bibliotek and Vellis indexes,
action/state/invariant tables, composition and use-case views, and the static Vellis application
manifest. `just model-check` rejects stale outputs, empty or semantically hollow public actions,
missing or signature-incompatible protocol operations, accepted Markdown fields/failures/invariants
that disappeared during shadow migration, requirements without verification objectives, unresolved
implementation bindings, invalid capability cardinality, the wrong Vellis role/tool surface, and
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

The repository profile checker is not a substitute for a formal parser. Run
`uv run python tools/model_tool.py check --require-external` for the formal gate after the official
Java pilot (or a conformant alternative behind the same adapter) is pinned and qualified. Until
then, KPAR outputs remain explicitly marked shadow candidates and Markdown retirement remains
blocked.

## Semantic discoveries

Changing representation does not authorize changing accepted boundaries. Record a genuine Python
disagreement in `model/implementation-drift.yaml`. Treat boundary, ownership, lifecycle,
dependency, and invariant changes as explicit proposals for human approval. Implementation-only
helpers and incidental behavior stay outside the model unless they acquire independent,
language-neutral contract meaning.
