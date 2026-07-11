# Model Organization

Use SysML packages to make ownership and dependency direction explicit.

## Package kinds

- Use a `library package` for reusable definitions intended to be imported by multiple models.
- Use an ordinary `package` for an application, a particular composition, a deployment or runtime
  realization, and project-local use cases or views.
- Use a KPAR or the repository's chosen interchange container to distribute a validated set of
  packages. The container is not a substitute for semantic package ownership.

## Recommended layers

Keep these concerns independently packageable:

1. A modeling foundation containing domain-independent conventions and typed metadata.
2. One or more reusable library packages containing component contracts and genuinely shared
   public semantics.
3. Application packages containing component roles, configuration, capability satisfaction,
   application actions, use cases, and application-owned invariants.
4. Realization packages mapping the logical model to languages, transports, runtimes, deployments,
   and concrete resources.

Dependencies point downward. A reusable library may import its modeling foundation. An application
may import libraries. A library must not import an application or an application-specific
realization.

Keep vocabulary at the narrowest layer that owns its meaning. Generic modeling metadata belongs in
the foundation; library-domain types belong in the library; a transport binding or tool registration
profile belongs in its runtime/adapter realization. Do not promote a one-application annotation into
the foundation merely because tooling consumes it.

## Library public surface

Use a small umbrella `library package` when consumers benefit from one stable import surface. Give
it `public import` relationships to the packages that constitute the supported library API. Use
`private import` for authoring dependencies and internal vocabulary that consumers should not
receive through the umbrella.

Keep each reusable component in its own library package even when an umbrella re-exports it. This
preserves narrow ownership, reviewability, and the option to package components separately later.

Do not turn the umbrella into a global type grab bag. A public type belongs with the component that
owns its meaning and invariants. Move a type into a shared library package only when multiple
components need the same semantics and no component is its natural owner.

## Runtime evolution

Keep logical actions, capabilities, state, and invariants independent of invocation topology unless
topology is observable contract meaning. A later message-oriented realization can introduce
ports, interfaces, messages, flows, routing, correlation, delivery, retry, ordering, or idempotency
semantics in separate reusable runtime library and realization packages.

Promote a runtime concept into a reusable library only when it has a stable contract and at least
one real composition need. Map logical capabilities to runtime interactions rather than changing
the component contract solely because the invocation mechanism changed.

## Compatibility and evolution

- Give public model elements stable identities independent of interchange UUIDs.
- Treat removal, renaming, multiplicity changes, strengthened preconditions, weakened guarantees,
  and incompatible value changes as library contract changes.
- Keep deprecated public definitions available while supported consumers remain.
- Validate application models against the packaged library artifact they claim to consume.
- Use qualified names at ownership boundaries and avoid relying on accidental transitive imports.
