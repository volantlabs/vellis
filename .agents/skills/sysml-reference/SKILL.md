---
name: sysml-reference
description: Ground textual SysML v2 and KerML authoring, software-system construct selection, official citations, semantic comparison, and validator diagnosis in the repository's checksum-pinned specification corpus. Use whenever model work depends on precise packages, features, parts, items, actions, performed actions, bindings, flows, ports, interfaces, states, constraints, requirements, satisfaction, verification cases, use cases, allocations, imports, multiplicities, specialization, ownership, derivation, reference, or other SysML/KerML meaning.
---

# SysML and KerML Reference

Use the pinned official specifications as the language authority. The corpus is generated from checksum-pinned sources into the ignored cache and must never be edited by hand.

## What answers which question

`just model-setup` provides four sources, and they answer different questions. Reaching for the wrong one is the most common way to waste a lookup.

| Source | Answers | How |
| --- | --- | --- |
| Specification | what a construct **means** | `just model-reference-find` |
| Model library | what **exists**, and what it specializes | same finder; hits are labelled `[library]` |
| Example models | what it **looks like** in working SysML | same finder; hits are labelled `[example]` |
| Pinned validator | what the parser **accepts** | `just model-probe`, `just model-check` |

Library and example hits are pinned-release evidence, not normative text. Cite them as such, and never present a worked example as though it were a clause.

## Prior knowledge is not evidence

SysML v1 and UML dominate training data, and SysML v2 displaced much of that notation. A construct you are confident about but cannot cite is an inference, and must be reported as one.

When a construct feels familiar, check that it exists before designing around it. `block`, `ValueType`, value properties, associations, flow ports, and stereotypes are all v1 notation with different v2 replacements. The parser rejects them and the diagnostic names the replacement, so an uncertain construct is cheaper to probe than to reason about.

Names are the other trap, and the maps below exist for it: SysML v2 names concepts differently from ordinary systems-engineering usage. If a search returns nothing convincing, the query is almost always using the wrong word rather than asking about something absent.

## Naming the construct

### From what you are trying to do, to what SysML v2 calls it

Search reaches the right clause reliably once the construct is named, so naming is
the step that decides whether a lookup succeeds. Searching in your own words often
cannot work: "mode", "rule" and "piece" appear on zero of 695 specification pages.
Map the intent first, then search by the construct name.

| If you are trying to express | The construct is | Clause |
| --- | --- | --- |
| a thing the system is made of, that is part of it | Parts | 7.11 |
| a thing that flows through, is acted on, or is exchanged | Items | 7.10 |
| a value, quantity, or characteristic with no identity | Attributes | 7.7 |
| a fixed set of allowed values | Enumerations | 7.8 |
| a point of interaction on something | Ports | 7.12 |
| a link between things | Connections | 7.13 |
| an agreed interaction surface between parts | Interfaces | 7.14 |
| something moving from one place to another | Flows and Messages | 7.16 |
| something the system does | Actions | 7.17 |
| behaviour that depends on a mode or condition, and changes between them | States | 7.18 |
| a computation that returns a result | Calculations | 7.19 |
| a rule that must always hold | Constraints | 7.20 |
| something required of the system, and who satisfies it | Requirements | 7.21 |
| a study, trade-off, or quantitative evaluation | Analysis Cases | 7.23 |
| evidence that a requirement is met | Verification Cases | 7.24 |
| what a user wants to accomplish with the system | Use Cases | 7.25 |
| a filtered presentation for a stakeholder concern | Views and Viewpoints | 7.26 |
| annotation, rationale, tags, or language extension | Metadata | 7.27 |
| responsibility handed from one element to another | Allocations | 7.15 |
| that one element depends on another | Dependencies | 7.3 |
| documentation attached to an element | Annotations | 7.4 |
| grouping and namespacing of a model | Namespaces and Packages | 7.5 |
| a reusable definition and its contextual uses | Definition and Usage | 7.6 |
| a family of variants, or a product line | Variability (Definition and Usage) | 7.6 |
| something occurring over time, or an individual instance | Occurrences | 7.9 |

Language mechanics, when the question is about the type system rather than the
system being modelled: Generalization, Subsetting, Redefinition, Multiplicities,
Features, Feature Values, Types, Classifiers, Expressions.

The left column is ordinary engineering intent, not SysML vocabulary; that is the
point. If a question does not fit a row, take the closest one and search by its
construct name rather than by the question's own words.

### Which specification answers it

SysML describes the systems layer; KerML describes the type system underneath.
Searching the wrong one wastes the query, and the split is stable.

- **SysML** — Parts, Items, Ports, Connections, Interfaces, Actions, States,
  Flows, Calculations, Constraints, Requirements, Use Cases, Analysis and
  Verification Cases, Views, Metadata, Allocations, Occurrences, Attributes,
  Enumerations, Definition and Usage, Namespaces and Packages.
- **KerML** — Types, Classifiers, Features, Feature Values, Multiplicities,
  Specialization, Structures, Behaviors, Functions, Expressions, Associations,
  Connectors, Namespaces, Packages.

A few concepts are covered by both, namespacing among them: SysML restates them
for the systems layer while KerML defines the underlying mechanism. When both
apply, read SysML first and follow its cross-reference down.

Rule of thumb: if the question is about the system being modelled, search SysML.
If it is about how the language types and relates things, search KerML.

### Which library file answers it

The specification never lists library declarations, so "what exists" and "what
does this implicitly specialize" are library questions, not clause questions.

