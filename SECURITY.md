# Security

## Reporting

Do not disclose security issues publicly before maintainers can respond. Use GitHub private
vulnerability reporting for [`volantlabs/vellis`](https://github.com/volantlabs/vellis/security/advisories)
when available. Otherwise email <labs@volantpartners.com>.

## Current scope

This repository contains the runnable local Vellis application as well as its SysML v2 system model
and development tooling. Vellis serves a trusted owner-configured client over STDIO or foreground
HTTP. Guided HTTP uses a private bearer token, and non-loopback binding refuses to start without
one. Vellis does not implement TLS, OAuth, users, roles, or per-call authorization; use a trusted
network, Tailscale or SSH tunnel, or an external TLS proxy for non-loopback HTTP. See
[`docs/http-operation.md`](docs/http-operation.md).

Vellis databases, backups, activity, and migration reports are plaintext at rest. Verbose activity
and v1 reports can be especially sensitive. On POSIX systems (macOS and Linux), new Vellis data
directories are mode `0700`, and databases, backups, reports, tokens, WAL/SHM companions, and import
temporaries are mode `0600`. These owner-private modes are the selected local protection boundary;
they are not encryption. Use platform full-disk or file-level encryption when confidentiality at
rest requires it.

Useful reports include unsafe runtime, store, CLI, backup/import, or MCP-boundary behavior; destructive
or unexpected file handling; unexpected network or subprocess behavior; dependency vulnerabilities;
checksum failures; and paths that could expose or modify ignored user data. The `.data/` directory
is local, may contain owner memory, and is outside repository checks; never include its contents in a
public report.
