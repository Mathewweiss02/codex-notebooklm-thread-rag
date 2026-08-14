from __future__ import annotations

from threading import Lock
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from notebooklm_temporal_executor import (  # noqa: E402
    ExecutorError,
    ExecutorPolicy,
    execute_bounded,
    run_with_retries,
    validate_policy,
)


class TemporalExecutorTests(unittest.TestCase):
    def test_safe_default_is_sequential_and_preserves_order(self) -> None:
        observed: list[int] = []
        result = execute_bounded(
            [3, 1, 2],
            lambda value: observed.append(value) or value * 2,
            policy=ExecutorPolicy(),
        )
        self.assertEqual(result, [6, 2, 4])
        self.assertEqual(observed, [3, 1, 2])

    def test_unsafe_shared_conversation_concurrency_is_rejected(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            validate_policy(ExecutorPolicy(mode="sequential", concurrency=2))
        self.assertEqual(caught.exception.code, "UNSAFE_CONCURRENCY")

    def test_packed_mode_is_one_remote_request(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            validate_policy(ExecutorPolicy(mode="packed", concurrency=2))
        self.assertEqual(caught.exception.code, "PACKED_CONCURRENCY_UNSUPPORTED")

    def test_approved_isolated_pool_can_use_bounded_workers(self) -> None:
        active = 0
        peak = 0
        guard = Lock()

        def operation(value: int) -> int:
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with guard:
                active -= 1
            return value

        result = execute_bounded(
            range(8),
            operation,
            policy=ExecutorPolicy(mode="isolated-replicas", concurrency=2, isolated_replica_proof=True),
        )
        self.assertEqual(result, list(range(8)))
        self.assertLessEqual(peak, 2)

    def test_failure_does_not_return_a_partial_success(self) -> None:
        def operation(value: int) -> int:
            if value == 2:
                raise RuntimeError("fixture failure")
            return value

        with self.assertRaises(ExecutorError) as caught:
            execute_bounded([1, 2, 3], operation, policy=ExecutorPolicy())
        self.assertEqual(caught.exception.code, "EXECUTION_FAILED")

    def test_checkpoint_failure_is_explicit(self) -> None:
        def checkpoint(_index: int, _value: int) -> None:
            raise RuntimeError("fixture")

        with self.assertRaises(ExecutorError) as caught:
            execute_bounded(
                [1],
                lambda value: value,
                policy=ExecutorPolicy(),
                on_result=checkpoint,
            )
        self.assertEqual(caught.exception.code, "CHECKPOINT_FAILED")

    def test_retry_budget_is_exactly_bounded(self) -> None:
        attempts = 0

        def operation() -> int:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("retryable fixture")
            return 7

        result = run_with_retries(operation, max_retries=1, retryable=lambda error: isinstance(error, TimeoutError))
        self.assertEqual(result, 7)
        self.assertEqual(attempts, 2)

    def test_executor_retry_requires_an_explicit_retry_classifier(self) -> None:
        attempts = 0

        def operation(_value: int) -> int:
            nonlocal attempts
            attempts += 1
            raise TimeoutError("fixture failure")

        with self.assertRaises(ExecutorError) as caught:
            execute_bounded(
                [1],
                operation,
                policy=ExecutorPolicy(max_retries=1),
                retryable=lambda error: isinstance(error, TimeoutError),
            )
        self.assertEqual(caught.exception.code, "EXECUTION_FAILED")
        self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
