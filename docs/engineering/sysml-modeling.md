# SysML v2 Modeling

Textual SysML v2 under `model/` is the normative design for Bibliotek and Vellis. Generated pages
under `generated/reference/` explain that model for humans; they are projections, not a second
contract source.

`generated/model/verification-evidence.json` resolves every modeled evidence group to the
exact test nodes currently available to evaluate it. Repository checks reject accepted component
evidence groups that resolve only to a path with no concrete tests.

`generated/model/formal-model-index.json` is produced by the official Java parser and records
the packages, element kinds, and named contract elements it resolves. Repository checks compare
every authored public definition and requirement with this inventory. The complementary
`generated/model/conformance-objectives.json` projects verification subjects, stable requirement
IDs, and concrete evidence nodes into a language-neutral implementation handoff.

The official Java pilot is pinned and qualified for headless syntax, linking, and semantic
validation. Human and technical acceptance are complete, and textual SysML is the normative design
authority. `model/migration/cutover-status.json` retains the completed transition record.

## Start here

To understand an existing design, begin with the generated
[`Bibliotek`](../../generated/reference/bibliotek/index.md) or
[`Vellis`](../../generated/reference/vellis/index.md) reference, then follow stable names into the SysML source
when changing or reviewing the contract. Generated references are optimized for reading; SysML is
the authority when they disagree.

For a first model-tooling setup:

```sh
just setup
just model-setup   # downloads and checksum-verifies the pinned validator and formal libraries
just model-check
```

For an ordinary model change:

```sh
# Edit only authored SysML and any intentional implementation/evidence changes.
just model-render
just model-diff
just model-check
just check
```

`model-render` must precede the freshness gate after a model change. Review the generated diff; do
not repair it by editing generated files.

## Artifact authority and ownership

| Location | Role | Committed | Edit directly? |
|---|---|---:|---:|
| `model/foundation/`, `model/bibliotek/`, `model/vellis/` | Normative SysML design | yes | yes |
| `model/config/` | Pinned language, profile, library, and validator policy | yes | deliberately |
| `model/migration/cutover-status.json` | Completed transition evidence, not contract meaning | yes | rarely |
| `tests/model/fixtures/` | Modeling-pattern fixture validated separately from products | yes | yes |
| `generated/reference/` | Generated human-readable model views | yes | no |
| `generated/model/` | Generated parser inventory, conformance objectives, and evidence index | yes | no |
| `apps/rtg_knowledge_graph/resources/model_app_manifest.json` | Generated runtime MCP metadata | yes | no |
| `apps/rtg_knowledge_graph/resources/everyday_life_schema.json` | Generated Vellis starter-schema bootstrap bundle | yes | no |
| `build/model/packages/` | Derived KPAR products | no | no |
| `.cache/sysml/` | Downloaded validator, Java runtime, libraries, and formal sources | no | no |

Hand-authored documentation may explain rationale, operation, tutorials, or unresolved questions.
It must not restate component signatures, state, invariants, or behavior as a parallel contract.

## Model products

- `model/foundation/SoftwareComponentModeling.sysml` defines minimal lifecycle, failure,
  realization, and evidence traceability vocabulary. Logical semantics stay in native SysML.
- `model/bibliotek/shared-values/` contains the deliberately narrow language-neutral value layer.
- `model/bibliotek/components/` contains ten reusable black-box component models.
- `model/bibliotek/views/` contains native reusable views for structure, behavior, requirements,
  satisfaction, and verification.
- `model/vellis/` contains the Vellis application composition, façade, use cases, and current
  Python/MCP realizations.
- `model/vellis/views/` contains native views for application composition, use cases, requirements,
  satisfaction, verification, and realization.

Bibliotek imports the foundation and never imports Vellis. Vellis imports Bibliotek. Derived KPAR
packaging preserves this direction so the library and application can later move to separate
repositories.

## Package and library architecture

SysML uses namespaces and packages rather than a software-language `module` construct. A package is
a namespace and organizational owner. A `library package` identifies reusable definitions. The
KPAR is the independently versioned distribution container for those packages.

The repository uses the following ownership rule:

