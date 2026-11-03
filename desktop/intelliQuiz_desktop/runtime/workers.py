"""Shared worker pool for IntelliQuiz desktop core I/O.

Keeps the webcam / app-lock / UI event loops free by running:
- encrypted event sync
- evidence JPEG / disk work
- screen capture helpers
on dedicated background threads.
"""

from __future__ import annotations

import atexit
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None
_sync_pool: ThreadPoolExecutor | None = None


def _ensure() -> tuple[ThreadPoolExecutor, ThreadPoolExecutor]:
    global _pool, _sync_pool
    with _lock:
        if _pool is None:
            # General I/O: evidence encode, screen snap, light disk work.
            _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="iq-io")
        if _sync_pool is None:
            # Single worker so sync batches stay ordered per process.
            _sync_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iq-sync")
        return _pool, _sync_pool


def submit_io(fn: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
    pool, _ = _ensure()
    return pool.submit(fn, *args, **kwargs)


def submit_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
    _, sync_pool = _ensure()
    return sync_pool.submit(fn, *args, **kwargs)


def shutdown_workers(wait: bool = False) -> None:
    global _pool, _sync_pool
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=wait, cancel_futures=not wait)
            _pool = None
        if _sync_pool is not None:
            _sync_pool.shutdown(wait=wait, cancel_futures=not wait)
            _sync_pool = None


atexit.register(lambda: shutdown_workers(wait=False))
