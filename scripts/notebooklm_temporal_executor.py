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
from threading import Event
from typing import Callable, Generic, Iterable, TypeVar


T = TypeVar("T")
R = TypeVar("R")


class ExecutorError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


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
) -> list[R]:
    """Execute all items or raise; never silently returns a partial batch.

    Results preserve input order. If an operation fails, pending futures are
    cancelled and an aggregate ``EXECUTION_FAILED`` error is raised without
    serializing the underlying exception text.
    """

    validate_policy(policy)
    values = list(items)
    if not values:
        return []
    if cancel_event and cancel_event.is_set():
        raise ExecutorError("CANCELLED", "execution cancelled before start")

    results: list[R | None] = [None] * len(values)

    def invoke(index: int) -> R:
        if cancel_event and cancel_event.is_set():
            raise ExecutorError("CANCELLED", "execution cancelled")
        return run_with_retries(
            lambda: operation(values[index]),
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
