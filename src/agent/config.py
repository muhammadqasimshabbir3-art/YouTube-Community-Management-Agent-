"""Environment-driven configuration for YouTube Community Manager Agent."""

from __future__ import annotations

import os
from functools import lru_cache


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on")


def _set_env_if_present(key: str, value: object | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text == "":
        return
    os.environ[key] = text


def _set_env_bool_if_present(key: str, value: object | None) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        os.environ[key] = "true" if value else "false"
        return
    text = str(value).strip().lower()
    if text == "":
        return
    os.environ[key] = "true" if text in ("1", "true", "yes", "on") else "false"


def _set_env_int_if_present(key: str, value: object | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text == "":
        return
    os.environ[key] = str(int(text))


def apply_runtime_overrides(state: dict | None = None) -> None:
    """Apply per-run UI overrides to process env before reading config."""
    if not state:
        return

    _set_env_int_if_present("MAX_VIDEOS_TO_SCAN", state.get("max_videos_to_scan"))
    _set_env_int_if_present("MAX_COMMENTS_PER_VIDEO", state.get("max_comments_per_video"))
    _set_env_int_if_present("MAX_REPLIES_PER_VIDEO", state.get("max_replies_per_video"))
    _set_env_int_if_present("MAX_NEW_COMMENTS", state.get("max_new_comments"))

    _set_env_if_present("REPLY_PERSONALITY", state.get("reply_personality"))
    if state.get("new_comment_text") is not None:
        os.environ["NEW_COMMENT_TEXT"] = str(state.get("new_comment_text") or "")

    _set_env_bool_if_present("ENABLE_COMMENT_REPLIES", state.get("enable_comment_replies"))
    _set_env_bool_if_present("ENABLE_NEW_COMMENTS", state.get("enable_new_comments"))
    _set_env_bool_if_present("KEEP_BROWSER_OPEN", state.get("keep_browser_open"))
    _set_env_bool_if_present("EMAIL_REPORTS", state.get("email_reports"))
    _set_env_bool_if_present("REPLY_TO_POSITIVE", state.get("reply_to_positive"))
    _set_env_bool_if_present("REPLY_TO_NEGATIVE", state.get("reply_to_negative"))
    _set_env_bool_if_present("REPLY_TO_NEUTRAL", state.get("reply_to_neutral"))
    _set_env_bool_if_present("REPLY_TO_QUESTIONS", state.get("reply_to_questions"))
    _set_env_bool_if_present("REPLY_TO_SUGGESTIONS", state.get("reply_to_suggestions"))
    _set_env_bool_if_present("REPLY_TO_SPAM", state.get("reply_to_spam"))

    recipient = str(state.get("email_recipient") or "").strip()
    if recipient:
        os.environ["GMAIL_DEFAULT_RECIPIENT"] = recipient

    get_youtube_config.cache_clear()


@lru_cache(maxsize=1)
def get_youtube_config() -> dict:
    """Load YouTube and reply configuration from environment."""
    return {
        "email": os.getenv("YOUTUBE_EMAIL", "").strip(),
        "password": os.getenv("YOUTUBE_PASSWORD", "").strip(),
        "channel_name": os.getenv("YOUTUBE_CHANNEL_NAME", "").strip(),
        "channel_url": os.getenv("YOUTUBE_CHANNEL_URL", "").strip(),
        "enable_comment_replies": _env_bool("ENABLE_COMMENT_REPLIES", False),
        "email_reports": _env_bool("EMAIL_REPORTS", False),
        "reply_to_positive": _env_bool("REPLY_TO_POSITIVE", True),
        "reply_to_negative": _env_bool("REPLY_TO_NEGATIVE", False),
        "reply_to_neutral": _env_bool("REPLY_TO_NEUTRAL", False),
        "reply_to_questions": _env_bool("REPLY_TO_QUESTIONS", True),
        "reply_to_suggestions": _env_bool("REPLY_TO_SUGGESTIONS", True),
        "reply_to_spam": _env_bool("REPLY_TO_SPAM", False),
        "max_videos": int(os.getenv("MAX_VIDEOS_TO_SCAN", "1")),
        # 0 = scrape/analyze all visible comments (up to YouTube's reported count)
        "max_comments_per_video": int(os.getenv("MAX_COMMENTS_PER_VIDEO", "0")),
        "max_replies_per_video": int(os.getenv("MAX_REPLIES_PER_VIDEO", "5")),
        "reply_personality": os.getenv("REPLY_PERSONALITY", "humorous").strip().lower(),
        "enable_new_comments": _env_bool("ENABLE_NEW_COMMENTS", False),
        "new_comment_text": os.getenv("NEW_COMMENT_TEXT", "").strip(),
        "max_new_comments": int(os.getenv("MAX_NEW_COMMENTS", "1")),
        "session_path": os.getenv(
            "YOUTUBE_SESSION_PATH", "./data/youtube_session.json"
        ),
        "reply_history_path": os.getenv(
            "REPLY_HISTORY_PATH", "./data/reply_history.json"
        ),
        "headless": _env_bool("BROWSER_HEADLESS", True),
        "keep_browser_open": _env_bool("KEEP_BROWSER_OPEN", True),
    }


def resolve_target_channel(
    channel_url: str = "",
    channel_name: str = "",
) -> tuple[str, str]:
    """Resolve target channel from explicit inputs or .env defaults."""
    config = get_youtube_config()
    resolved_url = (channel_url or config["channel_url"]).strip()
    resolved_name = (channel_name or config["channel_name"]).strip()
    return resolved_url, resolved_name


def is_category_reply_enabled(category: str) -> bool:
    """Return whether replies are enabled for a comment category."""
    config = get_youtube_config()
    mapping = {
        "positive": config["reply_to_positive"],
        "negative": config["reply_to_negative"],
        "neutral": config["reply_to_neutral"],
        "question": config["reply_to_questions"],
        "suggestion": config["reply_to_suggestions"],
        "spam": config["reply_to_spam"],
    }
    return mapping.get(category.lower(), False)
