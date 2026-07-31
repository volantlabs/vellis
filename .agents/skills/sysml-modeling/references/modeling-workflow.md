# Modeling Workflow

## 1. Frame the system

Record the subject being designed, its boundary, the owner whose outcomes matter, external actors, and the context in which value is produced. State assumptions and open decisions without turning them into product commitments.

## 2. Describe owner-valued behavior

Write use cases from actor objective to observable outcome. Include meaningful inputs, results, failures, and externally visible effects. Avoid internal services, adapters, queues, repositories, and protocols unless the behavior itself requires them.

## 3. Establish domain meaning

Introduce vocabulary only when a use case needs stable identity, typed facts, relationships, quantities, or state. Separate product concepts from possible storage or transport representations.

## 4. Close requirements

Put normative obligations in requirements with complete predicates. Identify the model elements expected to satisfy them and define subject-compatible verification objectives. Explanatory documentation is not a substitute for a requirement.

## 5. Select a vertical slice

A useful slice crosses context, behavior, domain meaning, requirements, satisfaction, and verification without depending on speculative breadth. Prefer the smallest slice that produces a complete owner outcome.

## 6. Authorize implementation

A human must approve:

- the owner outcome and boundary;
- consequential architecture and tradeoffs;
- the selected vertical slice;
- its verification objectives.

Parser acceptance and model completeness do not grant this approval.

## 7. Dispose of predecessor behavior

When historical behavior becomes relevant, classify it explicitly:

- **Preserve** because current users or product intent require it.
- **Reconsider** because the need remains but the old shape may not.
- **Retire** because it does not serve the new product.

Do not import historical concepts solely because they are available in git.
