#!/usr/bin/env python3
"""Resolve private benchmark title selectors to authoritative thread IDs and freeze corpus identity."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from thread_rag_benchmark_contract import normalize_suite, sha256_json, suite_public_summary


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def corpus_fingerprint(state: dict[str, Any]) -> str:
    rows = []
    for thread_id, thread in state.get("threads", {}).items():
        rows.append({
            "threadId": thread_id,
            "contentDigest": thread.get("contentDigest"),
            "revision": thread.get("revision"),
            "title": thread.get("title"),
        })
    return sha256_json(sorted(rows, key=lambda row: row["threadId"]))


def materialize(spec: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    by_title: dict[str, list[str]] = defaultdict(list)
    for thread_id, thread in state.get("threads", {}).items():
        by_title[str(thread.get("title", ""))].append(thread_id)
    output_cases = []
    for index, case in enumerate(spec.get("cases") or [], 1):
        resolved = dict(case)
        expectation = str(case.get("expectation", "match"))
        if expectation == "match":
            expected_title = str(case.get("expectedTitle", ""))
            expected_prefix = str(case.get("expectedTitlePrefix", ""))
            if bool(expected_title) == bool(expected_prefix):
                raise ValueError(f"Case {index} needs exactly one of expectedTitle or expectedTitlePrefix")
            matched_titles = [expected_title] if expected_title else sorted(title for title in by_title if title.startswith(expected_prefix))
            if expected_prefix and len(matched_titles) != 1:
                raise ValueError(f"Case {index} expectedTitlePrefix must resolve to exactly one title group")
            matches = sorted(by_title.get(matched_titles[0], [])) if matched_titles else []
            if not matches:
                raise ValueError(f"Case {index} title selector does not match current state")
            resolved["expectedThreadIds"] = matches
            resolved["labelProvenance"] = {
                "method": "exact-state-title-selector-v1",
                "acceptableSiblingCount": len(matches),
            }
        else:
            resolved["expectedThreadIds"] = []
            resolved["labelProvenance"] = {"method": "adjudicated-no-match-v1"}
        resolved.pop("expectedTitle", None)
        resolved.pop("expectedTitlePrefix", None)
        output_cases.append(resolved)
    suite = normalize_suite({
        **spec,
        "corpusFingerprint": corpus_fingerprint(state),
        "cases": output_cases,
    })
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    suite = materialize(read_json(args.spec.resolve()), read_json(args.state.resolve()))
    atomic_json(args.out.resolve(), suite)
    print(json.dumps(suite_public_summary(suite), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
