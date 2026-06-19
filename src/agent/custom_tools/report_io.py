"""Shared helpers for writing report files."""

from __future__ import annotations

from pathlib import Path


def prepare_report_output_path(output_path: str | Path) -> Path:
    """Ensure report directory exists and remove any previous file at this path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return path
