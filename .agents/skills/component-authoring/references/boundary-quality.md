# Boundary Quality

Use this reference when reviewing component boundaries, splitting or merging specs, or extracting specs from existing code.

## Design Values

Prefer modular, reusable, narrowly scoped components with explicit invariant ownership and low coupling.

Use these values as review pressure:

- Modularity: split or compose around distinct responsibilities, owners, invariants, dependencies, and reasons to change.
- Reusability: define behavior that can serve more than one app, transport, runtime, or storage representation.
- Narrow scope: keep each component focused on the smallest coherent responsibility that can hide implementation details.
- Invariant control: assign each invariant to the component that owns the relevant state, records, workflow, or sequencing authority.
- Low coupling: depend on public contracts, not private internals, framework choices, or unrelated runtime topology.
- Elegance: prefer one clear representation over parallel ways to say the same thing.
- Verifiability: make the boundary provable with black-box tests, side-effect checks, and dependency checks.

These values make systems easier to maintain, understand, test, and extend. A design that weakens one value should do so deliberately because another current component requirement needs it.

## One Component Archetype

Use the same ordinary black-box component shape for every responsibility. Components may own
records, calculations, validation, coordination, transport mapping, or combinations of local work
and collaborator invocation. Those differences belong in their contracts, state, invariants, and
actions.

Names such as store, controller, coordinator, facade, gateway, actor, and saga describe purpose,
composition role, or behavior. They do not justify a component metatype, runtime registration
kind, framework base class, or lifecycle branch. Introduce specialization only when consumers need
a genuine substitutable public contract that cannot be expressed by composing ordinary component
capabilities.

Watch for role-derived complexity when:

- runtime code branches because an occurrence is called a controller, saga, leaf, or edge;
- a model creates a component superclass only to group workflow styles;
- an implementation inherits orchestration machinery instead of composing message and policy
  helpers;
- a component must be reclassified before one of its actions can invoke a collaborator;
- local work and coordination cannot coexist in the same ordinary component occurrence.

Also reject disclosure-shaped coupling: an ordinary query, validation, mutation, fault, or effect
should not require a collaborator's complete snapshot. Model targeted reads, projections, deltas,
bounded diagnostics, digests, or opaque references instead. Reserve complete state for visibly
named state-transfer and external-document actions.
Ordinary mutation contracts should require component-local all-or-none batches whose preparation,
projection, and transient recovery footprint follow the requested delta and its documented cascade
closure, not unrelated canonical state. State observable atomicity and resource boundaries without
prescribing undo logs, copy-on-write structures, database transactions, or another private
algorithm. Cross-owner uncertainty should name the recovery outcome instead of promising online
distributed rollback unless that promise is intentionally part of the public boundary.

## Good Boundaries

A good component boundary usually has:

- a clear purpose in system/product language
- high internal cohesion
- low external coupling
- a small public surface
- explicit state ownership
- clear failure semantics
- known consumers
- meaningful tests at the boundary
- few reasons to change
- private implementation details that can vary without changing the spec

## Weak Boundaries

A weak component boundary often has:

- vague purpose
- many unrelated responsibilities
- many public contracts
- unclear state ownership
- dependencies in every direction
- `manager`, `helper`, `util`, or generic `service` naming without domain meaning
- tests coupled mostly to private implementation
- frequent need to touch adjacent components
- missing or ignored non-responsibilities
- change rules that allow agents to alter architecture by convenience
- assumptions that the component must be in-process, distributed, dependency-injected, or message-driven when the behavior does not require that commitment

## Split Heuristics

Consider splitting a component when:

- responsibilities have different owners
- responsibilities change for different reasons
- one part owns durable state and another is read-only
- consumers need only one subset of the public contracts
- invariants are unrelated or pull in different verification strategies
- dependencies form separate clusters
- agent changes to one area would routinely risk unrelated behavior

Do not split merely because the implementation has several files, classes, private helpers, or algorithms.

## Merge Heuristics

Consider merging components when:

- the components cannot be verified independently
- they always change together for one system reason
- one component has no meaningful public contract except to another
- state ownership is artificial or circular
- the separation forces broad internal details into public contracts

Do not merge merely to make one implementation task easier.

## Simplicity Heuristics

Prefer the smallest contract that can be implemented and verified now.

Good simple boundaries:

- have one representation for each operation
- make optional extension points earn their cost through a known consumer
- use ordinary component contracts before adding factories, registries, adapters, or strategy objects
- defer lifecycle states until the system has distinct behavior for each state
- keep reports canonical instead of carrying both grouped and flattened versions of the same facts

Watch for over-engineering when:

