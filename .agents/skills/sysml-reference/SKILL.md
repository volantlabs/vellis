---
name: sysml-reference
description: Ground textual SysML v2 and KerML authoring, review, language-semantics decisions, construct selection, and official-validator diagnosis in the repository's checksum-pinned specification corpus. Use for questions or changes involving parts, references, features, actions, bindings, successions, flows, ports, interfaces, states, constraints, requirements, views, imports, multiplicities, specialization, or other SysML/KerML syntax and semantics.
---

# SysML Reference

Use the committed page corpus as a searchable projection of the pinned official PDFs. Treat the
PDFs as authoritative and the Markdown as generated retrieval material.

## Workflow

1. Unless the request already supplies an exact specification section or page, the first corpus
   command **must** be the ranked, outline-aware finder. Pass the modeling question or a concise
   description, not just one generic word:

   ```sh
   just model-reference-find "<question or construct description>"
   ```

   Do not replace this first step with a broad `rg` over `pages/`. The finder is designed to handle
   natural wording without loading every textual match.
2. Review the ranked section titles and snippets. Open the best page, then read only the adjacent
   pages needed to finish the section. The finder routes to evidence; its rank is not an answer.
   If one specification is clearly in scope, rerun with `--specification sysml-2.0` or
   `--specification kerml-1.0` before broadening the search.
3. If results are broad or use different terminology, search outline headings before raw page text:

   ```sh
   rg -n -i '<construct or section phrase>' reference/specifications/{sysml-2.0,kerml-1.0}/index.md
   ```

   Use raw `rg` over `pages/` only for exact phrases, identifiers, or a cited section number.
4. Follow normative cross-references between SysML and KerML. Search by both the construct name and
   any referenced section number, and prefer the normative Clause 8 definition when Clause 7 is
   explicitly informative.
5. Inspect the pinned PDF under `.cache/sysml/formal/` when a table, figure, mathematical layout,
   indentation, or questionable extraction affects the conclusion. Run `just model-setup` if it is
   absent.
6. Separate the result into:
   - normative SysML or KerML semantics supported by cited sections and pages;
   - informative examples in the specifications;
   - Vellis repository profile or modeling conventions;
   - explicit inference where the sources do not directly decide the question.
7. State the reference basis for every consequential conclusion using specification, section, and
   printed or physical page. Never present training-memory recall as specification evidence.
8. After changing a model, run the narrow scoped check while editing and the official validation
   gate required by the repository before completion.

Before answering, verify that you can report the finder query (or the exact user-supplied citation),
the smallest sufficient page set, each source's normative or informative status, any Vellis
convention used, and every inference. If the pages read are much broader than the pages cited,
narrow the retrieval before answering.

## Corpus Rules

- Never edit files under `reference/specifications/` manually. Regenerate them with
  `just model-reference-render` after an intentional pinned-specification update.
- Use `just model-reference-check` to prove that Markdown, outlines, indexes, and manifests match
  the pinned PDFs.
- Do not infer section semantics merely from an outline title. Read the source text and its stated
  cross-references.
- Do not treat successful parsing as proof that a modeling interpretation is correct; the official
  validator and the specification provide different evidence and both are required.