```text
SoftwareComponentModeling (library package; generic modeling vocabulary)
  <- Bibliotek (library package façade; reusable component library)
       <- Vellis (application package; roles, façade, use cases, app invariants)
            <- VellisLocalPythonRealization / VellisMcpPythonRealization
```

`Bibliotek.sysml` is the curated library façade. Its public imports expose supported component and
shared-value packages. Individual component library packages remain the semantic owners of their
contracts, so consumers may use the umbrella or a narrower package without moving ownership.
Private imports express authoring dependencies without adding them to the umbrella API.

The foundation contains only concepts intended to apply to software-component models generally.
Bibliotek contains reusable component contracts and the smallest shared semantic vocabulary needed
by multiple Bibliotek components. Vellis contains application-specific request shaping, workflows,
use cases, transport mapping, and response policy. A type is not promoted to a shared package merely
because two Python modules happen to use similar structures.

### Runtime evolution

The logical Bibliotek contracts remain invocation-topology neutral. A future reusable messaging
layer may be added under a separately packageable Bibliotek runtime library when its observable
delivery semantics are designed. Ports, interfaces, message items, flows, endpoint identities,
correlation, ordering, retry, and idempotency then belong to that runtime contract. A Vellis runtime
realization maps existing logical capabilities onto it; it does not redefine component behavior
just to replace constructor injection or direct calls.

Repository-specific package, validator, and workflow rules live here and in `AGENTS.md`. The
reusable authoring skills contain only the generic package-layering and runtime-neutrality method,
so they can guide the next library or application without carrying Vellis/Bibliotek history.

## Right-sized modeling profile

Every component has a structural contract: identity, lifecycle, public values/items, typed actions,
defaults and multiplicities, principal failures, performed operations, and collaborator roles.
Invocation-scoped collaborators are action inputs. Collaborators retained for the component
occurrence are referential part roles with explicit multiplicity. Implementation bindings belong to
concrete realization packages, so the logical component may have multiple conforming realizations.

Stateful components additionally model abstract owned, derived, and externally referenced state,
which actions read or mutate it, concise effects, rejected-operation no-effects, and invariant
preservation.

Detailed behavior is selective. Model declarative matching rules, transition tables, observable
ordering, and rollback orchestration only when a consumer must predict them. Calculations are useful
for compact pure semantics such as query equality and ordering; successions are useful for
externally meaningful controller ordering. Do not model private helpers, call graphs,
implementation branches, storage layouts, Python exception inheritance, or algorithms where
equivalent implementations preserve the contract.

Stop when the model is sufficient for composition, substitution, design-level reasoning, and
black-box verification. It is intentionally not executable pseudocode.

Right-sized does not mean lossy. For an accepted component, the model must preserve its public
field names, multiplicities, defaults, construction actions, concrete failures, state categories,
observable effects, ordering promises, and invariant identities unless a human approves a contract
change. Concise requirements may replace several prose bullets only when they retain the same
meaning and do not admit incompatible black-box implementations.

Completeness is tested by behavioral substitutability, not source reconstruction. An independent
Rust, Python, or other realization may use entirely different algorithms and internal structures,
but the model must determine the same legal invocations, externally encoded values, abstract state
effects, ordering, failure/no-effect behavior, invariants, and dependency obligations. The same
rule applies at every modeled level: component, controller/subsystem, application façade, use case,
and transport realization. Deeper implementation or hardware modeling is selective rather than the
default mode.

## Native-first rules

- Use parts for active components and applications, attributes for values, and items for things
  whose identity or lifecycle matters.
- Give stable public identities with native SysML short names. Use the logical literal name when an
  enum value is itself a public encoding; otherwise define the encoding in a realization codec.
- Give every invocable action explicit multiplicity. `perform action` is the native
  provided-operation relationship and needs no duplicate role annotation.
- Use typed action inputs for invocation-scoped collaborators and multiplicited `ref part` features
  for collaborators retained by a component occurrence.
- In an application composition, bind a retained referential role to the actual application part
  usage when they denote the same occurrence. Binding is identity/equality, not a generic “calls”
  edge; never bind performed action usages to indicate invocation.
