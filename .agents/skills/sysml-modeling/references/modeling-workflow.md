# Modeling Workflow

## Contents

- [Preserve the decision frame](#preserve-the-decision-frame)
- [One semantic slice per change](#one-semantic-slice-per-change)
- [Semantic-strength ladder](#semantic-strength-ladder)
- [Needs through verification](#1-frame-owner-value-and-system-context)
- [Git review and historical material](#7-review-through-git)

## Preserve the decision frame

Before expanding the model, identify the current question, explicit owner decisions it depends on,
selected model meaning, concepts already removed, and choices intentionally deferred. Treat them as
constraints outside the requested review scope. Do not promote an incidental test, familiar pattern,
comment, or existing element into an owner decision. Reopen an explicit decision only when the owner
asks for reassessment or new evidence contradicts it, and then state:

1. the prior decision;
2. the new evidence;
3. the consequence that can no longer be preserved.

Do not ask the owner the same question again under different architecture, validation, API, or
implementation wording. A review may strengthen the rationale for a decision without reopening it.

## One semantic slice per change

Start with one owner or engineering question. Update the breadth-first landscape only where that
question changes it, then trace the changed claim through the applicable existing behavior, domain
meaning, native representation, responsibility, requirements, satisfiers, and verification. Add an
element only when that layer lacks meaning needed to close the claim. Exercise accepted, refused or
failed, and plausible-invalid instances. Defer unrelated cleanup and realization design.

The steps below are conditional gates, not a demand to elaborate every modeling dimension. A query
change need not invent recovery behavior; a recovery change need not elaborate the query language.
Stop when the changed owner outcome is semantically closed and further detail would only anticipate a
realization or hypothetical future use case.

Semantic closure is not artifact completion. A use-case change does not automatically need a new
action, requirement, verification case, result type, or part. Reuse or strengthen existing authority
when it already has the right subject and meaning. Add a new artifact only when it makes a necessary
distinction expressible or independently reviewable.

## Semantic-strength ladder

Place each claim at the strongest appropriate level:

1. Use native SysML structure or relationship when it directly expresses the claim.
2. Use a complete constraint or calculation when formal evaluation is useful and the expression is
   known.
3. Use normative requirement text plus decisive verification when formalization would be premature.
4. Use explanatory Markdown only for orientation, contribution, tooling, or operation.

Stronger is not automatically better: select the highest level justified by current knowledge and
engineering value. A deferred decision is not a product option and does not justify optional
multiplicity, variants, interfaces, or configuration. Keep one authority for each claim; do not
repeat it at weaker levels as a parallel contract. Names, comments, and Markdown may explain native
semantics but cannot replace or contradict them.

## 1. Frame owner value and system context

Name the system of interest, its boundary, the owner or stakeholder whose outcome matters, external actors, and the environment in which value appears. Keep personal applications and external agents outside the boundary unless the system intentionally owns them.

## 2. Build the use-case landscape

Cover each independently valuable owner objective with a distinct use case. Use an encompassing journey only to compose genuinely included outcomes. For every use case state:

- actors and objective;
- meaningful inputs or preconditions;
- successful result;
- refusal and failure outcomes;
- visible state effect or guaranteed non-effect;
- evidence that discriminates success from failure.

Do not create a use case for every API, MCP tool, command, framework hook, or transport exchange. Those
surfaces realize owner outcomes; they do not define the outcome landscape. A platform limitation may
bound feasible behavior, but it becomes product meaning only when a caller can observe the
difference or the repository intentionally selects that realization boundary.

Do not infer system responsibilities from a product name, acronym, framework analogy, or predecessor implementation. Establish the owner's meaning first. A term that resembles a known architecture pattern is still domain vocabulary until current behavior requires that architecture.

## 3. Establish domain meaning and owned state

Introduce identity, vocabulary, relationships, invariants, and state ownership needed by the behavior. Keep conceptual state independent from storage, serialization, transport, and deployment. Ensure every owned state has governing behavior and observable consequences.

Prefer existing natural identity before adding UUIDs, names, versions, statuses, or lineage. Prefer a
derived feature when another authoritative fact already determines the value. A proposed value or
captured copy is not automatically a second domain occurrence.

Distinguish absent, empty, unknown, not applicable, and undecided. Optional multiplicity expresses a
permitted absence in system instances, not uncertainty in the design process. Keep an unresolved
choice in the PR or issue unless the product itself must represent that uncertainty.

## 4. Derive functional behavior when it adds meaning

Derive actions from use cases and requirements only when decomposition reveals shared behavior, ordering, state effects, failures, interactions, or verification needs. A black-box use case may remain undecomposed. Do not create a same-named action merely to satisfy a traceability convention. Preserve the owner-valued origin of every action that remains.

An action tree must add actual semantics, not only labels. Connect the information or control that justifies the decomposition. Multiplicity states how many usages may occur; it does not state the condition under which one occurs. If the condition, transformation, or result cannot yet be modeled clearly, retain the black-box use case and requirements instead of implying a partial algorithm.

Do not derive one action per external tool operation. Introduce functional refinement only when the
system must explain behavior inside its boundary; a framework call can remain a later realization of
an existing action or use case.

An intentionally selected external operation inventory is different from accidental API mirroring.
It may be modeled as callable actions performed by the system when stable discovery and invocation
are themselves current contract meaning. Keep those actions direct unless internal decomposition
adds ordering, shared behavior, state, or failure meaning. Progressive disclosure can justify two
actions when the first deliberately provides the bounded vocabulary needed to formulate the second.

## 5. Group capabilities before structure

Group related actions as functional capabilities without assuming code objects or runtime boundaries. Introduce a logical part only when at least one independently meaningful commitment requires it:

- lifecycle or identity;
- canonical state ownership;
- failure or invariant responsibility;
- external interaction;
- substitution or independent realization under current consideration.

Code maintainability alone does not justify a system part. Use performed actions for behavior a part carries out. Use allocations only when an independent source hierarchy must map to a distinct realization hierarchy. Add ports, interfaces, or flows only for intentional connected transfers.

Similarly, do not turn validation scopes, activity capture, bootstrap paths, archives, snapshots, or
API operations into subsystems merely because established software designs often do. First state the
owner-visible distinction; add structure only if the distinction has independent occurrence meaning.

## 6. Close requirements and verification

Requirements state stakeholder obligations and identify a compatible subject. Do not add a
requirement merely to restate a type, use case, or test. Satisfaction assertions identify the
selected logical satisfier; they do not prove satisfaction. Verification cases identify compatible
subjects and decisive evidence, including failures and non-effects. One verification scenario may
cover several compatible requirements, and one requirement may need several discriminating
scenarios. Keep the chain navigable without forcing equal counts:

`owner outcome -> use case -> optional functional refinement -> system responsibility -> requirement -> satisfier -> verification case`

Before handoff, trace the changed claims through contextual use cases, any refined actions, system
responsibility, applicable requirements, explicit satisfying features, and verification. Audit
unchanged neighboring elements only for dangling consequences. Names, counts, and package proximity
are not traceability. Do not infer a missing element merely because another layer has one.

Then walk important semantic chains in both directions. Every input selector must reach the output it controls, every returned value must identify the request or projection that authorized it, every state-changing outcome must reach its state and history effects, and every reference to shared information must resolve to one authoritative occurrence. When a subtype family is collapsed into a kind or scope value, preserve the distinctions as kind-compatible content rules and verification.

For every consequential claim, exercise three examples before handoff:

1. the smallest accepted instance;
2. the smallest refusal or failure with its promised non-effects;
3. the smallest counterexample that would expose ambiguous ownership, cardinality, projection, transition, or responsibility.

If those examples require a concept the model cannot express, close that gap before adding deeper structure. If the examples make an element irrelevant, remove it.

Use informal requirement documentation when the obligation is not expressed as a formal predicate. Introduce a constraint usage only with a complete predicate.

## 7. Review through Git

Treat model changes like code changes:

1. map each mandatory plan claim and non-goal to its authority and evidence;
2. validate the complete model;
3. inspect the diff for changed system meaning;
4. review requirements and verification closure;
5. perform plan-conformance, adequacy, subtraction, and repository-truth reviews;
6. fix findings and repeat the full review sequence until it reaches a clean fixed point;
7. explain consequential tradeoffs in the PR;
8. merge through ordinary repository review.

Do not duplicate review state inside model elements. Put unresolved work in issues or the PR discussion.

## Historical material

Consult predecessor artifacts only when current work explicitly needs historical comparison or recovery. Preserve current compatibility meaning, not predecessor architecture by default.
