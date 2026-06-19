"""Tests for HTML dashboard report generator."""

from agent.custom_tools.html_report_generator import generate_html_dashboard_report_sync


def test_generates_html_dashboard(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    output = tmp_path / "test_dashboard.html"
    state = {
        "youtube_channel_name": "Test Channel",
        "youtube_channel_url": "https://www.youtube.com/@test",
        "video_metadata": {
            "title": "Latest Video",
            "url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "views": "1.2M views",
            "likes": "50K likes",
            "published": "2 days ago",
            "description": "Test video description",
            "video_about": "A test video about community reactions.",
        },
        "analyzed_comments": [
            {
                "author": "Fan",
                "text": "Great video!",
                "category": "positive",
                "engagement_priority": "medium",
                "sentiment_score": 0.8,
                "likes": 5,
                "timestamp": "1 day ago",
            }
        ],
        "positive_comments": [
            {"author": "Fan", "text": "Great video!", "category": "positive"}
        ],
        "negative_comments": [],
        "neutral_comments": [],
        "question_comments": [],
        "suggestion_comments": [],
        "spam_comments": [],
        "unanswered_comments": [{"author": "Fan", "text": "Great video!"}],
        "generated_replies": [],
        "reply_statistics": {"replies_generated": 0, "replies_posted": 0},
    }

    result = generate_html_dashboard_report_sync(state, str(output))
    assert output.exists()
    assert "HTML dashboard report generated" in result
    content = output.read_text(encoding="utf-8")
    assert "Latest Video" in content
    assert "Test Channel" in content
    assert "Great video!" in content
    assert "Executive Summary" in content
    assert "What this video is about" in content
    assert "community reactions" in content


def test_html_report_replaces_existing_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    output = tmp_path / "test_dashboard.html"
    output.write_text("old report", encoding="utf-8")
    state = {
        "youtube_channel_name": "Test Channel",
        "video_metadata": {"title": "Latest Video", "video_id": "abc123"},
        "analyzed_comments": [],
        "positive_comments": [],
        "negative_comments": [],
        "neutral_comments": [],
        "question_comments": [],
        "suggestion_comments": [],
        "spam_comments": [],
        "unanswered_comments": [],
        "generated_replies": [],
        "reply_statistics": {},
    }

    generate_html_dashboard_report_sync(state, str(output))
    content = output.read_text(encoding="utf-8")
    assert "old report" not in content
    assert "YouTube Community Dashboard" in content
