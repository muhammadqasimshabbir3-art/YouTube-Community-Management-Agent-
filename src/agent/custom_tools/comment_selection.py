"""Select which analyzed comments should receive replies."""

from __future__ import annotations

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
        if comment.get("category") != "positive":
            continue
        if comment.get("agent_replied") or comment.get("posted"):
            continue
        if comment.get("is_pinned") or comment.get("is_channel_owner"):
            continue
        if comment.get("channel_replied"):
            continue
        if _author_matches_channel(str(comment.get("author", "")), channel_name):
            continue
        eligible.append(comment)

    eligible.sort(key=_positive_reply_score, reverse=True)

    selected: list[dict[str, Any]] = []
    for rank, comment in enumerate(eligible[:limit], start=1):
        enriched = dict(comment)
        enriched["selected_for_reply"] = True
        enriched["reply_rank"] = rank
        selected.append(enriched)
    return selected


__all__ = ["select_top_positive_comments"]
