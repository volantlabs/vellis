# MCP realization

This note is non-normative. The SysML model selects the agent-visible RTG behavior; `vellis/mcp.py`
exposes it over local standard input and output.

## Agent path

An unfamiliar agent first calls `rtg_definition_summary`, omitting its optional revision-or-time
selection inside its typed request for current state, selecting prospective state explicitly, or
supplying exactly one selector for historical state, to learn every evaluated anchor type and its
owner-readable description. It then calls
`rtg_definition_inspect` with the same selection for only the anchor types relevant to its question.
Each result identifies its evaluated revision; if the revisions differ, the agent repeats discovery
instead of relying on stale vocabulary. After a time-based summary, it reuses the returned exact
revision for inspection and graph query. If
the current summary reports an in-flight proposal, an agent continuing definition work uses
`rtg_definition_delta` to retrieve that proposal's definition identity, overlay identity and counts,
and latest assessment reference/status. Focused prospective definition meaning is retrieved through
the same bounded summary and inspection operations; the tool never returns a whole proposal document.

The remaining selected tools query and change the graph, stage or resolve the sole definition delta,
check conformance, and inspect bounded history. Historical summary and inspection allow cold discovery
of vocabulary later retired; `rtg_definition_delta` remains current-only. History results contain
bounded owner-facing entries rather than canonical state or replay-sufficient changes. Results are
complete or rejected rather than silently truncated.
Activity-history results are selected before the current read is recorded, so a read never includes
its own observation. Activity summaries identify capability, outcome category, provenance, applicable
evaluated revision, and bounded semantic scope without copying result rows or canonical payloads.
Activity retention, snapshot, replay, initialization, restoration, and v1 first-use onboarding are
not in the initial MCP surface.

`rtg_check` accepts a typed validation request. It can create a complete current or proposal
assessment or retrieve one bounded, one-based finding interval from a stored assessment without
rerunning validation. A completed check returns assessment identity, evaluated revision, and, for a
prospective assessment, proposed-definition and graph-overlay identities, plus the complete finding
count, requested interval, and whether more findings remain. Nonconformance is
a successful assessment, not a tool rejection. An unexpected check failure produces no successful
report, and activation accepts only the exact clean, non-stale proposal assessment named by its
request.

Completed invocations return their modeled typed result. Accepted results carry their complete
purpose-specific payload. Semantic rejection and a safely reported failure carry no success payload;
malformed input forms no RTG request, and an unexpected tool failure produces no completed RTG
result. A rejected delta-staging request does not echo the unchanged proposal—the agent retrieves it
explicitly with `rtg_definition_delta`.

## FastMCP discipline

The completed implementation campaign selected direct pins for `fastmcp==4.0.0b1` and its
pre-release companion `fastmcp-slim==4.0.0b1`. Their pre-release status was an explicit owner
decision for the proving campaign; S009 changed no global prerelease policy, selected no unrelated
prereleases, updated the lock, and proved `uv sync --locked`. The current boundary uses typed input
and return models and keeps text and structured content semantically equivalent. FastMCP, Python
models, decorators, the selected local STDIO transport, and serialization remain realization rather
than RTG domain meaning.

FastMCP may represent a parameterless tool with an empty object schema, but that representation does
not create an empty RTG request concept. `rtg_definition_summary`, inspection, query, check, change,
definition staging, activation, and history each expose their modeled typed request; only the
semantically parameterless delta read and discard tools have empty input. Public input schemas must
advertise only caller-valid choices; internal validation scopes do not become `rtg_check` targets by
reuse.

Only core MCP tool discovery and invocation are required. Resources, prompts, elicitation, tasks,
sampling, sessions, notifications, subscriptions, application UI, transforms, tool search,
authentication, HTTP, remote hosting, and plugin packaging remain outside the initial contract.
Advisory annotations may describe modeled state effects but never enforce authorization, validation,
or atomicity.

