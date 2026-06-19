"""Persistent reply history — records what was replied to what."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HISTORY_PATH = Path("./data/reply_history.json")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_history() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.get("records") or [])
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_history(records: list[dict[str, Any]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps({"records": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def build_reply_record(
    reply: dict[str, Any],
    channel_name: str = "",
    video_metadata: dict[str, Any] | None = None,
    *,
    status: str = "generated",
    posted: bool = False,
) -> dict[str, Any]:
    """Build a single reply history record."""
    video = video_metadata or {}
    return {
        "recorded_at": _utc_now(),
        "channel_name": channel_name or video.get("channel_on_video", ""),
        "video_id": reply.get("video_id") or video.get("video_id", ""),
        "video_title": reply.get("video_title") or video.get("title", ""),
        "video_url": reply.get("video_url") or video.get("url", ""),
        "comment_id": reply.get("comment_id", ""),
        "comment_author": reply.get("author", "Unknown"),
        "comment_text": reply.get("text", ""),
        "comment_category": reply.get("category", ""),
        "engagement_priority": reply.get("engagement_priority", ""),
        "sentiment_score": reply.get("sentiment_score"),
        "reply_text": reply.get("reply_text", ""),
        "posted": posted,
        "status": status,
    }


def record_reply_entries(
    replies: list[dict[str, Any]],
    channel_name: str = "",
    video_metadata: dict[str, Any] | None = None,
    *,
    status: str = "generated",
) -> list[dict[str, Any]]:
    """Append reply records to persistent history."""
    if not replies:
        return []

    existing = _load_history()
    new_records: list[dict[str, Any]] = []

    for reply in replies:
        posted = bool(reply.get("posted")) if status == "posted" else False
        record = build_reply_record(
            reply,
            channel_name=channel_name,
            video_metadata=video_metadata,
            status=status if not posted else "posted",
            posted=posted,
        )
        # Update existing record for same comment_id + video_id if re-posting
        updated = False
        for index, old in enumerate(existing):
            if (
                old.get("comment_id") == record["comment_id"]
                and old.get("video_id") == record["video_id"]
                and old.get("reply_text") == record["reply_text"]
            ):
                existing[index] = {**old, **record}
                updated = True
                break
        if not updated:
            existing.append(record)
        new_records.append(record)

    _save_history(existing)
    return new_records


def get_reply_history(
    channel_name: str = "",
    video_id: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Load reply history, optionally filtered."""
    records = _load_history()
    if channel_name:
        records = [r for r in records if r.get("channel_name") == channel_name]
    if video_id:
        records = [r for r in records if r.get("video_id") == video_id]
    return records[-limit:]


__all__ = [
    "record_reply_entries",
    "get_reply_history",
    "build_reply_record",
    "HISTORY_PATH",
]
