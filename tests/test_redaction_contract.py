from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from redaction_contract import POLICY, sanitize_remote_text  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class RedactionContractTests(unittest.TestCase):
    def test_python_and_projection_sanitizers_share_the_same_secret_contract(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for cross-runtime redaction verification")
        private_marker = "-----BEGIN " + "PRIVATE KEY-----"
        private_end = "-----END " + "PRIVATE KEY-----"
        aws_key = "".join(("AK", "IA1234567890ABCDEF"))
        google_key = "".join(("AI", "za1234567890abcdefghijklmnopqrstuvwxyz123"))
        github_token = "".join(("gh", "p_abcdefghijklmnopqrstuvwxyz1234"))
        slack_token = "".join(("xox", "b-abcdefghijkl"))
        examples = [
            "Order 26-12504 remains ordinary data.",
            f"{private_marker}\nprivate-material\n{private_end}",
            aws_key,
            google_key,
            "sk-proj-abcdefghijklmnop",
            github_token,
            slack_token,
            "sk_live_abcdefghijkl",
            "eyJabcdefghijkl.eyJabcdefghijkl.eyJabcdefghijkl",
            "Authorization: Bearer abcdefghijklmnop",
            "Cookie: session=private-cookie-value",
            "https://alice:password@example.com/path",
            r"C:\Users\alice\Documents\trace.txt",
            "/home/alice/.codex/trace.txt",
            "https://example.test/?access_token=private-access-token",
            "password=private-password-value",
            "data:text/plain;base64," + ("A" * 100),
            "base64 " + ("B" * 260),
        ]
        source = "\n".join(examples)
        python_text, python_counts = sanitize_remote_text(source)
        self.assertEqual(POLICY, "remote-notebooklm-secrets-redacted-v1")
        for raw in examples[1:]:
            self.assertNotIn(raw, python_text)
        self.assertIn("Order 26-12504 remains ordinary data.", python_text)
        self.assertGreaterEqual(sum(python_counts.values()), 10)

        javascript = (
            "import { readFileSync } from 'node:fs'; "
            "import { REMOTE_REDACTION_POLICY, sanitizeSecrets } from './scripts/notebooklm_thread_projection_lib.mjs'; "
            "const value = readFileSync(0, 'utf8'); "
            "const result = sanitizeSecrets(value); "
            "console.log(JSON.stringify({ policy: REMOTE_REDACTION_POLICY, text: result.text, counts: result.counts }));"
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", javascript],
            cwd=ROOT,
            input=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        projection = json.loads(completed.stdout)
        self.assertEqual(projection["policy"], POLICY)
        for raw in examples[1:]:
            self.assertNotIn(raw, projection["text"])
        self.assertIn("Order 26-12504 remains ordinary data.", projection["text"])
        self.assertGreaterEqual(sum(projection["counts"].values()), 10)


if __name__ == "__main__":
    unittest.main()
