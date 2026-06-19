"""LLM-powered YouTube comment analysis and classification."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

CATEGORIES = ("positive", "negative", "neutral", "question", "suggestion", "spam")


def _get_model() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    return ChatGroq(model="llama-3.1-8b-instant", temperature=0, api_key=api_key)


def _heuristic_analysis(comment: dict[str, Any]) -> dict[str, Any]:
    """Fallback classification when LLM parsing fails."""
    text = (comment.get("text") or "").lower()
    category = "neutral"
    sentiment = 0.0

    if "?" in text or text.startswith(
        ("how", "what", "why", "when", "where", "can you")
    ):
        category = "question"
        sentiment = 0.1
    elif any(
        word in text
        for word in ("love", "great", "awesome", "thanks", "amazing", "best")
    ):
        category = "positive"
        sentiment = 0.8
    elif any(
        word in text
        for word in ("hate", "bad", "worst", "terrible", "awful", "dislike")
    ):
        category = "negative"
        sentiment = -0.7
    elif any(
        word in text for word in ("should", "could", "suggest", "idea", "please add")
    ):
        category = "suggestion"
        sentiment = 0.3
    elif any(
        word in text
        for word in ("subscribe", "click here", "free money", "crypto scam")
    ):
        category = "spam"
        sentiment = -0.5

    priority = _engagement_priority(category, sentiment, comment.get("likes", 0))
    return {
        **comment,
        "category": category,
        "sentiment_score": sentiment,
        "engagement_priority": priority,
    }


def _engagement_priority(category: str, sentiment: float, likes: int) -> str:
    """Compute engagement priority from category, sentiment, and likes."""
    score = likes
    if category == "question":
        score += 10
    elif category == "negative":
        score += 8
    elif category == "suggestion":
        score += 6
    elif category == "positive":
        score += 4
    elif category == "spam":
        score -= 20
    score += int(abs(sentiment) * 5)

    if score >= 15:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    """Extract JSON object from LLM response text."""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def analyze_single_comment(
    comment: dict[str, Any], channel_name: str = ""
) -> dict[str, Any]:
    """Analyze one comment with the LLM."""
    try:
        model = _get_model()
    except ValueError:
        return _heuristic_analysis(comment)

    prompt = (
        f"Analyze this YouTube comment on channel '{channel_name}':\n"
        f"Author: {comment.get('author', 'Unknown')}\n"
        f"Text: {comment.get('text', '')}\n"
        f"Likes: {comment.get('likes', 0)}\n\n"
        "Return ONLY valid JSON with keys: category, sentiment_score, engagement_priority.\n"
        "category must be one of: positive, negative, neutral, question, suggestion, spam.\n"
        "sentiment_score is a float from -1.0 to 1.0.\n"
        "engagement_priority is one of: high, medium, low."
    )
    try:
        response = model.invoke(
            [
                SystemMessage(
                    content="You classify YouTube comments. Respond with JSON only."
                ),
                HumanMessage(content=prompt),
            ]
        )
        parsed = _parse_llm_json(str(response.content))
        if parsed and parsed.get("category") in CATEGORIES:
            return {
                **comment,
                "category": parsed["category"],
                "sentiment_score": float(parsed.get("sentiment_score", 0)),
                "engagement_priority": parsed.get("engagement_priority", "medium"),
            }
    except Exception:
        pass
    return _heuristic_analysis(comment)


def analyze_comments(
    comments: list[dict[str, Any]],
    channel_name: str = "",
) -> dict[str, Any]:
    """Analyze all comments and bucket by category."""
    analyzed: list[dict[str, Any]] = []
    buckets: dict[str, list[dict[str, Any]]] = {cat: [] for cat in CATEGORIES}

    for comment in comments:
        result = analyze_single_comment(comment, channel_name)
        analyzed.append(result)
        buckets[result["category"]].append(result)

    unanswered = [c for c in analyzed if not c.get("replied")]

    return {
        "analyzed_comments": analyzed,
        "positive_comments": buckets["positive"],
        "negative_comments": buckets["negative"],
        "neutral_comments": buckets["neutral"],
        "question_comments": buckets["question"],
        "suggestion_comments": buckets["suggestion"],
        "spam_comments": buckets["spam"],
        "unanswered_comments": unanswered,
    }


__all__ = ["analyze_comments", "analyze_single_comment", "CATEGORIES"]
