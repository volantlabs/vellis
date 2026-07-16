---
name: model-hygiene-review
description: Audit accepted SysML v2 component or application models against implementations, protocols, consumers, tests, generated evidence, predecessor contracts, and git history before proposing remediation. Use for periodic model hygiene, suspected model/implementation drift, migration-loss reviews, verification-closure audits, realization-codec review, or possible SysML-native modeling misuse.
---

# Model Hygiene Review

Review divergence without assuming that either the accepted model or current implementation is
automatically correct. Produce an advisory authority assessment before changing either side.

## Workflow

1. Run the deterministic evidence collector for the requested stable ID. Omit the target only when
   the user requests every accepted component:

   ```sh
   just model-audit component.rtg.query
   ```

   Read the JSON bundle under `build/model-audits/`. Treat comparisons as leads, not findings.
   Use `architecture-projection` to add an ignored impact and verification-coverage projection when
   dependency direction or traceability is part of the audit; treat it as evidence, not authority.
2. Read `references/authority-triage.md` completely. Identify the model lifecycle, owner,
   requirements, satisfiers, realization binding, codecs, verification cases, and exact evidence
   nodes.
3. Inspect the public implementation protocol, behavior, black-box tests, adapters, and consumers.
   Do not infer a contract from private helpers. Flag non-state-transfer operations that export,
   clone, hash, scan, or retain complete canonical state for validation, atomicity, summaries, or
   recovery; distinguish semantically required global traversal from scaffolding that duplicates
   the traversed state. Check whether transient recovery data survives beyond one invocation and
   whether tests observe read/allocation scaling rather than only action names.
4. Inspect `git log --follow`, the introducing commits on both sides, and any predecessor accepted
   specification. Determine whether code predates the model, implements a later decision, or merely
   drifted.
5. Invoke `sysml-reference` only when syntax or language semantics affect the conclusion. Report
   the specification, section, printed or physical page, and whether the source is normative or
   informative. Do not use training recall as specification evidence.
6. Classify every material difference using the authority-triage reference. Separate an explicit
   realization codec or intentional implementation freedom from public semantic drift.
7. Report compatibility impact, confidence, evidence on each side, proposed authority, and the
   smallest verification needed before remediation.

## Safety Rule

This skill is review-only. Do not edit the model, implementation, tests, generated views, or
evidence while performing the audit. If accepted behavior is unresolved, classify it as
`human_decision_required` and pause for the human owner. Successful parsing, tests, or evidence
reference resolution are evidence, not proof of semantic agreement or verification closure.

## Output

For every finding report:

- stable component and affected model/implementation symbols;
- classification and confidence;
- model, implementation, consumer, history, and specification evidence as applicable;
- compatibility and state/invariant impact;
- proposed authority and remediation;
- verification needed and whether human approval is required.

Conclude with unresolved decisions and the exact commands used. Keep generated audit bundles
ignored and advisory; do not add them to CI or commit them.
