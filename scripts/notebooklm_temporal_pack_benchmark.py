#!/usr/bin/env python3
"""Plan and score the structural side of temporal NotebookLM prompt packing.

This lane is deliberately offline. It freezes question identity, batching,
heading parsing, marker-first citation section mapping, and source-scope
checks before any new live calls are authorized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from redaction_contract import sanitize_remote_text  # noqa: E402


CONTRACT = "temporal-prompt-pack-v1"
HEADING_RE = re.compile(r"(?im)^[ \t]*#{1,6}[ \t]*Q(\d+)\b[^\r\n]*$")
CITATION_RE = re.compile(r"(?:\[(\d+)\]|【(\d+)】)")


# Keep the ASCII source line above for backward-compatible parsing of older
# fixtures, then override it with the correctly encoded Unicode citation form.
CITATION_RE = re.compile(r"(?:\[(\d+)\]|\u3010(\d+)\u3011)")


class PromptPackError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptPackError("INVALID_INPUT", f"cannot read JSON: {path.name}") from exc


def batches(cases: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    if size < 1:
        raise PromptPackError("INVALID_PACK_SIZE", "pack size must be positive")
    for offset in range(0, len(cases), size):
        yield cases[offset : offset + size]


def build_packed_prompt(cases: list[dict[str, Any]], expression: str, timezone_name: str) -> tuple[str, int]:
    lines = [
        "Treat every numbered question below as an independent retrieval task.",
        "The selected temporal scope is authoritative: " + expression + " in " + timezone_name + ".",
        "Return exactly one section per question headed ## Q1, ## Q2, and so on.",
        "Keep each answer inside its own section and put only that section's citations inside it.",
        "Use NO EVIDENCE when the selected sources do not support the question. Do not guess.",
        "Use exact timestamps only when the selected sources provide them.",
        "",
    ]
    redactions = 0
    for number, case in enumerate(cases, start=1):
        safe_query, counts = sanitize_remote_text(str(case.get("query") or ""))
        if not safe_query.strip():
            raise PromptPackError("INVALID_CASE", "question is empty after redaction")
        redactions += sum(counts.values())
        lines.extend((f"Q{number}: {safe_query}", ""))
    return "\n".join(lines).strip(), redactions


def answer_sections(answer: str, count: int) -> dict[int, tuple[int, int]]:
    markers: list[tuple[int, int]] = []
    seen: set[int] = set()
    for match in HEADING_RE.finditer(answer):
        number = int(match.group(1))
        if 1 <= number <= count and number not in seen:
            markers.append((number, match.start()))
            seen.add(number)
    markers.sort(key=lambda item: item[1])
    return {
        number: (start, markers[index + 1][1] if index + 1 < len(markers) else len(answer))
        for index, (number, start) in enumerate(markers)
    }


def heading_diagnostics(answer: str, count: int) -> dict[str, int]:
    numbers = [int(match.group(1)) for match in HEADING_RE.finditer(answer)]
    valid = [number for number in numbers if 1 <= number <= count]
    return {
        "headingCount": len(numbers),
        "duplicateHeadingCount": len(valid) - len(set(valid)),
        "outOfRangeHeadingCount": sum(1 for number in numbers if number < 1 or number > count),
    }


def citation_position(answer: str, citation_number: int | None, answer_start: Any) -> int:
    if citation_number is not None:
        positions = [match.start() for match in CITATION_RE.finditer(answer) if int(match.group(1) or match.group(2)) == citation_number]
        if positions:
            try:
                offset = int(answer_start) if answer_start is not None else None
            except (TypeError, ValueError):
                offset = None
            if offset is not None and len(positions) > 1:
                return min(positions, key=lambda position: abs(position - offset))
            return min(positions)
    try:
        return int(answer_start) if answer_start is not None else -1
    except (TypeError, ValueError):
        return -1


def map_references_to_sections(answer: str, references: list[dict[str, Any]], section_count: int) -> tuple[dict[int, list[dict[str, Any]]], int]:
    spans = answer_sections(answer, section_count)
    mapped: dict[int, list[dict[str, Any]]] = {number: [] for number in range(1, section_count + 1)}
    unmapped = 0
    for index, reference in enumerate(references, start=1):
        if not isinstance(reference, dict):
            unmapped += 1
            continue
        citation_value = reference.get("citation_number")
        if citation_value is None:
            citation_value = reference.get("citationNumber")
        try:
            citation_number = int(citation_value) if citation_value is not None else None
        except (TypeError, ValueError):
            citation_number = None
        answer_start = reference.get("answer_start_char")
        if answer_start is None:
            answer_start = reference.get("answerStartChar")
        position = citation_position(answer, citation_number, answer_start)
        section = next((number for number, (start, end) in spans.items() if start <= position < end), None) if position >= 0 else None
        if section is None:
            unmapped += 1
        else:
            mapped[section].append({**reference, "_inputIndex": index})
    return mapped, unmapped


def score_structural_response(answer: str, references: list[dict[str, Any]], case_count: int, allowed_source_ids: set[str]) -> dict[str, Any]:
    sections = answer_sections(answer, case_count)
    heading_stats = heading_diagnostics(answer, case_count)
    mapped, unmapped = map_references_to_sections(answer, references, case_count)
    out_of_scope = 0
    for reference in references:
        if not isinstance(reference, dict):
            out_of_scope += 1
            continue
        source_id = str(reference.get("source_id") or reference.get("sourceId") or reference.get("id") or "")
        if source_id not in allowed_source_ids:
            out_of_scope += 1
    return {
        "contractVersion": CONTRACT,
        "status": "ok" if (
            len(sections) == case_count
            and not unmapped
            and not out_of_scope
            and heading_stats["duplicateHeadingCount"] == 0
            and heading_stats["outOfRangeHeadingCount"] == 0
        ) else "degraded",
        "caseCount": case_count,
        "headingCount": len(sections),
        "rawHeadingCount": heading_stats["headingCount"],
        "duplicateHeadingCount": heading_stats["duplicateHeadingCount"],
        "outOfRangeHeadingCount": heading_stats["outOfRangeHeadingCount"],
        "missingHeadingCount": case_count - len(sections),
        "referenceCount": len(references),
        "mappedReferenceCount": sum(len(value) for value in mapped.values()),
        "unmappedReferenceCount": unmapped,
        "outOfScopeReferenceCount": out_of_scope,
        "perSectionReferenceCounts": {str(number): len(mapped[number]) for number in range(1, case_count + 1)},
    }


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--expression", default="development temporal scope")
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--pack-sizes", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        fixture = read_json(args.cases.resolve())
        cases = fixture.get("cases") if isinstance(fixture, dict) else None
        if not isinstance(cases, list) or not cases:
            raise PromptPackError("INVALID_CASES", "cases must be a non-empty array")
        if any(not isinstance(case, dict) for case in cases):
            raise PromptPackError("INVALID_CASES", "case entries must be objects")
        prompt_records: list[dict[str, Any]] = []
        for size in sorted(set(args.pack_sizes)):
            if size < 1 or size > 8:
                raise PromptPackError("INVALID_PACK_SIZE", "development pack sizes must be between 1 and 8")
            for batch_number, batch in enumerate(batches(cases, size), start=1):
                prompt, redactions = build_packed_prompt(batch, args.expression, args.timezone)
                prompt_records.append({
                    "packSize": size,
                    "batchNumber": batch_number,
                    "questionCount": len(batch),
                    "redactionCount": redactions,
                    "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                })
        suite_digest = hashlib.sha256(json.dumps(fixture, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        prompt_plan_digest = hashlib.sha256(json.dumps(prompt_records, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        payload = {
            "contractVersion": CONTRACT,
            "suiteId": fixture.get("suiteId"),
            "suiteDigest": suite_digest,
            "caseCount": len(cases),
            "packSizes": sorted(set(args.pack_sizes)),
            "promptCount": len(prompt_records),
            "promptPlanSha256": prompt_plan_digest,
            "prompts": prompt_records,
        }
        atomic_json(args.out.resolve(), payload)
        print(json.dumps({"status": "ok", "contractVersion": CONTRACT, "caseCount": len(cases), "promptCount": len(prompt_records), "suiteDigest": suite_digest, "out": str(args.out.resolve())}))
        return 0
    except PromptPackError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
