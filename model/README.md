# Vellis model

The textual SysML v2 files here are the current product and system authority for Vellis. They form one ordered dependency path:

1. `10-rtg-domain.sysml` — `RTG`: graph, owner-described definitions, progressive discovery views, bounded query and change meaning, validation results, snapshots, revision, and ledger vocabulary.
2. `20-rtg-system.sysml` — `RTGSystem`: one cohesive RTG boundary, black-box use cases, and the selected ten-tool MCP contract.
3. `30-vellis.sysml` — `Vellis`: owner and external-agent context, product use cases, and RTG composition.
4. `40-requirements.sysml` — `VellisRequirements`: stakeholder requirements, selected subjects, and explicit satisfying features.
5. `50-verification.sysml` — `VellisVerification`: subject-bound verification cases and decisive evidence.

The packages are intentional namespaces, not runtime layers. RTG owns graph, definition, revision, and history state as one semantic and transactional boundary. Query, validation, history, and recovery are capabilities rather than internal subsystem parts.

The current elements express selected Vellis meaning; they are not a template requiring every future
feature to add a use case, action, result, requirement, and verification in matching counts. Extend
only the affected semantic path and reuse existing authority where it already carries the claim.

The model selects core MCP tool discovery and invocation as the first agent-access contract. It does
not select a server part, FastMCP runtime, storage design, transport, deployment, migration utility,
generator, or implementation language. Its discovery results, snapshots, and ledgers are semantic
artifacts, not serialized formats.

A cold agent first requests the complete shallow anchor summary for current active state, then
inspects the relevant anchor neighborhoods. Each result identifies its evaluated revision; if those
revisions differ, the agent repeats discovery rather than relying on stale vocabulary. If a
current definition delta exists, the agent retrieves that sole proposal whole and compares it with
the focused current views; the system does not manufacture a second schema authority or a server-side
diff. Current discovery does not browse retired definitions, so a historical query initially requires
caller-known vocabulary valid at its selected revision.

The initial MCP boundary assumes one trusted owner-configured client; its tools do not decide
per-call authorization or owner approval. History tools return bounded owner-facing entries rather
than replay-bearing canonical payloads. Owner-directed activity retention and recovery behavior remain
modeled but are not additional initial MCP tools.

Realization remains open. Select the simplest approach from actual scale, startup, durability, and portability needs in the first implementation-focused semantic slice. Do not add interchangeable persistence or runtime abstractions before demonstrated need.

The SysML on a branch is that branch's current system definition. Review its diff like code and accept changes through the normal pull-request process. Official validation establishes language conformance; requirements closure, verification evidence, and engineering review establish design quality.

Run `just model-check` for full-model validation. Use `$sysml-modeling` for the engineering workflow, `$sysml-reference` for language evidence, `$rtg-schema-design` for RTG meaning and governance, and `$documentation-sync` after model or workflow changes.
