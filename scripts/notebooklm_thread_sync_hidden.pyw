"""Launch the scheduled PowerShell runner without creating a console window."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


EXIT_USAGE = 64
EXIT_LAUNCH_FAILURE = 70


def _launch_error_path(config_path: str) -> Path:
    return Path(config_path).resolve().parent / "scheduler-launch-error.json"


def _record_launch_error(config_path: str, error: BaseException) -> None:
    """Leave a local breadcrumb when pythonw has no stderr console."""
    try:
        message = f"{type(error).__name__}: {error}".replace("\r", " ").replace("\n", " ")
        error_path = _launch_error_path(config_path)
        temporary_path = error_path.with_name(f".{error_path.name}.{os.getpid()}.tmp")
        payload = {
            "Status": "launch-error",
            "At": datetime.now(timezone.utc).isoformat(),
            "Error": message,
        }
        temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_path, error_path)
    except OSError:
        # Task Scheduler still receives EXIT_LAUNCH_FAILURE if even logging fails.
        pass


def _clear_launch_error(config_path: str) -> None:
    try:
        _launch_error_path(config_path).unlink(missing_ok=True)
    except OSError:
        pass


def run_hidden(powershell_path: str, runner_path: str, config_path: str) -> int:
    if os.name != "nt":
        raise RuntimeError("The console-free scheduler launcher requires Windows.")

    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = subprocess.SW_HIDE
    completed = subprocess.run(
        [
            powershell_path,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            runner_path,
            "-Config",
            config_path,
        ],
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        startupinfo=startup_info,
    )
    _clear_launch_error(config_path)
    return int(completed.returncode)


def main(arguments: list[str]) -> int:
    if len(arguments) != 3:
        return EXIT_USAGE
    powershell_path, runner_path, config_path = arguments
    try:
        return run_hidden(powershell_path, runner_path, config_path)
    except BaseException as error:  # pythonw has no visible stderr; preserve a diagnostic.
        _record_launch_error(config_path, error)
        return EXIT_LAUNCH_FAILURE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
