---
name: sysml-reference
description: Ground textual SysML v2 and KerML authoring, software-system construct selection, implementation-facing model interpretation, official citations, semantic comparison, and validator diagnosis in an active checksum-pinned specification baseline. Use whenever model or implementation work depends on precise packages, features, parts, items, actions, performed actions, bindings, flows, ports, interfaces, states, constraints, requirements, satisfaction, verification cases, use cases, allocations, imports, multiplicities, specialization, ownership, derivation, reference, or other SysML or KerML meaning.
---

# SysML and KerML Reference

Use the project's active, pinned official specifications as language authority. Generated search
corpora, indexes, and extracted pages are derivative evidence and must never be edited as though they
were authority.

## Project binding

This skill defines a portable evidence method. Discover the project's local instructions and bind
the following capabilities before use:

| Capability | Purpose |
| --- | --- |
| Baseline identity | identifies the exact specification publication, version, release, commit, and checksums |
| Normative reference search | locates clauses and necessary cross-references by engineering question |
| Construct inventory | maps ordinary engineering intent to SysML and KerML terminology |
| Standard-library search | establishes which declarations exist and what they specialize |
| Example search | finds informative textual forms from the same release |
| Snippet probe | settles isolated syntax against the selected official validator |
| Complete model validation | checks the project's required authored model scope |

The capabilities may be supplied by a repository, an installed plugin, or another reproducible local
toolchain. Do not assume paths, command names, a command runner, document format, or source-control
workflow. If a required capability is unavailable, report the evidence limitation instead of
substituting recalled syntax, an unpinned summary, or a different language baseline.

## What answers which question

The sources answer different questions. Reaching for the wrong one is the most common cause of a
confident but unsupported decision.

| Source | Answers |
| --- | --- |
| Normative specification | what a construct means |
| Standard model library | what exists and what it specializes |
| Example and training models | what accepted textual usage looks like |
| Official validator | what the selected parser accepts |

Library and example hits are release-matched evidence, not normative text. Cite them as such, and
never present a worked example as though it were a clause. Parser acceptance establishes neither
semantic correctness nor model adequacy.

## Prior knowledge is not evidence

SysML v1 and UML dominate historical examples and much training data, while SysML v2 displaced much
of that notation. A construct recalled with confidence but not supported by the active baseline is an
inference and must be reported as one.

When a construct feels familiar, check that it exists before designing around it. Examples such as
block, ValueType, value properties, associations, flow ports, and stereotypes are v1 or UML notation
with different v2 replacements. An uncertain construct is cheaper to probe than to reason about from
memory.

Names are another trap: SysML v2 often names concepts differently from ordinary systems-engineering
usage. If a search returns nothing convincing, first map the intent to a construct and search again.

## Naming the construct

### From engineering intent to SysML v2

The headings below are conceptual routing, not fixed clause numbers. Confirm the exact section in the
active baseline before citing it.

| If you are trying to express | Search for |
| --- | --- |
| an occurrence representing all or part of a system, including a component or interacting actor, especially when it performs actions | Parts |
| an identifiable object that is part of, exists in, or flows through a system, including one transferred, stored, or acted on | Items |
| a value, quantity, or characteristic with no identity | Attributes |
| a fixed set of allowed values | Enumerations |
| a point of interaction on something | Ports |
| a link between things | Connections |
| an agreed interaction surface between parts | Interfaces |
| something moving from one place to another | Flows and Messages |
| something the system does | Actions |
| behavior that depends on mode or condition and changes between them | States |
| a computation that returns a result | Calculations |
| a predicate that must hold | Constraints |
| an obligation on a subject and who satisfies it | Requirements |
| a study, trade-off, or quantitative evaluation | Analysis Cases |
| evidence that a requirement is met | Verification Cases |
| what an actor wants to accomplish with the system | Use Cases |
| a filtered presentation for a stakeholder concern | Views and Viewpoints |
| annotation, rationale, tags, or language extension | Metadata |
| responsibility mapped from one element to another | Allocations |
| one element depending on another | Dependencies |
| documentation attached to an element | Annotations |
| grouping and namespacing of a model | Namespaces and Packages |
| a reusable definition and its contextual uses | Definition and Usage |
| a family of variants or a product line | Variability |
| something occurring over time or an individual instance | Occurrences |

For type-system mechanics rather than the system being modeled, search for Generalization,
Subsetting, Redefinition, Multiplicities, Features, Feature Values, Types, Classifiers, and
Expressions.

The left column is ordinary engineering intent. If a question does not fit a row, take the closest
construct and use the construct inventory before broad full-text searching.

### Which specification answers it

SysML describes the systems layer; KerML describes the type system underneath.

