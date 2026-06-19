"""Intent detection and routing for YouTube Community Manager Agent."""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

YOUTUBE_KEYWORDS = (
    "youtube",
    "channel",
    "comment",
    "comments",
    "community",
    "subscriber",
    "video comments",
    "analyze channel",
    "manage comments",
)

REPORT_KEYWORDS = (
    "pdf",
    "report",
    "generate report",
    "create report",
)

EMAIL_KEYWORDS = (
    "email",
    "e-mail",
    "mail me",
    "send me",
    "send report",
    "email report",
)


def get_latest_user_text(messages: list[AnyMessage]) -> str:
    """Return the most recent human message text."""
    for message in reversed(messages):
        if (
            isinstance(message, HumanMessage)
            or getattr(message, "type", None) == "human"
        ):
            content = message.content
            if isinstance(content, str):
                return content
            return str(content)
    return ""


def extract_channel_url(text: str) -> str:
    """Extract a YouTube channel URL from user text."""
    match = re.search(
        r"(https?://(?:www\.)?youtube\.com/(?:@[\w\-]+|channel/[\w\-]+|c/[\w\-]+)[^\s]*)",
        text,
    )
    if match:
        return match.group(1).strip()
    match = re.search(r"(youtube\.com/@[\w\-]+)", text)
    if match:
        return f"https://www.{match.group(1)}"
    return ""


def extract_channel_name(text: str) -> str:
    """Extract channel name from natural language."""
    patterns = (
        r"(?i)analyze\s+(?:the\s+)?['\"]?([^'\".\n]+?)['\"]?\s+channel",
        r"(?i)channel\s+(?:named|called)\s*['\"]?([^'\".\n]+)['\"]?",
        r"(?i)for\s+channel\s+['\"]?([^'\".\n]+)['\"]?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def wants_youtube_analysis(
    text: str, state_channel_url: str = "", state_channel_name: str = ""
) -> bool:
    """Detect whether the user wants YouTube channel comment analysis."""
    _ = (
        state_channel_url,
        state_channel_name,
    )  # channel config alone is not user intent
    if not text.strip():
        return False
    lowered = text.lower()
    if extract_channel_url(text):
        return True
    if any(keyword in lowered for keyword in YOUTUBE_KEYWORDS):
        return True
    if "youtube.com" in lowered:
        return True
    return False


def wants_pdf_report(text: str) -> bool:
    """Detect PDF report generation intent."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in REPORT_KEYWORDS)


def wants_email_report(text: str) -> bool:
    """Detect email report intent."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in EMAIL_KEYWORDS)


def is_empty_ai_message(response: AIMessage) -> bool:
    """Check if an AI message has no usable text content."""
    content = response.content
    if content is None or content == "":
        return True
    if isinstance(content, list):
        return len(content) == 0
    if isinstance(content, str):
        return not content.strip()
    return False


def build_analysis_summary(state: dict) -> str:
    """Build a human-readable summary from analysis state."""
    total = len(state.get("comments") or [])
    analyzed = state.get("analyzed_comments") or []
    stats = state.get("reply_statistics") or {}
    channel = state.get("youtube_channel_name") or "Unknown Channel"
    video = state.get("video_metadata") or state.get("latest_video") or {}

    lines = [
        f"**YouTube Community Analysis — {channel}**",
        "",
    ]
    if video:
        lines.extend(
            [
                f"- Latest video: {video.get('title', 'N/A')}",
                f"- Video URL: {video.get('url', 'N/A')}",
                f"- Published: {video.get('published', 'N/A')}",
                f"- Views: {video.get('views', 'N/A')}",
                f"- Comments on video: {video.get('comment_count', 'N/A')}",
            ]
        )
        about = video.get("video_about")
        if about:
            lines.extend(["", "**What this video is about:**", about])
        description = video.get("description") or video.get("og_description")
        if description:
            excerpt = description[:600] + ("..." if len(description) > 600 else "")
            lines.extend(["", "**Video description:**", excerpt, ""])
    lines.extend(
        [
            f"- Total comments collected: {total}",
            f"- Positive: {len(state.get('positive_comments') or [])}",
            f"- Negative: {len(state.get('negative_comments') or [])}",
            f"- Neutral: {len(state.get('neutral_comments') or [])}",
            f"- Questions: {len(state.get('question_comments') or [])}",
            f"- Suggestions: {len(state.get('suggestion_comments') or [])}",
            f"- Spam: {len(state.get('spam_comments') or [])}",
            f"- Unanswered: {len(state.get('unanswered_comments') or [])}",
            f"- Reply targets selected: {len(state.get('reply_targets') or [])}",
            f"- Replies generated: {stats.get('replies_generated', len(state.get('generated_replies') or []))}",
            f"- Replies posted: {stats.get('replies_posted', 0)}",
            f"- Replies failed: {stats.get('replies_failed', len(state.get('failed_replies') or []))}",
            f"- New video comments: {len(state.get('generated_new_comments') or [])} "
            f"({stats.get('new_comments_posted', 0)} posted)",
        ]
    )

    if state.get("pdf_path"):
        lines.extend(["", f"PDF report: `{state['pdf_path']}`"])
    if state.get("html_path"):
        lines.extend(["", f"HTML dashboard: `{state['html_path']}`"])

    if analyzed:
        high_priority = [
            c
            for c in analyzed
            if c.get("engagement_priority") == "high" and not c.get("replied")
        ][:3]
        if high_priority:
            lines.extend(["", "**Top engagement opportunities:**"])
            for comment in high_priority:
                lines.append(
                    f"- [{comment.get('category')}] {comment.get('author')}: "
                    f"{comment.get('text', '')[:120]}"
                )

    return "\n".join(lines)


def format_login_result(logged_in: bool, channel_url: str = "") -> AIMessage:
    """Format login node result."""
    if logged_in:
        msg = "Successfully logged in to YouTube."
        if channel_url:
            msg += f" Session ready for channel: {channel_url}"
        return AIMessage(content=msg)
    return AIMessage(content="YouTube login failed. Check credentials in .env.")


__all__ = [
    "get_latest_user_text",
    "extract_channel_url",
    "extract_channel_name",
    "wants_youtube_analysis",
    "wants_pdf_report",
    "wants_email_report",
    "is_empty_ai_message",
    "build_analysis_summary",
    "format_login_result",
]
