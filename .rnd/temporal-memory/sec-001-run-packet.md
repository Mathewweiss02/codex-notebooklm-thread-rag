# SEC-001 Run Packet: Privacy, dependency, and retention gate

## Objective

Verify that credentials and private answer text stay out of repository
artifacts, redaction surfaces agree, ignored generated state is blocked, and
the locked dependency graph has no known vulnerabilities.

## Checks

- Confirm required auth/config/generated-state patterns are ignored and no
  credential-like file is tracked.
- Run redaction and projection tests.
- Run profile ACL integration.
- Export the locked dependency graph and run strict hash-aware `pip-audit`.
- Confirm live reports store aggregate hashes/counts rather than answers or
  cited passages.
