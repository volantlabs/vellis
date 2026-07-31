---
name: sysml-reference
description: Ground textual SysML v2 and KerML authoring, review, construct selection, language-semantics decisions, official citations, and validator diagnosis in the repository's checksum-pinned specification corpus. Use whenever model work depends on precise parts, features, actions, bindings, flows, ports, interfaces, states, constraints, requirements, views, imports, multiplicities, specialization, ownership, or other SysML/KerML meaning.
---

# SysML and KerML Reference

Use the pinned official specifications as the language authority. The generated page corpus is a searchable projection and must never be edited by hand.

## Retrieval Workflow

1. Start with the ranked natural-language finder:

   ```text
   just model-reference-find "<question>" [sysml-2.0|kerml-1.0] [limit]
   ```

2. Inspect the best page and the smallest adjacent page set needed to understand the clause. Check page frontmatter for `extraction_warnings` before relying on questionable text.
3. Follow normative cross-references into SysML or KerML instead of inferring missing semantics.
4. If the first query ranks poorly, reformulate once with terminology learned from the best result, then inspect outline headings. Use raw page search only for an exact phrase, identifier, or section number.
5. Inspect the pinned PDF when figures, tables, typography, or extraction warnings affect meaning.
6. Report the specification, section, printed page, and physical PDF page for consequential conclusions.

Always distinguish:

- normative language clauses;
- informative examples or annex material;
- repository or Vellis conventions;
- agent inference.

Parser acceptance is not semantic proof, and semantic validity is not architectural approval.

## Validator Diagnosis

Run the current full-model workflow with `just model-check`. For an error:

1. isolate the first diagnostic;
2. identify the construct involved;
3. retrieve its normative section;
4. distinguish a model error, import/order error, repository convention, and validator limitation;
5. create a temporary minimal model only when isolation requires it;
6. do not weaken a valid model solely to placate the parser without recording the compatibility decision.

## Specification Baseline Updates

A language-baseline change is intentional and human-approved:

1. update the pinned URL, document identity, and checksum;
2. run `just model-setup`;
3. run `just model-reference-render`;
4. inspect the corpus diff;
5. run `just model-reference-check` and `just model-check`;
6. obtain human approval before accepting the new baseline.

Do not create or maintain a second language summary inside this skill.
