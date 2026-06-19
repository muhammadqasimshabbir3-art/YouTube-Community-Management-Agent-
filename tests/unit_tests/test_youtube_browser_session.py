"""Tests for browser session reuse and comment composer helpers."""

from agent.custom_tools.youtube_tools import (
    _store_browser_session,
    _video_url_for_comment,
    release_browser_session,
)


def test_video_url_for_comment_adds_lc_param():
    url = _video_url_for_comment(
        "https://www.youtube.com/watch?v=abc123",
        {"youtube_comment_id": "UgzDE1abc"},
    )
    assert url == "https://www.youtube.com/watch?v=abc123&lc=UgzDE1abc"


def test_store_and_release_browser_session():
    release_browser_session()
    sentinel = object()
    _store_browser_session(sentinel, sentinel, sentinel, sentinel, video_url="https://youtube.com/watch?v=test")  # type: ignore[arg-type]
    from agent.custom_tools import youtube_tools

    assert youtube_tools._get_stored_page() is sentinel
    assert youtube_tools._BROWSER_SESSION.get("video_url") == "https://youtube.com/watch?v=test"
    release_browser_session()
    assert youtube_tools._get_stored_page() is None
