# VAL-001 Run Packet

## Mission

Create a repeatable temporal benchmark surface with independent expected
logical identities, development cases, and a held-out case set before tuning
prompt packing or concurrency.

## Safety boundary

- The runner constructs production-shaped event IDs and a temporary SQLite
  index from synthetic fixture data.
- Expected logical identities live in the fixture and are compared against
  both direct index selection and the context packer.
- Resolver cases use fixed `now` values and explicit IANA time zones.
- Reports contain case IDs, counts, statuses, and digests only; fixture text
  and message identities are not copied into result reports.
- Development and holdout cases are scored separately. The holdout digest is
  recorded before later tuning work.

## Method

1. Build a temporary canonical event handoff from the fixture.
2. Rebuild a temporary SQLite index.
3. Resolve each fixed natural-language or explicit range through the Node ICU
   resolver.
4. Compare exact half-open index membership and deep context-pack membership
   against the fixture's expected logical identities.
5. Run expected invalid-time cases and require the exact error class.
6. Write aggregate result files and stable result digests.

## Reproducibility commands

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python scripts/temporal_validation_runner.py `
  --suite .rnd\temporal-memory\fixtures\val-001-suite.json `
  --set development `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\val-001-development-result.json"
& $python scripts/temporal_validation_runner.py `
  --suite .rnd\temporal-memory\fixtures\val-001-suite.json `
  --set holdout `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\val-001-holdout-result.json"
```

The current holdout is synthetic and local. It is a benchmark separation
surface, not a secret from the local operator; a release-grade holdout should
be moved outside the repository and referenced by digest before final tuning.
