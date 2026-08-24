# V2 simplification model evidence

## Authority and compatibility

Phase 1 read `model/README.md`, every current `model/*.sysml` file, the accepted owner plan, the
active evolution record, and the applicable modeling, reference, RTG, and implementation-handoff
guidance before editing. The accepted authored-model digest is
`sha256:8af0ac5250d5186b8baa693bc8ebcc2b5e69f0e130754fbc676cb2302bfa8794`.

The change intentionally breaks the unreleased prototype-v2 model, query, mutation, proposal,
assessment, snapshot, tail, and replay contracts. It changes no product source or user data. Storage,
Python decomposition, FastMCP, CLI parsing, and deployment remain later realization work.

## Phase 1 conformance matrix

| Qualified authority | In-scope obligation | Nearest wrong model excluded | Decisive evidence intent | Explicit non-goal |
| --- | --- | --- | --- | --- |
| `RTG::Scalar Value`, `Scalar And Definition Integrity` | Closed scalar/null values and compatible property rules | Recursive JSON survives under a scalar wrapper | Safe-number, calendar, timestamp, null/absence, Unicode, and RE2 counterexamples | Nested active user JSON or dimensional algebra |
| `RTG::Graph`, `Graph And Lineage Integrity` | Permanent UUID/type-kind reservation, resolvable graph, read-only system envelope | Retired identity becomes reusable as another kind or agents write lifecycle metadata | Removal/reactivation, wrong-kind, dangling, and metadata-preservation cases | Prototype identity compatibility |
| `Associated Data Type Definition`, `Link Type Definition`, `Local Cardinality Integrity` | Four local per-type bounds | Relationship-rule identities or subset-specific overlaps remain | Exact/unbounded bounds over complete permitted populations | General relationship-rule language |
| `Identity Selection`, `Pattern Selection`, `Unified Query Meaning` | One direct identity or connected-pattern query and selected hydration | Separate get, projection, aggregation, hidden selector, or disconnected product | Cold discovery, known/missing UUID, cycles, self-links, distinct aliases, and requested-field cases | Server aggregation, traversal, fuzzy or semantic search |
| `Graph Change`, `Atomic Field Change` | Field patches, explicit idempotent removal, final-state atomicity, no cascade | Upsert adapter still replaces complete objects or request order changes meaning | One-field unseen-data preservation, batch permutations, and dependent-removal cases | Whole-state ordinary validation |
| `RTG::Draft`, `Durable Draft Governance` | One normalized noncanonical bucket over changing live state | Proposal revision/status/assessment survives or live writes discard staged work | Same-field staged win, unrelated-live-field survival, lost base, tombstone, and unstage cases | Public draft version, status, digest, or activation token |
| `Draft Inspection Validation And Activation` | Raw inspect, current findings, fresh activation validation, discard | Status-only tool or prior assessment authorizes activation | Cursor expiry, repeated repair, invalid/valid/redundant activation | Assessment identity or conflict-list lifecycle |
| `Historical State And Canonical Ledger`, `Activity Separation And Privacy` | Indexed historical state and separate owner-readable ledgers | Replay remains state authority or activity duplicates canonical meaning | Restart without traversal, time ties, history self-exclusion, and semantic/verbose privacy cases | Snapshot/tail/replay and automatic activity pruning |
| `History Restore Audit And Backup`, `Fresh And V1 Initialization` | Restore-as-revision, read-only audit, complete backup, streamed reported v1 start | Replay export, in-place migration, silent conversion, or whole-source materialization | Corruption, concurrent backup, digest mismatch, mixed-property conversion, and publication non-effect cases | V1 storage migration or prototype-v2 compatibility |
| `MCP Boundary Integrity`, `Simple Secure Individual Operation` | Typed selected tools, STDIO, protected HTTP, truthful client lifecycle | Tool count becomes architecture, private hooks decide behavior, or client change is claimed rolled back | Real transports, token cases, concurrent isolation, replacement failure, and post-commit reconciliation | OAuth, roles, TLS termination, daemon/service management |

## SysML reference evidence

The pinned SysML 2.1 and KerML 1.1 corpus was searched before authoring for feature multiplicity,
reference ownership, redefinition/subsetting, included use-case subject/actor binding, requirement
satisfaction, and verification usage. Consequential choices use native ownership and reference
features, multiplicity for occurrence cardinality, contextual use cases, selected satisfiers, and
subject-bound verification. `just model-reference-check` confirms the corpus remains at its pinned
checksum.

## Adequacy review

The revised model closes the accepted observable distinctions for scalar equality and constraints,
identity lineage, graph closure, local counts, query connectedness and bounding, field-patch
non-effects, live/draft composition, activation failure and redundancy, historical selection,
ledger separation, restore, audit, backup, v1 conversion/reporting, installed agent connection, and
post-commit response loss. Each governed state has behavior that creates, observes, changes, or
removes it. Requirements select compatible `RTG System` or `Vellis System` subjects, and verification
cases exercise nominal, refusal/failure, and plausible-invalid instances. No later implementation
phase requires a new public or durable product decision.

