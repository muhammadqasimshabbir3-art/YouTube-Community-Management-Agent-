"""Helpers for running blocking code without blocking the LangGraph event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def _run_blocking_with_skip(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Execute blocking work in a worker thread.

    LangGraph dev installs ``blockbuster`` which raises ``BlockingError`` for
    filesystem and other sync calls on threads that inherit the ASGI event-loop
    context. Mark these worker calls as intentionally blocking.
    """
    try:
        from blockbuster.blockbuster import blockbuster_skip
    except ImportError:
        return func(*args, **kwargs)

    token = blockbuster_skip.set(True)
    try:
        return func(*args, **kwargs)
    finally:
        blockbuster_skip.reset(token)


async def run_in_thread(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Run a blocking function in a worker thread."""
    return await asyncio.to_thread(_run_blocking_with_skip, func, *args, **kwargs)
