# Model-first engineering vision

Vellis is both a useful, individually owned application and an open demonstration of model-first
software engineering for the agentic era.

Humans own product intent, architectural judgment, tradeoffs, and acceptance. Agents help express
that intent in textual SysML v2, check the language and consequences, generate source, and gather
verification evidence. The working loop is:

1. Express a small owner-valued change in the model.
2. Validate it against the pinned SysML/KerML language resources.
3. Resolve decisions that require human judgment.
4. Select an implementation-authorizing vertical slice and its verification objectives.
5. Generate the source and tests for that slice.
6. Verify the result and keep public guidance synchronized.

The model is an engineering definition, not a transcription of code. It captures observable
behavior, conceptual state, invariants, requirements, and intentional structure. Algorithms,
storage layouts, transports, frameworks, and deployment choices remain absent until they matter to
the product or are deliberately selected.

The measure of success is a turnkey personal application and a repository whose model-to-running-
system flow is easy to inspect, understand, and trust. Added machinery must earn its place through
a present use case, requirement, invariant, failure boundary, or verification need.
