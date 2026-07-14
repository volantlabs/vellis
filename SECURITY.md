# Security

Vellis is beta-stage software and should not be used yet with sensitive production data.

## Reporting

Do not disclose security issues publicly before maintainers have had a chance to respond. Use GitHub private vulnerability reporting on [`volantlabs/vellis`](https://github.com/volantlabs/vellis/security/advisories) when it is enabled for the repository. If private reporting is not available, email the maintainer at <labs@volantpartners.com>.

## Scope

Useful reports include:

- unsafe file writes or path traversal
- unexpected network or subprocess behavior
- dependency or packaging vulnerabilities
- MCP interface behavior that exposes unintended data or mutation authority
- failures to preserve audit, replay, or recovery guarantees

## Beta Caveat

Vellis is intended for a person's own local graph or a graph shared deliberately on a private
machine. Ordinary stdio mode opens no network service; advanced HTTP mode is unauthenticated and
must remain bound to `127.0.0.1`.

Graph state is reconstructed from the durable local controller ledger and stored unencrypted under
the ignored `.data/rtg_knowledge_graph/` directory by default. The AI agent or model connected to
Vellis can receive graph contents when it invokes tools. Back up local state as appropriate and do
not use it for information you are unwilling to provide to that client or model. Vellis does not
yet provide encryption, authentication, user accounts, or multi-user authorization.