The initial boundary assumes one trusted, owner-configured MCP client. Tool invocation neither
establishes nor evaluates per-call authorization. An owner-declined context proposal is never
submitted to `rtg_change`; exposing graph mutation does not by itself implement Vellis's higher-level
owner approval of personal context. The implementation preserves that distinction without inventing
roles, tenants, or an authentication subsystem inside RTG.

Current operations must use normalized current SQLite membership rather than replaying history.
Bounded history and revision/time selection must avoid scanning excluded ledger prefixes, and
historical definition discovery must avoid replaying unrelated graph-only transitions. Materialized
projections, revision/time indexes, definition checkpoints, caches, and snapshot cadence are allowed
realization choices, not selected architecture. Conformance should use semantic record-access counts
or equivalent traces; wall-clock targets wait for representative runtime, hardware, and owner data.

The reviewed query implementation stores normalized object values, definition entries, presence
intervals, proposal entries, assessments, canonical events, and activity records in shared SQLite
tables. The state head carries transactionally maintained current-graph and proposal summaries, so
ordinary transition identity is derived without a population scan. Queries analyze one positive
conjunction, populate one indexed selector-member relation, compile unreturned variables as existence
conditions, and materialize at most the requested bound plus one distinct answer identities before
hydration or aggregation. Row and aggregate output are exclusive, and aggregate output has one
associated-data target population. Compiled statements carry their actual bindings and structural
profile and prepare before answer execution. Definition discovery reads each result from one SQLite
snapshot. Ordinary mutation validation still derives the affected invariant closure; explicit
full checks and broad cutovers use set-based scans and SQLite-backed findings. Snapshot, tail, restore,
and compatibility import are streaming or SQL set operations. These are Vellis realization choices,
not portable RTG architecture.

The W007 implementation candidate prepares the canonical permitted-value key set once for each
relevant property constraint in a graph-validation scope. In-memory neighborhoods and normalized
SQLite assessment then reuse that immutable set across governed values; unrelated data types do not
cause their permitted collections to be prepared.

Implementation evidence verifies two realization-only properties that do not belong in the RTG
domain model: text and structured content communicate the same typed outcome, and removing or
changing advisory annotations cannot change authorization, validation, atomicity, or any promised
failure non-effect.

## Semantic work-locality trigger evidence

The `vellis-2-semantic-work-locality` evolution began from a clean
`ca6539e10393a5a52e2cd2f67d0af662e92cc010` checkout with all 1,192 existing tests passing. That
pass is evidence of missing discrimination, not evidence that the following shapes conform:

- Aggregation's late `SELECT DISTINCT` in `vellis/store.py` first enumerates hidden flat-join
  witnesses. Distinct output therefore does not prevent a hidden cross-product.
- Active endpoint-type validation obtains generic affected participants, loads every incident
  relationship, and promotes both endpoints. Hub-of-hubs degree 10, 20, and 40 produced respectively
  15,187, 52,857, and 200,389 SQLite steps and 231, 861, and 3,321 decoded objects.
- Prospective multiplicity selection considers every rule mentioning a locally impacted type. An
  isolated display rename with 10, 100, 500, and 1,000 irrelevant rules produced 8,434, 45,154,
  208,354, and 412,354 SQLite steps. Independent K changes and K rules at K 5, 10, 20, and 40
  produced 13,498, 31,543, 93,133, and 318,313 steps.
- Historical aggregation capacity accounting omitted the additional bound parameter compiled into
  its `LIMIT`; at a SQLite variable limit of 32 the historical form failed after equivalent current
  and prospective forms passed preflight.
- Permitted-value validation scans every earlier accepted value. Valid collections of 500, 1,000,
  2,000, and 4,000 values took 0.047, 0.174, 0.672, and 2.640 seconds; 8,000 took 10.455 seconds.
- `vellis/query.py` contained an assignment evaluator used by `tests/vellis/oracle.py`; component
  splitting was duplicated in query and store code, alongside specialized collection paths,
  recursive component evaluation, manual capacity formulas, legacy state/payload channels, and
  post-hydration row deduplication. W003 deletes those mechanisms and replaces their source-shape
  triggers with independent-oracle, bounded-identity, compiled-capacity, and hidden-witness evidence.