| Looking for | Library |
| --- | --- |
| String, Boolean, Real, Integer, Natural | `Kernel Data Type Library/ScalarValues.kerml` |
| units, quantities, physical values | `Domain Libraries/Quantities and Units/` (ISQ, SI) |
| what a `part def` / `item def` / `action def` implicitly specializes | `Systems Library/<Concept>.sysml` |
| the base types of the language itself | `Kernel Semantic Library/Base.kerml`, `KerML.kerml` |
| callable functions and operators | `Kernel Function Library/` |

### Distinctions worth resolving before choosing

These are the decisions that actually recur. Both options are valid SysML, so the
parser cannot settle them; retrieve the clause and decide on meaning.

| Question | Turns on |
| --- | --- |
| `item def` or `part def`? | `Part :> Item`. A part is a structural constituent of the system; an item flows through, is exchanged, or is acted on. |
| `attribute def` or `item def`? | Identity. Attributes are values and have none; items do. |
| `part x` or `ref part x`? | Ownership. Plain means composite and lifetime-bound; `ref` means it exists independently. |
| `:>` or `:>>`? | Subsetting keeps the inherited feature alongside the new one; redefinition replaces it. |
| action or use case? | A use case is what a user wants to accomplish; an action is behaviour the system performs. |
| connection or interface? | An interface is the agreed interaction surface between ports; a connection is a link between things. |
| allocation or satisfaction? | Allocation hands responsibility to a realizing element; satisfaction claims a requirement is met. |
| constraint or requirement? | A constraint is a rule that must hold; a requirement is an obligation on the system, with a subject and satisfiers. |

The full construct inventory, generated from the pinned release so it cannot drift:

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
- Establish the product claim before retrieving a construct. A specification clause explains the
  meaning of an element; it does not create a need for that element.
- Search first for the semantic commitment, not the project's noun. “Can the same occurrence be shared?” is a better starting question than “How should a ledger tail be modeled?”
- Cite the clause that supports the exact commitment being made. A nearby keyword hit or informative example is not enough.
- Apply the clause at the instance level: state what becomes owned, shared, performed, ordered, conditional, satisfied, or verified.
- Do not copy an example's surrounding architecture when only one language construct is relevant.
- If the specification does not decide the product design, label the remaining choice as repository convention or inference rather than laundering it through a citation.

## Evidence workflow

1. State the semantic question independently of Vellis vocabulary: ownership, identity, lifecycle, behavior performance, responsibility, transfer, satisfaction, verification, or another language commitment.
2. Identify the smallest plausible construct set. Common comparisons include use case versus action,
   action versus performed action, abstract dependency versus included or performed behavior, item
   versus part, composite versus referential usage, owned versus derived versus reference feature,
   multiplicity versus conditional action control, binding versus flow versus interface, allocation
   versus satisfaction, requirement subject versus verification subject, and state behavior versus
   ordinary state.
3. Start with the ranked natural-language finder:

   ```text
   just model-reference-find "<question>" [<specification-id>] [limit]
   ```

4. Inspect the primary clause and the smallest adjacent page set needed. Check page-frontmatter `extraction_warnings` before relying on extracted text.
5. Follow necessary normative cross-references into SysML or KerML. If the first query ranks poorly, reformulate once with terminology discovered in the best result, then inspect outline headings. Use raw page search only for an exact phrase, identifier, or section number.
6. Compare the semantic commitments added by each candidate, including leaving the claim at a less
   formal authority level, and choose the least committal construct that expresses the required
   meaning. Check instance-level consequences: whether values may be shared, whether a nested action
   is actually performed, and whether multiplicity, binding, succession, or a guard carries the
   intended claim.
7. Inspect the pinned PDF when figures, tables, typography, or extraction quality matters.
8. Validate the selected textual form. Use `just model-probe "<snippet>"` to settle a syntax
   question against the pinned parser in about six seconds rather than reading grammar clauses.
9. Report the specification version and release tag, section, printed page, physical PDF page, and
   the concrete model commitment the clause supports. The pinned beta documents carry no OMG
   document number, so the version and release tag are the identity.

Always separate:

- normative specification clauses;
- informative examples or annex material;
- pinned model-library and example-model evidence;
- repository convention;
- agent inference.

Parser acceptance establishes neither full semantic proof nor design correctness. The model diff still requires engineering review.

## Validator diagnosis

Run the complete source set with `just model-check`. For an error:

1. isolate the first diagnostic;
2. identify the construct involved;
3. retrieve its normative clause and necessary cross-references;
4. distinguish model error, import or order error, repository convention, and validator limitation;
5. reduce to the smallest snippet that reproduces the diagnostic and run it through
   `just model-probe`; do not create temporary model files;
6. do not silently weaken a semantically correct model to placate the parser; record any validator-compatibility choice in the PR.

## Specification baseline changes

Treat a language-baseline change as an explicit PR:

1. update the pinned release tag, commit, version identity, and checksums;
2. run `just model-setup`, which fetches the pinned checkout and regenerates the corpus;
3. compare the reported page and outline counts against the lock, since the corpus is generated
   rather than committed and so has no reviewable diff;
4. run `just model-reference-check` and `just model-check`;
5. re-run the retrieval eval and confirm each register still meets its floor;
6. review the complete lock and model impact before merge.

Do not create or maintain a second bundled language summary in this skill.

## References

- [SysML v2 is not SysML v1](references/v1-displacement.md): displaced v1 and UML notation, and the
  forms that parse cleanly but mean something else, which no tooling here checks.
