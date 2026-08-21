# Phase 7 — MCP, transports, setup, and client onboarding

## Conformance frame

Qualified authority is `Vellis::'Connect trusted MCP agent'`,
`VellisRequirements::'MCP Boundary Integrity'`,
`VellisRequirements::'Simple Secure Individual Operation'`, and
`VellisVerification::'MCP And Owner Lifecycle Are Truthful'`, with the selected
realization recorded by D008 and W007. Phase 7 makes the already implemented successor
operations runnable. It does not change RTG meaning.

| Boundary | In-scope obligation | Required non-effect | Nearest wrong implementation | Evidence |
|---|---|---|---|---|
| Ten tools | Strict ordinary JSON schemas bind each selected operation | No extra tool, match/get split, status tool, recursive user JSON, or adapter domain-conformance decision | A renamed predecessor tool still reaches the monolith | Schema, list, call, malformed/semantic/runtime tests |
| Transactions | One successor operation and connection per call; response is serializable before its commit | No shared connection or fabricated rollback | Adapter owns state or reuses a connection | operation instrumentation and concurrent HTTP calls |
| STDIO | Public FastMCP lifecycle supports initialize/list/call and EOF | No private MCP hooks or monkeypatch | Custom protocol transport repairs framework output | installed and in-process public client probes |
| HTTP | Exact `/mcp`, complete bearer protection, selected host/token rules, one connection per request | No TLS, OAuth, users, daemon, service manager, token disclosure | Authentication covers only tool calls or literal token reaches argv/logs | ASGI/auth matrix and concurrent calls |
| Owner CLI | Only setup/connect/serve/backup/restore/audit/configure | No preserve, serve-mcp, alias, prototype migration, or background process | Legacy dispatcher remains the installed boundary | parser inventory and installed artifact tests |
| Setup | Interactive starter/blank/v1/backup choice and explicit noninteractive state machine; connection follows publication | No guessed choice or rollback after client failure | Setup silently falls back to blank or couples registration to publication | mode/preview/confirmation/failure tests |
| Clients | Public Codex/Claude CLI status/add/remove only; existence and replacement precede preflight | No config parsing/files, secret argv, or claimed external rollback | An existing entry is probed or removed before replacement is authorized | fake CLI argv/state matrix |
| Packaging | Exact stable pins and one `vellis` executable work from wheel and sdist | No beta/private fallback or old executable alias | Source checkout works while installed artifact fails | package smoke and artifact tests |

## Boundary inventory before coding

### Tool schemas and operation bindings

| Tool | Strict input | Successor operation | Accepted payload |
|---|---|---|---|
| `rtg_type_summary` | optional state | `type_summary` | complete anchor types |
| `rtg_type_inspect` | state, anchor keys, legacy flag | `type_inspect` | focused neighborhoods |
| `rtg_query` | state plus identity or pattern selection | `query_graph` | bounded matches/objects |
| `rtg_change` | expected revision, upserts, removals | `apply_graph_change` | outcome/revisions |
| `rtg_draft_inspect` | fresh filters/page or cursor | `inspect_draft` | raw/effective entries |
| `rtg_draft_change` | definition/object stage or unstage commands | `change_draft` | draft counts |
| `rtg_validate` | fresh scope/page or continuation | `validate_state` | findings page |
| `rtg_draft_activate` | empty | `activate_draft` | outcome or validation page |
| `rtg_draft_discard` | empty | `discard_draft` | outcome |
| `rtg_history` | ledger/range/maximum/detail | `inspect_history` | complete selected interval |

All adapter models use JSON-native literal discriminators, strict Pydantic validation, and unknown
members forbidden; conversion to domain enums happens once. Draft inspection and validation expose
two closed `oneOf` request schemas so fresh and continuation members cannot be mixed. A
Pydantic/FastMCP argument error forms no domain request or activity. A typed domain refusal is
ordinary structured `accepted`/`rejected` output. An unexpected operation exception remains an MCP
execution error. Operation functions retain activity and commit ownership; precommit serialization
and the adapter share one framework-free public projection.

