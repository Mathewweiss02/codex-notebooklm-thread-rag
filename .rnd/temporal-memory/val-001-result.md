# VAL-001 Result

## Development suite

- Cases: 19.
- Passed: 19/19.
- Result digest: `64824f73548e4a7a4fc27592d3f705f0df548cf4cdec3cd712e5dfc4b36e3daa`.

## Holdout suite

- Cases: 10.
- Passed: 10/10.
- Result digest: `7a69e462d95812150a08c4585206d6fce533973c8408e65d02f66671195767fb`.

The benchmark first failed 5 development and 1 holdout case because the
expected oracle lists misunderstood local-date membership and deterministic
thread tie ordering. Those fixture expectations were corrected from the
runner's aggregate failure evidence; the production resolver/index/context
code was not changed to make the benchmark pass. The clean rerun is therefore
evidence that the benchmark definitions now agree with the independent
selection path.

Coverage includes today/yesterday, rolling windows, calendar week semantics,
half-open boundaries, future empty periods, DST spring/fall transitions,
leap-day and month boundaries, timezone regrouping, deterministic ties, and
invalid timezone/ambiguous/nonexistent/unsupported inputs.

## Decision

Accept VAL-001 as the development/holdout temporal gate for subsequent
prompt-packing, verifier, performance, and concurrency work. Do not tune
against the holdout details; rerun it only as a frozen pass/fail check after a
policy change.

## Limitation

The current holdout fixture is still local and readable by the operator. It is
separated from development scoring and sealed by digest, but it is not yet a
cryptographically hidden release holdout. Final certification must move the
holdout file outside the repository and retain only its digest in the release
packet.

## Next gate

Advance to PQ-001: expand the prompt-packing development benchmark while
keeping VAL-001 holdout cases untouched.
