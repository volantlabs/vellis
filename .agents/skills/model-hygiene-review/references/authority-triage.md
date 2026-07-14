# Authority Triage

Use evidence to classify a difference before proposing any mutation.

## Evidence order

1. Identify the accepted model element, lifecycle, owner, normative requirement, satisfier, and
   verification objective.
2. Inspect public protocols, externally observable implementation behavior, black-box tests,
   adapters, and active consumers.
3. Inspect chronology and predecessor contracts. A pre-model implementation may expose migration
   loss; a post-model implementation may embody an intentional but unmodeled decision or ordinary
   drift.
4. Consult the official SysML/KerML corpus for language semantics only. The language specification
   cannot decide Vellis product behavior.
5. Check whether a concrete realization declares a lossless codec or normalization before calling
   non-isomorphic shapes drift.

## Classifications

- `model_drift`: the accepted model lost or contradicts established intended public behavior.
- `implementation_drift`: the realization violates a settled model or predecessor contract.
- `intentional_codec`: logical and implementation shapes differ through a declared lossless map.
- `intentional_implementation_freedom`: the difference is private and does not affect the modeled
  boundary, state, invariant, failure, or composition semantics.
- `tooling_gap`: a validator, projection, checker, or resolver reports misleading closure or misses
  a mechanically decidable mismatch.
- `evidence_gap`: the contract may be correct, but its bound evidence does not establish it.
- `human_decision_required`: sources conflict or leave externally meaningful behavior unsettled.

## Decision rules

- Do not let a passing test override an accepted contract; first ask what the test actually proves.
- Do not let accepted status hide migration loss, incorrect SysML semantics, or an ambiguity that
  independent implementers cannot resolve.
- Treat names, types, multiplicities, defaults, failure families, state effects, ordering, and
  invariant changes as public until evidence shows otherwise.
- Treat tuple/object encodings, absent-to-default normalization, and language-specific exception
  inheritance as realization details only when the mapping is explicit and lossless.
- Require a human owner for a genuine accepted-contract change. A correction that restores an
  already approved predecessor meaning still needs the evidence recorded, but does not invent a new
  boundary.

## Finding template

```text
Finding:
Classification / confidence:
Model evidence:
Implementation and consumer evidence:
History or predecessor evidence:
SysML/KerML basis (if relevant):
Compatibility and invariant impact:
Proposed authority and remediation:
Verification required:
Human decision required: yes/no
```
