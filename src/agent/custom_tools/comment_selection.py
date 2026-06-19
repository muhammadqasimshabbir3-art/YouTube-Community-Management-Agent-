"""Select which analyzed comments should receive replies."""

from __future__ import annotations

import random
from typing import Any


def _author_matches_channel(author: str, channel_name: str) -> bool:
    if not channel_name or not author:
        return False
    normalized_channel = channel_name.lower().strip().lstrip("@")
    normalized_author = author.lower().strip().lstrip("@")
    return (
        normalized_channel in normalized_author
        or normalized_author in normalized_channel
    )


def _positive_reply_score(comment: dict[str, Any]) -> float:
    likes = int(comment.get("likes") or 0)
    sentiment = float(comment.get("sentiment_score") or 0)
    priority_boost = {"high": 3.0, "medium": 1.5, "low": 0.0}.get(
        str(comment.get("engagement_priority", "low")).lower(), 0.0
    )
    return likes * 10 + sentiment * 5 + priority_boost


def _is_positive(comment: dict[str, Any]) -> bool:
    return str(comment.get("category", "")).lower() == "positive"


def is_channel_author_comment(comment: dict[str, Any], channel_name: str) -> bool:
    """True when the comment author is the target channel (not generic YouTube badges)."""
    return _author_matches_channel(str(comment.get("author", "")), channel_name)


def _fallback_positive_pool(
    analyzed: list[dict[str, Any]],
    channel_name: str = "",
) -> list[dict[str, Any]]:
    """Relaxed pool when strict filters remove every positive comment."""
    pool: list[dict[str, Any]] = []
    for comment in analyzed:
        if not _is_positive(comment):
            continue
        if comment.get("agent_replied") or comment.get("posted"):
            continue
        if is_channel_author_comment(comment, channel_name):
            continue
        if not str(comment.get("text", "")).strip():
            continue
        pool.append(comment)
    return pool


def _any_positive_pool(analyzed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Last-resort pool: any positive comment with text."""
    return [
        comment
        for comment in analyzed
        if _is_positive(comment)
        and not comment.get("agent_replied")
        and not comment.get("posted")
        and str(comment.get("text", "")).strip()
    ]


def select_top_positive_comments(
    analyzed: list[dict[str, Any]],
    limit: int = 5,
    channel_name: str = "",
) -> list[dict[str, Any]]:
    """Pick up to N positive comments that are eligible for a channel reply."""
    if limit <= 0:
        return []

    eligible: list[dict[str, Any]] = []
    for comment in analyzed:
        if not _is_positive(comment):
            continue
        if comment.get("agent_replied") or comment.get("posted"):
            continue
        if comment.get("is_pinned"):
            continue
        if is_channel_author_comment(comment, channel_name):
            continue
        if comment.get("channel_replied"):
            continue
        eligible.append(comment)

    eligible.sort(key=_positive_reply_score, reverse=True)
    use_fallback = not eligible
    if use_fallback:
        eligible = _fallback_positive_pool(analyzed, channel_name)
        random.shuffle(eligible)
    if not eligible:
        eligible = _any_positive_pool(analyzed)
        random.shuffle(eligible)
        use_fallback = bool(eligible)

    selected: list[dict[str, Any]] = []
    for rank, comment in enumerate(eligible[:limit], start=1):
        enriched = dict(comment)
        enriched["selected_for_reply"] = True
        enriched["reply_rank"] = rank
        if use_fallback:
            enriched["fallback_selection"] = True
        selected.append(enriched)
    return selected


__all__ = ["is_channel_author_comment", "select_top_positive_comments"]
