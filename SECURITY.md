# Security

## Reporting

Do not disclose security issues publicly before maintainers can respond. Use GitHub private
vulnerability reporting for [`volantlabs/vellis`](https://github.com/volantlabs/vellis/security/advisories)
when available. Otherwise email <labs@volantpartners.com>.

## Current scope

This reset contains a draft SysML v2 model and development tooling. It does not contain a supported
Vellis runtime, service, CLI, installable package, or migration utility.

Useful reports include unsafe development-tool file handling, unexpected network or subprocess
behavior, dependency vulnerabilities, checksum failures, and paths that could expose or modify
ignored user data. The `.data/` directory is local and outside repository checks; never include its
contents in a public report.
