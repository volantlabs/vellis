# Modeling Quality

## Contents

- [Meaning and state](#meaning-and-state)
- [Behavior and responsibility](#behavior-and-responsibility)
- [Definitions and expressions](#definitions-and-expressions)
- [Requirements and verification](#requirements-and-verification)
- [Reasoning demonstrations](#reasoning-demonstrations)

## Meaning and state

- Use an owned feature when the subject governs the value's lifecycle and invariants.
- Use a derived feature when the value is determined from other modeled facts.
- Use a reference feature for an independently existing occurrence that the subject does not own.
- Audit repeated appearances of the same conceptual occurrence. If an authoritative record, snapshot, actor, or domain object is used in another context, reference it unless a genuinely distinct copy with separately defined identity is intended.
- Reify a relationship only when the relationship itself needs identity, metadata, direction, lifecycle, or behavior.
- Prefer a natural key already present in domain meaning before introducing a surrogate identifier.
  Do not give rules, definitions, snapshots, archives, or requests UUIDs merely so they resemble
  persisted entities.
- Derive a value from its authoritative state when storing it independently would permit
  contradiction. Do not duplicate lifecycle flags, statuses, counts, or projections that another
  modeled relationship already determines.
- Model a proposed replacement as proposed state for an identity unless the proposal itself needs
  independent identity and lifecycle. Avoid creating current and staged domain occurrences that claim
  the same identity.
- Distinguish absent, empty, unknown, not applicable, and not yet decided. Encode each only when it is
  system meaning; do not use optionality or a status value to store modeling uncertainty.
- Keep storage identifiers, rows, documents, events, and serialized associations out of canonical domain meaning unless they are intentional product contracts.
- Ensure each owned state has governing behavior, failure rules, and verification evidence.
- Test ownership with concrete instances: ask whether the same occurrence must appear in two containers, whether it may outlive either, and which subject governs its invariants. Use a reference when the answers reveal independent existence.
- Expand owned payloads recursively during review. A transition record that does not directly own a
  resulting state can still imply snapshot-per-change semantics when its owned change object contains
  a complete state one level below.

## Behavior and responsibility

- Give every use case a distinct actor-valued objective, success, refusal or failure, state effect, and evidence.
- Derive actions from use cases, requirements, or invariants only when functional refinement adds engineering meaning; avoid both orphan actions and mechanical one-action-per-use-case mappings.
- Connect action inputs, outputs, and control when those connections are the reason for decomposition. Optional multiplicity does not encode a guard or acceptance decision.
- Remove an action tree whose steps exchange no information or control and exclude no invalid
  behavior. Stage names are not functional refinement; keep the behavior black-box until a meaningful
  handoff is known.
- Group actions as capabilities before introducing structural decomposition.
- Use performed actions when a part carries out referenced behavior during its lifetime.
- Use allocations only to map distinct source and realization elements. Do not allocate a performed action back to its existing performer.
- Add a part only for independently meaningful lifecycle, state ownership, failure or invariant responsibility, external interaction, substitution, or realization. A desirable code module alone is not a system part.
- Add ports and interfaces only for intentional connected interactions and transfers.
- Use state behavior only for activated or event-driven behavior, not merely because data has possible values.
- Give intended system use-case definitions contextual usages; do not let the instantiated landscape collapse back to one encompassing journey.
- State explicit multiplicity for included use cases when their occurrence count affects success or state change.
- Do not let comments imply control, transformation, or authorization that the selected action, binding, succession, guard, or usage does not express.
- Treat a trusted or owner-configured actor as a boundary assumption, not an authorization decision.
  If the system does not evaluate authorization or approval, scope the input to an already permitted
  request and do not promise a refusal the modeled behavior cannot produce.
- Qualify nonmutation by authority. A read may leave canonical state and revision unchanged while
  appending observational activity; calling that operation entirely state-free contradicts the
  activity owner.
- Do not turn a human judgment into an automatic system guard without modeled evidence the system can
  evaluate. Put owner review in owner-facing behavior and verification; keep machine-checkable
  preconditions limited to information available to the system.
- Do not mirror a tool, protocol, or framework operation into a use case and action by default.
  External affordances constrain realizability; owner outcomes and system semantics determine the
  model decomposition.
- When a public operation inventory is deliberately selected, test every operation for a distinct
  caller intent, input/output meaning, and state effect. Model it without deriving equal-count use
  cases, internal parts, requests, reports, or verification wrappers. Treat staged discovery as real
  refinement only when one bounded result supplies information needed to formulate the next request.
- Trace a selected public operation to its black-box behavior at the least committal native level.
  Use `$sysml-reference` to distinguish abstract trace or change impact from actual included or
  performed behavior; do not choose behavioral composition solely as a trace marker.
- Keep a general actor protocol-neutral when only one contextual role uses a selected protocol.
  Specialize or type the contextual role rather than asserting that every future actor of that kind
  is a client of the current boundary.

## Definitions and expressions

- Add definitions and supertypes only for current reuse, substitution, or shared semantics.
- Prefer native SysML semantics to annotations or prose-shaped pseudo-language.
- Define a calculation only when it returns an evaluable result.
- Define a constraint usage only when it has a complete predicate.
- Keep packages as intentional namespaces rather than artificial architecture layers.
- When replacing subtypes with a kind, scope, or status attribute, state which payload combinations
  are valid. For a public result, define success-payload presence for every status and distinguish a
  malformed request, a typed semantic rejection, a safely reported failure, and an unexpected
  failure that produces no completed result. Simplifying representation must not make previously
  distinct states indistinguishable.
- A public request type must expose only choices the caller may invoke. Do not reuse a broader
  internal scope enumeration when most values are invalid at that operation, and do not create an
  empty domain request solely because a protocol represents parameterless calls with an empty object.
- Do not add a generic superclass, predicate, envelope, status, identifier, extension point, or lifecycle merely because several names look similar. Require shared semantics and a current consumer.
- Do not model a deferred realization choice as configurable strategies, interchangeable parts,
  variants, or optional connections. Open design space is not runtime variability.
- Keep one source for each relationship rule. Do not split permission, endpoint eligibility,
  multiplicity, and validation into overlapping authorities that can disagree unless the distinctions
  are independently owner-visible.
- Choose the smallest one-current-proposal representation from actual scale and agent workflow. A
  small complete proposal can simplify inspection and replacement; a keyed overlay can avoid
  material copying. Add intent ordering only when edit history itself is required product behavior.
- Treat effective no-ops as no state change before adding idempotency keys, request lineage, or
  expected-version protocols.

## Requirements and verification

- Give each requirement a clear obligation and compatible subject.
- Reuse or refine an existing requirement when it already governs the changed claim. Do not create a
  requirement and verification pair merely to mirror each use case, action, tool, or type.
- Keep satisfaction assertions distinct from the requirement and from evidence.
- Identify a logical satisfier for every consequential requirement.
- Give each verification case a subject compatible with the requirement and evidence that discriminates success, refusal, failure, and required non-effects.
- Check that owner outcomes, contextual use-case usages, any functional refinement, system responsibility, requirements, explicit satisfiers, and verification are navigable without demanding identical element counts.
- Trace request semantics through response semantics. A shaped result must identify the request and the exact selector or projection responsible for each returned binding.
- For row-shaped results, define one row's joint assignment, exactly which projections bind in it,
  whether equal projected tuples duplicate, and how a requested absent value differs from null. A
  collection of optional binding families is not sufficient by itself.
- Treat every type exposed through a selected public contract as an implementation obligation. An
  empty placeholder type with only a promising name is under-modeling: give it the smallest closed
  meaning current behavior needs or defer it from the contract.
- Prefer tests for semantic invariants, valid references, closure, and forbidden commitments. Freeze exact inventories only when the inventory itself is an intentional repository contract.
- Use assertions and verification to observe the chosen design, not to choose it. A test that demands element names, counts, or symmetry without an owner invariant is a design generator and should be removed.
- Test the absence of an actual declaration, dependency, command, or generated capability rather
  than banning generic words or requiring explanatory prose to match one sentence shape.
- Classify automated checks as durable semantic invariants, repository or tool safety, or temporary
  transition guards. A transition guard must name the condition that retires it and must not prohibit
  generic roots, commands, platforms, or capabilities that the next phase may legitimately add.
- Change a test alongside an intentional model decision. Do not preserve an obsolete assertion by
  hiding the new design under different names or by restoring decorative elements.
- Distinguish state-bearing artifacts from agent-facing responses. A snapshot, ledger, archive, or
  full graph may be required for recovery without being suitable for inline return into an agent's
  context. Prefer bounded questions or artifact references before inventing pagination and streaming.
- A count bound does not bound an owned payload recursively. If one selected ledger record can own a
  complete graph or snapshot, return a bounded owner-facing projection unless the caller actually
  needs the replay artifact.
- Capture observability asymmetrically. Reads, rejected changes, and accepted canonical changes need
  not duplicate the same request and result payloads. Record only what the current reflection or audit
  use case needs.

Before retaining any new element, answer:

1. What current claim does it express that was otherwise missing?
2. Which accepted, rejected, or failed example depends on it?
3. What invalid model instance does it exclude?
4. Why is this the least committal native construct for that claim?
5. Is this detail semantic authority, decisive evidence, or merely implementation-shaped precision?

Use `$sysml-reference` to ground ownership, reference, derivation, performed behavior, allocation, satisfaction, and verification decisions in the pinned specifications.

## Reasoning demonstrations

These are demonstrations of questions to ask, not templates or prescribed architecture.

- **Composite copy versus reference:** if a ledger owns an authoritative transition and a replay tail
  selects that same occurrence, the tail references it. Composition would assert a second owned copy
  or contradictory ownership. A self-contained snapshot, by contrast, owns its captured state because
  that state is intentionally a distinct copy.
- **Filtering participation versus authorized projection:** an associated-data object may determine
  whether an anchor matches without appearing in the result. Return only bindings explicitly selected
  by the return shape; participation in evaluation is not disclosure authority.
- **Optional multiplicity versus conditional behavior:** `[0..1]` permits zero or one occurrence but
  does not say when it occurs. If commit happens only after acceptance, use native conditional control
  or keep the behavior black-box with a requirement and decisive verification until that control is
  known.
- **Exact inventory versus invariant testing:** removing decorative actions should cause a test of an
  old action-name set to change, not the actions to return. Test that remaining actions are used and
  semantic paths are closed; freeze an exact inventory only when the inventory itself is intentional.
- **Open choice versus configurable design:** if storage technology is undecided, omit storage
  structure. A set of storage strategy parts would falsely claim that runtime interchangeability is
  a selected system responsibility.
- **Tool affordance versus owner behavior:** if a protocol exposes separate read and resource forms,
  first decide which owner outcomes need bounded inline results or referenced artifacts. Do not create
  parallel use cases and response families merely because the framework has two primitives.