### Lifecycle and security inventories

- STDIO: validate database, close probe, resolve the absolute installed `vellis` console script,
  initialize, list, call, EOF/interruption, and register the exact probed command and absolute data
  directory.
- HTTP host/token: `127.0.0.1`, `::1`, and `localhost` may explicitly develop without a
  token; guided setup creates at least 256 random bits; every other host requires a
  readable nonempty owner-private token. Missing, multiple, wrong-scheme, invalid, and
  valid authorization are distinct cases. Raw ASGI middleware protects the complete app and uses
  constant-time comparison for both rejected and accepted bearer values. Real lifecycle evidence
  covers both token-protected HTTP and explicit loopback development without a token.
- CLI commands: setup, connect, serve, backup, restore, audit, configure. Every parser
  combination has an explicit mode; noninteractive setup never guesses initialization or
  connection. Setup has no `--yes` shortcut: interactive initialization always confirms, while
  noninteractive initialization is authorized by its explicit mode and connect/no-connect choice.
  Connect, restore, and configure retain their selected `--yes` behavior.
- Client matrix: Codex/Claude × absent/existing × STDIO/HTTP × add/replace/remove-failure/
  add-after-remove-failure/final-probe-failure. Claude HTTP additionally requires public CLI help
  that explicitly documents environment-variable header-template expansion. Existence and the `--replace` requirement precede
  target preflight; an absent or replace-authorized entry is probed before mutation. Recovery output
  contains the exact secret-free add command, while a failed final probe reports that the external
  entry changed and readiness is unconfirmed.
- Token secrecy sinks: process arguments, stdout/stderr, application logs, activity,
  reports, backups, exception text, CLI recovery commands, and test snapshots.
- Packaging paths: installed wheel and sdist each exercise exact blank and starter initialization,
  backup initialization, preview-and-digest-confirmed v1 initialization, the registered `vellis
  serve` STDIO command, bearer HTTP, explicit loopback/no-token HTTP, nested JSON-native wire enums,
  fresh draft/validation shapes, audit, backup, exact dependency metadata, and no legacy executable.

The intentionally deferred set remains closed: TLS termination, OAuth, roles, users,
tenants, daemon/service/container management, config-file editing, shell-profile mutation,
and alternate MCP/client frameworks are absent rather than stubbed.

### Bounded root-cause audit inventory

Every successor connection-owning operation that appends activity converges through the same
framework-free `public_result` projection and non-finite-forbidden `serialize_wire` call before its
activity append and commit:

| Operation family | Result paths inventoried |
|---|---|
| Active graph change | semantic rejection, accepted no-op, accepted revision |
| Draft change | rejected structure/reservation, accepted staged/no-op |
| Draft inspection | rejected fresh shape, fresh page, continuation/expiry |
| Validation | current/draft fresh result, continuation/expiry |
| Activation | absent, invalid, redundant clear, effective revision |
| Discard | absent and present |
| Discovery | accepted/rejected summary and focused inspection |
| Query | accepted/rejected identity/pattern and missing state |
| History | accepted, invalid range/detail, over-limit canonical/activity |
| Restore | refusal, no-op, effective revision |
| Configuration | activity-mode changed/no-op; HTTP-token pre-effect projection and post-effect activity |

Private `_wire` helpers now encode only normalized request, finding, cursor, or stored semantic
activity details; no private helper defines a public response. Verbose response payloads reuse
`public_result`. Failure injection covers each mutation family, all four activation branches,
fresh/continuation draft reads, restore, discovery/query/history, activity configuration, and token
configuration. A projection/serialization failure rolls back canonical state, draft state,
validation backing, settings, and activity; token publication is invoked only after projection.

