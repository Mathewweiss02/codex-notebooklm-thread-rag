#!/usr/bin/env python3
"""Run the locked dependency audit and retain aggregate evidence only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


CONTRACT = "dependency-audit-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(uv: str, repository: Path) -> dict[str, object]:
    lockfile = repository / "uv.lock"
    if not lockfile.is_file():
        raise RuntimeError("LOCKFILE_MISSING")
    with tempfile.TemporaryDirectory(prefix="codex-notebooklm-audit-") as temporary:
        requirements = Path(temporary) / "requirements.txt"
        export = subprocess.run(
            [uv, "--quiet", "export", "--locked", "--no-default-groups", "--no-emit-project", "--format", "requirements.txt", "--output-file", str(requirements)],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if export.returncode != 0:
            return {"status": "error", "code": "LOCK_EXPORT_FAILED", "exportReturnCode": export.returncode}
        audit = subprocess.run(
            [uv, "run", "--group", "audit", "pip-audit", "--strict", "--require-hashes", "--disable-pip", "-r", str(requirements)],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "contractVersion": CONTRACT,
            "status": "pass" if audit.returncode == 0 else "fail",
            "executedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "lockFile": "uv.lock",
            "lockSha256": sha256_file(lockfile),
            "auditTool": "pip-audit==2.10.1",
            "requirementsHashCount": sum(1 for line in requirements.read_text(encoding="utf-8").splitlines() if "--hash=" in line),
            "auditReturnCode": audit.returncode,
            "outputSuppressed": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    try:
        result = run(args.uv, repository)
        args.out.resolve().parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.resolve().with_name(f".{args.out.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(args.out.resolve())
        print(json.dumps({"status": result.get("status"), "out": str(args.out.resolve())}, separators=(",", ":")))
        return 0 if result.get("status") == "pass" else 1
    except (OSError, RuntimeError):
        print(json.dumps({"status": "error", "code": "AUDIT_RUNTIME_ERROR"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
