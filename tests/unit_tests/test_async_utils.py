"""Tests for async thread offloading helpers."""

import pytest

from agent.async_utils import _run_blocking_with_skip, run_in_thread


def test_run_blocking_with_skip_marks_blockbuster_context():
    try:
        from blockbuster.blockbuster import blockbuster_skip
    except ImportError:
        pytest.skip("blockbuster not installed")

    observed: list[bool] = []

    def worker() -> None:
        observed.append(blockbuster_skip.get())

    _run_blocking_with_skip(worker)
    assert observed == [True]


@pytest.mark.anyio
async def test_run_in_thread_runs_mkdir_without_error(tmp_path):
    target = tmp_path / "nested" / "reports"

    def create_dir() -> str:
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    result = await run_in_thread(create_dir)
    assert result == str(target)
    assert target.is_dir()
