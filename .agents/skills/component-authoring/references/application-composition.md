# Application Composition

Model an application separately from reusable component libraries.

- Use an ordinary application package that imports reusable library packages.
- Use part usages for the component occurrences that play roles in the application.
- Bind retained `ref part` collaborator roles to the actual application part occurrences. Binding
  is correct here because both features denote the same occurrence.
- Supply invocation-scoped dependencies through typed action inputs; do not add a permanent role
  solely because one operation receives a collaborator.
- Put application-specific request shaping and workflows in application façade actions, not in
  reusable stores or registries.
- Use use cases for actor-visible outcomes rather than method inventories.
- Put whole-system invariants with the component or application that has authority to enforce them.
- Use action decomposition and successions only for externally meaningful application orchestration.
- Model façade-to-component and adapter-to-façade delegation as nested performed actions. Preserve
  request/result mappings with typed bindings or flows and use allocation for logical-to-realization
  traceability.
- Use allocations to map logical elements to implementation, deployment, or runtime realizations.
- Put implementation bindings on concrete realization definitions/usages, not reusable logical
  component definitions.
- Keep transports such as MCP, HTTP, CLI, and SDKs in realization packages unless their interaction
  semantics are part of the logical application contract.
- When connected interaction is modeled, define typed ports, interfaces, transferred items, and
  flows. Do not use an empty port or interface as generic software API notation.
- Define reusable views for composition, behavior, use cases, verification, and realization.
  Define viewpoints only when named stakeholder concerns constrain those views.

Alternative in-process, message-oriented, distributed, or other realizations may map the same
logical roles and actions without changing the component contracts solely because invocation
mechanics differ.