- **SysML** — Parts, Items, Ports, Connections, Interfaces, Actions, States, Flows, Calculations,
  Constraints, Requirements, Use Cases, Analysis and Verification Cases, Views, Metadata,
  Allocations, Occurrences, Attributes, Enumerations, Definition and Usage, Namespaces, and Packages.
- **KerML** — Types, Classifiers, Features, Feature Values, Multiplicities, Specialization,
  Structures, Behaviors, Functions, Expressions, Associations, Connectors, Namespaces, and Packages.

When both apply, read the SysML systems-layer meaning first and follow its normative cross-reference
into KerML. Rule of thumb: a question about the modeled system starts in SysML; a question about how
the language types, owns, or relates elements often continues in KerML.

### Which library file answers it

The normative prose may not list every standard declaration. “What exists?” and “what does this
implicitly specialize?” are library questions.

| Looking for | Typical standard-library area |
| --- | --- |
| String, Boolean, Real, Integer, Natural | scalar or kernel data types |
| units, quantities, and physical values | quantities and units domain libraries |
| implicit specialization of part, item, action, and other definitions | systems concept libraries |
| base language types | kernel semantic libraries |
| callable functions and operators | kernel function libraries |

Locate the exact file through the configured standard-library search; do not assume a checkout path.

### Distinctions worth resolving before choosing

Both options in these comparisons can be valid syntax. The validator cannot select the intended
meaning; retrieve the relevant clauses and decide from instance-level consequences.

Whenever omitted multiplicity is consequential, resolve every subsetted or redefined target usage
and retrieve the active normative multiplicity clause before deciding cardinality. Do not rely on a
remembered default: inherited constraints and the conditions for an implicit multiplicity must be
established from the current model and pinned baseline.

| Question | Turns on |
| --- | --- |
| item definition or part definition? | All parts are items. Use a part when an occurrence represents all or part of a system or is normally modeled as an action performer; parts may represent people, organizations, software, hardware, facilities, or external systems. Use an item when its relevant role is being part of, existing in, flowing through, transferred, stored, or acted on by a system. Items may themselves have attributes, states, and nested items, so state or lifecycle alone does not select a part. Confirm specialization in the active library. |
| attribute definition or item definition? | Identity. Attributes are values; items are occurrences. |
| composite usage or reference usage? | Ownership and lifetime versus independent existence and sharing. |
| subsetting or redefinition? | Whether the inherited feature remains alongside a specializing feature or is replaced in context. |
| action or use case? | Actor-valued objective versus behavior the system performs. |
| connection or interface? | A link between things versus a specified interaction surface. |
| allocation or satisfaction? | Mapping responsibility versus claiming that an obligation is met. |
| constraint or requirement? | A predicate that holds versus an obligation on a subject with satisfiers and evidence. |
| part definition, package, or interface definition for a software boundary? | What the boundary owns. A part when it owns governed state, lifecycle, or failure responsibility. A package when it only groups a namespace or viewpoint and owns nothing. An interface definition when it fixes what one part may assume about another without owning either side. |
| dependency or connection for permitted direction? | Whether anything flows. A dependency states that one element relies on another and constrains direction only. A connection is a link along which interaction occurs, so it needs an intentional interaction to justify it. |
| owned state or referenced state at subsystem granularity? | Which part the model holds responsible when the value is wrong. Composite ownership names one responsible part; a reference lets several parts read state one of them owns. |
| when does a private call boundary warrant a port? | Whether the project means to fix the assumption across independent implementation work. A private code call is not an interaction surface by itself; a boundary the project intends to hold, and states a prohibition for, is. |

Use the active construct inventory rather than treating this table as exhaustive.

<!-- generated: construct inventory -->
Action Definitions · Action Performance · Actions · Allocation · Allocations · Analysis ·
Analysis Cases · Annotations · Assignment Actions · Associations · Asynchronous Messaging ·
Attributes · Behaviors · Binding Connectors · Calculations · Cases · Classes · Classifiers ·
Conditional Succession · Connections · Connectors · Constraints · Control · Data Types ·
Definition and Usage · Dependencies · Elements and Relationships · Enumeration Definitions ·
Enumerations · Expressions · Feature Values · Features · Filtering · Flows · Flows and
Messages · Functions · Generalization · Individuals · Interactions · Interfaces · Items ·
Language Extension · Metadata · Multiplicities · Namespaces · Namespaces and Packages ·
Occurrences · Opaque Actions · Packages · Part Definitions · Parts · Ports · Redefinition ·
Requirements · State Definitions · State Exhibition · States · Structures · Subsetting ·
Terminate Actions · Transitions · Types · Use Cases · Variability · Verification ·
Verification Cases · Views · Views and Viewpoints
<!-- end generated -->

## Evidence guardrails

