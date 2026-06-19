"""Tests for new top-level video comment generation."""

from agent.custom_tools.new_comment_generator import (
    build_generated_new_comments,
    generate_new_video_comment,
)


def test_build_generated_new_comments_wraps_video_metadata(monkeypatch):
    monkeypatch.setenv("NEW_COMMENT_TEXT", "Thanks everyone for watching!")
    from agent.config import get_youtube_config

    get_youtube_config.cache_clear()
    generated = build_generated_new_comments(
        "Thanks everyone for watching!",
        {
            "video_id": "abc",
            "title": "Test Video",
            "url": "https://youtube.com/watch?v=abc",
        },
    )
    assert generated[0]["comment_text"] == "Thanks everyone for watching!"
    assert generated[0]["video_id"] == "abc"
    assert generated[0]["posted"] is False


def test_generate_new_video_comment_uses_env_override(monkeypatch):
    monkeypatch.setenv("NEW_COMMENT_TEXT", "Custom pinned-style comment")
    from agent.config import get_youtube_config

    get_youtube_config.cache_clear()
    text = generate_new_video_comment(channel_name="Test Channel")
    assert text == "Custom pinned-style comment"
