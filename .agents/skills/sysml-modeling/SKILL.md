---
name: sysml-modeling
description: Design, revise, review, simplify, or prepare implementation-authorizing slices of textual SysML v2 system models. Use for system context, owner-valued use cases, domain vocabulary, requirements, behavior, structure, verification objectives, model quality, or subtraction reviews; pair with sysml-reference whenever a decision depends on SysML or KerML syntax or semantics.
---

# SysML Modeling

Shape system intent into the smallest coherent textual SysML v2 model that can support human decisions and black-box verification.

## Workflow

1. Establish the current product intent, the model's authority, and whether the affected content is a working draft or an approved slice.
2. Begin with the system context: subject, owner, actors, objectives, and outcomes the owner values.
3. Express black-box use cases and observable behavior before proposing internal parts or services.
4. Introduce domain vocabulary and state only when the behavior needs identity, ownership, relationships, or durable meaning.
5. Add requirements, satisfiers, and verification objectives that close the reasoning for the intended slice.
6. Add white-box structure incrementally. Every internal element must be justified by a use case, requirement, invariant, or verification need.
7. Use `$sysml-reference` before a consequential construct or language-semantics decision. Apply `$rtg-schema-design` as well for RTG concepts or schemas.
8. Run the official validator. Treat successful validation as language evidence, not architectural approval.
9. Perform a subtraction review: remove speculative layers, duplicate representations, placeholder contracts, and detail that does not change a current claim.
10. Use `$documentation-sync` after model, workflow, tooling, or public-status changes.

## Authorization Gate

Working-draft content explores intent; it does not authorize implementation. Implementation begins only after a human selects a coherent vertical slice, approves its product intent and tradeoffs, and approves verification objectives sufficient to judge the resulting behavior.

Do not mine predecessor code or models merely to fill gaps. Classify predecessor behavior deliberately as preserve, reconsider, or retire when it becomes relevant.

## References

- [Modeling workflow](references/modeling-workflow.md): context through authorization and predecessor disposition.
- [Modeling quality](references/modeling-quality.md): native construct use, state, behavior, representation, and verification closure.
- [Simplicity review](references/simplicity-review.md): abstraction tests and final subtraction pass.