- Keep construction actions separate from actions performed by an existing component.
- Use ordinary owned features for component-owned state, `derived` features for projections, and
  `ref` features for independently existing durable resources or collaborators.
- Use typed dependencies for action-to-state access and allowed dependency topology. Model a call as
  a nested action performed by its provider. Explicitly redefine the typed action parameters and
  bind or flow every contract-significant input and output.
- Put every testable obligation in a requirement `require constraint`. A required constraint may be
  a complete Boolean predicate or normative text when exact formalization would reduce clarity.
  Top-level documentation is not a truth condition.
- Assert which part or action usage satisfies each accepted requirement. Verify it separately with a
  verification case whose subject is compatible with the requirement subject and whose evidence ID
  names a concrete evidence group.
- Use constraints only for complete predicates. Use an
  enum-valued status plus transition obligations for request-driven record lifecycle; use an
  exhibited state when activated behavior or event-triggered transitions are actually modeled.
- Use a calculation only when it defines a real reusable computation with an evaluable result.
  Never use hollow calculations, constraints, states, ports, or interfaces as prose containers.
- Use cases describe actor-visible value. Ports, interfaces, messages, and flows appear only when
  connection or transfer semantics are part of the current contract.
- A modeled interface has typed port ends and explicit contract-significant flows. Empty ports are
  not generic software API notation.
- Use view definitions for reusable projections. Define a viewpoint only when explicit stakeholders
  and concerns constrain the view; generated prose and diagrams remain projections.
- SysML names identify logical model features and literals; they do not implicitly define a wire
  encoding. When an external spelling is contract-significant, model it as an explicit logical
  literal or in a realization codec rather than deriving it from identifier style.

The JSON storage, query, and controller models are the representative patterns: respectively
durable state, declarative matching, and externally meaningful orchestration.

Useful source examples:

- [`SoftwareComponentPattern.sysml`](../../tests/model/fixtures/SoftwareComponentPattern.sysml)
  exercises the supported Foundation constructs without entering a product KPAR.
- [`component.storage.json_file.sysml`](../../model/bibliotek/components/component.storage.json_file.sysml)
  demonstrates state authority, containment, effects, atomic failure, and verification.
- [`component.rtg.query.sysml`](../../model/bibliotek/components/component.rtg.query.sysml)
  demonstrates declarative calculations, matching semantics, coherent reads, and no mutation.
- [`component.rtg.controller.sysml`](../../model/bibliotek/components/component.rtg.controller.sysml)
  demonstrates retained roles, cross-component invariants, observable orchestration, and recovery.
- [`Vellis.sysml`](../../model/vellis/Vellis.sysml) and its
  [realizations](../../model/vellis/realizations/) demonstrate application composition, role
  binding, allocations, and transport mapping.

## Author, review, and implementation workflows

For a new or changed component contract:

1. Use the `component-authoring` skill or its linked modeling references.
2. Edit the owning SysML package and preserve stable public identities unless the contract change
   is intentionally approved.
3. Add or revise requirements, satisfiers, verification cases, and evidence bindings with the
   affected actions, state, and invariants.
4. Run `just model-render`, inspect `just model-diff`, and review the generated component page.
5. Run the relevant implementation-neutral handoff and final checks.

For implementation work, start with:

```sh
just model-handoff TARGET=component.rtg.query
# or
just model-handoff TARGET=application.vellis
```

The handoff names the packaged model product, generated human view, source files, and structured
verification-objective count. Implementations may choose different languages, algorithms, storage
layouts, and private structure while conforming at the modeled boundary. Use the
`python-component-implementation` skill for the current Python realization workflow.

For review, check both directions:

- Model to realization: every public modeled action, value, failure, state effect, collaborator,
  and invariant is implemented and evidenced.
- Realization to model: implementation decisions that affect black-box behavior are modeled;
  helpers, algorithms, framework mechanics, and language-specific inheritance remain private.

If code exposes an ambiguity or disagrees with an accepted model, stop and surface the decision.
Do not silently redefine the model from implementation behavior.

## Generated views and checks