- The first selected tagged-union handoff used defaulted discriminators and open standard
  dataclasses. The locked Pydantic realization accepted contradictory members by silently choosing
  a union branch and discarding the other branch's fields. The revised handoff requires explicit
  discriminators for supplied variants, discriminated unions, and closed state/output variants.
- Definition discovery and assessment interval reads executed related statements under a
  connection-local lock but no SQLite read transaction. W003 now gives summary, inspection, and
  proposal discovery one read snapshot. W006 still owns the independent assessment publication case.
- Successful assessment and restoration leave population-sized rows in reusable temporary work
  relations. A three-object fixture retained three effective/impacted/validation assessment rows and
  three restore-candidate/current rows until another same-kind operation or connection close.

These measurements characterize forbidden dependency shapes; they are not public latency budgets.
The successor evolution record owns their model, implementation, evidence, and deletion closure.

The raw measurements used CPython 3.14.5, SQLite 3.53.1, macOS 15.7.8 arm64, and the repository's
`uv.lock` identity `sha256:d71473693aa50faef1a25a449aa5808490e21eaf2a987942d1fb134c773550d1`.
SQLite work was counted with `Connection.set_progress_handler(..., 1)` and decoded objects with
`SQLiteStore.current_graph_object_decodes`, using the reusable measurement boundary in
`tests/vellis/characterization.py`. Each series rebuilt a fresh temporary database for each size and
measured only the named operation after fixture construction.

The remaining temporary executable characterization is
`uv run pytest tests/vellis/test_semantic_work_locality_triggers.py`. It rebuilds fresh databases,
resets the shared instrumentation boundary, and reproduces the active 10/20/40 hub series, the
10/100/500/1,000 irrelevant-rule series, and the 5/10/20/40 independent-change-by-rule series. It
also counts the exact pairwise equality calls for 500/1,000/2,000/4,000/8,000 permitted values.
Its query-capacity case now requires the same typed whole refusal for current, prospective, and
revision-selected aggregation. Permanent W003 evidence exercises positive pattern topologies,
source-preserving row identity, hidden-witness fanout, large relational filters, exact compiled
bindings, VDBE capacity, regex locality, an independent oracle that catches a mutated compiler, MCP
schema rejection, and one-snapshot definition discovery. The remaining source-mechanism trigger pins
only the mutation-locality paths owned by W004; assessment publication and retained work rows remain
W006 triggers. No fixture or instrumentation must be invented from this prose.

W002 through W004 and W006 replace these trigger recipes with permanent discriminating regression
fixtures; the final subtraction review removes any evidence that asserts the superseded
implementation shape.

The proposed target instead has exclusive row and aggregate outputs. Row identity preserves every
projected source object, including the associated-data UUID behind a property value, while aggregate
output operates on one distinct associated-data target population. Equal property values from
different source objects therefore remain different rows. Implementation work deletes the old
return-shape advice and translation paths; callers needing distinct values may deduplicate a complete
bounded row result. The query itself remains a finite must-exist pattern: disconnected, parallel,
self-link, and cyclic predicates are ordinary conjunctions rather than invalid shapes.

## Local setup path

The campaign selects a Python setup program as the primary local onboarding path, packaged as
`vellis setup` and still available as `python -m vellis.setup`, with the
repository README pointing both agents and developers to it. It previews every effect and confirms
before applying it, and complete non-interactive arguments plus `--yes` support agent-driven setup;
`--dry-run` changes nothing.

The setup path selects blank or Everyday Life initialization, v2 snapshot plus optional tail, and v1
preview and exact confirmation. All three starting inputs are implemented, and a companion command
writes the snapshot document the second one takes. It accepts a configurable data
location with a platform-appropriate user-data default; tests use temporary directories, and neither
tests nor the runtime default use the repository's protected `.data/` directory.

## Client configuration

Registering Vellis with an MCP client changes that client's own user-scoped state rather than
anything in this repository. Whichever way that happens, it goes through the public `codex mcp` and
`claude mcp` commands and never edits a configuration file directly, a matching `vellis` entry is a
no-op, a differing entry is replaced only deliberately, and client tool approval settings stay
entirely client-owned.

