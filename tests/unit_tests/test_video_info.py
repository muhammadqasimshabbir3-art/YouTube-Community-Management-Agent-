"""Tests for latest-video description and summary helpers."""

from agent.custom_tools.video_info import (
    _heuristic_video_about,
    build_video_about_summary,
    merge_video_records,
)


def test_merge_video_records_keeps_base_and_adds_metadata():
    base = {
        "video_id": "abc",
        "title": "Base title",
        "url": "https://youtube.com/watch?v=abc",
    }
    metadata = {
        "title": "Scraped title",
        "description": "Full description",
        "views": "1K views",
    }
    merged = merge_video_records(base, metadata)
    assert merged["url"] == base["url"]
    assert merged["description"] == "Full description"
    assert merged["views"] == "1K views"


def test_heuristic_video_about_uses_description(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    summary = build_video_about_summary(
        {
            "title": "Reacting to the finale",
            "description": "We break down the ending scene by scene and discuss fan theories.",
            "category": "Entertainment",
        }
    )
    assert "Reacting to the finale" in summary
    assert "ending scene" in summary.lower() or "break down" in summary.lower()


def test_heuristic_video_about_without_description():
    summary = _heuristic_video_about({"title": "Silent vlog"})
    assert "Silent vlog" in summary
    assert "did not expose a description" in summary


def test_format_view_count_and_duration():
    from agent.custom_tools.video_info import format_duration_seconds, format_view_count

    assert format_view_count("41000") == "41K views"
    assert format_view_count("1200000") == "1.2M views"
    assert format_duration_seconds(12248) == "3:24:08"
