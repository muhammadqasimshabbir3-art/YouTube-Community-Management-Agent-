"""Tests for environment configuration."""

import os

from agent.config import (
    apply_runtime_overrides,
    get_youtube_config,
    is_category_reply_enabled,
    resolve_target_channel,
)


def test_config_max_replies_default(monkeypatch):
    monkeypatch.delenv("MAX_REPLIES_PER_VIDEO", raising=False)
    monkeypatch.delenv("MAX_COMMENTS_PER_VIDEO", raising=False)
    monkeypatch.delenv("REPLY_PERSONALITY", raising=False)
    get_youtube_config.cache_clear()
    config = get_youtube_config()
    assert config["max_replies_per_video"] == 5
    assert config["max_comments_per_video"] == 0
    assert config["reply_personality"] == "humorous"


def test_reply_category_defaults(monkeypatch):
    monkeypatch.delenv("REPLY_TO_POSITIVE", raising=False)
    monkeypatch.delenv("REPLY_TO_SPAM", raising=False)
    get_youtube_config.cache_clear()
    assert is_category_reply_enabled("positive") is True
    assert is_category_reply_enabled("spam") is False


def test_reply_category_override(monkeypatch):
    monkeypatch.setenv("REPLY_TO_NEGATIVE", "true")
    get_youtube_config.cache_clear()
    assert is_category_reply_enabled("negative") is True


def test_resolve_target_channel_from_env(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CHANNEL_NAME", "Test Channel")
    monkeypatch.setenv("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@test")
    get_youtube_config.cache_clear()
    url, name = resolve_target_channel()
    assert name == "Test Channel"
    assert url == "https://www.youtube.com/@test"
    monkeypatch.delenv("YOUTUBE_CHANNEL_NAME", raising=False)
    monkeypatch.delenv("YOUTUBE_CHANNEL_URL", raising=False)
    get_youtube_config.cache_clear()


def test_apply_runtime_overrides_from_ui(monkeypatch):
    monkeypatch.setenv("MAX_REPLIES_PER_VIDEO", "5")
    monkeypatch.setenv("ENABLE_COMMENT_REPLIES", "false")
    monkeypatch.setenv("REPLY_PERSONALITY", "humorous")
    get_youtube_config.cache_clear()

    apply_runtime_overrides(
        {
            "max_replies_per_video": 3,
            "max_comments_per_video": 0,
            "max_videos_to_scan": 1,
            "reply_personality": "friendly",
            "enable_comment_replies": True,
            "enable_new_comments": False,
            "keep_browser_open": True,
            "email_reports": True,
            "reply_to_negative": True,
            "email_recipient": "run@example.com",
        }
    )
    config = get_youtube_config()
    assert config["max_replies_per_video"] == 3
    assert config["max_comments_per_video"] == 0
    assert config["reply_personality"] == "friendly"
    assert config["enable_comment_replies"] is True
    assert config["enable_new_comments"] is False
    assert config["keep_browser_open"] is True
    assert config["email_reports"] is True
    assert config["reply_to_negative"] is True
    assert os.getenv("GMAIL_DEFAULT_RECIPIENT") == "run@example.com"
