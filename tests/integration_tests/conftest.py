"""Fixtures for integration tests — avoid real browser/YouTube calls."""

from __future__ import annotations

import pytest


def _mock_analyze_comments(comments, channel_name=""):
    analyzed = []
    for comment in comments:
        analyzed.append(
            {
                **comment,
                "category": "positive",
                "sentiment_score": 0.8,
                "engagement_priority": "medium",
            }
        )
    return {
        "analyzed_comments": analyzed,
        "positive_comments": analyzed,
        "negative_comments": [],
        "neutral_comments": [],
        "question_comments": [],
        "suggestion_comments": [],
        "spam_comments": [],
        "unanswered_comments": analyzed,
    }


def _mock_generate_replies(unanswered, channel_name=""):
    return {
        "generated_replies": [],
        "reply_statistics": {
            "replies_generated": 0,
            "replies_skipped": len(unanswered),
            "posting_enabled": False,
            "filters": {},
        },
    }


@pytest.fixture(autouse=True)
def mock_playwright_and_youtube(monkeypatch):
    """Stub Playwright and YouTube fetch so integration tests do not need browsers."""
    monkeypatch.setattr(
        "agent.custom_tools.browser_tools.ensure_youtube_session",
        lambda *args, **kwargs: (None, None, None, None, True),
    )
    monkeypatch.setattr(
        "agent.custom_tools.browser_tools.close_browser_session",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "agent.workflow_executor.fetch_channel_data",
        lambda channel_url="", channel_name="": {
            "success": True,
            "youtube_channel_name": channel_name or "Test Channel",
            "youtube_channel_url": channel_url or "https://www.youtube.com/@test",
            "youtube_channel_id": "test",
            "latest_video": {
                "video_id": "test123",
                "title": "Latest Test Video",
                "url": "https://www.youtube.com/watch?v=test123",
            },
            "video_metadata": {
                "video_id": "test123",
                "title": "Latest Test Video",
                "url": "https://www.youtube.com/watch?v=test123",
                "views": "1,000 views",
                "likes": "100 likes",
                "dislikes": "5 dislikes",
                "published": "1 day ago",
                "description": "Test description",
                "video_about": "This video covers the latest community reactions.",
            },
            "comments": [
                {
                    "author": "Viewer",
                    "text": "Great video!",
                    "likes": 3,
                    "timestamp": "1 hour ago",
                    "replied": False,
                    "video_id": "test123",
                    "video_title": "Latest Test Video",
                    "video_url": "https://www.youtube.com/watch?v=test123",
                    "comment_id": "test123_0",
                }
            ],
            "videos_scanned": 1,
        },
    )
    monkeypatch.setattr(
        "agent.workflow_executor.post_replies_to_comments",
        lambda replies: {"posted": 0, "failed": 0, "replies": replies},
    )
    monkeypatch.setattr(
        "agent.workflow_executor.analyze_comments",
        _mock_analyze_comments,
    )
    monkeypatch.setattr(
        "agent.workflow_executor.generate_replies",
        _mock_generate_replies,
    )
    monkeypatch.setattr(
        "agent.custom_tools.html_report_generator._generate_llm_executive_summary",
        lambda state: "Test executive summary.",
    )
