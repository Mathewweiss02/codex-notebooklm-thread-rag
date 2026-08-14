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
    powershell = shutil.which("powershell") or "powershell"
    return [
        {
            "id": "TIME-001",
            "label": "today local midnight to capture",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_001_today_is_local_midnight_to_capture"],
        },
        {
            "id": "TIME-002",
            "label": "yesterday calendar day",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_002_yesterday_is_a_calendar_day"],
        },
        {
            "id": "TIME-003",
            "label": "past 24 hours rolling window",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_003_past_24_hours_is_rolling"],
        },
        {
            "id": "TIME-004",
            "label": "past 7 days rolling window",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_004_past_7_days_is_explicitly_rolling"],
        },
        {
            "id": "TIME-005",
            "label": "last configured calendar week",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_005_last_week_uses_monday_calendar_boundary"],
        },
        {
            "id": "TIME-006",
            "label": "week to date capture bound",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_006_week_to_date_stops_at_capture"],
        },
        {
            "id": "TIME-007",
            "label": "explicit local date",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_007_explicit_date_is_one_local_day"],
        },
        {
            "id": "TIME-008",
            "label": "explicit half-open timestamp range",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_008_explicit_timestamp_range_is_half_open"],
        },
        {
            "id": "TIME-009",
            "label": "adjacent midnight ranges do not overlap",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_009_adjacent_midnight_ranges_do_not_overlap"],
        },
        {
            "id": "TIME-010",
            "label": "end-of-day millisecond",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_010_end_of_day_millisecond_is_retained"],
        },
        {
            "id": "TIME-011",
            "label": "DST spring gap",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_011_spring_gap_is_rejected"],
        },
        {
            "id": "TIME-012",
            "label": "DST fall overlap",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_012_fall_overlap_requires_offset"],
        },
        {
            "id": "TIME-013",
            "label": "leap day",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_013_leap_day_is_a_valid_local_day"],
        },
        {
            "id": "TIME-014",
            "label": "month and year boundary",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_014_month_year_boundary_advances_to_next_year"],
        },
        {
            "id": "TIME-015",
            "label": "timezone override",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_015_timezone_override_changes_grouping_not_instant_contract"],
        },
        {
            "id": "TIME-016",
            "label": "invalid natural phrase",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_016_invalid_natural_phrase_fails_closed"],
        },
        {
            "id": "TIME-017",
            "label": "safe default period",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_017_missing_period_has_a_safe_find_default"],
        },
        {
            "id": "TIME-018",
            "label": "future period disclosure",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalRangeCertificationTests.test_time_018_future_period_is_explicitly_empty_unless_time_advances"],
        },
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
            "id": "CTX-020",
            "label": "current thread inclusion is explicit",
            "command": [node, "--test", "--test-name-pattern", "current thread inclusion is excluded by default and explicit when requested", "scripts/thread_search.test.mjs"],
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
            "id": "NLM-003",
            "label": "split thread source parts are all current",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_split_thread_parts_are_all_current_and_unique"],
        },
        {
            "id": "NLM-015",
            "label": "disposable retrieval reset policy",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_disposable_reset_requires_retrieval_role_and_is_explicit"],
        },
        {
            "id": "NLM-016",
            "label": "exact period routes to local authority",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_skill_routing.TemporalSkillRoutingTests.test_exact_period_question_stays_local_without_remote_latency"],
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
            "id": "PAR-006",
            "label": "reordered or duplicate headings do not create false sections",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_pack_benchmark.TemporalPromptPackTests.test_heading_parser_rejects_duplicate_or_out_of_range_questions"],
        },
        {
            "id": "PAR-008",
            "label": "shared conversation concurrency is rejected",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_unsafe_shared_conversation_concurrency_is_rejected"],
        },
        {
            "id": "PAR-017",
            "label": "one child failure is explicit and non-partial",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_failure_does_not_return_a_partial_success"],
        },
        {
            "id": "PAR-018",
            "label": "global cancellation stops before the next request",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_executor.TemporalExecutorTests.test_global_cancellation_stops_before_the_next_request"],
        },
        {
            "id": "PAR-020",
            "label": "cross-question citations do not count as expected hits",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_batch_benchmark.BatchBenchmarkTests.test_cross_question_citations_do_not_count_as_expected_hits"],
        },
        {
            "id": "PAR-021",
            "label": "duplicate notebook identity is rejected before query",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_isolated_ramp.IsolatedRampTests.test_query_waves_reject_duplicate_notebook_identity_before_remote_use"],
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
            "id": "SEC-001",
            "label": "shared Python and projection redaction contract",
            "command": [sys.executable, "-m", "unittest", "tests.test_redaction_contract.RedactionContractTests.test_python_and_projection_sanitizers_share_the_same_secret_contract"],
        },
        {
            "id": "SEC-003",
            "label": "profile database ACL",
            "command": [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/profile_acl.integration.ps1", "-ProfileScript", "scripts/notebooklm_profiles.ps1"],
        },
        {
            "id": "SEC-004",
            "label": "runner report secret exclusion",
            "command": [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/runner.integration.ps1", "-Runner", "scripts/notebooklm_thread_sync_runner.ps1"],
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
            "id": "UX-001",
            "label": "fresh installation contains the current skill surface",
            "command": [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/install_skill.integration.ps1", "-RepositoryRoot", str(repo_root())],
        },
        {
            "id": "UX-002",
            "label": "nontechnical yesterday phrasing routes locally",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_skill_routing.TemporalSkillRoutingTests.test_exact_period_question_stays_local_without_remote_latency"],
        },
        {
            "id": "UX-004",
            "label": "empty period is honest and machine-readable",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalContextCertificationTests.test_ux_004_empty_period_is_honest_and_machine_readable"],
        },
        {
            "id": "UX-005",
            "label": "degraded remote uses local fallback",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_thread_search.SearchTests.test_remote_outage_uses_real_local_fallback"],
        },
        {
            "id": "UX-006",
            "label": "diagnostics expose mode range coverage retry and verification",
            "command": [sys.executable, "-m", "unittest", "tests.test_temporal_certification_cases.TemporalContextCertificationTests.test_ux_006_diagnostics_expose_mode_range_coverage_and_verification", "tests.test_notebooklm_thread_search.SearchTests.test_search_diagnostics_expose_attempt_retry_and_verification_state"],
        },
        {
            "id": "OPS-001",
            "label": "console-free scheduler launcher and overlap behavior",
            "command": [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/task_scheduler.integration.ps1", "-RepositoryRoot", str(repo_root()), "-PythonPath", sys.executable],
        },
        {
            "id": "OPS-002",
            "label": "doctor detects stale runner and auth JSON error",
            "command": [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/doctor.integration.ps1", "-Doctor", "scripts/thread_rag_doctor.ps1"],
        },
        {
            "id": "OPS-003",
            "label": "derived index rebuild restores state",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_corruption_fails_closed_until_explicit_rebuild"],
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
    parser.add_argument("--replace", action="store_true", help="allow overwriting an existing retained result file")
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
    if output.exists() and not args.replace:
        raise SystemExit(f"refusing to overwrite retained evidence: {output}; choose a new --out path or pass --replace")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "caseCount": payload["caseCount"], "passedCaseCount": payload["passedCaseCount"], "out": str(output)}))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
