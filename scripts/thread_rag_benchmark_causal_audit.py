#!/usr/bin/env python3
"""Audit causal evidence before a retrieval benchmark is promoted.

An aggregate score can tell us that a run passed.  It cannot, by itself, tell
us why a case passed or failed, or whether a claimed improvement is real.  This
small audit keeps those claims tied to a case-level score report and requires
an independent replay/counterfactual check for every miss and every claimed
improvement.

The packet is deliberately a separate artifact from the scorer.  The scorer
measures outcomes; a human or experiment runner supplies the causal hypothesis
and the independent check.  This prevents the score itself from becoming its
own explanation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


CONTRACT = "thread-rag-causal-evidence-v1"
CHECK_TYPES = {"replay", "counterfactual"}
OUTCOMES = {"pass", "miss", "false-positive", "abstain", "no-match", "error"}
CAUSES = {
    "no-failure",
    "true-no-match",
    "transport-rate-limit",
    "source-scope",
    "semantic-candidate-omission",
    "raw-citation-order",
    "local-reranker",
    "abstention",
    "false-positive",
}


class CausalAuditError(ValueError):
    """Raised for a malformed or self-justifying causal packet."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CausalAuditError(f"cannot read JSON: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_root(path: Path) -> Path:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / ".git").exists():
            return parent
    return resolved.parent


