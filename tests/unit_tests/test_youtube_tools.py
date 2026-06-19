"""Unit tests for YouTube scraping helpers."""

from agent.custom_tools.youtube_tools import (
    _channel_videos_url,
    _is_watch_video_href,
    _normalize_js_comment,
    _parse_comment_count,
    _resolve_scrape_target,
    _video_url_for_comment,
)


def test_channel_videos_url_appends_videos_tab():
    assert (
        _channel_videos_url("https://www.youtube.com/@KayRatedReacts")
        == "https://www.youtube.com/@KayRatedReacts/videos"
    )


def test_channel_videos_url_keeps_existing_tab():
    url = "https://www.youtube.com/@KayRatedReacts/videos"
    assert _channel_videos_url(url) == url


def test_is_watch_video_href_filters_shorts():
    assert _is_watch_video_href("/watch?v=abc123")
    assert not _is_watch_video_href("/shorts/abc123")
    assert not _is_watch_video_href("")


def test_parse_comment_count():
    assert _parse_comment_count("440 Comments") == 440
    assert _parse_comment_count("1,234 comments") == 1234
    assert _parse_comment_count("") == 0


def test_resolve_scrape_target():
    assert _resolve_scrape_target(23, 0) == 25
    assert _resolve_scrape_target(0, 0) == 500
    assert _resolve_scrape_target(100, 5) == 100
    assert _resolve_scrape_target(0, 20) == 20


def test_normalize_js_comment_uses_youtube_comment_id():
    video = {
        "video_id": "abc123",
        "title": "Test Video",
        "url": "https://www.youtube.com/watch?v=abc123",
    }
    normalized = _normalize_js_comment(
        {
            "author": "@viewer",
            "text": "Great video!",
            "timestamp": "1 day ago",
            "likes_raw": "12",
            "youtube_comment_id": "UgzDE1abc",
            "thread_index": 3,
            "channel_replied": False,
        },
        video,
    )
    assert normalized["comment_id"] == "UgzDE1abc"
    assert normalized["youtube_comment_id"] == "UgzDE1abc"
    assert normalized["thread_index"] == 3
    assert normalized["likes"] == 12
    assert normalized["replied"] is False


def test_video_url_for_comment_adds_lc_param():
    url = _video_url_for_comment(
        "https://www.youtube.com/watch?v=abc123",
        {"youtube_comment_id": "UgzDE1abc"},
    )
    assert url == "https://www.youtube.com/watch?v=abc123&lc=UgzDE1abc"
