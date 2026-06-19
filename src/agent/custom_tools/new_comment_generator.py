"""Generate new top-level video comments for community engagement."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from agent.config import get_youtube_config


def _get_model() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    return ChatGroq(model="llama-3.1-8b-instant", temperature=0.4, api_key=api_key)


def _system_prompt_for_new_comment(personality: str) -> str:
    if personality in {"humorous", "humor", "funny", "witty"}:
        return (
            "You are the YouTube channel owner posting under your own video. "
            "Write warm, witty, authentic comments with light humor. "
            "Sound like a real creator talking to fans — never robotic, never a test message."
        )
    return (
        "You are the YouTube channel owner posting under your own video. "
        "Write warm, authentic creator comments that invite discussion."
    )


def generate_new_video_comment(
    channel_name: str = "",
    video_metadata: dict[str, Any] | None = None,
    analysis_summary: str = "",
) -> str:
    """Generate a personality-driven top-level comment for the latest video."""
    config = get_youtube_config()
    override = config.get("new_comment_text", "").strip()
    if override:
        return override

    personality = config.get("reply_personality", "humorous")
    video = video_metadata or {}
    title = video.get("title", "this video")
    prompt = (
        f"You are posting as the YouTube channel '{channel_name}' on your own latest video.\n"
        f"Video title: {title}\n"
        f"Video about: {video.get('video_about', video.get('description', ''))[:500]}\n"
        f"Community analysis: {analysis_summary[:600]}\n\n"
        "Write one short, authentic top-level comment to post under the video. "
        "Thank viewers, reference the mood/theme of the track, and invite discussion. "
        "Use the channel's personality. Keep it under 280 characters. No hashtags. "
        "Never mention automation, testing, diagnostics, or that you are an AI."
    )
    try:
        model = _get_model()
        response = model.invoke(
            [
                SystemMessage(content=_system_prompt_for_new_comment(personality)),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content).strip()
    except Exception:
        return (
            f"Thank you for listening to '{title}' — what moment hit you the hardest?"
        )


def build_generated_new_comments(
    comment_text: str,
    video_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Wrap generated comment text in workflow-friendly records."""
    video = video_metadata or {}
    video_id = video.get("video_id", "")
    video_url = video.get("url", "")
    if not video_url and video_id:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
    return [
        {
            "comment_text": comment_text,
            "video_id": video_id,
            "video_title": video.get("title", ""),
            "video_url": video_url,
            "posted": False,
            "post_error": "",
        }
    ]


__all__ = ["generate_new_video_comment", "build_generated_new_comments"]
