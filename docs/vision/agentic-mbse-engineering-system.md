# Model-based engineering vision

Vellis uses a durable engineering model to let people spend more time on system intent, boundaries,
tradeoffs, and acceptance while agents handle more translation and consistency work.

Textual SysML v2 is the normative design for component and application structure, public behavior,
abstract state, invariants, requirements, composition, and verification. Implementations remain
independent artifacts: Python is the first realization, but any implementation that satisfies the
modeled black-box contract is valid.

## Working relationship

Humans are responsible for product intent, architectural judgment, unresolved tradeoffs, and final
acceptance. Agents help by proposing model changes, checking their consequences, producing or
reviewing realizations, generating projections, and gathering verification evidence.

The useful loop is:

1. Express the intended system change in the model.
2. Validate structure, behavior, requirements, composition, and affected contracts.
3. Review the decisions that require human judgment.
4. Implement or update realizations independently of the model's internal representation.
5. Verify observable conformance and attach useful evidence.
6. Regenerate explanatory and machine-readable projections.

The model should make questions about ownership, dependencies, effects, invariants, composition,
and verification answerable without reconstructing intent from code, tickets, or prose.

## Boundaries

The model is a high-level engineering blueprint, not a transcription of source code. It captures
detail when that detail affects legal invocation, observable results, abstract state, invariant
preservation, substitutability, composition, or verification. Private algorithms, helper structure,
storage layout, framework mechanics, and language-specific inheritance normally remain realization
choices.

SysML is the component and application design authority. Generated references explain that model;
operational guides teach people how to use a realization; implementation bindings and evidence
connect the design to code and validation. Temporary plans, historical narratives, and speculative
ontologies do not become permanent repository artifacts merely because an agent produced them.

## Measure of success

This approach succeeds when the model is precise enough to design, compose, independently realize,
and verify functionally equivalent systems while remaining substantially easier to reason about
than their implementations. Additional process or model-management machinery should be introduced
only when a demonstrated engineering need justifies it.
