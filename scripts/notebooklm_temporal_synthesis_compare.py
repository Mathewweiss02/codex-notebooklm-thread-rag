#!/usr/bin/env python3
"""Sequential NLM-002 local-vs-source-scoped CLI experiment.

The report deliberately stores no answer text.  It records local coverage,
remote latency, answer/reference hashes/counts, and whether every returned
citation stayed inside the mapper-approved source set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from notebooklm_temporal_source_map import map_sources  # noqa: E402
from notebooklm_temporal_executor import ExecutorError, ExecutorPolicy, execute_bounded  # noqa: E402
from redaction_contract import sanitize_remote_text  # noqa: E402
from notebooklm_temporal_verify import verify_remote_payload  # noqa: E402


CONTRACT = "temporal-synthesis-compare-v1"


class SynthesisExperimentError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SynthesisExperimentError("INVALID_INPUT", f"cannot read JSON fixture: {path.name}") from exc


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def run_local_context(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "thread_temporal_cli.py"),
        "context",
        "--db", str(args.db.resolve()),
        "--expression", args.expression,
        "--timezone", args.timezone,
        "--mode", "deep",
    ]
    if args.now:
        command.extend(["--now", args.now])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=args.timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SynthesisExperimentError("LOCAL_CONTEXT_TIMEOUT", "local context pack exceeded the experiment timeout") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SynthesisExperimentError("LOCAL_CONTEXT_INVALID", "local temporal CLI returned malformed JSON") from exc
    if completed.returncode != 0 or payload.get("result", {}).get("status") not in {"ok"}:
        raise SynthesisExperimentError("LOCAL_CONTEXT_INCOMPLETE", "source-scoped synthesis requires a complete local context pack")
    return payload["result"]


def parse_remote_payload(payload: Any, allowed_source_ids: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SynthesisExperimentError("REMOTE_INVALID", "NotebookLM CLI returned a non-object JSON result")
    answer = str(payload.get("answer") or payload.get("text") or "")
    references = payload.get("references") or payload.get("sources") or []
    if not isinstance(references, list):
        references = []
    referenced_ids = set()
    for reference in references:
        if not isinstance(reference, dict):
            continue
        source_id = reference.get("source_id") or reference.get("sourceId") or reference.get("id")
        if source_id:
            referenced_ids.add(str(source_id))
    return {
        "answerSha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "answerChars": len(answer),
        "referenceCount": len(references),
        "referencedSourceCount": len(referenced_ids),
        "referencedSourceIdsInScope": len(referenced_ids & allowed_source_ids),
        "referencedSourceIdsOutOfScope": len(referenced_ids - allowed_source_ids),
        "citationScopeValid": referenced_ids.issubset(allowed_source_ids),
        "answerContainsCitationMarker": bool(re.search(r"\[\d+\]|【\d+】", answer)),
        "isFollowUp": bool(payload.get("is_follow_up") or payload.get("isFollowUp")),
    }


def attach_local_source_files(config: dict[str, Any], source_ids: list[str]) -> dict[str, str]:
    """Attach local-only projection paths for in-memory citation verification."""

    projection_root = str(config.get("ProjectionRoot") or "").strip()
    if not projection_root:
        return {}
    try:
        state = json.loads((Path(projection_root) / "state.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    wanted = set(source_ids)
    result: dict[str, str] = {}
    for thread in (state.get("threads") or {}).values():
        if not isinstance(thread, dict):
            continue
        for part in thread.get("parts") or []:
            if not isinstance(part, dict):
                continue
            source_id = str(part.get("sourceId") or "")
            local_file = str(part.get("file") or "")
            if source_id in wanted and local_file:
                result[source_id] = local_file
    return result


def ask_source_scoped(
    args: argparse.Namespace,
    config: dict[str, Any],
    source_ids: list[str],
    prompt: str,
    context: dict[str, Any],
    source_mapping: dict[str, Any],
) -> dict[str, Any]:
    notebooklm = str(args.notebooklm or config.get("NotebookLmCli") or "notebooklm")
    command = [
        notebooklm,
        "--quiet",
        "--profile", str(config.get("Profile") or ""),
        "ask",
        "--notebook", str(config.get("NotebookId") or ""),
        "--new", "--yes", "--json",
    ]
    for source_id in source_ids:
        command.extend(["--source", source_id])
    command.extend(["--prompt-file", "-"])
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=args.timeout, check=False)
    except FileNotFoundError as exc:
        raise SynthesisExperimentError("REMOTE_CLI_UNAVAILABLE", "configured NotebookLM CLI is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        return {"status": "error", "code": "REMOTE_TIMEOUT", "latencyMs": round((time.perf_counter() - started) * 1000, 3)}
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    if completed.returncode != 0:
        return {"status": "error", "code": "REMOTE_ASK_FAILED", "latencyMs": elapsed}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "code": "REMOTE_INVALID", "latencyMs": elapsed}
    summary = parse_remote_payload(payload, set(source_ids))
    verification = verify_remote_payload(payload, context, source_mapping)
    return {
        "status": "ok",
        "latencyMs": elapsed,
        **summary,
        "verification": {
            "status": verification["status"],
            "decision": verification["decision"],
            "codes": verification["codes"],
            "supportedReferenceCount": verification["citations"]["supportedReferenceCount"],
            "unsupportedReferenceCount": verification["citations"]["unsupportedReferenceCount"],
            "localSourceFileCount": verification["sourceScope"]["localSourceFileCount"],
            "localSourceFileDriftCount": verification["sourceScope"]["localSourceFileDriftCount"],
            "temporalLiteralStatus": verification["temporalLiterals"]["status"],
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--case-file", required=True, type=Path)
    parser.add_argument("--expression", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--now")
    parser.add_argument("--notebooklm")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--confirm-disposable-retrieval-notebook", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_disposable_retrieval_notebook:
        parser.error("--confirm-disposable-retrieval-notebook is required")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args(argv or sys.argv[1:])
    try:
        local = run_local_context(args)
        thread_ids = list(local.get("selection", {}).get("threadIds") or [])
        if not thread_ids:
            raise SynthesisExperimentError("THREAD_SCOPE_REQUIRED", "local context selected no threads")
        mapping = map_sources(args.config.resolve(), [str(value) for value in thread_ids], live=True, notebooklm=args.notebooklm, timeout=args.timeout)
        if mapping["status"] != "ok":
            raise SynthesisExperimentError("SOURCE_MAPPING_DEGRADED", "current source mapping is not complete")
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        source_ids = [str(item["sourceId"]) for item in mapping["mapping"]]
        if not source_ids:
            raise SynthesisExperimentError("SOURCE_SCOPE_EMPTY", "source mapping returned no current parts")
        mapping["localSourceFiles"] = attach_local_source_files(config, source_ids)
        case_data = read_json(args.case_file.resolve())
        cases = case_data.get("cases") if isinstance(case_data, dict) else None
        if not isinstance(cases, list) or not cases:
            raise SynthesisExperimentError("INVALID_CASES", "case fixture must contain a non-empty cases array")
        report: dict[str, Any] = {
            "contractVersion": CONTRACT,
            "experiment": "NLM-002",
            "startedAt": time.time(),
            "expression": args.expression,
            "timezone": args.timezone,
            "local": {
                "status": local["status"],
                "resolvedRange": local["resolvedRange"],
                "canonicalEventCount": local["coverage"]["canonicalEventCount"],
                "includedEventCount": local["coverage"]["includedEventCount"],
                "omittedEventCount": local["coverage"]["omittedEventCount"],
                "segmentCount": local["coverage"]["segmentCount"],
                "localDayCount": local["coverage"]["localDayCount"],
                "latencyMs": local["latency"]["totalMs"],
            },
            "sourceMapping": {
                "requestedThreadCount": mapping["coverage"]["requestedThreadCount"],
                "mappedThreadCount": mapping["coverage"]["mappedThreadCount"],
                "mappedPartCount": mapping["coverage"]["mappedPartCount"],
                "liveVerification": mapping["liveVerification"],
            },
            "remotePolicy": {
                "mode": "sequential",
                "conversation": "disposable retrieval only",
                "sourceScope": "mapped current parts only",
                "executor": {"concurrency": 1, "maxRetries": 0, "isolation": "single disposable retrieval notebook"},
            },
            "cases": [],
        }
        prepared_cases: list[dict[str, Any]] = []
        for case in cases:
            safe_prompt, redaction_counts = sanitize_remote_text(str(case.get("prompt") or ""))
            if not safe_prompt.strip():
                raise SynthesisExperimentError("INVALID_CASES", "a case prompt is empty after redaction")
            prepared_cases.append({
                "case": case,
                "prompt": safe_prompt,
                "redactions": sum(redaction_counts.values()),
            })

        def run_case(item: dict[str, Any]) -> dict[str, Any]:
            return ask_source_scoped(args, config, source_ids, item["prompt"], local, mapping)

        def checkpoint(index: int, remote: dict[str, Any]) -> None:
            item = prepared_cases[index]
            case = item["case"]
            report["cases"].append({
                "caseId": case.get("caseId"),
                "queryRedactions": item["redactions"],
                "remote": remote,
            })
            atomic_json(args.out.resolve(), report)

        execute_bounded(
            prepared_cases,
            run_case,
            policy=ExecutorPolicy(mode="sequential", concurrency=1, max_retries=0),
            on_result=checkpoint,
        )
        print(json.dumps({"status": "ok", "experiment": "NLM-002", "caseCount": len(cases), "out": str(args.out.resolve())}))
        return 0
    except (SynthesisExperimentError, ExecutorError) as exc:
        payload = {"status": "error", "code": exc.code, "message": str(exc)}
        print(json.dumps(payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
