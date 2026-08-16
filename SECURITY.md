# Security

## Reporting

Do not disclose security issues publicly before maintainers can respond. Use GitHub private
vulnerability reporting for [`volantlabs/vellis`](https://github.com/volantlabs/vellis/security/advisories)
when available. Otherwise email <labs@volantpartners.com>.

## Current scope

This repository contains the runnable local Vellis application as well as its SysML v2 system model
and development tooling. The implemented MCP boundary is a local STDIO subprocess launched by one
trusted, owner-configured client. It does not listen on a network port, provide an authenticated
remote endpoint, or decide per-call authorization. Advisory tool annotations describe behavior and
do not enforce authorization.

Useful reports include unsafe runtime, store, CLI, snapshot, or MCP-boundary behavior; destructive
or unexpected file handling; unexpected network or subprocess behavior; dependency vulnerabilities;
checksum failures; and paths that could expose or modify ignored user data. The `.data/` directory
is local, may contain owner memory, and is outside repository checks; never include its contents in a
public report.