The installed `vellis serve` command and `vellis-rtg-knowledge-graph` executable alias reach the
same STDIO boundary. `vellis serve-mcp` is retained as a command alias, and a bare `vellis` invocation
continues to serve for existing registrations. Packaging does not select remote hosting,
authentication, deployment, or plugin packaging; those remain outside the contract.

The selected owner of this behavior is the setup program. Repeating `--client codex` or
`--client claude` selects either or both clients; omitting `--client` selects neither. Setup previews
the public inspection and mutation commands before confirmation, treats a matching entry as a no-op,
and requires `--replace-client CLIENT` before replacing a differing entry. Matching includes the
enabled user scope, STDIO command and arguments, and an empty launch environment; another transport,
destination-bearing environment, scope, or enabled state is a difference. Client inspection and
connection outcomes are reported separately from memory initialization, name their failed stage,
state the memory effect of the complete setup operation, and provide an exact client-only retry
command. An unavailable client is told to repair its public inspection command before retrying; an
unparseable inspection must first become a readable absent, matching, or differing state, or stop
for owner direction. Linux and Windows command rendering, paths containing spaces, and non-default
destinations have fake-client evidence.

Corrective slice S018 implements decisions D004 and D005. Closure decision D006 reran the matching
live dry run and reread both matching entries. Codex desktop then exercised all ten public tools in
one owner scenario, restored the active starter vocabulary, removed its synthetic graph data, and
left revision 8 conforming with no staged proposal. Claude Code completed a bounded
`rtg_definition_summary` invocation against that state. Those accepted observations combine with
the reproducible project boundary, setup, persistence, inventory, registration, and dry-run evidence
to close A017, D006, and the runnable campaign boundary without changing client approval policy.

The commands below are a manual source-checkout fallback when automated registration was not
selected or completed, not the selected primary workflow. They still require the named client CLI;
if it is unavailable, install or repair it until its public inspection command succeeds before
retrying registration. An installed artifact instead registers the absolute interpreter
that owns the package with `-m vellis`, so later client launches do not depend on an activated shell
or a source checkout. For the checkout form, establish a system first with `vellis setup` (or
`uv run python -m vellis.setup`),
then, with `VELLIS` standing for the absolute path of this clone:

```sh
VELLIS=/absolute/path/to/this/clone

codex mcp list                       # what is registered now
codex mcp remove vellis              # only if that list shows a vellis entry that differs
codex mcp add vellis -- uv --directory "$VELLIS" run python -m vellis

claude mcp list                      # what is registered now
claude mcp remove vellis             # only if that list shows a vellis entry that differs
claude mcp add --scope user vellis -- uv --directory "$VELLIS" run python -m vellis
```

The two `list` commands come first because they, not this page, are what say where the entries
actually stand: skip both the `remove` and the `add` for a client whose `vellis` entry already
matches, and skip only the `remove` for one that has no entry at all. Codex is user-scoped already,
which is why only `claude mcp add` carries `--scope user`. `--directory` is what makes the launch
work from wherever the client starts it, since the module is resolved out of this project, so
`VELLIS` has to be a real absolute path before either `add` runs — neither CLI checks the command it
stores, and a wrong one fails at launch instead. Add `--data-dir DESTINATION` after `-m vellis` when
setup put the system somewhere other than its default, and list again afterwards to confirm. Any
state drift, different destination, unsupported CLI behavior, or permission-policy change stops for
the owner's direction instead.

The completed macOS closure supplies the initial real-client runnable evidence. Matching enabled
user-scoped STDIO entries remain idempotent no-ops; conflicting or unparseable state, another
destination, unsupported behavior, or any approval-policy consequence still requires owner
direction. Linux and Windows remain tested command-rendering compatibility targets rather than live
closure environments.
The client command contracts are
documented by
[OpenAI](https://learn.chatgpt.com/docs/extend/mcp) and
[Anthropic](https://docs.anthropic.com/en/docs/claude-code/mcp).
