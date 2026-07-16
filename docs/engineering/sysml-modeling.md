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
validation. Textual SysML is the normative design authority; Git history retains superseded
transition material without adding historical status files to the active model tree.

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

Before choosing or interpreting a SysML/KerML construct, use the repo-local `sysml-reference` skill.
Unless an exact section or page is already known, always start with
`just model-reference-find "<question>"`, review its ranked outline-aware results, then read
the containing section and only the adjacent pages needed for context. Search outline headings before
falling back to raw page-text search, and follow normative cross-references between SysML and KerML.
Consequential modeling conclusions should name the specification section and page that supports them
and separately identify repository conventions or inference. The Markdown is a generated search
projection; the checksum-pinned PDFs under `.cache/sysml/formal/` remain authoritative.

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
| `reference/specifications/` | Generated searchable SysML/KerML page corpus, outlines, and manifests | yes | no |
| `tests/model/fixtures/` | Modeling-pattern fixture validated separately from products | yes | yes |
| `generated/reference/` | Generated human-readable model views, normalized PlantUML, and SVG | yes | no |
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
- `model/bibliotek/components/` contains thirteen reusable black-box component models.
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
- Author graphical view usages in the model with targeted exposure and a unique
  `diagram.<product>.<name>` short name. A registered view renders exactly once as a tree or
  interconnection diagram. Express alternative type filters in one `or` expression because
  separate filter conditions are conjunctive. Keep element-table views out of the graphical catalog.
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
Do not silently redefine the model from implementation behavior, but do not assume accepted status
proves that a migration preserved every predecessor contract or used SysML correctly. Use the
`model-hygiene-review` skill and `just model-audit <stable-id>` to inspect chronology, predecessor
material, consumers, realization codecs, and exact evidence before classifying which side drifted.
Audit bundles are ignored, advisory artifacts under `build/model-audits/`; they never mutate either
side and do not gate CI.

## Generated views and checks

`just model-render` produces one page per Bibliotek component, Bibliotek and Vellis indexes,
action/state/requirement/satisfaction/verification tables, composition and use-case projections,
the formal parser inventory, registered PlantUML/SVG diagrams, structured conformance objectives,
and the static Vellis application manifest. Registered diagrams are discovered from parser-resolved
`ViewUsage` elements whose native short names begin with `diagram.`. The remaining identity maps
directly to `generated/reference/<product>/diagrams/<name>.puml` and `.svg`.

The only selectable backend is `pilot`: it uses the checksum-pinned official kernel's PlantUML
projection and PlantUML's embedded Smetana layout. Component contract overviews use the pilot's
`COMPMOST` compartment layout and standard color skin; relationship-heavy concerns belong in
separate focused views. Generation removes volatile `psysml:` links, normalizes wrapping, and
removes SVG text-metric overrides that macOS Quick Look renders incorrectly. It replaces committed
artifacts only after every registered view succeeds. Empty output, renderer errors, unsupported
renderings, and `EXCEEDS THE LIMIT` fail closed. The traversal ceiling is a
correctness boundary: split an oversized view into focused concerns rather than publishing a
truncated image. Broad composition views may remain useful authored or table projections without
being registered graphically.

Both the official kernel and PlantUML subprocess are launched with
`-Djava.awt.headless=true` before the Java classpath arguments. This prevents AWT initialization
from creating a Dock application or stealing keyboard focus on macOS. Keep the property local to
these subprocesses; do not set a repository-wide `JAVA_TOOL_OPTIONS` value.

Component pages embed a diagram only when a complete registered projection exists; the Bibliotek
index catalogs the available SVG and PlantUML sources. Use the `sysml-view-authoring` skill for view
authoring and visual completeness review. The underlying CLI is
`uv run python tools/sysml_diagrams.py render|check --backend pilot`. `just model-check` rejects
stale outputs, empty or semantically hollow public actions,
missing or signature-incompatible protocol operations and public values, requirements without
required constraints, satisfiers, or subject-compatible verification objectives, untyped state access, unresolved
implementation bindings, invalid referential-role bindings, the wrong Vellis role/tool surface, and
unrecorded drift.

### Architecture projections

`just model-render` also exports `generated/model/architecture-graph.json` from the official
kernel's JSON abstract syntax tree. Nodes use stable short names for public package members and
qualified names for nested occurrences; typed edges retain ownership, typing, performance,
dependency, binding, allocation, succession, flow, satisfaction, and verification facts. The graph
contains no kernel UUIDs and every edge endpoint must resolve to a generated node.

The stable dashboard under `generated/reference/architecture/` regenerates on every model render:
package layers, Bibliotek component dependencies, Vellis logical composition, Vellis runtime
topology, operation ownership, and requirement/verification coverage. Graphs are normalized
PlantUML/Smetana SVGs; dense traceability uses generated Markdown matrices. These are review
projections, not additional contracts.

Architects and agents can ask model-based questions without authoring a persistent view:

```text
just model-view-presets
just model-view-targets --kind PartDefinition
just model-view context component.rtg.schema
just model-view impact component.rtg.schema --direction inbound --depth 2
just model-view operation operation.vellis.rtg_apply_live_graph_changes
just model-view requirements component.rtg.schema
just model-view-changed BASE=main
```

