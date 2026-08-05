# Security

## Reporting

Do not disclose security issues publicly before maintainers can respond. Use GitHub private
vulnerability reporting for [`volantlabs/vellis`](https://github.com/volantlabs/vellis/security/advisories)
when available. Otherwise email <labs@volantpartners.com>.

## Current scope

This repository currently contains a SysML v2 system model and development tooling, not an
application implementation. The modeled MCP tool contract is not a deployed server, authenticated
endpoint, or claim that advisory tool annotations enforce authorization.

Useful reports include unsafe development-tool file handling, unexpected network or subprocess
behavior, dependency vulnerabilities, checksum failures, and paths that could expose or modify
ignored user data. The `.data/` directory is local and outside repository checks; never include its
contents in a public report.