The complete adapter-value inventory validates before operation dispatch: every object, endpoint,
association, removal, identity filter, and draft UUID uses the reusable canonical UUID wire type;
state/history timestamps and timestamp scalar values use one canonicalizing RFC 3339 wire type;
date scalar values use one Gregorian-date wire type; revision and sequence values are nonnegative;
integers are safe-range bounded and numbers finite. In-process, installed STDIO, and installed HTTP
malformed-value matrices prove invalid values create neither domain requests nor activity.
Predicate input is a JSON-native discriminated union at the discovered boundary: presence/nullness,
scalar equality/order, `anyOf`, text, term, and phrase operators each expose only their required
payload. Equality, inequality, and ordering require a non-null scalar; nullable null remains valid
only inside `anyOf`. Irrelevant or missing members, empty alternatives/terms/phrases, display-name
presence, and direct null comparison are invalid arguments before operation dispatch; source and
installed STDIO/HTTP matrices exercise those distinctions without activity.

The second bounded audit enumerates every nested definition constructor and separates malformed
wire structure from draft meaning. Pydantic rejects wrong JSON types and members, unknown
discriminators, noncanonical scalar syntax, unsafe/non-finite scalar representations, invalid or
inverted cardinalities that the domain constructor cannot represent, and duplicates in explicitly
set-like permitted-type/property/allowed-value collections. It does not decide definition
conformance. Empty names/descriptions/populations, a zero anchors-per-object minimum, empty allowed
values, incompatible or inverted property bounds, negative/inverted text lengths, allowed values
outside their rule, and malformed definition patterns all stage as normalized raw draft entries and
surface as dirty findings from `rtg_validate`. Draft persistence retains otherwise-invalid scalar
bounds without widening canonical definition storage. The table-driven dirty matrix runs
in-process, through real source STDIO and bearer HTTP, and from installed wheel/sdist transports;
audit and backup accept the normalized dirty bucket. The malformed matrix creates no operation
activity.

The installed CLI captures its own absolute console-script path once at startup. Setup and connect
pass that exact value through probe, registration, and every guided serve/connect command; they
never search `PATH` again. Artifact tests put a failing `vellis` decoy first on `PATH`, parse the
printed commands, and prove that each retains the captured wheel/sdist executable. Interactive setup
publishes the confirmed initialization before asking transport/client questions; refusal or
initialization failure asks none. Setup reports registration summaries, recovery commands, changed
external state, and unconfirmed readiness while preserving successful initialization and returning
failure. Remove/add/final-probe nonzero and exception paths have explicit secret-free recovery.
The complete registration result table covers existing/no-replace, confirmation, preflight,
remove/add nonzero and exceptions, post-add probe loss, absent-add success, and replacement success.
Readiness defaults false and becomes true only after the second successful target probe; mutation
order and CLI exit behavior are asserted. Existing HTTP/no-replace guidance precedes environment
and target preflight, while an absent entry or authorized replacement requires its environment token.

HTTP-token rotation projects its response before invoking the filesystem publication callback. Once
publication occurs, activity, durability, supported-client enumeration, and output failures retain
the truth that the token file changed, a running server retains its old credential until foreground
restart, every HTTP client must then reconnect, supported enumeration may be incomplete, and manual
clients cannot be enumerated. A real server accepts old/rejects new before restart and reverses that
result after restart.
Rotation changes only the default token file. A real server started with a custom `--token-file`
continues to accept that custom credential before and after default rotation and after restart;
output and failure paths tell the owner to replace the custom file themselves before restarting and
reconnecting.

Server startup has three explicit pre-request failure stages. Database probing names setup/audit as
the corrective action, token validation names the required readable nonempty owner-private file,
and HTTP bind/start failure names host/port selection. A real occupied-port process exits nonzero;
all three cases leave canonical and activity state unchanged.

The Review 8 boundary sweep preserves optional-definition presence without adding public draft
metadata. An omitted `allowedValues` remains absent and unconstrained; an explicit empty list is
stored in the normalized draft, appears as `allowedValues: []` in inspection, produces the isolated
nonempty-list finding, and blocks activation while leaving the draft auditable and backup-safe.
Zero-valued length bounds and empty pattern text already retained their presence through nullable
columns, so no other optional constraint needed a presence marker. Public and semantic-activity
serialization omit absent allowed values and retain an explicitly present list. Token files likewise
retain exact nonempty bytes: leading/trailing spaces participate in comparison and a trailing
newline is never silently normalized into an authenticating credential.