- Retrieve evidence before committing to a consequential construct, not only after validation fails.
- Establish the system claim before retrieving a construct. A clause explains an element; it does not
  create a need for that element.
- Search for the semantic commitment, not the project's noun. “May the same occurrence be shared?”
  is more useful than asking how to model a project-specific container.
- Cite the clause that supports the exact commitment. A nearby keyword hit or informative example is
  not enough.
- Apply the clause at instance level: state what becomes owned, shared, performed, ordered,
  conditional, satisfied, or verified.
- Do not copy an example's surrounding architecture when only one language construct is relevant.
- If the specification does not decide system design, label the remaining choice as project
  convention, stakeholder decision, or inference rather than laundering it through a citation.

## Implementation-facing interpretation

When a language question arises while planning or reviewing code, report separately:

1. the normative construct meaning supported by the retrieved clause;
2. the concrete instance-level commitment the current model makes;
3. the implementation mapping, explicitly labeled as a project choice or inference.

Also state the nearest tempting mapping the construct does not establish. A package does not by
itself select a code package or deployable layer; a part does not select a service or class; an item
does not select a record, transfer object, or table; an action does not select a method; a port does
not select a private code interface; and a verification case does not require one same-named
automated test. A project may still select such a mapping intentionally; that is project authority
rather than language entailment, and must be recorded as such.

Judge a code representation by semantic equivalence at the modeled instance level. Several code
structures may realize the same SysML commitment. Conversely, matching names or generated shapes do
not establish conformance when lifecycle, sharing, cardinality, control, state, timing, interaction,
or evidence differs.

Resolve language meaning before a whole-model planner creates dependency or coverage claims. A
campaign record may point to qualified model elements and a pinned baseline, but it does not prove
that a reference is semantically complete or that two elements may be implemented independently.
Return those questions to the current model and normative clauses rather than inferring meaning from
the campaign graph.

## Evidence workflow

1. State the semantic question independently of project vocabulary: ownership, identity, lifecycle,
   behavior performance, responsibility, transfer, calculation, state, satisfaction, verification,
   or another language commitment.
2. Identify the smallest plausible construct set. Common comparisons include use case versus action,
   action definition versus performed action, item versus part, composite versus referential usage,
   owned versus derived versus reference feature, multiplicity versus conditional control, binding
   versus flow versus interface, allocation versus satisfaction, requirement subject versus
   verification subject, and state behavior versus an enumerated value.
3. Use the configured natural-language reference search with the engineering question and active
   specification identity.
4. Inspect the primary clause and the smallest adjacent section set needed. Check extraction warnings
   before relying on generated text.
5. Follow necessary normative cross-references into SysML or KerML. If ranking is poor, reformulate
   once with terminology discovered in the best result, then inspect headings. Use raw text search
   only for an exact phrase, identifier, or section.
6. Compare the commitments added by each candidate, including leaving the claim at a less formal
   authority level. Choose the least committal construct that expresses required meaning, and check
   ownership, occurrence, performance, multiplicity, binding, succession, and guard consequences.
7. Inspect the authoritative publication directly when figures, tables, typography, or extraction
   quality matters.
8. Validate the selected textual form with the configured snippet probe.
9. Report the active baseline identity, clause or section, source location or page when available,
   and the concrete model commitment supported.

Always separate:

- normative specification clauses;
- informative examples or annex material;
- release-matched standard-library evidence;
- project convention or stakeholder decision;
- agent inference.

## Validator diagnosis

Run complete model validation through the configured official validator. For an error:

1. isolate the first diagnostic;
2. identify the construct involved;
3. retrieve its normative clause and required cross-references;
4. distinguish model error, import or evaluation-order error, project convention, and validator
   limitation;
5. reduce to the smallest snippet that reproduces the diagnostic and use the configured snippet
   probe without adding temporary product-model files;
6. do not silently weaken a semantically correct model to placate a parser. Record any
   validator-compatibility choice in the project's review record.

## Specification baseline changes

Treat a language-baseline change as an explicit, reviewable engineering change:

1. update the pinned publication, release or commit identity, and checksums;
2. fetch or regenerate derivative corpora, indexes, library metadata, and validator bindings;
3. compare expected corpus and outline metadata because generated evidence may have no reviewable
   source diff;
4. validate the reference package and complete authored model scope;
5. rerun retrieval evaluations or known semantic probes;
6. review model, citation, library, and validator impact before integration.

Do not maintain a second bundled language summary as a substitute for the pinned official baseline.

## References

- [Modeling altitude](references/altitude.md): one subject expressed at process, system, and software
  altitude, so the difference is visible rather than described.
- [SysML v2 is not SysML v1](references/v1-displacement.md): displaced v1 and UML notation, and valid
  v2 forms whose meaning is easy to misread.