`just model-render` produces one page per Bibliotek component, Bibliotek and Vellis indexes,
action/state/requirement/satisfaction/verification tables, composition and use-case projections,
the formal parser inventory, structured conformance objectives, and the static Vellis application
manifest. `just model-check` rejects stale outputs, empty or semantically hollow public actions,
missing or signature-incompatible protocol operations and public values, requirements without
required constraints, satisfiers, or subject-compatible verification objectives, untyped state access, unresolved
implementation bindings, invalid referential-role bindings, the wrong Vellis role/tool surface, and
unrecorded drift.

| Command | Purpose |
|---|---|
| `just model-setup` | Fetch and checksum-verify the pinned validator, Java runtime, specifications, and formal libraries. |
| `just model-render` | Regenerate committed human references, parser inventory, conformance/evidence projections, and runtime manifest. |
| `just model-diff` | Show authored model, generated reference/machine projection, and runtime-manifest changes together. |
| `just model-check-foundation` | Run fast repository-profile checks over Foundation sources. |
| `just model-check-bibliotek` | Run fast repository-profile and component checks over Foundation plus Bibliotek sources. |
| `just model-check-vellis` | Run fast repository-profile, composition, and realization checks over all product sources. |
| `just model-package` | Build the three KPAR files without claiming that packaging alone validates them. |
| `just model-check-formal` | Package and validate Foundation, Bibliotek, and Vellis through fresh official Java kernels. |
| `just model-check` | Mandatory full model gate: package, formally validate, run repository architecture/realization checks, and reject stale generated files. |
| `just model-handoff TARGET=<stable-id>` | Print the model product, sources, generated view, and verification-objective count for implementation. |
| `just check` | Run lint, type checking, skills, the mandatory model gate, and all tests. |

Scoped checks are useful feedback while editing, but they do not replace `just model-check` or
`just check` before review.

The repository profile checker is not a substitute for formal validation. `just model-setup`
downloads checksum-pinned copies of the official 2025-06 Java pilot, its SysML 2.0/KerML 1.0
libraries, and a Java 21 runtime into the ignored `.cache/sysml/` directory. `just model-check`
then packages the model products and validates Foundation, Bibliotek, and Vellis from their KPAR
contents in fresh Java kernels. This prevents source loading from hiding undeclared dependencies
and confirms that downstream products consume the packaged layers. `just model-check-formal` runs
those formal product checks directly. The published BNF is useful for syntax tooling, but it cannot
replace the pilot's linking, type, multiplicity, specialization, and other semantic diagnostics.
KPAR outputs are independently validated model products.

## Troubleshooting

- **Generated artifact is stale:** run `just model-render`, inspect `just model-diff`, and rerun the
  check. Never hand-edit the generated artifact.
- **Validator or library asset is missing:** run `just model-setup`. Downloads are checksum-pinned
  under `.cache/sysml/` and may be safely recreated.
- **Formal syntax, linking, or semantic error:** use the reported `.sysml` line and column. Fix the
  authored model rather than weakening repository profile checks.
- **Implementation binding does not resolve:** update the realization allocation/binding or the
  implementation symbol as part of the same reviewed change.
- **Protocol, MCP, or manifest drift:** change the normative model if the contract intentionally
  changed, then render; otherwise align the implementation to the accepted model.
- **Generated page omits modeled meaning:** fix the renderer or native view and add a regression
  check. The omission is not permission to maintain prose manually.
- **Unsure what a generated file represents:** consult the artifact table above or `docs/README.md`;
  files under `generated/reference/` and `generated/model/` are always derived.

## Semantic discoveries

Changing representation does not authorize changing accepted boundaries. Surface a genuine
model/realization disagreement for human review, then align the accepted model, realization, and
conformance evidence together. Treat boundary, ownership, lifecycle, dependency, and invariant
changes as explicit proposals for human approval. Implementation-only helpers and incidental
behavior stay outside the model unless they acquire independent, language-neutral contract meaning.

Non-normative questions that remain useful after a predecessor specification is retired live in
[`open-design-questions.md`](../design/open-design-questions.md). They are a design backlog, not an alternate
component contract; resolving one requires an intentional model change.
