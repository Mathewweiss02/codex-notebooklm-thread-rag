#!/usr/bin/env python3
"""Archive sealed private benchmark evidence outside operational run-log retention."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from thread_rag_benchmark_contract import make_seal, normalize_suite, read_json, suite_digests


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def copy_immutable(source: Path, target: Path) -> str:
    source_digest = sha256_file(source)
    if target.exists():
        if sha256_file(target) != source_digest:
            raise FileExistsError(f"Refusing to replace different archived evidence: {target}")
        return source_digest
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    if sha256_file(temporary) != source_digest:
        temporary.unlink(missing_ok=True)
        raise IOError(f"Archived copy verification failed: {source}")
    os.replace(temporary, target)
    return source_digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--report", action="append", type=Path, default=[])
    parser.add_argument("--allow-unbound-report", action="store_true", help="Permit legacy reports that predate suiteSha256 binding")
    args = parser.parse_args()

    source_suite = args.suite.resolve()
    suite = normalize_suite(read_json(source_suite))
    digests = suite_digests(suite)
    destination = args.evidence_root.resolve() / suite["suiteId"] / digests["suiteSha256"]
    destination.mkdir(parents=True, exist_ok=True)
    seal_path = destination / "seal.json"
    seal = make_seal(suite)
    if seal_path.exists() and read_json(seal_path) != seal:
        raise ValueError(f"Archived seal differs from current suite: {seal_path}")
    if not seal_path.exists():
        atomic_json(seal_path, seal)

    archived = [{"name": "suite.private.json", "sha256": copy_immutable(source_suite, destination / "suite.private.json"), "suiteBound": True}]
    for report_path in args.report:
        report_source = report_path.resolve()
        report = read_json(report_source)
        report_digest = report.get("suiteSha256")
        if report_digest is None and not args.allow_unbound_report:
            raise ValueError(f"Report is not cryptographically bound to a suite: {report_source}")
        if report_digest is not None and report_digest != digests["suiteSha256"]:
            raise ValueError(f"Report suiteSha256 does not match suite: {report_source}")
        archived.append({
            "name": report_source.name,
            "sha256": copy_immutable(report_source, destination / report_source.name),
            "suiteBound": report_digest == digests["suiteSha256"],
        })
    manifest = {
        "suiteId": suite["suiteId"],
        **digests,
        "seal": "seal.json",
        "files": archived,
    }
    atomic_json(destination / "manifest.json", manifest)
    print(json.dumps({"destination": str(destination), "suiteId": suite["suiteId"], "files": len(archived), **digests}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
