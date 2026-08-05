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

Names are the other trap. SysML v2 names concepts differently from ordinary systems-engineering usage: states rather than modes, constraints rather than rules, specialization rather than inheritance, "Definition and Usage" rather than variability. If a search returns nothing convincing, the query is probably using the wrong word rather than asking about something absent. Run `just model-reference-concepts` for the full construct inventory, pick the name, and search again.

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
