"""Tests for reply history persistence."""

from agent.custom_tools.reply_history import (
    build_reply_record,
    get_reply_history,
    record_reply_entries,
)


def test_record_and_load_reply_history(tmp_path, monkeypatch):
    history_file = tmp_path / "reply_history.json"
    monkeypatch.setattr(
        "agent.custom_tools.reply_history.HISTORY_PATH",
        history_file,
    )

    reply = {
        "comment_id": "vid_1",
        "video_id": "vid",
        "video_title": "Test Video",
        "video_url": "https://youtube.com/watch?v=vid",
        "author": "Fan",
        "text": "Love this!",
        "category": "positive",
        "reply_text": "Thank you!",
        "engagement_priority": "medium",
        "sentiment_score": 0.9,
    }

    records = record_reply_entries(
        [reply],
        channel_name="Test Channel",
        status="generated",
    )
    assert len(records) == 1
    assert records[0]["comment_author"] == "Fan"
    assert records[0]["status"] == "generated"

    loaded = get_reply_history(channel_name="Test Channel")
    assert len(loaded) == 1
    assert loaded[0]["reply_text"] == "Thank you!"


def test_build_reply_record():
    record = build_reply_record(
        {
            "author": "User",
            "text": "Question?",
            "category": "question",
            "reply_text": "Here is the answer.",
            "comment_id": "abc_0",
            "video_id": "abc",
        },
        channel_name="Channel",
        status="posted",
        posted=True,
    )
    assert record["posted"] is True
    assert record["status"] == "posted"