## Subtraction review

The authored model falls from 4,750 SysML lines to 2,470 while preserving the accepted owner
outcomes. It removes recursive JSON, value-shape objects, relationship and multiplicity constraint
families, definition-set/overlay/assessment identities, projection and aggregation families,
complete-object mutation, canonical draft revisions, replay-sufficient changes, snapshots, ledger
tails, and replay outcomes. It also removes mirrored use cases, requirements, and verification cases
whose only purpose was to preserve those mechanisms.

The retained abstractions each exclude a current invalid system: graph objects have independent
identity; direct associations do not; definitions own local constraints; a draft has independent
durable presence but no public lifecycle identity; canonical and activity ledgers answer different
owner questions. No code module, table, repository, framework, protocol hook, or deployment unit is
modeled as system structure.

## Medium rehearsal disposition

A fresh read-only GPT-5.6 Sol Medium agent reconstructed the Phase 2 typed-domain, fresh indexed
SQLite, per-operation connection/transaction, one-resolver, and no-replay boundaries, and the Phase
4 order-independent field-patch, affected-closure validation, live-write-during-draft, cursor,
activation, redundancy, and failure boundaries. It proposed no event framework, compatibility
layer, global store, complete-object mutation, proposal version, assessment token, generalized
relationship rule, or extra public operation.

The rehearsal found one genuine public-boundary ambiguity: a staged complete definition replacement
could have been interpreted as carrying the canonical read-only system envelope. The model was
corrected before freeze by introducing `RTG::Definition Replacement`, whose complete kind-specific
owner content has no writable system member; canonical definitions retain the separate envelope.
After that disposition, the rehearsal identified no public or durable choice that Phase 2 or Phase 4
would have to invent. The prompt and transcript remain outside the repository.

## Documentation synchronization disposition

`model/README.md` and the repository README's authority-facing introduction now match the accepted
model while clearly separating it from currently runnable predecessor behavior. SECURITY guidance,
MCP realization notes, completed campaign handoffs, detailed command examples, and RTG skill
vocabulary continue to describe the runnable predecessor or portable generic method. Rewriting those
before their runtime paths change would advertise unimplemented v2 behavior or alter completed
history. Their obsolete product claims are already owned by F010/W008 and will be removed with the
corresponding implementation, followed by a complete documentation-sync pass at closure.

## Review convergence

The first frozen review pair found four authority contradictions rather than implementation choices:
same-request draft command collisions and open inspection vocabularies, an eight-versus-nine starter
date count, inclusive-versus-exclusive history lower-bound wording, and an ungoverned activity-mode
setting. The model now rejects duplicate or cross-category draft commands, uses closed draft category
and operation enums, verifies the exact eight starter date properties, defines sequence history as
exclusive-after/inclusive-through, and owns semantic-default activity mode plus its accepted and
failed configuration effects. The repository README was also corrected to distinguish accepted v2
authority from the runnable predecessor. These are model/evidence corrections, so the earlier pair is
superseded and both lenses must review the new frozen token.

The next pair found one stale line-count measurement, a revision-zero wording conflict, and four
unused declarations. The count is now recomputed from all six authored files; v1 success explicitly
creates its required initialization record while importing no predecessor transitions; and the
unconstraining declarations were removed rather than retained as speculative vocabulary.

After the third non-clean pair, the required bounded root-cause audit swept every public request and
continuation shape rather than patching only the reported lines. It closed contradictory property
set/null/remove and anchor add/remove operations; made omitted read state explicitly current; fixed
fresh-versus-continuation argument combinations, empty-filter meaning, validation scope binding, and
draft-absence behavior; and stated the remaining history option restrictions. No generic request,
cursor, or validation abstraction was introduced.

The following pair exposed places where prose promised distinctions that unordered or zero-valued
features could not represent. The model now uses one optional complete-anchor-set value for supplied
versus omitted creation content, native ordered usages for every promised request/result order, and
small purpose-payload values only where accepted-empty must differ from rejected-absent. History
range, head, selected-family, and activity effects are closed explicitly. The README's remaining
predecessor workflow paragraph was replaced. Evolution findings and decisions that the predecessor
still violates now remain implementation work owned by Phases 2–4; Phase 1 claims accepted model
authority, not product conformance.

The next pair found residual unordered response features, occurrence identity on scalar facts, and
the absence of truthful canonical metadata for never-live draft proposals. Scalar values and system
envelopes are now attributes, response views natively own every promised order, and the model no
longer calls its language-neutral backup SQLite-native. The owner clarified the remaining public
meaning: draft operations never carry system metadata; live-backed draft results retain unchanged
canonical metadata; staged additions/reactivations omit it; activation alone applies the ordinary
canonical create, update, or reactivation rules. No in-flight or prospective revision is created.

## Evidence commands

The primary agent runs, rather than infers, the following Phase 1 gates:

```text
just model-check
just model-reference-check
just system-evolution-check
git diff --check
```
