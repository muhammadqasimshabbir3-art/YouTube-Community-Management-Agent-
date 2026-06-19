"""Tests for comment analysis heuristics."""

from agent.custom_tools.comment_analyzer import analyze_single_comment


def test_heuristic_question_classification():
    comment = {"author": "User", "text": "How do you edit videos?", "likes": 2}
    result = analyze_single_comment(comment, channel_name="Test")
    assert result["category"] == "question"


def test_heuristic_positive_classification(monkeypatch):
    def fake_model():
        raise ValueError("no api")

    monkeypatch.setattr("agent.custom_tools.comment_analyzer._get_model", fake_model)
    comment = {
        "author": "Fan",
        "text": "Love this channel, amazing content!",
        "likes": 10,
    }
    result = analyze_single_comment(comment)
    assert result["category"] == "positive"
    assert result["sentiment_score"] > 0
