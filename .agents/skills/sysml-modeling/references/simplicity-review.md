# Simplicity Review

Perform two independent reviews. Adequacy catches missing authority; subtraction catches unjustified complexity. Do not use simplicity as a reason to erase behavior, state governance, recovery semantics, or verification.

## Adequacy review

Look for:

- one omnibus use case hiding independently valuable outcomes;
- owned state with no governing behavior;
- failures, refusals, or required non-effects absent from black-box behavior;
- actions with no owner-valued origin or no added refinement value;
- parts with no performed or allocated behavior, requirement, state, invariant, or failure responsibility;
- requirements with no logical satisfier or verification path;
- important responsibilities existing only in Markdown or comments outside the model;
- recovery, ordering, atomicity, or lifecycle semantics too vague to judge;
- state-change history that cannot reconstruct promised canonical state from an initial state or snapshot plus a contiguous tail;
- reusable use-case definitions absent from the actual system context;
- alternative selectors, outcomes, or relationship roles that the model cannot distinguish;
- outputs that cannot be traced to the selector, projection, request, or decision that authorizes them;
- result rows whose joint assignment, projection completeness, duplicate semantics, or absent values
  are undefined;
- one conceptual occurrence compositionally owned by multiple containers;
- a nested composite that quietly carries a complete state where only a semantic change was intended;
- optional subactions whose multiplicity is being mistaken for a condition;
- kind or scope values with payload combinations whose validity is undefined;
- public request schemas that advertise internal-only enum values;
- selected public input or output types that remain empty placeholders;
- historical behavior evaluated against definitions other than those active at that revision;
- a cold historical outcome that cannot discover or otherwise obtain vocabulary valid at the selected
  revision;
- a read declared state-free while its required observability behavior mutates an activity ledger;
- a trusted-client label being used as if it were an authorization or approval guard;
- optional features whose absence is being used to hide an unresolved design decision;
- excessive deletion that makes system authority unknowable.

Add the smallest native model element that closes each material gap.

## Subtraction review

For every element ask:

1. Which use case, requirement, invariant, failure, or verification case needs it?
2. What becomes false, unrealizable, or unverifiable if it is removed?
3. Is it the lowest-commitment native representation of that claim?

Remove or defer elements with no concrete answer.

Warning signs include:

- classes, methods, handlers, or call graphs transcribed into the model;
- one same-named action, outcome, report, or verification wrapper for every use case without added meaning;
- one use case, action, request, result, requirement, or test for every tool or protocol operation;
- one universal discovery operation that either floods an agent with the full definition state or
  requires it to guess identifiers before it can ask a focused question;
- action trees that name stages without connecting the information, state, or control that makes the stages meaningful;
- empty subtype families that differ only by label;
- capability groupings promoted to parts solely to anticipate code modules;
- generic predicates or extension points with no current semantic need;
- speculative services, runtimes, adapters, controllers, managers, repositories, or protocols;
- request/response envelopes or generic JSON standing in for domain meaning;
- empty request types created only to make parameterless protocol calls look symmetrical;
- duplicate authoritative representations;
- event, snapshot, checkpoint, database, or serialized-form commitments stronger than the owner-visible durability and recovery need;
- ports and interfaces with no intentional connected transfer;
- lifecycle machinery with no behavior that depends on it;
- extension seams or interchangeable layers with no current consumer;
- a distinction carried forward only because predecessor code had it;
- package structure that merely mirrors documents or phases;
- surrogate identifiers, lineage, statuses, or versions added before anything must address or compare
  them independently;
- stored flags or result wrappers that duplicate meaning already available from ownership,
  membership, omission, or the operation being performed;
- separate permission, endpoint, multiplicity, and validation representations for one relationship;
- a public check or assessment operation duplicating a current report already returned by the
  governing workflow;
- full-state reads, response mirroring, or result capture that pushes state-bearing artifacts into an
  agent context without an owner use case;
- a record-count bound that still permits one record to carry an unbounded full-state payload;
- initialization state machines for a system that can simply begin in a valid empty state;
- incremental-validation, locking, paging, retry, archive, or checkpoint algorithms promoted into
  normative meaning before their tradeoff is selected;
- exhaustive error codes, scopes, paths, request IDs, correlations, and envelopes before a caller
  demonstrates the need;
- generic vocabulary bans and exact prose assertions used as substitutes for repository-truth tests;
- an intent history where the product only needs one current prospective overlay;
- strategies, plugins, variants, or configurable parts representing a realization choice that is only
  deferred;

## Agent correction patterns

Use these groups to diagnose behavior, not as another checklist to satisfy:

- **Transcription:** noun transcription, familiar-name substitution, API-surface mirroring, and
  symmetry completion create elements because source material contains names or matching columns.
  Return to the owner distinction and keep only elements that change its meaning.
- **Authority theater:** prose repair, parser theater, and specification cosplay substitute comments,
  successful parsing, or nearby citations for correct native semantics and design evidence. State the
  instance-level commitment and test it.
- **Anticipation:** enterprise-prior gravity, future-proofing, precision theater, contract inflation,
  and uncertainty encoding turn common or possible implementations into current product contracts.
  Keep choices open in the work, not configurable in the system.
- **Mechanical closure:** test-shaped modeling and layer completion add mirrored actions,
  requirements, reports, or verifications to satisfy an inventory. Reset-era tests can fossilize the
  same mistake by banning future directories, commands, packages, or capabilities after the
  transition ends. Close claims and invariants, not columns or historical snapshots.
- **Destructive correction:** subtraction panic and local-patch blindness remove necessary authority
  or fix one declaration without following its semantic consequences. Review adequacy first, then
  subtract.
- **Decision churn:** repeated reviews reopen explicit owner decisions without new evidence or an
  explicit reassessment scope. Preserve continuity while still challenging incidental structure.

For execution of a formal plan, also look for quiet omission: a plan item marked complete because a
nearby name exists, a negative commitment checked only in one file, or a later edit invalidating an
earlier review. A clean fixed point requires one full review cycle after the last material correction.

## Final result

Prefer one laminar route from owner outcome through behavior, domain meaning, logical responsibility, requirements, satisfiers, verification, and later implementation. Record unresolved design work in an issue or PR discussion instead of modeling a speculative answer.

Prefer **semantic compression**: fewer elements with all necessary distinctions intact. Mere deletion is not simplification when it leaves outputs unauthorized, ownership contradictory, or tagged payloads ambiguous.
