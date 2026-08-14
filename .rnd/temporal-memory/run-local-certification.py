"""Run exact deterministic certification cases and retain aggregate-only evidence.

This packet intentionally excludes live NotebookLM calls, prompts, answers,
source IDs, and machine paths.  A row is eligible for promotion only when its
mapped focused test command exits successfully; live, soak, and replica rows
remain outside this local packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cases(node: str) -> list[dict[str, object]]:
    extract = "tests/thread_temporal_extract.test.mjs"
    return [
        {"id": "IDX-001", "label": "new session visible-message inventory", "command": [node, "--test", "--test-name-pattern", "indexes every visible message in a new session exactly once", extract]},
        {
            "id": "IDX-002",
            "label": "unchanged incremental no-op",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_unchanged_handoff_is_an_exact_incremental_no_op"],
        },
        {
            "id": "IDX-003",
            "label": "appended canonical events",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_incremental_update_removes_stale_events_and_retains_last_good_on_bad_handoff"],
        },
        {"id": "IDX-004", "label": "active to archive move", "command": [node, "--test", "--test-name-pattern", "preserves canonical identity when a thread moves from active to archive", extract]},
        {
            "id": "IDX-005",
            "label": "active/archive duplicate canonicalization",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_build_deduplicates_lineage_and_queries_half_open_ranges"],
        },
        {"id": "IDX-010", "label": "tool and reasoning payload exclusion", "command": [node, "--test", "--test-name-pattern", "keeps tool and reasoning payloads out of visible temporal events", extract]},
        {"id": "IDX-011", "label": "duplicate message identity", "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_build_deduplicates_lineage_and_queries_half_open_ranges" ]},
        {"id": "IDX-013", "label": "missing timestamp quarantine", "command": [node, "--test", "--test-name-pattern", "quarantines missing and invalid timestamps without assigning a day", extract]},
        {"id": "IDX-014", "label": "invalid timestamp quarantine", "command": [node, "--test", "--test-name-pattern", "quarantines missing and invalid timestamps without assigning a day", extract]},
        {"id": "IDX-006", "label": "resumed old thread", "command": [node, "--test", "--test-name-pattern", "resumed old thread", extract]},
        {"id": "IDX-007", "label": "forked thread identity", "command": [node, "--test", "--test-name-pattern", "forked thread identity", extract]},
        {"id": "IDX-008", "label": "subagent policy", "command": [node, "--test", "--test-name-pattern", "excludes subagent sources", extract]},
        {"id": "IDX-009", "label": "compaction exclusion", "command": [node, "--test", "--test-name-pattern", "excludes compaction summaries", extract]},
        {"id": "IDX-012", "label": "same text at different time", "command": [node, "--test", "--test-name-pattern", "same text at different timestamps", extract]},
        {"id": "IDX-015", "label": "malformed JSONL", "command": [node, "--test", "--test-name-pattern", "malformed and partial lines", extract]},
        {"id": "IDX-016", "label": "partial final line", "command": [node, "--test", "--test-name-pattern", "malformed and partial lines", extract]},
        {"id": "IDX-018", "label": "Unicode and bidi", "command": [node, "--test", "--test-name-pattern", "malformed and partial lines", extract]},
        {"id": "IDX-019", "label": "transient Windows file lock retry", "command": [node, "--test", "--test-name-pattern", "transient Windows file lock", extract]},
        {"id": "IDX-017", "label": "oversized visible line", "command": [node, "--test", "--test-name-pattern", "blocks an oversized visible line instead of publishing a partial handoff", extract]},
        {
            "id": "IDX-020",
            "label": "concurrent index writers",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_concurrent_writers_serialize_and_leave_a_valid_committed_index"],
        },
        {
            "id": "IDX-021",
            "label": "process kill during transaction",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_process_kill_during_transaction_preserves_last_good_and_rebuilds"],
        },
        {
            "id": "IDX-022",
            "label": "database corruption and rebuild",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_corruption_fails_closed_until_explicit_rebuild"],
        },
        {
            "id": "IDX-023",
            "label": "disk-full rollback",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_incremental_write_failure_rolls_back_to_last_good_state"],
        },
        {
            "id": "IDX-024",
            "label": "schema v1 to v2 migration and rebuild recovery",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_schema_v1_migrates_in_place_and_rebuild_restores_supported_state", "tests.test_thread_temporal_index.TemporalIndexTests.test_missing_v2_metadata_tables_fail_closed_until_explicit_rebuild"],
        },
        {
            "id": "IDX-025",
            "label": "redaction policy change requires rebuild",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_redaction_policy_change_fails_closed_until_rebuild"],
        },
        {
            "id": "PAR-022",
            "label": "overlapping temporal refreshes serialize",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_refresh.TemporalRefreshTests.test_overlapping_refreshes_serialize_and_leave_paired_verified_state"],
        },
        {
            "id": "CTX-001",
            "label": "empty period is explicit",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_drill_down_is_a_scoped_evidence_pack_and_equal_range_is_empty"],
        },
        {
            "id": "CTX-003",
            "label": "one thread many messages is chronological and exhaustive",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_full_pack_is_exhaustive_and_keeps_cross_midnight_segment"],
        },
        {
            "id": "CTX-005",
            "label": "cross-midnight activity retains local-day membership",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_full_pack_is_exhaustive_and_keeps_cross_midnight_segment"],
        },
        {
            "id": "CTX-006",
            "label": "activity segmentation is reproducible",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_full_pack_is_exhaustive_and_keeps_cross_midnight_segment"],
        },
        {
            "id": "CTX-008",
            "label": "giant-thread budget disclosure",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_subset_uses_full_thread_history_and_budget_omissions_are_explicit"],
        },
        {
            "id": "CTX-009",
            "label": "giant-period budget disclosure",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_subset_uses_full_thread_history_and_budget_omissions_are_explicit"],
        },
        {
            "id": "CTX-018",
            "label": "scoped drill-down preserves parent segment",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_drill_down_is_a_scoped_evidence_pack_and_equal_range_is_empty"],
        },
        {
            "id": "CTX-019",
            "label": "context budget omissions are explicit",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_subset_uses_full_thread_history_and_budget_omissions_are_explicit"],
        },
        {
            "id": "CTX-017",
            "label": "period comparison keeps evidence separate",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_cli.TemporalCliTests.test_when_recap_find_and_compare_share_one_resolved_contract"],
        },
        {
            "id": "NLM-005",
            "label": "stale projection blocks remote use",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_projection_digest_drift_degrades_before_remote_use"],
        },
        {
            "id": "NLM-001",
            "label": "current ready source maps",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_current_ready_part_maps_without_previous_lineage"],
        },
        {
            "id": "NLM-002",
            "label": "missing mapped thread degrades",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_missing_thread_degrades_and_strict_boundary_is_available"],
        },
        {
            "id": "NLM-004",
            "label": "previous source lineage remains non-current",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_live_mapping_rejects_untracked_sources_but_allows_previous_lineage"],
        },
        {
            "id": "NLM-006",
            "label": "untracked extra source is rejected",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_live_mapping_rejects_untracked_sources_but_allows_previous_lineage"],
        },
        {
            "id": "NLM-014",
            "label": "persistent chat notebook is excluded from search targets",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_registered_chat_notebooks_are_not_automatic_search_targets"],
        },
        {
            "id": "PAR-005",
            "label": "missing packed section degrades independently",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_pack_benchmark.TemporalPromptPackTests.test_missing_heading_and_out_of_scope_reference_degrade"],
        },
        {
            "id": "PAR-007",
            "label": "citation offset drift uses marker-first mapping",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_pack_benchmark.TemporalPromptPackTests.test_marker_first_mapping_survives_drifted_offsets"],
        },
        {
            "id": "PAR-017",
            "label": "one child failure is explicit and non-partial",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_failure_does_not_return_a_partial_success"],
        },
        {
            "id": "NLM-007",
            "label": "wrong-day citation rejection",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_verify.NotebookLMTemporalVerifierTests.test_rejects_wrong_day_literal"],
        },
        {
            "id": "NLM-008",
            "label": "wrong-thread citation rejection",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_verify.NotebookLMTemporalVerifierTests.test_rejects_out_of_scope_source"],
        },
        {
            "id": "NLM-009",
            "label": "citation-free claim rejection",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_verify.NotebookLMTemporalVerifierTests.test_structural_citation_without_cited_text_is_not_promoted"],
        },
        {
            "id": "NLM-010",
            "label": "remote outage uses verified local fallback",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_remote_outage_uses_real_local_fallback"],
        },
        {
            "id": "NLM-011",
            "label": "expired auth uses verified local fallback",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_expired_auth_uses_real_local_fallback"],
        },
        {
            "id": "NLM-012",
            "label": "429 and 5xx use verified local fallback",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_rate_limit_and_server_error_use_real_local_fallback"],
        },
        {
            "id": "NLM-013",
            "label": "remote timeout uses verified local fallback",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_timeout_uses_real_local_fallback"],
        },
        {
            "id": "PAR-019",
            "label": "bounded adaptive rate-limit mock",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_rate_limiter_applies_bounded_retry_after_backoff", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_rate_limiter_budget_fails_closed", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_executor_rate_limit_burst_is_bounded_and_retried"],
        },
        {
            "id": "CTX-011",
            "label": "heuristic user intent extraction with provenance",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_signals_are_conservative_and_point_only_to_included_evidence"],
        },
        {
            "id": "CTX-012",
            "label": "heuristic completion extraction with provenance",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_signals_are_conservative_and_point_only_to_included_evidence"],
        },
        {
            "id": "CTX-013",
            "label": "heuristic unresolved-item extraction with provenance",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_signals_are_conservative_and_point_only_to_included_evidence"],
        },
        {
            "id": "CTX-014",
            "label": "heuristic artifact extraction with provenance",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_signals_are_conservative_and_point_only_to_included_evidence"],
        },
        {
            "id": "CTX-015",
            "label": "path-free project filter and fail-closed metadata",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_context.TemporalContextTests.test_project_filter_uses_path_free_workspace_metadata", "tests.test_thread_temporal_context.TemporalContextTests.test_project_filter_fails_closed_without_metadata", "tests.test_thread_temporal_cli.TemporalCliTests.test_project_filter_is_available_through_the_primary_cli"],
        },
        {
            "id": "SEC-002",
            "label": "private path projection redaction",
            "command": [node, "--test", "--test-name-pattern", "fixture projection survives compaction", "tests/projection_cli.integration.test.mjs"],
        },
        {
            "id": "SEC-006",
            "label": "bounded retention keeps recovery floor",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_rag_retention.RetentionTests.test_plan_and_apply_preserve_current_and_previous_lineage"],
        },
        {
            "id": "SEC-005",
            "label": "query error redaction",
            "command": [node, "--test", "--test-name-pattern", "CLI errors redact sensitive query material", "scripts/thread_search.test.mjs"],
        },
        {
            "id": "SEC-007",
            "label": "derived index removal and rebuild",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_removed_derived_index_rebuilds_without_changing_canonical_handoff"],
        },
        {
            "id": "UX-003",
            "label": "ambiguous local time disclosure",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_cli.TemporalCliTests.test_ambiguous_local_time_is_disclosed_instead_of_guessed"],
        },
        {
            "id": "OPS-004",
            "label": "digest-paired rollback rehearsal",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_rollback.TemporalRollbackTests.test_restores_verified_previous_pair_without_touching_canonical_marker", "tests.test_thread_temporal_rollback.TemporalRollbackTests.test_mismatched_previous_pair_fails_closed_without_mutation"],
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(".rnd/temporal-memory/local-certification-run.json"))
    args = parser.parse_args(argv)
    root = repo_root()
    node = shutil.which("node")
    if not node:
        raise SystemExit("node executable was not found")

    results: list[dict[str, object]] = []
    for case in cases(node):
        command = [str(part) for part in case["command"]]
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        elapsed = round((time.perf_counter() - started) * 1000)
        combined = (completed.stdout + completed.stderr).encode("utf-8", errors="replace")
        result = {
            "id": case["id"],
            "label": case["label"],
            "status": "pass" if completed.returncode == 0 else "fail",
            "returnCode": completed.returncode,
            "durationMs": elapsed,
            "outputBytes": len(combined),
            "outputDigest": digest_bytes(combined),
        }
        results.append(result)
        if completed.returncode:
            print(f"{case['id']} failed with exit code {completed.returncode}", file=sys.stderr)
            tail = (completed.stdout + completed.stderr).splitlines()[-8:]
            if tail:
                print("\n".join(tail), file=sys.stderr)

    payload = {
        "contractVersion": "temporal-local-certification-v1",
        "generatedAt": utc_now(),
        "scope": "deterministic-focused-tests-only",
        "status": "pass" if all(item["status"] == "pass" for item in results) else "fail",
        "caseCount": len(results),
        "passedCaseCount": sum(item["status"] == "pass" for item in results),
        "failedCaseCount": sum(item["status"] == "fail" for item in results),
        "cases": results,
    }
    output = (root / args.out).resolve() if not args.out.is_absolute() else args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "caseCount": payload["caseCount"], "passedCaseCount": payload["passedCaseCount"], "out": str(output)}))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
