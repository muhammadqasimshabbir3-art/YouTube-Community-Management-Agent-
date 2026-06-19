"""HTML dashboard report generator for YouTube video community analysis."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from agent.async_utils import run_in_thread
from agent.custom_tools.report_io import prepare_report_output_path

REPORTS_DIR = Path("./reports")


def _escape(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def _bar_row(label: str, count: int, total: int, color: str) -> str:
    pct = _pct(count, total)
    return f"""
    <div class="bar-row">
      <div class="bar-label"><span>{_escape(label)}</span><span>{count} ({pct}%)</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>
    </div>"""


def _generate_llm_executive_summary(state: dict[str, Any]) -> str:
    """Generate an LLM narrative summary of the video and community health."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _fallback_executive_summary(state)

    video = state.get("video_metadata") or state.get("latest_video") or {}
    stats = {
        "total_comments": len(state.get("comments") or []),
        "positive": len(state.get("positive_comments") or []),
        "negative": len(state.get("negative_comments") or []),
        "questions": len(state.get("question_comments") or []),
        "unanswered": len(state.get("unanswered_comments") or []),
        "replies_generated": len(state.get("generated_replies") or []),
    }
    prompt = (
        f"Write a concise executive summary (3-5 paragraphs) for a YouTube community management "
        f"dashboard report.\n\n"
        f"Channel: {state.get('youtube_channel_name', 'Unknown')}\n"
        f"Video: {video.get('title', 'N/A')}\n"
        f"Views: {video.get('views', 'N/A')}\n"
        f"Likes: {video.get('likes', 'N/A')}\n"
        f"Published: {video.get('published', 'N/A')}\n"
        f"Description excerpt: {(video.get('description') or '')[:400]}\n"
        f"Comment stats: {json.dumps(stats)}\n\n"
        "Cover: audience sentiment, engagement quality, risks, opportunities, and recommended "
        "creator actions. Use plain professional language."
    )
    try:
        model = ChatGroq(model="llama-3.1-8b-instant", temperature=0.2, api_key=api_key)
        response = model.invoke(
            [
                SystemMessage(
                    content="You write YouTube analytics executive summaries."
                ),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content).strip()
    except Exception:
        return _fallback_executive_summary(state)


def _fallback_executive_summary(state: dict[str, Any]) -> str:
    """Heuristic summary when LLM is unavailable."""
    channel = state.get("youtube_channel_name", "the channel")
    video = (state.get("video_metadata") or state.get("latest_video") or {}).get(
        "title", "latest video"
    )
    total = len(state.get("comments") or [])
    unanswered = len(state.get("unanswered_comments") or [])
    positive = len(state.get("positive_comments") or [])
    negative = len(state.get("negative_comments") or [])
    return (
        f'This report covers community engagement on {channel}\'s video "{video}". '
        f"{total} comments were analyzed. Sentiment is "
        f"{'predominantly positive' if positive > negative else 'mixed' if negative else 'neutral'}. "
        f"{unanswered} comments remain unanswered and represent immediate engagement opportunities."
    )


def _reply_history_rows(records: list[dict]) -> str:
    if not records:
        return "<tr><td colspan='6'>No reply history recorded</td></tr>"
    rows = []
    for record in records:
        rows.append(
            f"<tr>"
            f"<td>{_escape(record.get('recorded_at', ''))}</td>"
            f"<td>{_escape(record.get('comment_author', ''))}</td>"
            f"<td>{_escape(record.get('comment_category', ''))}</td>"
            f"<td class='comment-text'>{_escape(record.get('comment_text', ''))}</td>"
            f"<td class='reply'>{_escape(record.get('reply_text', ''))}</td>"
            f"<td>{_escape(record.get('status', ''))}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _failed_reply_rows(failed_replies: list[dict]) -> str:
    if not failed_replies:
        return "<tr><td colspan='4'>No failed reply attempts</td></tr>"
    rows = []
    for reply in failed_replies:
        rows.append(
            f"<tr>"
            f"<td>{_escape(reply.get('author', ''))}</td>"
            f"<td class='comment-text'>{_escape(reply.get('text', ''))}</td>"
            f"<td class='reply'>{_escape(reply.get('reply_text', ''))}</td>"
            f"<td class='error'>{_escape(reply.get('post_error', 'Unknown error'))}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _new_comment_rows(new_comments: list[dict]) -> str:
    if not new_comments:
        return "<tr><td colspan='3'>No new video comment generated</td></tr>"
    rows = []
    for item in new_comments:
        status = "Posted" if item.get("posted") else "Not posted"
        if item.get("post_error"):
            status = f"Failed: {item.get('post_error')}"
        rows.append(
            f"<tr>"
            f"<td class='comment-text'>{_escape(item.get('comment_text', ''))}</td>"
            f"<td>{_escape(status)}</td>"
            f"<td class='error'>{_escape(item.get('post_error', ''))}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _category_section(title: str, comments: list[dict], color: str) -> str:
    if not comments:
        return f"<div class='card' style='margin-bottom:16px'><h2>{_escape(title)} (0)</h2><p class='summary'>None</p></div>"
    return f"""
    <div class="card" style="margin-bottom:16px;border-left:4px solid {color}">
      <h2>{_escape(title)} ({len(comments)})</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Author</th><th>Priority</th><th>Sentiment</th><th>Likes</th><th>Time</th><th>Comment</th>
          </tr></thead>
          <tbody>{_comment_rows(comments)}</tbody>
        </table>
      </div>
    </div>"""


def _reply_target_rows(targets: list[dict]) -> str:
    if not targets:
        return "<tr><td colspan='5'>No positive reply targets selected</td></tr>"
    rows = []
    for comment in targets:
        rows.append(
            f"<tr>"
            f"<td>{comment.get('reply_rank', '')}</td>"
            f"<td>{_escape(comment.get('author', ''))}</td>"
            f"<td>{comment.get('likes', 0)}</td>"
            f"<td>{comment.get('sentiment_score', '')}</td>"
            f"<td class='comment-text'>{_escape(comment.get('text', ''))}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _comment_rows(comments: list[dict], include_reply: bool = False) -> str:
    if not comments:
        return "<tr><td colspan='7'>No data</td></tr>"
    rows = []
    for comment in comments:
        reply_cell = (
            f"<td class='reply'>{_escape(comment.get('reply_text', ''))}</td>"
            if include_reply
            else ""
        )
        rows.append(
            f"<tr>"
            f"<td>{_escape(comment.get('author', ''))}</td>"
            f"<td>{_escape(comment.get('category', comment.get('sentiment', '')))}</td>"
            f"<td>{_escape(comment.get('engagement_priority', ''))}</td>"
            f"<td>{comment.get('sentiment_score', '')}</td>"
            f"<td>{comment.get('likes', 0)}</td>"
            f"<td>{_escape(comment.get('timestamp', ''))}</td>"
            f"<td class='comment-text'>{_escape(comment.get('text', ''))}</td>"
            f"{reply_cell}"
            f"</tr>"
        )
    return "\n".join(rows)


def generate_html_dashboard_report_sync(
    state: dict[str, Any],
    output_path: str | None = None,
) -> str:
    """Build a comprehensive dashboard-style HTML report from workflow state."""
    channel = state.get("youtube_channel_name") or "YouTube Channel"
    slug = re.sub(r"[^a-z0-9]+", "_", channel.lower()).strip("_") or "channel"
    output_path = str(
        prepare_report_output_path(
            output_path or REPORTS_DIR / f"{slug}_dashboard_report.html"
        )
    )

    video = dict(state.get("video_metadata") or state.get("latest_video") or {})
    analyzed = state.get("analyzed_comments") or state.get("comments") or []
    generated = state.get("generated_replies") or []
    reply_targets = list(state.get("reply_targets") or [])
    if not reply_targets and analyzed:
        from agent.config import get_youtube_config
        from agent.custom_tools.comment_selection import select_top_positive_comments

        cfg = get_youtube_config()
        limit = cfg["max_replies_per_video"] if cfg["max_replies_per_video"] > 0 else 5
        reply_targets = select_top_positive_comments(
            analyzed,
            limit=limit,
            channel_name=state.get("youtube_channel_name", ""),
        )
    if not reply_targets:
        reply_targets = generated
    failed_replies = state.get("failed_replies") or [
        reply
        for reply in generated
        if not reply.get("posted") and reply.get("post_error")
    ]
    new_comments = state.get("generated_new_comments") or []
    recommendations = state.get("recommendations") or []
    reply_history = state.get("reply_history") or []
    if not reply_history:
        from agent.custom_tools.reply_history import get_reply_history

        reply_history = get_reply_history(
            channel_name=state.get("youtube_channel_name", ""),
            video_id=video.get("video_id", ""),
        )

    total = len(analyzed)
    stats = {
        "positive": len(state.get("positive_comments") or []),
        "negative": len(state.get("negative_comments") or []),
        "neutral": len(state.get("neutral_comments") or []),
        "questions": len(state.get("question_comments") or []),
        "suggestions": len(state.get("suggestion_comments") or []),
        "spam": len(state.get("spam_comments") or []),
        "unanswered": len(state.get("unanswered_comments") or []),
    }
    reply_stats = state.get("reply_statistics") or {}
    executive_summary = state.get("llm_summary") or _generate_llm_executive_summary(
        state
    )

    if not recommendations:
        from agent.workflow_executor import _build_recommendations

        recommendations = _build_recommendations(state)

    avg_sentiment = (
        round(sum(c.get("sentiment_score", 0) for c in analyzed) / total, 2)
        if total
        else 0
    )
    high_priority = [c for c in analyzed if c.get("engagement_priority") == "high"]

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    thumbnail = video.get("thumbnail_url", "")
    thumb_block = (
        f'<img class="thumb" src="{_escape(thumbnail)}" alt="Video thumbnail" />'
        if thumbnail
        else '<div class="thumb placeholder">No thumbnail</div>'
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>YouTube Community Dashboard — {_escape(channel)}</title>
  <style>
    :root {{
      --bg: #0f0f0f; --card: #1a1a1a; --text: #f1f1f1; --muted: #aaaaaa;
      --accent: #ff0000; --accent2: #cc0000; --border: #303030;
      --green: #2ecc71; --yellow: #f1c40f; --red: #e74c3c; --blue: #3498db; --purple: #9b59b6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: 'Segoe UI', Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    .header {{ background: linear-gradient(135deg, #1a1a1a 0%, #2d0a0a 100%); border: 1px solid var(--border);
      border-radius: 16px; padding: 28px; margin-bottom: 24px; }}
    .header h1 {{ margin: 0 0 8px; font-size: 1.8rem; }}
    .header .sub {{ color: var(--muted); }}
    .grid {{ display: grid; gap: 16px; }}
    .grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px; }}
    .card h2 {{ margin: 0 0 14px; font-size: 1.1rem; color: #fff; border-bottom: 2px solid var(--accent); padding-bottom: 8px; }}
    .metric {{ text-align: center; }}
    .metric .val {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
    .metric .lbl {{ color: var(--muted); font-size: 0.85rem; margin-top: 4px; }}
    .video-hero {{ display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }}
    .thumb {{ width: 100%; border-radius: 10px; aspect-ratio: 16/9; object-fit: cover; background: #222; }}
    .thumb.placeholder {{ display:flex; align-items:center; justify-content:center; min-height:120px; color:var(--muted); }}
    .meta dt {{ color: var(--muted); font-size: 0.8rem; margin-top: 10px; }}
    .meta dd {{ margin: 4px 0 0; font-weight: 600; }}
    .desc {{ color: #ccc; line-height: 1.5; white-space: pre-wrap; max-height: 160px; overflow: auto; }}
    .bar-row {{ margin-bottom: 12px; }}
    .bar-label {{ display:flex; justify-content:space-between; font-size:0.85rem; margin-bottom:4px; }}
    .bar-track {{ height: 10px; background: #2a2a2a; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 999px; }}
    .summary {{ line-height: 1.7; color: #ddd; white-space: pre-wrap; }}
    ul.recs {{ margin: 0; padding-left: 20px; line-height: 1.8; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--card); }}
    .comment-text {{ max-width: 320px; }}
    .reply {{ max-width: 260px; color: #9fe870; }}
    .error {{ max-width: 260px; color: var(--red); }}
    .table-wrap {{ max-height: 420px; overflow: auto; border: 1px solid var(--border); border-radius: 10px; }}
    .footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 28px; }}
    a {{ color: #3ea6ff; }}
    @media (max-width: 700px) {{ .video-hero {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <h1>YouTube Community Dashboard</h1>
      <div class="sub">{_escape(channel)} · Generated {_escape(generated_at)}</div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Video Overview</h2>
      <div class="video-hero">
        {thumb_block}
        <dl class="meta">
          <dt>Title</dt><dd>{_escape(video.get("title", "N/A"))}</dd>
          <dt>Video URL</dt><dd><a href="{_escape(video.get("url", ""))}">{_escape(video.get("url", ""))}</a></dd>
          <dt>Video ID</dt><dd>{_escape(video.get("video_id", ""))}</dd>
          <dt>Views</dt><dd>{_escape(video.get("views", "N/A"))}</dd>
          <dt>Likes</dt><dd>{_escape(video.get("likes", "N/A"))}</dd>
          <dt>Dislikes</dt><dd>{_escape(video.get("dislikes", "N/A"))}</dd>
          <dt>Duration</dt><dd>{_escape(video.get("duration", "N/A"))}</dd>
          <dt>Category</dt><dd>{_escape(video.get("category", "N/A"))}</dd>
          <dt>Subscribers</dt><dd>{_escape(video.get("subscribers", "N/A"))}</dd>
          <dt>Comments (on video)</dt><dd>{_escape(video.get("comment_count", "N/A"))}</dd>
          <dt>Published</dt><dd>{_escape(video.get("published", "N/A"))}</dd>
          <dt>Channel URL</dt><dd><a href="{_escape(state.get("youtube_channel_url", ""))}">{_escape(state.get("youtube_channel_url", ""))}</a></dd>
        </dl>
      </div>
      <dt style="color:var(--muted);font-size:0.8rem;margin-top:16px">What this video is about</dt>
      <div class="summary">{_escape(video.get("video_about", "Summary not available."))}</div>
      <dt style="color:var(--muted);font-size:0.8rem;margin-top:16px">Full description</dt>
      <div class="desc">{_escape(video.get("description", video.get("og_description", "No description available.")))}</div>
    </div>

    <div class="grid grid-4" style="margin-bottom:24px">
      <div class="card metric"><div class="val">{total}</div><div class="lbl">Comments Analyzed</div></div>
      <div class="card metric"><div class="val">{video.get("comment_count_value", video.get("comments_scraped_count", total))}</div><div class="lbl">Reported on Video</div></div>
      <div class="card metric"><div class="val">{len(reply_targets)}</div><div class="lbl">Top Positive Targets</div></div>
      <div class="card metric"><div class="val">{reply_stats.get("replies_generated", len(generated))}</div><div class="lbl">Replies Generated</div></div>
      <div class="card metric"><div class="val">{reply_stats.get("replies_posted", 0)}</div><div class="lbl">Replies Posted</div></div>
      <div class="card metric"><div class="val">{reply_stats.get("replies_failed", len(failed_replies))}</div><div class="lbl">Replies Failed</div></div>
      <div class="card metric"><div class="val">{reply_stats.get("new_comments_posted", 0)}</div><div class="lbl">New Comments Posted</div></div>
      <div class="card metric"><div class="val">{avg_sentiment}</div><div class="lbl">Avg Sentiment Score</div></div>
      <div class="card metric"><div class="val">{len(high_priority)}</div><div class="lbl">High Priority</div></div>
      <div class="card metric"><div class="val">{_pct(stats["positive"], total)}%</div><div class="lbl">Positive</div></div>
      <div class="card metric"><div class="val">{_pct(stats["negative"], total)}%</div><div class="lbl">Negative</div></div>
    </div>

    <div class="grid grid-2" style="margin-bottom:24px">
      <div class="card">
        <h2>Comment Categories</h2>
        {_bar_row("Positive", stats["positive"], total, "var(--green)")}
        {_bar_row("Negative", stats["negative"], total, "var(--red)")}
        {_bar_row("Neutral", stats["neutral"], total, "#95a5a6")}
        {_bar_row("Questions", stats["questions"], total, "var(--blue)")}
        {_bar_row("Suggestions", stats["suggestions"], total, "var(--purple)")}
        {_bar_row("Spam", stats["spam"], total, "#7f8c8d")}
      </div>
      <div class="card">
        <h2>Executive Summary (LLM)</h2>
        <div class="summary">{_escape(executive_summary)}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Recommended Actions</h2>
      <ul class="recs">{"".join(f"<li>{_escape(r)}</li>" for r in recommendations)}</ul>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Reply History — What We Replied To</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>When</th><th>Author</th><th>Category</th><th>Original Comment</th><th>Our Reply</th><th>Status</th>
          </tr></thead>
          <tbody>{_reply_history_rows(reply_history)}</tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Failed Reply Attempts ({len(failed_replies)})</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Author</th><th>Original Comment</th><th>Attempted Reply</th><th>Error</th>
          </tr></thead>
          <tbody>{_failed_reply_rows(failed_replies)}</tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>New Video Comment ({len(new_comments)})</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Comment Text</th><th>Status</th><th>Error</th>
          </tr></thead>
          <tbody>{_new_comment_rows(new_comments)}</tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Comments by Category</h2>
      {_category_section("Positive Comments", state.get("positive_comments") or [], "var(--green)")}
      {_category_section("Negative Comments", state.get("negative_comments") or [], "var(--red)")}
      {_category_section("Neutral Comments", state.get("neutral_comments") or [], "#95a5a6")}
      {_category_section("Questions", state.get("question_comments") or [], "var(--blue)")}
      {_category_section("Suggestions", state.get("suggestion_comments") or [], "var(--purple)")}
      {_category_section("Spam", state.get("spam_comments") or [], "#7f8c8d")}
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>All Analyzed Comments ({total})</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Author</th><th>Category</th><th>Priority</th><th>Sentiment</th>
            <th>Likes</th><th>Time</th><th>Comment</th>
          </tr></thead>
          <tbody>{_comment_rows(analyzed)}</tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Top Positive Reply Targets ({len(reply_targets)})</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Rank</th><th>Author</th><th>Likes</th><th>Sentiment</th><th>Comment</th>
          </tr></thead>
          <tbody>{_reply_target_rows(reply_targets)}</tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <h2>Generated AI Replies ({len(generated)})</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Author</th><th>Category</th><th>Priority</th><th>Sentiment</th>
            <th>Likes</th><th>Time</th><th>Original Comment</th><th>AI Reply</th>
          </tr></thead>
          <tbody>{_comment_rows(generated, include_reply=True)}</tbody>
        </table>
      </div>
    </div>

    <div class="footer">Generated by YouTube Community Manager Agent</div>
  </div>
</body>
</html>"""

    Path(output_path).write_text(html_doc, encoding="utf-8")
    size = Path(output_path).stat().st_size
    return f"HTML dashboard report generated: {output_path} ({size} bytes)"


@tool
async def generate_html_report(state_json: str = "") -> str:
    """Generate a comprehensive HTML dashboard report for YouTube video analysis.

    Pass workflow state as a JSON string, or leave empty to use latest ./reports data.
    """
    state: dict[str, Any] = {}
    if state_json.strip():
        state = json.loads(state_json)
    return await run_in_thread(generate_html_dashboard_report_sync, state)


__all__ = ["generate_html_dashboard_report_sync", "generate_html_report"]