The Review 9 sweep inventories every omissible nested wire member and every top-level tool default.
One shared Pydantic pre-validator rejects an explicitly supplied JSON null while omission still
selects the documented default. Reusable `SkipJsonSchema` annotations keep null out of discovered
optional-member schemas; the only remaining raw-null schema is the `value` inside the intentional
tagged `{kind: "null", value: null}` scalar branch. The complete in-process table creates no
activity, and representative real STDIO/HTTP tables exercise state, graph-patch, definition,
filter/cursor, and history cases. Serve ports are parsed as 1 through 65,535 before database/server
startup; invalid text, zero, and overflow exit with an actionable bind-port message, no traceback,
and no activity.

Dirty-definition evidence now stages a conforming local anchor alongside each affected definition.
Every allowed-value, bound, length, pattern, wrong-kind, cardinality, and empty-population case
asserts one exact finding code and path, so no unknown reference can make the matrix pass. Setup has
an explicit mode/flag matrix: report output is preview-only; preview is v1-only and forbids
connection/confirmation options; confirmed v1 requires both digests; other initialization modes
reject all v1-only flags. Source and installed parser evidence proves these refusals publish no
destination and register no client.

The Review 10 projection audit classifies every nullable field transitively reachable from a
public result root. Ordinary optional findings, revisions, cursors, legacy metadata, property
constraints, kind-inapplicable hydrated fields, and history detail remain omitted; the two draft
inspection before/after members are the sole required-null fields. The framework-free projector
rejects an unclassified `None`, and a mechanical dataclass walk requires every newly reachable
nullable result field to join exactly one of those two finite policies. Empty finding references
remain omitted, while intentional null user-property values inside hydrated maps remain JSON null.
Draft definition additions expose `current: null` and removals expose `proposed: null` on fresh and
continuation pages through in-process, real STDIO, bearer HTTP, and installed wheel/sdist probes.
The already-inventoried precommit paths continue to share this exact projector through
`serialize_wire` and semantic/verbose activity response projection; no second response shape was
introduced.

## Evidence status

Candidate evidence, measured from the exact working tree before review:

- 65 focused MCP/CLI tests pass; the combined change/draft/history/recovery/MCP root-audit set
  passes 234 tests.
- The reproducible successor union passes **553 tests** using exactly:

  ```text
  uv run pytest -q tests/test_repository_policy.py \
    tests/vellis/test_domain_v2.py tests/vellis/test_storage_v2.py \
    tests/vellis/test_canonical_encoding_v2.py tests/vellis/test_query_v2_successor.py \
    tests/vellis/test_change_draft_v2.py tests/vellis/test_history_recovery_v2.py \
    tests/vellis/test_v1_import_v2.py tests/vellis/test_mcp_lifecycle_v2.py
  ```

  The predecessor `test_query_contract_v2.py` is W008 residue and intentionally excluded.
- The complete suite reports 1,674 passed and three expected failures: the two F010 completed-
  campaign failures assigned to W008 and the pre-bookkeeping committed-evolution baseline check
  whose HEAD copy necessarily lacks this candidate's dependency digest.
- `ruff` F821, repository lint/format, basedpyright, model, pinned-reference, evolution, skills, and
  diff checks pass.
- C901 at maximum 10 passes across every new or rewritten Phase 7 production module; the largest is
  the 796-physical/767-logical-line schema declaration, below the 800-logical-line subtraction
  trigger. The largest orchestration module is 706 physical/626 logical lines.
- `just package-check` builds and installs both wheel and sdist, then proves blank and exact starter
  setup, backup and confirmed-v1 setup, registered-command STDIO, bearer and loopback/no-token HTTP,
  representative nested wire calls, audit, backup, and absence of the old executable.
- Production uses no private FastMCP/MCP symbol, direct `fastmcp-slim` dependency, schema rewrite,
  server monkeypatch, client configuration-file access, or literal-token process argument.

The candidate is not frozen until the parent manager records the exact state token.
