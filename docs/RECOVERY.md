# Recovery and rollback

## Browser sign-in closes early

Rerun the profile's master login with `--fresh`, complete Google sign-in, and leave the window open until the terminal reports success. Then run the browserless refresh command. Do not keep retrying with multiple windows open.

## Master-token refresh fails

Stop scheduled uploads. Run `doctor-*`, then recapture only the affected profile. Do not copy a token from another profile or weaken the account check.

## A scheduled task fails

Inspect the newest JSON file under the configured projection root's `runs` directory and `runner_state.json`. The doctor rejects stale timestamps and a latest `LastStatus` other than `ok`. Correct the failing step, run the runner manually, then trigger the Scheduled Task once. Require parsed JSON auth status `ok`, exit code 0, and strict source reconciliation before considering it healthy.

## Automatic enrollment fails

Do not add only the tasks that happen to fit. Run `notebooklm_thread_enroll.py` without `--apply`, inspect the staged-projection or source-budget failure, and either repair the task or create a new planned shard. The explicit scope is updated only after every newly visible task passes.

## Retention reports unexpected candidates

Leave `RetentionApply=false`. Confirm the state references current and previous lineage under the configured projection root. Retention refuses paths outside its guarded roots; never work around that guard with a broader root.

## Projection policy changes

The uploader refuses unknown policy versions. Review the new projection boundary, rerun sanitizer tests, rebuild a sacrificial notebook, and repeat the retrieval benchmark before promotion.

## Interrupted upload

Rerun the same sync. Exact-title ready sources are reused and state is checkpointed after each accepted source. Old lineage-linked sources are deleted only after the full new revision is ready.

## Reconciliation fails

Do not delete sources blindly. Compare state-linked source IDs and titles with the live notebook. Repair or re-upload the missing revision, then use guarded swaps. Never delete a source that is not explicitly linked to the task's prior revision.

## NotebookLM unavailable

Use local Codex metadata and deterministic ThreadOps content search. The semantic notebook is optional acceleration, not the authoritative archive.
