# Security

Vellis is beta-stage software and should not be used yet with sensitive production data.

## Reporting

Do not disclose security issues publicly before maintainers have had a chance to respond. Use GitHub private vulnerability reporting on [`volantlabs/vellis`](https://github.com/volantlabs/vellis/security/advisories) when it is enabled for the repository. If private reporting is not available, email the maintainer at <mloumagnuson@gmail.com>.

## Scope

Useful reports include:

- unsafe file writes or path traversal
- unexpected network or subprocess behavior
- dependency or packaging vulnerabilities
- MCP interface behavior that exposes unintended data or mutation authority
- failures to preserve audit, replay, or recovery guarantees

## Beta Caveat

The RTG Knowledge Graph reference app currently uses in-memory RTG stores for live graph, schema, constraint, and migration state. Treat beta eval storage roots and snapshots as local test artifacts, not production records.
