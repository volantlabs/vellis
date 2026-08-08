# Vellis model

The textual SysML v2 files here are the current product and system authority for Vellis. The current
namespace map is:

1. `10-rtg-domain.sysml` — `RTG`: graph, owner-described definitions and constraints, canonical equality, progressive discovery views, bounded query and change meaning, validation results, snapshots, revision, and ledger vocabulary.
2. `15-everyday-life-starter.sysml` — `EverydayLifeStarter`: the complete modeled optional Everyday Life fresh-start definition set, with no graph data or separate schema authority.
3. `20-rtg-system.sysml` — `RTGSystem`: one cohesive RTG boundary, black-box use cases, and the selected MCP tool contract.
4. `30-vellis.sysml` — `Vellis`: owner and external-agent context, product use cases, fresh vocabulary choice, confirmed v1 onboarding, proactive improvement analysis, and RTG composition.
5. `40-requirements.sysml` — `VellisRequirements`: stakeholder requirements, scaling constraints, selected subjects, and explicit satisfying features.
6. `50-verification.sysml` — `VellisVerification`: subject-bound verification cases, performance characterization, and decisive evidence.

These packages are intentional namespaces, not validator-required file structure or runtime layers.
RTG owns graph, definition, revision, and history state as one semantic and transactional boundary.
Its canonical ledger is authoritative; one current canonical-state tuple containing graph, active
definitions, optional delta, and revision is derived through the final canonical record rather than
forming parallel authority.
Query, validation, history, and recovery are capabilities rather than internal subsystem parts.

The current elements express selected Vellis meaning; they are not a template requiring every future
feature to add a use case, action, result, requirement, and verification in matching counts. Extend
only the affected semantic path and reuse existing authority where it already carries the claim.

The model selects core MCP tool discovery and invocation as the first agent-access contract. It does
not select a server part, FastMCP runtime, storage design, transport, deployment, importer utility,
generator, or implementation language. Its discovery results, snapshots, and ledgers are semantic
artifacts, not serialized formats.

The model requires a supported local owner to follow supplied setup guidance, connect one trusted
MCP agent, recover identical memory after restart, and receive actionable setup or connection
failure. Framework, script, client-configuration, storage, packaging, and transport mechanics remain
realization choices; the campaign may select them without turning them into model structure.

The modeled property vocabulary includes RE2 whole-string constraints for string shape without
selecting a runtime regex engine. Fresh systems may begin blank or, after explicit confirmation,
with the recommended Everyday Life starter. Snapshot initialization uses the snapshot's definitions;
the starter is not a later installer and is never overlaid on existing state. Existing systems adapt
vocabulary through ordinary owner-controlled definition governance, including an agent translating
an owner prompt. A first-use owner may instead preview and confirm compatible graph and definition
meaning translated from a complete Vellis v1 JSON snapshot. That path establishes a new revision-zero
v2 lineage; it is never an existing-system merge or replacement and never overlays the v2 starter.
Starter dates constrain lexical shape only, not calendar validity or ordering.

A cold agent first requests the complete shallow anchor summary for current state or an optional
revision/time selection, then inspects the relevant anchor neighborhoods at that evaluated revision.
Each result identifies its evaluated revision; if those revisions differ, the agent repeats discovery
rather than relying on stale vocabulary. A time-based summary's resolved revision can be reused for
inspection and graph query. If a current definition delta exists, the agent retrieves that sole
proposal whole and compares it with
the focused current views; the system does not manufacture a second schema authority or a server-side
diff. Delta retrieval remains current-only.

The initial MCP boundary assumes one trusted owner-configured client; its tools do not decide
per-call authorization or owner approval. History tools return bounded owner-facing entries rather
than replay-bearing canonical payloads. Owner-directed activity retention and recovery behavior remain
modeled but are not additional initial MCP tools.

The model constrains current work to avoid history traversal and bounded historical selection to
avoid scanning excluded ledger prefixes. It does not select materialized projections, revision/time
indexes, definition checkpoints, caches, snapshot cadence, databases, or storage layouts. Those are
possible non-normative realizations whose conformance is shown with semantic record-access evidence.
Numerical latency, startup, throughput, and storage budgets remain deferred until the modeled
performance analysis has representative runtime, hardware, and owner-data measurements.

Realization remains open. Select the simplest approach from actual scale, startup, durability, and portability needs in the first implementation-focused semantic slice. Do not add interchangeable persistence or runtime abstractions before demonstrated need.

The SysML on a branch is that branch's current system definition. Review its diff like code and accept changes through the normal pull-request process. Official validation establishes language conformance; requirements closure, verification evidence, and engineering review establish design quality.

Run `just model-check` for full-model validation. Use `$sysml-modeling` for the engineering workflow,
`$sysml-reference` for language evidence, `$rtg-schema-design` for RTG meaning and governance,
`$sysml-implementation-planning` to derive the complete implementation campaign,
`$sysml-implementation` for one accepted semantic slice, `$sysml-implementation-campaign` to execute
an approved campaign through system closure, and
`$documentation-sync` after model or workflow changes.
