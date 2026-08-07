# Recovery and rollback

## Browser sign-in closes early

Rerun the profile's master login with `--fresh`, complete Google sign-in, and leave the window open until the terminal reports success. Then run the browserless refresh command. Do not keep retrying with multiple windows open.

## Master-token refresh fails

Stop scheduled uploads. Run `doctor-*`, then recapture only the affected profile. Do not copy a token from another profile or weaken the account check.

## A scheduled task fails

Inspect the newest JSON file under the configured projection root's `runs` directory. Correct the failing step, run the runner manually, then trigger the Scheduled Task once. Require exit code 0 before considering it healthy.

## Projection policy changes

The uploader refuses unknown policy versions. Review the new projection boundary, rerun sanitizer tests, rebuild a sacrificial notebook, and repeat the retrieval benchmark before promotion.

## Interrupted upload

Rerun the same sync. Exact-title ready sources are reused and state is checkpointed after each accepted source. Old lineage-linked sources are deleted only after the full new revision is ready.

## Reconciliation fails

Do not delete sources blindly. Compare state-linked source IDs and titles with the live notebook. Repair or re-upload the missing revision, then use guarded swaps. Never delete a source that is not explicitly linked to the task's prior revision.

## NotebookLM unavailable

Use local Codex metadata and deterministic ThreadOps content search. The semantic notebook is optional acceleration, not the authoritative archive.