def safe_reference(root: Path, reference: Any) -> Path:
    if not isinstance(reference, str) or not reference.strip():
        raise CausalAuditError("evidence reference must be a non-empty relative path")
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CausalAuditError(f"evidence reference escapes the repository: {reference}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise CausalAuditError(f"evidence reference escapes the repository: {reference}") from exc
    if not resolved.is_file():
        raise CausalAuditError(f"evidence file does not exist: {reference}")
    return resolved


def verify_file_ref(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, dict):
        raise CausalAuditError(f"{label} must contain path and sha256")
    path = safe_reference(root, value.get("path"))
    expected = str(value.get("sha256", "")).lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise CausalAuditError(f"{label} has an invalid sha256")
    actual = sha256_file(path)
    if actual != expected:
        raise CausalAuditError(f"{label} sha256 does not match retained evidence")
    return path


def expected_case(case: dict[str, Any]) -> tuple[str, set[str]]:
    expectation = case.get("expectation")
    passed = bool(case.get("passed"))
    abstained = bool(case.get("abstained"))
    candidate_hit = case.get("candidateHit")
    top1_hit = case.get("top1Hit")

    if expectation == "match":
        if passed:
            return "pass", {"no-failure"}
        if abstained:
            return "abstain", {"abstention", "transport-rate-limit"}
        if candidate_hit is False:
            return "miss", {"semantic-candidate-omission", "source-scope", "transport-rate-limit"}
        if candidate_hit is True and top1_hit is False:
            return "miss", {"raw-citation-order", "local-reranker"}
        return "error", {"transport-rate-limit", "source-scope"}

    if expectation == "no_match":
        if passed:
            return "no-match", {"true-no-match"}
        return "false-positive", {"false-positive", "source-scope", "local-reranker", "raw-citation-order"}

    raise CausalAuditError(f"unsupported benchmark expectation: {expectation}")


def audit_packet(packet_path: Path) -> dict[str, Any]:
    root = repository_root(packet_path)
    packet = read_json(packet_path)
    errors: list[str] = []

    if not isinstance(packet, dict):
        raise CausalAuditError("causal packet must be a JSON object")
    if packet.get("contractVersion") != CONTRACT:
        raise CausalAuditError("causal packet contract is unsupported")

    benchmark = packet.get("benchmark")
    if not isinstance(benchmark, dict):
        raise CausalAuditError("causal packet needs a benchmark object")
    score_path = safe_reference(root, benchmark.get("scoreReport"))
    expected_score_digest = str(benchmark.get("scoreReportSha256", "")).lower()
    if sha256_file(score_path) != expected_score_digest:
        raise CausalAuditError("benchmark score report digest does not match retained evidence")
    score = read_json(score_path)
    if not isinstance(score, dict):
        raise CausalAuditError("benchmark score report must be a JSON object")
    if score.get("split") == "holdout" or score.get("caseDetailsSuppressed"):
        raise CausalAuditError("public causal packets cannot disclose sealed holdout case details")
    details = score.get("details")
    if not isinstance(details, list) or not details:
        raise CausalAuditError("benchmark score report needs unsuppressed case details")
    detail_by_id: dict[str, dict[str, Any]] = {}
    for detail in details:
        if not isinstance(detail, dict) or not isinstance(detail.get("caseId"), str):
            raise CausalAuditError("every score detail needs a caseId")
        case_id = detail["caseId"]
        if case_id in detail_by_id:
            raise CausalAuditError(f"duplicate score detail: {case_id}")
        detail_by_id[case_id] = detail

    checks = packet.get("independentChecks", [])
    if not isinstance(checks, list):
        raise CausalAuditError("independentChecks must be an array")
    checks_by_id: dict[str, dict[str, Any]] = {}
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("checkId"), str):
            raise CausalAuditError("every independent check needs a checkId")
        check_id = check["checkId"]
        if check_id in checks_by_id:
            raise CausalAuditError(f"duplicate independent check: {check_id}")
        if check.get("type") not in CHECK_TYPES:
            raise CausalAuditError(f"independent check {check_id} has an unsupported type")
        if not isinstance(check.get("prediction"), str) or not check["prediction"].strip():
            raise CausalAuditError(f"independent check {check_id} needs a prediction")
        if not isinstance(check.get("observed"), str) or not check["observed"].strip():
            raise CausalAuditError(f"independent check {check_id} needs an observation")
        if check.get("matches") is not True:
            raise CausalAuditError(f"independent check {check_id} does not confirm its prediction")
        refs = check.get("evidenceRefs")
        if not isinstance(refs, list) or not refs:
            raise CausalAuditError(f"independent check {check_id} needs retained evidence")
        for index, ref in enumerate(refs, 1):
            referenced = verify_file_ref(root, ref, f"independent check {check_id} evidence {index}")
            if referenced == score_path:
                raise CausalAuditError(f"independent check {check_id} cannot cite only its score report")
        checks_by_id[check_id] = check

    packet_cases = packet.get("cases")
    if not isinstance(packet_cases, list) or not packet_cases:
        raise CausalAuditError("causal packet needs a non-empty cases array")
    packet_by_id: dict[str, dict[str, Any]] = {}
    for item in packet_cases:
        if not isinstance(item, dict) or not isinstance(item.get("caseId"), str):
            raise CausalAuditError("every causal case needs a caseId")
        case_id = item["caseId"]
        if case_id in packet_by_id:
            raise CausalAuditError(f"duplicate causal case: {case_id}")
        packet_by_id[case_id] = item

    if set(packet_by_id) != set(detail_by_id):
        raise CausalAuditError("causal cases must cover exactly the score report cases")

    failure_count = 0
    for case_id, detail in detail_by_id.items():
        item = packet_by_id[case_id]
        outcome, allowed_causes = expected_case(detail)
        if item.get("outcome") != outcome:
            errors.append(f"case {case_id} outcome disagrees with score report")
        cause = item.get("causeClass")
        if cause not in CAUSES:
            errors.append(f"case {case_id} has an unsupported cause class")
        elif cause not in allowed_causes:
            errors.append(f"case {case_id} cause class contradicts observed outcome")
        if not isinstance(item.get("claim"), str) or not item["claim"].strip():
            errors.append(f"case {case_id} needs a causal claim")
        if not isinstance(item.get("prediction"), str) or not item["prediction"].strip():
            errors.append(f"case {case_id} needs a testable prediction")
        check_ids = item.get("independentCheckIds", [])
        if not isinstance(check_ids, list) or any(check_id not in checks_by_id for check_id in check_ids):
            errors.append(f"case {case_id} references an unknown independent check")
        if outcome not in {"pass", "no-match"}:
            failure_count += 1
            if not check_ids:
                errors.append(f"case {case_id} needs an independent check for its failure explanation")

    improvements = packet.get("claimedImprovements", [])
    if not isinstance(improvements, list):
        raise CausalAuditError("claimedImprovements must be an array")
    for index, improvement in enumerate(improvements, 1):
        if not isinstance(improvement, dict):
            errors.append(f"claimed improvement {index} is not an object")
            continue
        case_id = improvement.get("caseId")
        if case_id not in packet_by_id:
            errors.append(f"claimed improvement {index} references an unknown case")
        if not isinstance(improvement.get("prediction"), str) or not improvement["prediction"].strip():
            errors.append(f"claimed improvement {index} needs a prediction")
        if not isinstance(improvement.get("observedChange"), str) or not improvement["observedChange"].strip():
            errors.append(f"claimed improvement {index} needs an observed change")
        before = improvement.get("beforeReport")
        after = improvement.get("afterReport")
        try:
            before_path = verify_file_ref(root, before, f"claimed improvement {index} before report")
            after_path = verify_file_ref(root, after, f"claimed improvement {index} after report")
            if before_path == after_path:
                errors.append(f"claimed improvement {index} before and after reports must differ")
        except CausalAuditError as exc:
            errors.append(str(exc))
        check_ids = improvement.get("independentCheckIds", [])
        if not isinstance(check_ids, list) or not check_ids or any(check_id not in checks_by_id for check_id in check_ids):
            errors.append(f"claimed improvement {index} needs known independent checks")

    if failure_count and not checks_by_id:
        errors.append("a packet with misses needs at least one independent replay or counterfactual")
    return {
        "contractVersion": CONTRACT,
        "status": "pass" if not errors else "invalid",
        "scoreReport": benchmark["scoreReport"],
        "scoreReportSha256": expected_score_digest,
        "caseCount": len(detail_by_id),
        "failureCaseCount": failure_count,
        "independentCheckCount": len(checks_by_id),
        "claimedImprovementCount": len(improvements),
        "errors": errors,
    }


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_packet(args.packet.resolve())
    except CausalAuditError as exc:
        report = {"contractVersion": CONTRACT, "status": "invalid", "errors": [str(exc)]}
    if args.out:
        atomic_json(args.out.resolve(), report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
