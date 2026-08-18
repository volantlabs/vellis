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

Vellis stores and canonical snapshot documents are plaintext at rest. On POSIX systems (macOS and
Linux), new Vellis data directories are mode `0700`, and databases, WAL/SHM companions, import
temporaries, and published snapshots are mode `0600`. Vellis fails closed before opening an
existing data directory or database that is symlinked, not a regular owner-owned path, lacks the
required owner access, or grants group/other access. It does not silently change permissions; after
verifying the path and ownership, use the reported `chmod 0700 -- DIRECTORY` or
`chmod 0600 -- FILE` guidance. Windows continues to use the owner's profile location and native
default ACLs; this prerelease does not claim verified Windows ACL enforcement. Filesystem modes do
not provide encryption, so use platform full-disk or file-level encryption where confidentiality at
rest is required.

Useful reports include unsafe runtime, store, CLI, snapshot, or MCP-boundary behavior; destructive
or unexpected file handling; unexpected network or subprocess behavior; dependency vulnerabilities;
checksum failures; and paths that could expose or modify ignored user data. The `.data/` directory
is local, may contain owner memory, and is outside repository checks; never include its contents in a
public report.