- a spec adds an abstraction only to preserve theoretical implementation freedom
- callers can express the same request in two equivalent ways
- a status value implies runtime, recovery, or transaction behavior that has not been specified
- a future split is modeled as a public contract instead of as a private implementation rule
- verification must prove mechanics that are not part of the current user-visible behavior

## Contract Quality

Provided contracts should describe externally observable behavior:

- inputs and outputs
- errors and failure semantics
- side effects
- idempotency or ordering rules where relevant
- consistency expectations
- security or authorization behavior where relevant
- events emitted or consumed
- compatibility promises to consumers

Avoid contracts that expose private helper structure or implementation sequencing unless that sequencing is externally meaningful.

## Representation Quality

Component specs should describe the model the component owns, not the shape a storage engine or transport might force.

Good representation choices:

- separate the component's conceptual model from possible persistence, database, transport, or interchange representations
- name canonical owned state separately from derived indexes, caches, projections, and snapshots
- expose relationship records only when the relationship needs identity, metadata, lifecycle, permissions, validation, or independent behavior
- keep storage adapters, query engines, schema validators, ledgers, controllers, and facades from leaking policy or representation constraints into lower-level reusable components
- explain when an index or snapshot is just a representation of existing state rather than a new domain object

Weak representation choices:

- modeling an in-memory component like a database merely because one possible implementation or storage backend would require that shape
- turning every relationship into a public object when a direct index, pointer, or containment rule is the component's actual owned state
- treating derived indexes as canonical state without saying what they derive from and how consistency is verified
- exposing persistence or graph-database concepts such as tables, documents, nodes, edges, labels, or traversal primitives when they are not part of the component's public behavior
- splitting policy decisions such as UUID generation, authorization, lifecycle workflow, or field-level mutation across a low-level state component and a higher-level controller or facade without naming the owner

## Store, Registry, And Coordinator Boundaries

When a design includes low-level state stores plus higher-level workflow, keep invariant ownership explicit.

Good store or registry boundaries:

- own native records, record identity, basic lifecycle metadata, and indexes
- enforce record-local invariants such as UUID uniqueness, reference integrity, valid status fields, and canonical-to-derived-index consistency
- preserve caller-supplied metadata without assigning workflow meaning unless the workflow is part of the component purpose
- expose reads and full-record writes without deciding which records participate in a larger operation

Good coordinator, migration, proposal, or publication boundaries:

- own participation sets such as "make these records live" or "retire these records"
- own readiness, approval, evidence references, status transitions, and cutover plans
- consume lower-level store contracts rather than taking over their records
- keep validation, constraint checking, and operational cutover separate unless those are explicitly the component purpose

Watch for scope drift when:

- a store starts owning change sets, workflow readiness, or batch cutover membership
- a validator starts mutating source records
- a migration tracker starts storing the records it references
- a controller or facade becomes the only place where lower-level invariants are enforced
- lifecycle fields such as `live`, `published`, or `retired` are used both as record metadata and as workflow authority without naming which component owns the transition rules

## System Controller Boundaries

A broad controller component can be a good boundary when it is the black-box API for a composed system and owns invariants that no lower-level component can own alone.

Good controller boundaries:

- sequence public contracts from lower-level components
- own cross-component invariants, preconditions, and operation-level failure semantics
- expose system actions such as validate-and-apply, cutover, query delegation, snapshot, and restore
- keep transport adapters such as MCP, REST, CLI, SDK, and UI thin and outside the controller
- avoid owning lower-level records, indexes, persistence, or validation algorithms directly
- expose distinct public operations when callers have distinct intent, authority, validation rules, or failure semantics, even if the controller normalizes those operations into one private internal representation
- keep shared internal operation representations private or explicitly non-primary; they must not become generic mutation backdoors around the public lanes that own user intent and policy

Weak controller boundaries:

- reach into private internals of the components they coordinate
- become the only place where lower-level record-local invariants are enforced
- require transport, storage, deployment, authentication, or authorization frameworks when those are not part of the system contract
- hide unrelated workflows behind a generic manager API without naming the invariants it owns
- leave removed or demoted public contracts callable on common concrete implementations unless those compatibility shims enforce the same invariants as the current public operations

## Replay, Recovery, And Audit Boundaries

Replay and recovery behavior should make its target state explicit. A replay contract should rebuild from an empty state or from a supplied snapshot/checkpoint, and reject ambiguous replay into active mutable state unless merge semantics are part of the public contract.

Good replay and recovery boundaries:

