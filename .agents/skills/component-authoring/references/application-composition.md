# Application Composition

Model an application separately from reusable components.

- Use an ordinary application package that imports reusable component library packages; do not put
  application roles or workflows in the library umbrella.
- Use part usages for component roles.
- Satisfy every required capability with an explicit dependency to a compatible provided feature.
- Put app-specific request shaping and workflows in application facade actions, not reusable stores.
- Use use cases for actor-visible outcomes rather than method inventories.
- Use allocation for logical-to-implementation realization.
- Put implementation bindings on concrete realization definitions/usages and allocations, not on
  reusable logical component definitions.
- Keep transports such as MCP, HTTP, CLI, and SDKs in realization packages unless transport is the
  application's logical purpose.
- When connected interaction is modeled, type port features with transferred items, define
  conjugate-compatible interface ends, and state flows that matter. Do not add an empty port or
  interface merely as a diagrammatic API symbol.
- Let alternative realization packages map the same logical roles and capabilities to in-process,
  message-oriented, distributed, or other runtimes without changing the application or component
  contracts solely because the invocation mechanism differs.
- Use action successions only where application-visible ordering matters.
- Keep whole-system invariants with the controller or application that owns their enforcement.
