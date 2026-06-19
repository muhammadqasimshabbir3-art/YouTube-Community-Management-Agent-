"""Unit tests for comment reply target selection."""

from agent.custom_tools.comment_selection import select_top_positive_comments


def _comment(
    author: str,
    likes: int,
    *,
    category: str = "positive",
    replied: bool = False,
    sentiment: float = 0.8,
) -> dict:
    return {
        "author": author,
        "text": f"Comment from {author}",
        "likes": likes,
        "category": category,
        "sentiment_score": sentiment,
        "engagement_priority": "medium",
        "replied": replied,
    }


def test_select_top_positive_comments_allows_fewer_than_limit():
    analyzed = [_comment("@viewer1", 3), _comment("@viewer2", 1)]
    selected = select_top_positive_comments(analyzed, limit=5)
    assert len(selected) == 2
    assert selected[0]["author"] == "@viewer1"


def test_select_top_positive_comments_limits_and_ranks():
    analyzed = [
        _comment("@viewer1", 2),
        _comment("@viewer2", 50),
        _comment("@viewer3", 10),
        _comment("@viewer4", 25),
        _comment("@viewer5", 5),
        _comment("@viewer6", 100),
        _comment("@negative", 200, category="negative"),
    ]
    selected = select_top_positive_comments(analyzed, limit=5)
    assert len(selected) == 5
    assert [item["reply_rank"] for item in selected] == [1, 2, 3, 4, 5]
    assert selected[0]["author"] == "@viewer6"
    assert selected[1]["author"] == "@viewer2"
    assert all(item.get("selected_for_reply") for item in selected)


def test_select_top_positive_comments_skips_channel_replied_threads():
    analyzed = [
        {**_comment("@viewer1", 10), "channel_replied": True},
        _comment("@viewer2", 40),
    ]
    selected = select_top_positive_comments(analyzed, limit=5)
    assert len(selected) == 1
    assert selected[0]["author"] == "@viewer2"


def test_select_top_positive_comments_not_blocked_by_legacy_replied_flag():
    """replied used to mirror channel_replied and wrongly excluded all comments."""
    analyzed = [
        {**_comment("@viewer1", 50), "replied": True, "channel_replied": False},
        _comment("@viewer2", 40),
    ]
    selected = select_top_positive_comments(analyzed, limit=5)
    assert len(selected) == 2


def test_select_top_positive_comments_skips_agent_replied_and_channel_author():
    analyzed = [
        {**_comment("@viewer1", 99), "agent_replied": True},
        _comment("KayRatedReacts", 80),
        _comment("@viewer2", 40),
    ]
    selected = select_top_positive_comments(
        analyzed,
        limit=5,
        channel_name="KayRatedReacts",
    )
    assert len(selected) == 1
    assert selected[0]["author"] == "@viewer2"
