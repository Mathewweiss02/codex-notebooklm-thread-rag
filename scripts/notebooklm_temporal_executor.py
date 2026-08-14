#!/usr/bin/env python3
"""Bounded execution primitives for verified temporal NotebookLM work.

The executor is deliberately topology-aware. A transport semaphore is not
conversation isolation, so concurrency above one is rejected unless the caller
supplies an approved isolated-replica proof. The module contains no NotebookLM
credentials, notebook IDs, or answer handling.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event, Lock
import time
from typing import Callable, Iterable, TypeVar


T = TypeVar("T")
R = TypeVar("R")


class ExecutorError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class AdaptiveRateLimiter:
    """Thread-safe bounded backoff state for explicitly classified rate limits.

    The limiter is transport-neutral. Callers must classify rate-limit errors;
    ordinary failures never consume the rate-limit budget. ``clock`` and
    ``sleep`` are injectable so burst behavior can be tested without waiting.
    """

    def __init__(
        self,
        *,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        max_rate_limit_events: int = 3,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if base_delay_seconds <= 0 or max_delay_seconds <= 0 or base_delay_seconds > max_delay_seconds:
            raise ValueError("rate-limit delays must be positive and ordered")
        if max_rate_limit_events < 1:
            raise ValueError("rate-limit event budget must be positive")
        self._base_delay = float(base_delay_seconds)
        self._max_delay = float(max_delay_seconds)
        self._max_events = int(max_rate_limit_events)
        self._clock = clock
        self._sleep = sleep
        self._lock = Lock()
        self._next_allowed = 0.0
        self._events = 0
        self._backoff_seconds = 0.0

    def acquire(self) -> None:
        with self._lock:
            wait_seconds = max(0.0, self._next_allowed - self._clock())
        if wait_seconds:
            self._sleep(wait_seconds)

    def record_rate_limit(self, retry_after_seconds: float | None = None) -> float:
        with self._lock:
            if self._events >= self._max_events:
                raise ExecutorError("RATE_LIMIT_BUDGET_EXCEEDED", "rate-limit backoff budget exhausted")
            self._events += 1
            exponential = min(self._max_delay, self._base_delay * (2 ** (self._events - 1)))
            requested = 0.0 if retry_after_seconds is None else float(retry_after_seconds)
            if requested < 0:
                raise ExecutorError("INVALID_RETRY_AFTER", "retry-after delay must not be negative")
            delay = min(self._max_delay, max(exponential, requested))
            self._next_allowed = max(self._next_allowed, self._clock() + delay)
            self._backoff_seconds += delay
            return delay

    def record_success(self) -> None:
        with self._lock:
            self._next_allowed = min(self._next_allowed, self._clock())

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "rateLimitEvents": self._events,
                "backoffSeconds": round(self._backoff_seconds, 6),
                "maxRateLimitEvents": self._max_events,
                "maxDelaySeconds": self._max_delay,
            }


@dataclass(frozen=True)
class ExecutorPolicy:
    mode: str = "sequential"
    concurrency: int = 1
    max_retries: int = 0
    isolated_replica_proof: bool = False


def validate_policy(policy: ExecutorPolicy) -> None:
    if policy.mode not in {"sequential", "packed", "isolated-replicas"}:
        raise ExecutorError("INVALID_EXECUTOR_MODE", "unsupported executor mode")
    if policy.concurrency < 1:
        raise ExecutorError("INVALID_CONCURRENCY", "concurrency must be positive")
    if policy.max_retries < 0 or policy.max_retries > 1:
        raise ExecutorError("INVALID_RETRY_BUDGET", "max_retries must be 0 or 1")
    if policy.mode == "sequential" and policy.concurrency != 1:
        raise ExecutorError("UNSAFE_CONCURRENCY", "sequential mode requires concurrency=1")
    if policy.mode == "packed" and policy.concurrency != 1:
        raise ExecutorError("PACKED_CONCURRENCY_UNSUPPORTED", "packed mode is one remote ask")
    if policy.concurrency > 1 and (policy.mode != "isolated-replicas" or not policy.isolated_replica_proof):
        raise ExecutorError(
            "UNSAFE_CONCURRENCY",
            "concurrency above one requires an approved isolated-replica proof",
        )


def run_with_retries(
    operation: Callable[[], R],
    *,
    max_retries: int,
    retryable: Callable[[Exception], bool] | None = None,
) -> R:
    if max_retries < 0 or max_retries > 1:
        raise ExecutorError("INVALID_RETRY_BUDGET", "max_retries must be 0 or 1")
    should_retry = retryable or (lambda _error: False)
    attempt = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            if attempt >= max_retries or not should_retry(exc):
                raise
            attempt += 1


def execute_bounded(
    items: Iterable[T],
    operation: Callable[[T], R],
    *,
    policy: ExecutorPolicy,
    cancel_event: Event | None = None,
    on_result: Callable[[int, R], None] | None = None,
    retryable: Callable[[Exception], bool] | None = None,
    rate_limiter: AdaptiveRateLimiter | None = None,
    rate_limit_classifier: Callable[[Exception], bool] | None = None,
    retry_after: Callable[[Exception], float | None] | None = None,
) -> list[R]:
    """Execute all items or raise; never silently returns a partial batch.

    Results preserve input order. If an operation fails, pending futures are
    cancelled and an aggregate ``EXECUTION_FAILED`` error is raised without
    serializing the underlying exception text.
    """

    validate_policy(policy)
    if rate_limiter is not None and rate_limit_classifier is None:
        raise ExecutorError("RATE_LIMIT_CLASSIFIER_REQUIRED", "rate-limit handling requires an explicit classifier")
    values = list(items)
    if not values:
        return []
    if cancel_event and cancel_event.is_set():
        raise ExecutorError("CANCELLED", "execution cancelled before start")

    results: list[R | None] = [None] * len(values)

    def invoke(index: int) -> R:
        if cancel_event and cancel_event.is_set():
            raise ExecutorError("CANCELLED", "execution cancelled")

        def attempt() -> R:
            if rate_limiter is not None:
                rate_limiter.acquire()
            try:
                result = operation(values[index])
            except Exception as exc:
                if rate_limiter is not None and rate_limit_classifier is not None and rate_limit_classifier(exc):
                    rate_limiter.record_rate_limit(retry_after(exc) if retry_after else None)
                raise
            if rate_limiter is not None:
                rate_limiter.record_success()
            return result

        return run_with_retries(
            attempt,
            max_retries=policy.max_retries,
            retryable=retryable,
        )

    if policy.concurrency == 1:
        for index in range(len(values)):
            try:
                result = invoke(index)
            except ExecutorError:
                raise
            except Exception as exc:
                raise ExecutorError("EXECUTION_FAILED", "one or more operations failed") from exc
            results[index] = result
            if on_result:
                try:
                    on_result(index, result)
                except Exception as exc:
                    raise ExecutorError("CHECKPOINT_FAILED", "result checkpoint failed") from exc
            if cancel_event and cancel_event.is_set():
                raise ExecutorError("CANCELLED", "execution cancelled")
        return [result for result in results]  # type: ignore[misc]

    futures: dict[Future[R], int] = {}
    try:
        with ThreadPoolExecutor(max_workers=policy.concurrency, thread_name_prefix="temporal-nlm") as pool:
            for index in range(len(values)):
                futures[pool.submit(invoke, index)] = index
            for future in as_completed(futures):
                index = futures[future]
                result = future.result()
                results[index] = result
                if on_result:
                    try:
                        on_result(index, result)
                    except Exception as exc:
                        raise ExecutorError("CHECKPOINT_FAILED", "result checkpoint failed") from exc
                if cancel_event and cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    raise ExecutorError("CANCELLED", "execution cancelled")
    except ExecutorError:
        for future in futures:
            future.cancel()
        raise
    except Exception as exc:
        for future in futures:
            future.cancel()
        raise ExecutorError("EXECUTION_FAILED", "one or more operations failed") from exc
    return [result for result in results]  # type: ignore[misc]