- name the starting state, cursor, and stop condition for replay
- keep replay ledger-silent unless recording replay itself is part of the audit contract
- use recorded, resolved request data rather than current mutable store lookups when reconstructing historical mutations
- reject partial or ambiguous recovery inputs with clear failure semantics
- select effects only when both their record and the owning trace's committed terminal record are
  within the requested cursor
- require a complete, common-cursor checkpoint set for every canonical-state owner
- report external-boundary availability without contacting the external collaborator during replay

When audit, ledger, or observability is part of a component invariant, failures in that subsystem must be visible to callers. If the primary state mutation succeeds but audit persistence degrades, the operation result should report degraded audit state and preserve enough detail for a human or operator to understand what applied without durable confirmation.

Weak replay, recovery, and audit boundaries:

- replay directly into a non-empty active store without an explicit snapshot, merge policy, or overwrite rule
- depend on mutable current state for information that should have been captured in the audit record
- silently hide ledger, audit, or observability failures after state mutation succeeds
- treat compatibility or retry paths as private implementation details when they affect externally meaningful recovery evidence

## Composite Validation Boundaries

A validation component can stay whole when consumers need one validation report for one proposed operation. Keep it split-ready by isolating validation tracks around the source of truth and invariant each track checks.

Good composite validation boundaries:

- keep validation stateless and side-effect free
- separate tracks by dependency cluster, such as schema/object checks, constraint/network checks, and migration/cutover checks
- make track selection explicit through options
- return one canonical finding list with track labels unless callers prove they need grouped reports
- communicate between tracks through explicit inputs, read-only views, and report data

Consider extracting a validation track into its own component when:

- the track needs independent consumers
- the track's dependencies diverge from the rest of validation
- the track owns distinct report semantics or verification evidence
- the track requires independent scaling, scheduling, or runtime treatment
- the track starts accumulating state or mutation pressure

## Runtime Neutrality

Component specs should usually be neutral about runtime topology.

Good runtime-neutral specs:

- define behavior and contracts before wiring choices
- support in-process, dependency-injected, message-driven, or distributed implementation when those choices do not change observable behavior
- describe event delivery, ordering, retries, idempotency, and consistency only when they affect the public contract
- treat RabbitMQ, HTTP, function calls, imports, dependency-injection containers, and deployment units as implementation choices unless the component contract exposes them

Weak specs:

- require a broker, queue, service boundary, or dependency-injection mechanism without a behavioral reason
- hide transport-visible guarantees in implementation prose
- make reuse difficult by coupling the component to one runtime topology
- confuse a deployment unit with a component boundary

## Language Neutrality

Component specs should be implementable in more than one programming language.

Good language-neutral specs:

- describe contracts, inputs, outputs, errors, and invariants as externally observable behavior
- name verification by what it must prove — contract behavior, side effects, forbidden dependencies — not by a specific test framework or command
- treat the current implementation language as one realization of the contract

Weak specs:

- bake test commands, package layouts, or language constructs into the contract or verification
- describe behavior in terms only meaningful to one language's type system or runtime
- make a second-language implementation re-decide owned state, invariants, or contracts

## Dependency Quality

Required contracts should make boundary violations obvious.

Good dependency sections:

- name allowed components or external contracts
- name forbidden components or external contracts
- explain sensitive dependencies through invariants or non-responsibilities
- keep implementation convenience from becoming architecture

Weak dependency sections:

- say only "uses the database" or "calls services"
- omit forbidden dependencies
- allow broad packages when only one contract is needed
- let a component reach across ownership boundaries for convenience

## Invariant Quality

Good invariants are:

- durable
- externally meaningful
- testable or reviewable
- tied to the component purpose
- independent of private helper structure

Examples:

- Preview must not create durable financial state.
- Token validation must not extend token lifetime.
- Notification retry must not duplicate successful deliveries.
- Search indexing must not mutate source records.
- Authorization failure must not reveal resource existence.

Avoid implementation-style invariants unless implementation structure is itself part of the public contract.

## Verification Quality

Prefer black-box verification:

- contract tests
- API tests
- golden input/output fixtures
- property-based tests
- event schema tests
- migration checks
- side-effect checks
- forbidden dependency checks
- observability assertions
- integration tests at the public boundary

Avoid relying only on private helper tests. Private helper tests can support implementation confidence, but they are not enough to validate the component contract.

## Human Judgment Questions

Ask for human judgment when any of these are ambiguous:

- Who owns this component?
- Which contracts are public?
- Which state is authoritative?
- Which dependencies are allowed or forbidden?
- Which invariants are design commitments?
- What evidence is sufficient to accept an agent-delivered slice?
- Should this boundary be accepted, deprecated, retired, split, or merged?
