"""AI reply generation for YouTube comments."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from agent.config import get_youtube_config, is_category_reply_enabled


def _get_model() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    return ChatGroq(model="llama-3.1-8b-instant", temperature=0.3, api_key=api_key)


def _system_prompt_for_comment(comment: dict[str, Any], personality: str) -> str:
    category = str(comment.get("category", "neutral")).lower()
    if category == "positive" and personality in {
        "humorous",
        "humor",
        "funny",
        "witty",
    }:
        return (
            "You write warm, witty YouTube creator replies. "
            "Use light humor, playful jokes, or clever wordplay while staying kind and on-brand. "
            "Never be sarcastic toward the viewer."
        )
    return "You write warm, professional YouTube creator replies."


def _user_prompt_for_comment(comment: dict[str, Any], channel_name: str) -> str:
    category = comment.get("category", "neutral")
    rank = comment.get("reply_rank")
    rank_line = f"This is reply target #{rank} by engagement.\n" if rank else ""
    tone = (
        "Write a short, funny-but-friendly reply that makes the viewer smile."
        if category == "positive"
        else "Write a short, friendly, professional reply on behalf of the channel team."
    )
    return (
        f"You are managing community engagement for the YouTube channel '{channel_name}'. "
        f"A viewer left this {category} comment on the channel's latest video.\n"
        f"{rank_line}"
        f"Comment by {comment.get('author', 'viewer')}: {comment.get('text', '')}\n"
        f"Likes: {comment.get('likes', 0)}\n"
        f"{tone} Keep the reply under 280 characters. Do not use hashtags. "
        "Never mention automation, testing, diagnostics, or that you are an AI."
    )


def generate_reply_for_comment(
    comment: dict[str, Any],
    channel_name: str = "",
    personality: str = "",
) -> str:
    """Generate a community-manager reply for a comment on the target channel's video."""
    config = get_youtube_config()
    personality = personality or config.get("reply_personality", "humorous")
    model = _get_model()
    prompt = _user_prompt_for_comment(comment, channel_name)
    system_prompt = _system_prompt_for_comment(comment, personality)
    try:
        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content).strip()
    except Exception:
        if comment.get("category") == "positive":
            return "Haha, love this energy — thanks for hanging out with us!"
        return "Thanks for watching and for leaving a comment!"


def generate_replies(
    comments: list[dict[str, Any]],
    channel_name: str = "",
    prior_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate replies for pre-selected comment targets based on .env filters."""
    config = get_youtube_config()
    generated: list[dict[str, Any]] = []
    skipped = 0

    for comment in comments:
        if comment.get("agent_replied") or comment.get("posted"):
            skipped += 1
            continue

        category = comment.get("category", "neutral")
        if not is_category_reply_enabled(category):
            skipped += 1
            continue

        reply_text = generate_reply_for_comment(comment, channel_name)
        generated.append(
            {
                **comment,
                "reply_text": reply_text,
                "posted": False,
            }
        )

    stats = {
        **(prior_stats or {}),
        "total_comments": len(comments),
        "replies_generated": len(generated),
        "replies_skipped": skipped,
        "replies_target_limit": config["max_replies_per_video"],
        "posting_enabled": config["enable_comment_replies"],
        "reply_personality": config.get("reply_personality", "humorous"),
        "filters": {
            "positive": config["reply_to_positive"],
            "negative": config["reply_to_negative"],
            "neutral": config["reply_to_neutral"],
            "questions": config["reply_to_questions"],
            "suggestions": config["reply_to_suggestions"],
            "spam": config["reply_to_spam"],
        },
    }

    return {"generated_replies": generated, "reply_statistics": stats}


__all__ = ["generate_replies", "generate_reply_for_comment"]
