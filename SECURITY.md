# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report security issues privately via [GitHub's private vulnerability reporting](https://github.com/kalink0/crush-forensics/security/advisories/new), or by emailing **crush@be-binary.de**.

Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected version(s)

## Scope

Crush is a **read-only** forensic analysis tool. It opens and displays evidence files but never writes to the source. Relevant security concerns include:

- Maliciously crafted evidence files (ZIP, TAR, SQLite, plist, Protobuf, Realm, etc.) that trigger crashes or arbitrary code execution in parsers
- Path traversal or directory escape when extracting/exporting files
- Unexpected network access (Crush is designed to be fully offline)
