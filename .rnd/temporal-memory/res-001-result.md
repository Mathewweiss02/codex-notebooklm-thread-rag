# RES-001 Result

## Gate

- Full suite: 34 Node tests and 108 Python tests passed.
- Corrupt/unsupported temporal indexes fail closed and retain a rebuild path.
- Bad handoffs and oversized visible lines do not publish partial state.
- Stale runner success and auth JSON with `status=error` fail the doctor even
  when the process exit code is zero.
- Out-of-scope sources, projection drift, unsupported citations, wrong-day
  literals, follow-up state, and unmatched evidence abstain in the verifier.
- Executor operation/checkpoint failures raise aggregate codes and never return
  a partial-success list.

## Decision

Accept RES-001 for the modeled failure classes. Process-kill, disk-full, and
multi-day soak evidence remain release gates before a final certificate.
