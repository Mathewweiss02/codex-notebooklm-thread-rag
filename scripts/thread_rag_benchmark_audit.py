#!/usr/bin/env python3
"""Audit and optionally seal a private retrieval benchmark without printing its contents."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from thread_rag_benchmark_contract import make_seal, normalize_suite, read_json, verify_seal


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--seal", type=Path, help="Verify an existing seal")
    parser.add_argument("--write-seal", type=Path, help="Create a new immutable seal; refuses to overwrite")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    suite = normalize_suite(read_json(args.suite.resolve()))
    report = {"status": "ok", **make_seal(suite), "sealVerified": None, "mismatchedSealFields": []}
    if args.seal:
        mismatches = verify_seal(suite, read_json(args.seal.resolve()))
        report["sealVerified"] = not mismatches
        report["mismatchedSealFields"] = mismatches
        if mismatches:
            report["status"] = "error"
    if args.write_seal:
        target = args.write_seal.resolve()
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing seal: {target}")
        atomic_json(target, make_seal(suite))
        report["sealWritten"] = str(target)
    if args.out:
        atomic_json(args.out.resolve(), report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
