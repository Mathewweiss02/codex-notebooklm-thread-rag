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
        {"id": "IDX-006", "label": "resumed old thread", "command": [node, "--test", "--test-name-pattern", "resumed old thread", extract]},
        {"id": "IDX-007", "label": "forked thread identity", "command": [node, "--test", "--test-name-pattern", "forked thread identity", extract]},
        {"id": "IDX-008", "label": "subagent policy", "command": [node, "--test", "--test-name-pattern", "excludes subagent sources", extract]},
        {"id": "IDX-009", "label": "compaction exclusion", "command": [node, "--test", "--test-name-pattern", "excludes compaction summaries", extract]},
        {"id": "IDX-012", "label": "same text at different time", "command": [node, "--test", "--test-name-pattern", "same text at different timestamps", extract]},
        {"id": "IDX-015", "label": "malformed JSONL", "command": [node, "--test", "--test-name-pattern", "malformed and partial lines", extract]},
        {"id": "IDX-016", "label": "partial final line", "command": [node, "--test", "--test-name-pattern", "malformed and partial lines", extract]},
        {"id": "IDX-018", "label": "Unicode and bidi", "command": [node, "--test", "--test-name-pattern", "malformed and partial lines", extract]},
        {"id": "IDX-019", "label": "transient Windows file lock retry", "command": [node, "--test", "--test-name-pattern", "transient Windows file lock", extract]},
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
            "id": "IDX-025",
            "label": "redaction policy change requires rebuild",
            "command": [sys.executable, "-m", "unittest", "tests.test_thread_temporal_index.TemporalIndexTests.test_redaction_policy_change_fails_closed_until_rebuild"],
        },
        {
            "id": "NLM-005",
            "label": "stale projection blocks remote use",
            "command": [sys.executable, "-m", "unittest", "tests.test_notebooklm_temporal_source_map.NotebookLMTemporalSourceMapTests.test_projection_digest_drift_degrades_before_remote_use"],
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
