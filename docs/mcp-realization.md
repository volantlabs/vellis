# MCP realization

This is implementation guidance; the SysML under `model/` remains system authority.

The runnable boundary uses stable FastMCP public APIs and ordinary strict Pydantic input models.
Each call converts once to the framework-free successor domain, invokes one connection-owning
operation, and projects its already validated result to ordinary JSON. The adapter does not decide
graph validity, draft meaning, revision effects, or activity. Unknown wire members and malformed
shapes fail argument validation before an operation runs; semantic refusals are structured rejected
results; unexpected failures remain MCP errors.

The public tools are `rtg_type_summary`, `rtg_type_inspect`, `rtg_query`, `rtg_change`,
`rtg_draft_inspect`, `rtg_draft_change`, `rtg_validate`, `rtg_draft_activate`,
`rtg_draft_discard`, and `rtg_history`. Their count is not an internal architecture. A cold agent
starts with summary and focused inspection, uses identity query directly for known UUIDs or pattern
query for connected questions, requests only needed properties, and narrows an over-broad match.
Active change assumes owner approval in the surrounding workflow. The draft workflow is inspect,
effective query, validate, activate or discard; it has no status/version or assessment token.

STDIO and HTTP use FastMCP's public server and client lifecycles. HTTP is a foreground Uvicorn
application at `/mcp`; a small raw ASGI middleware protects the entire application with one bearer
token. Vellis uses no private framework request objects, schema rewriting, monkeypatching, custom MCP
transport, or shared SQLite connection.

Codex and Claude registration uses only their public CLIs. Vellis checks only the fixed `vellis`
entry's existence by exit status, probes the intended target before mutation, requires explicit
replacement, removes and adds through public commands, and reports add-after-remove failure with an
exact secret-free recovery command. It never reads or edits a client configuration file and never
claims an external client change was rolled back.
