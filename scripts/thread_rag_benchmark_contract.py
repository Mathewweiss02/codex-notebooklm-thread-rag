#!/usr/bin/env python3
"""Shared validation, sealing, and statistics for private retrieval benchmarks."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SPLITS = {"regression", "development", "holdout"}
EXPECTATIONS = {"match", "no_match"}
STRATA = {
    "exact",
    "vague",
    "misleading-title",
    "sibling",
    "giant-split",
    "related-decoy",
    "adversarial",
    "negative",
    "temporal",
    "freshness",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_suite(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        value = {
            "schemaVersion": SCHEMA_VERSION,
            "suiteId": "legacy-private-suite",
            "split": "regression",
            "cases": value,
        }
    if not isinstance(value, dict):
        raise ValueError("Benchmark suite must be an object or a legacy case array")
    if "cases" in value and "suiteId" not in value:
        value = {
            **value,
            "schemaVersion": SCHEMA_VERSION,
            "suiteId": "legacy-private-suite",
            "split": "regression",
        }
    if value.get("schemaVersion", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported benchmark schemaVersion: {value.get('schemaVersion')}")
    suite_id = str(value.get("suiteId", "")).strip()
    split = str(value.get("split", "")).strip()
    cases = value.get("cases")
    if not suite_id:
        raise ValueError("Benchmark suite needs suiteId")
    if split not in SPLITS:
        raise ValueError(f"Benchmark split must be one of {sorted(SPLITS)}")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark suite needs a non-empty cases array")

    normalized_cases = [normalize_case(case, index) for index, case in enumerate(cases, 1)]
    require_unique((case["caseId"] for case in normalized_cases), "caseId")
    require_unique((case["name"] for case in normalized_cases), "name")
    require_unique((normalize_query(case["query"]) for case in normalized_cases), "normalized query")
    return {
        **value,
        "schemaVersion": SCHEMA_VERSION,
        "suiteId": suite_id,
        "split": split,
        "cases": normalized_cases,
    }


def normalize_case(case: Any, index: int) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError(f"Case {index} must be an object")
    name = str(case.get("name", "")).strip()
    query = str(case.get("query", "")).strip()
    case_id = str(case.get("caseId") or name).strip()
    expectation = str(case.get("expectation", "match")).strip()
    stratum = str(case.get("stratum", "vague")).strip()
    expected = case.get("expectedThreadIds", [])
    if isinstance(expected, str):
        expected = [expected]
    if not isinstance(expected, list) or any(not isinstance(item, str) or not item.strip() for item in expected):
        raise ValueError(f"Case {case_id or index} expectedThreadIds must be an array of non-empty strings")
    expected = sorted(set(item.strip() for item in expected))
    if not case_id or not name or not query:
        raise ValueError(f"Case {index} needs caseId, name, and query")
    if expectation not in EXPECTATIONS:
        raise ValueError(f"Case {case_id} expectation must be one of {sorted(EXPECTATIONS)}")
    if stratum not in STRATA:
        raise ValueError(f"Case {case_id} stratum must be one of {sorted(STRATA)}")
    if expectation == "match" and not expected:
        raise ValueError(f"Match case {case_id} needs expectedThreadIds")
    if expectation == "no_match" and expected:
        raise ValueError(f"No-match case {case_id} cannot contain expectedThreadIds")
    return {
        **case,
        "caseId": case_id,
        "name": name,
        "query": query,
        "expectation": expectation,
        "stratum": stratum,
        "expectedThreadIds": expected,
    }


def normalize_query(value: str) -> str:
    return " ".join(value.casefold().split())


def require_unique(values: Any, label: str) -> None:
    counts = Counter(values)
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates[0]}")


def suite_digests(suite: dict[str, Any]) -> dict[str, str]:
    cases = suite["cases"]
    query_surface = [
        {
            "caseId": case["caseId"],
            "name": case["name"],
            "query": case["query"],
            "stratum": case["stratum"],
        }
        for case in cases
    ]
    label_surface = [
        {
            "caseId": case["caseId"],
            "expectation": case["expectation"],
            "expectedThreadIds": case["expectedThreadIds"],
        }
        for case in cases
    ]
    return {
        "suiteSha256": sha256_json(suite),
        "querySha256": sha256_json(query_surface),
        "labelSha256": sha256_json(label_surface),
    }


def suite_public_summary(suite: dict[str, Any]) -> dict[str, Any]:
    strata = Counter(case["stratum"] for case in suite["cases"])
    expectations = Counter(case["expectation"] for case in suite["cases"])
    return {
        "schemaVersion": suite["schemaVersion"],
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        "caseCount": len(suite["cases"]),
        "strata": dict(sorted(strata.items())),
        "expectations": dict(sorted(expectations.items())),
        **suite_digests(suite),
    }


def make_seal(suite: dict[str, Any]) -> dict[str, Any]:
    return {
        **suite_public_summary(suite),
        "corpusFingerprint": suite.get("corpusFingerprint"),
        "frozenAt": suite.get("frozenAt"),
        "labelPolicy": suite.get("labelPolicy"),
    }


def verify_seal(suite: dict[str, Any], seal: dict[str, Any]) -> list[str]:
    current = make_seal(suite)
    fields = ("schemaVersion", "suiteId", "split", "caseCount", "suiteSha256", "querySha256", "labelSha256")
    return [field for field in fields if current.get(field) != seal.get(field)]


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float | int | None]:
    if total == 0:
        return {"successes": successes, "total": total, "rate": None, "lower95": None, "upper95": None}
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return {
        "successes": successes,
        "total": total,
        "rate": round(rate, 6),
        "lower95": round(max(0.0, center - margin), 6),
        "upper95": round(min(1.0, center + margin), 6),
    }


def percentile(values: list[int | float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)