The preset registry is the parameter source of truth. On-demand output is cached by model digest
under `build/model-views/`; changed-model review bundles live under `build/model-review/`. Both are
ignored. Every bundle includes provenance and completeness in `manifest.json`. Exceeding
`--max-nodes` fails rather than truncates. `model-view-promote` prints a candidate SysML view usage,
but adding it to `model/` still requires `sysml-reference` and `sysml-view-authoring`, formal
validation, completeness checks, and visual review. The projection service never invents sequence
or state-transition semantics absent from the model.

| Command | Purpose |
|---|---|
| `just model-setup` | Fetch and checksum-verify the pinned validator, Java runtime, specifications, and formal libraries. |
| `just model-reference-render` | Regenerate committed page Markdown, outline indexes, and manifests from the pinned PDFs. |
| `just model-reference-check` | Regenerate temporarily and reject stale, missing, extra, or hand-edited reference files. |
| `just model-reference-find "<question>"` | Rank relevant sections and page snippets without loading whole specifications. |
| `just model-diagrams` | Refresh the parser inventory and generate normalized PlantUML/SVG with the pinned pilot and Smetana. |
| `just model-dashboard` | Refresh the parser inventory, typed architecture graph, and stable architecture dashboard. |
| `just model-view-presets` | List architectural questions, supported targets, and default parameters. |
| `just model-view <preset> [target] [options]` | Generate an ignored on-demand projection and provenance manifest. |
| `just model-view-changed BASE=<git-ref>` | Generate an ignored change-relative architecture review bundle. |
| `just model-render` | Regenerate diagrams, committed human references, parser inventory, conformance/evidence projections, and runtime manifest. |
| `just model-diff` | Show authored model, generated reference/machine projection, and runtime-manifest changes together. |
| `just model-check-foundation` | Run fast repository-profile checks over Foundation sources. |
| `just model-check-bibliotek` | Run fast repository-profile and component checks over Foundation plus Bibliotek sources. |
| `just model-check-vellis` | Run fast repository-profile, composition, and realization checks over all product sources. |
| `just model-package` | Build the three KPAR files without claiming that packaging alone validates them. |
| `just model-check-formal` | Package and validate Foundation, Bibliotek, and Vellis through fresh official Java kernels. |
| `just model-check` | Mandatory full model gate: package, formally validate, run repository architecture/realization checks, and reject stale generated files. |
| `just model-handoff TARGET=<stable-id>` | Print the model product, sources, generated view, and verification-objective count for implementation. |
| `just model-audit [stable-id]` | Collect an advisory model/implementation/history/evidence bundle for one component or all accepted components. |
| `just check` | Run lint, type checking, skills, the mandatory model gate, and all tests. |

Scoped checks are useful feedback while editing, but they do not replace `just model-check` or
`just check` before review.

Routine mutation modeling uses component-local atomic batches. Non-state-transfer actions state
observable all-or-none behavior and bound preparation, projection, targeted reads, and transient
recovery data to the requested delta plus documented cascade closure. They do not prescribe a
private undo algorithm and do not authorize complete-state export, cloning, hashing, or retention.
Cross-owner uncertainty is modeled as an indeterminate operation resolved by runtime quiescence and
reconstruction. The generated architecture dashboard's state-transfer boundary matrix shows the
small set of actions whose request, result, or effect may carry complete component state.

The repository profile checker is not a substitute for formal validation. `just model-setup`
downloads checksum-pinned copies of the official 2025-06 Java pilot, its SysML 2.0/KerML 1.0
libraries, and a Java 21 runtime into the ignored `.cache/sysml/` directory. `just model-check`
then packages the model products and validates Foundation, Bibliotek, and Vellis from their KPAR
contents in fresh Java kernels. This prevents source loading from hiding undeclared dependencies
and confirms that downstream products consume the packaged layers. `just model-check-formal` runs
those formal product checks directly. The published BNF is useful for syntax tooling, but it cannot
replace the pilot's linking, type, multiplicity, specialization, and other semantic diagnostics.
KPAR outputs are independently validated model products.

### Specification reference upgrades

The SysML and KerML PDFs are singular, checksum-pinned sources. Each physical source page is stored
once as generated Markdown; the embedded PDF outlines provide section hierarchy and page routing
without duplicating parent and child section text. To upgrade a specification baseline, update its
URL, checksum, document metadata, expected page count, and expected outline count in
`model/config/language.lock.json`; run `just model-setup` and `just model-reference-render`; inspect
`just model-diff`; then run `just model-reference-check` and the full model gate. Do not preserve a
second active reference version or repair generated pages manually.

## Troubleshooting

- **Generated artifact is stale:** run `just model-render`, inspect `just model-diff`, and rerun the
  check. Never hand-edit the generated artifact.
- **Diagram exceeds the pilot traversal limit:** narrow the exposed root or split the concern into
  independently complete views. Do not register or commit the partial rendering.
- **Diagram is unreadable or incomplete:** fix the canonical view exposure/filter or split it, run
  `just model-diagrams`, and visually inspect the SVG. Never repair the PlantUML or SVG directly.
- **On-demand view exceeds its node limit:** reduce depth, select one direction, or narrow the
  relationship kinds. Do not raise the limit merely to publish an unreadable or partial graph.
- **On-demand view has no edges:** verify that the selected relationship is actually modeled. Do
  not add an inferred architecture fact solely to improve the picture.
- **Validator or library asset is missing:** run `just model-setup`. Downloads are checksum-pinned
  under `.cache/sysml/` and may be safely recreated.
- **Specification reference is stale or its source PDF is missing:** run `just model-setup`, then
  `just model-reference-render`; inspect the diff rather than editing page Markdown.
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
