"""Execute YouTube community management workflow steps."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from agent.config import apply_runtime_overrides, get_youtube_config
from agent.custom_tools.comment_analyzer import analyze_comments
from agent.custom_tools.comment_selection import select_top_positive_comments
from agent.custom_tools.email_tools import send_smtp_email
from agent.custom_tools.html_report_generator import (
    _generate_llm_executive_summary,
    generate_html_dashboard_report_sync,
)
from agent.custom_tools.new_comment_generator import (
    build_generated_new_comments,
    generate_new_video_comment,
)
from agent.custom_tools.pdf_generator import _generate_youtube_report_pdf_sync
from agent.custom_tools.reply_generator import generate_replies
from agent.custom_tools.reply_history import record_reply_entries
from agent.custom_tools.youtube_tools import (
    fetch_channel_data,
    post_new_video_comments,
    post_replies_to_comments,
    release_browser_session,
)
from agent.routing import build_analysis_summary
from agent.task_planner import TaskPlan

REPORTS_DIR = Path("./reports")


def _build_recommendations(state: dict[str, Any]) -> list[str]:
    """Generate recommended creator actions from analysis."""
    recommendations: list[str] = []
    unanswered = len(state.get("unanswered_comments") or [])
    questions = len(state.get("question_comments") or [])
    negative = len(state.get("negative_comments") or [])

    if unanswered > 0:
        recommendations.append(
            f"Respond to {unanswered} unanswered comments to boost engagement."
        )
    positive_count = len(state.get("positive_comments") or [])
    config = get_youtube_config()
    if positive_count:
        recommendations.append(
            f"Reply workflow targets up to {config['max_replies_per_video']} top positive "
            f"comments ({positive_count} positive found after full analysis)."
        )
    if questions > 0:
        recommendations.append(
            f"Prioritize {questions} question comments — viewers expect answers."
        )
    if negative > 0:
        recommendations.append(
            f"Address {negative} negative comments professionally to protect community sentiment."
        )
    high_priority = [
        c
        for c in (state.get("analyzed_comments") or [])
        if c.get("engagement_priority") == "high" and not c.get("replied")
    ]
    if high_priority:
        recommendations.append(
            f"Focus on {len(high_priority)} high-priority engagement opportunities first."
        )
    if not recommendations:
        recommendations.append(
            "Community engagement looks healthy. Keep monitoring new comments."
        )
    return recommendations


def _build_pdf_stats(state: dict[str, Any]) -> dict[str, int]:
    """Aggregate stats for PDF report."""
    stats = state.get("reply_statistics") or {}
    return {
        "total": len(state.get("comments") or []),
        "positive": len(state.get("positive_comments") or []),
        "negative": len(state.get("negative_comments") or []),
        "neutral": len(state.get("neutral_comments") or []),
        "questions": len(state.get("question_comments") or []),
        "suggestions": len(state.get("suggestion_comments") or []),
        "spam": len(state.get("spam_comments") or []),
        "unanswered": len(state.get("unanswered_comments") or []),
        "replies_generated": stats.get(
            "replies_generated", len(state.get("generated_replies") or [])
        ),
        "replies_posted": stats.get("replies_posted", 0),
        "replies_failed": stats.get(
            "replies_failed", len(state.get("failed_replies") or [])
        ),
        "new_comments_generated": len(state.get("generated_new_comments") or []),
        "new_comments_posted": stats.get("new_comments_posted", 0),
        "new_comments_failed": stats.get("new_comments_failed", 0),
    }


def execute_youtube_login(state: dict[str, Any]) -> dict[str, Any]:
    """Verify YouTube session via Playwright (login before scrape)."""
    from agent.custom_tools.browser_tools import (
        close_browser_session,
        ensure_youtube_session,
    )

    playwright = browser = context = page = None
    try:
        playwright, browser, context, page, logged_in = ensure_youtube_session()
        config = get_youtube_config()
        session_exists = Path(config["session_path"]).exists()
        if logged_in and session_exists:
            detail = "Signed in via saved session — no new login required"
        elif logged_in:
            detail = "Signed in — YouTube session active"
        else:
            detail = "Could not verify YouTube login"
        return {
            "logged_in": logged_in,
            "youtube_login_detail": detail,
        }
    finally:
        close_browser_session(playwright, browser, context)


def execute_fetch_channel_data(state: dict[str, Any]) -> dict[str, Any]:
    """Fetch comments from the target channel's latest video."""
    result = fetch_channel_data(
        channel_url=state.get("youtube_channel_url", ""),
        channel_name=state.get("youtube_channel_name", ""),
    )
    if not result.get("success"):
        return {"error": result.get("error", "Failed to fetch channel data")}
    return {
        "logged_in": True,
        "youtube_login_detail": "Signed in — browser session active on target video",
        "youtube_channel_name": result.get("youtube_channel_name", ""),
        "youtube_channel_url": result.get("youtube_channel_url", ""),
        "youtube_channel_id": result.get("youtube_channel_id", ""),
        "latest_video": result.get("latest_video"),
        "video_metadata": result.get("video_metadata"),
        "comments": result.get("comments", []),
    }


def execute_analyze_comments(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze collected comments with LLM classification."""
    comments = state.get("comments") or []
    channel_name = state.get("youtube_channel_name", "")
    return analyze_comments(comments, channel_name)


def execute_select_reply_targets(state: dict[str, Any]) -> dict[str, Any]:
    """Pick up to N top positive comments to reply to after full analysis."""
    apply_runtime_overrides(state)
    config = get_youtube_config()
    analyzed = list(state.get("analyzed_comments") or [])
    if not analyzed:
        analyzed = list(state.get("positive_comments") or [])
    channel_name = state.get("youtube_channel_name", "")
    positive_total = len(state.get("positive_comments") or [])
    limit = state.get("max_replies_per_video")
    if limit is None or int(limit) <= 0:
        limit = config["max_replies_per_video"]
    if int(limit) <= 0:
        limit = 5
    else:
        limit = int(limit)
    reply_targets = select_top_positive_comments(
        analyzed,
        limit=limit,
        channel_name=channel_name,
    )
    return {
        "reply_targets": reply_targets,
        "reply_statistics": {
            **(state.get("reply_statistics") or {}),
            "positive_comments_total": positive_total,
            "reply_targets_selected": len(reply_targets),
            "reply_target_limit": limit,
        },
    }


def execute_generate_replies(state: dict[str, Any]) -> dict[str, Any]:
    """Generate humorous AI replies for pre-selected top positive comments."""
    config = get_youtube_config()
    channel_name = state.get("youtube_channel_name", "")
    reply_targets = list(state.get("reply_targets") or [])
    if not reply_targets:
        analyzed = state.get("analyzed_comments") or []
        limit = config["max_replies_per_video"] if config["max_replies_per_video"] > 0 else 5
        reply_targets = select_top_positive_comments(
            analyzed,
            limit=limit,
            channel_name=channel_name,
        )
    result = generate_replies(
        reply_targets,
        channel_name,
        state.get("reply_statistics"),
    )
    generated = result.get("generated_replies") or []
    history = record_reply_entries(
        generated,
        channel_name=channel_name,
        video_metadata=state.get("video_metadata"),
        status="generated",
    )
    return {**result, "reply_history": history, "reply_targets": reply_targets}


def execute_post_replies(state: dict[str, Any]) -> dict[str, Any]:
    """Post generated replies when enabled in .env."""
    apply_runtime_overrides(state)
    config = get_youtube_config()
    replies = list(state.get("generated_replies") or [])
    enable_replies = (
        state.get("enable_comment_replies")
        if state.get("enable_comment_replies") is not None
        else config["enable_comment_replies"]
    )
    if not enable_replies or not replies:
        stats = dict(state.get("reply_statistics") or {})
        stats["replies_posted"] = 0
        return {"reply_statistics": stats}

    result = post_replies_to_comments(replies, enabled=bool(enable_replies))
    stats = dict(state.get("reply_statistics") or {})
    stats["replies_posted"] = result.get("posted", 0)
    stats["replies_failed"] = result.get("failed", 0)
    updated_replies = result.get("replies", replies)
    failed_replies = result.get("failed_replies") or [
        reply for reply in updated_replies if not reply.get("posted")
    ]
    history = record_reply_entries(
        updated_replies,
        channel_name=state.get("youtube_channel_name", ""),
        video_metadata=state.get("video_metadata"),
        status="posted",
    )
    return {
        "generated_replies": updated_replies,
        "failed_replies": failed_replies,
        "reply_statistics": stats,
        "reply_history": history,
    }


def execute_generate_new_comment(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a top-level community comment for the latest video."""
    apply_runtime_overrides(state)
    config = get_youtube_config()
    stats = dict(state.get("reply_statistics") or {})
    enabled = (
        state.get("enable_new_comments")
        if state.get("enable_new_comments") is not None
        else config["enable_new_comments"]
    )
    if not enabled:
        stats["new_comments_generated"] = 0
        return {
            "generated_new_comments": [],
            "reply_statistics": stats,
        }

    channel_name = state.get("youtube_channel_name", "")
    video = state.get("video_metadata") or state.get("latest_video") or {}
    summary = build_analysis_summary(state)
    comment_text = generate_new_video_comment(
        channel_name=channel_name,
        video_metadata=video,
        analysis_summary=summary,
    )
    generated = build_generated_new_comments(comment_text, video)
    stats["new_comments_generated"] = len(generated)
    return {
        "generated_new_comments": generated,
        "reply_statistics": stats,
    }


def execute_post_new_comment(state: dict[str, Any]) -> dict[str, Any]:
    """Post a generated top-level comment when ENABLE_NEW_COMMENTS=true."""
    apply_runtime_overrides(state)
    config = get_youtube_config()
    comments = list(state.get("generated_new_comments") or [])
    stats = dict(state.get("reply_statistics") or {})

    enabled = (
        state.get("enable_new_comments")
        if state.get("enable_new_comments") is not None
        else config["enable_new_comments"]
    )
    if not enabled or not comments:
        stats["new_comments_posted"] = 0
        stats["new_comments_failed"] = 0
        return {"reply_statistics": stats, "generated_new_comments": comments}

    result = post_new_video_comments(comments, enabled=bool(enabled))
    stats["new_comments_posted"] = result.get("posted", 0)
    stats["new_comments_failed"] = result.get("failed", 0)
    updated = result.get("new_comments", comments)
    if result.get("error"):
        for item in updated:
            if not item.get("posted"):
                item["post_error"] = result.get("error")
    return {
        "generated_new_comments": updated,
        "failed_new_comments": [item for item in updated if not item.get("posted")],
        "reply_statistics": stats,
    }


def execute_generate_pdf_report(state: dict[str, Any]) -> dict[str, Any]:
    """Generate PDF community management report."""
    channel_name = state.get("youtube_channel_name") or "YouTube Channel"
    slug = re.sub(r"[^a-z0-9]+", "_", channel_name.lower()).strip("_") or "channel"
    output_path = str(REPORTS_DIR / f"{slug}_community_report.pdf")

    analyzed = state.get("analyzed_comments") or []
    top_opportunities = sorted(
        [c for c in analyzed if not c.get("replied")],
        key=lambda c: {"high": 3, "medium": 2, "low": 1}.get(
            c.get("engagement_priority", "low"), 1
        ),
        reverse=True,
    )[:10]

    result = _generate_youtube_report_pdf_sync(
        channel_name=channel_name,
        analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        stats=_build_pdf_stats(state),
        top_opportunities=top_opportunities,
        generated_replies=state.get("generated_replies") or [],
        recommendations=_build_recommendations(state),
        output_path=output_path,
        video_metadata=state.get("video_metadata") or state.get("latest_video") or {},
        failed_replies=state.get("failed_replies") or [],
        new_comments=state.get("generated_new_comments") or [],
    )
    return {"pdf_path": output_path, "pdf_result": result}


def execute_generate_html_report(state: dict[str, Any]) -> dict[str, Any]:
    """Generate comprehensive HTML dashboard report."""
    release_browser_session()

    channel_name = state.get("youtube_channel_name") or "YouTube Channel"
    slug = re.sub(r"[^a-z0-9]+", "_", channel_name.lower()).strip("_") or "channel"
    output_path = str(REPORTS_DIR / f"{slug}_dashboard_report.html")

    enriched_state = dict(state)
    enriched_state["recommendations"] = _build_recommendations(state)
    enriched_state["llm_summary"] = _generate_llm_executive_summary(enriched_state)

    result = generate_html_dashboard_report_sync(enriched_state, output_path)
    return {
        "html_path": output_path,
        "html_result": result,
        "llm_summary": enriched_state["llm_summary"],
    }


def execute_email_report(state: dict[str, Any]) -> dict[str, Any]:
    """Email HTML dashboard and PDF reports when EMAIL_REPORTS is enabled."""
    config = get_youtube_config()
    pdf_path = state.get("pdf_path", "")
    html_path = state.get("html_path", "")
    channel_name = state.get("youtube_channel_name") or "YouTube Channel"
    video = state.get("video_metadata") or state.get("latest_video") or {}

    if not config["email_reports"]:
        saved = []
        if html_path and Path(html_path).exists():
            saved.append(html_path)
        if pdf_path and Path(pdf_path).exists():
            saved.append(pdf_path)
        if saved:
            return {
                "email_result": (
                    "EMAIL_REPORTS is disabled. Reports saved locally: "
                    + ", ".join(saved)
                ),
            }
        return {"email_result": "EMAIL_REPORTS is disabled. Report saved locally only."}

    attachments: list[str] = []
    if html_path and Path(html_path).exists():
        attachments.append(html_path)
    if pdf_path and Path(pdf_path).exists():
        attachments.append(pdf_path)

    if not attachments:
        return {"email_result": "No HTML or PDF report found to email."}

    body_lines = [
        build_analysis_summary(state),
        "",
        f"Video: {video.get('title', 'N/A')}",
        f"Views: {video.get('views', 'N/A')}",
        f"Likes: {video.get('likes', 'N/A')}",
        "",
        "Attached reports:",
    ]
    for path in attachments:
        body_lines.append(f"- {path}")
    body_lines.append("")
    body_lines.append(
        "Open the HTML attachment for the full interactive-style dashboard report."
    )

    result = send_smtp_email(
        subject=f"YouTube Community Dashboard — {channel_name}",
        body="\n".join(body_lines),
        attachment_paths=",".join(attachments),
        to_email=str(state.get("email_recipient") or "").strip(),
    )
    return {"email_result": result}


def execute_task_plan(
    plan: TaskPlan, initial_state: dict[str, Any] | None = None
) -> AIMessage:
    """Run each planned YouTube task in order and return a combined response."""
    state: dict[str, Any] = dict(initial_state or {})
    state.setdefault("youtube_channel_url", plan.channel_url)
    state.setdefault("youtube_channel_name", plan.channel_name)
    sections: list[str] = [f"**Workflow:** {plan.summary()}", ""]

    task_handlers = {
        "login": ("### Login", execute_youtube_login),
        "fetch_channel": ("### Channel Data", execute_fetch_channel_data),
        "analyze": ("### Comment Analysis", execute_analyze_comments),
        "select_reply_targets": ("### Reply Targets", execute_select_reply_targets),
        "generate_replies": ("### Reply Generation", execute_generate_replies),
        "post_replies": ("### Post Replies", execute_post_replies),
        "generate_new_comment": ("### New Video Comment", execute_generate_new_comment),
        "post_new_comment": ("### Post New Comment", execute_post_new_comment),
        "generate_pdf": ("### PDF Report", execute_generate_pdf_report),
        "generate_html": ("### HTML Dashboard Report", execute_generate_html_report),
        "email_report": ("### Email Report", execute_email_report),
    }

    for task in plan.tasks:
        label, handler = task_handlers.get(task, (task, None))
        if handler is None:
            continue
        sections.append(label)
        updates = handler(state)
        if updates.get("error"):
            sections.append(f"Error: {updates['error']}")
            break
        state.update(updates)
        if task == "login":
            sections.append(
                "YouTube session ready." if state.get("logged_in") else "Login failed."
            )
        elif task == "fetch_channel":
            latest = state.get("latest_video") or {}
            title = latest.get("title", "latest video")
            sections.append(
                f"Collected {len(state.get('comments') or [])} comments from latest video: {title}."
            )
        elif task == "analyze":
            sections.append(build_analysis_summary(state))
        elif task == "select_reply_targets":
            stats = state.get("reply_statistics") or {}
            selected = stats.get(
                "reply_targets_selected", len(state.get("reply_targets") or [])
            )
            limit = stats.get("reply_target_limit", 5)
            sections.append(
                f"Selected {selected} of up to {limit} top positive comments for replies."
            )
        elif task == "generate_replies":
            stats = state.get("reply_statistics") or {}
            sections.append(f"Generated {stats.get('replies_generated', 0)} replies.")
        elif task == "post_replies":
            stats = state.get("reply_statistics") or {}
            sections.append(
                f"Posted {stats.get('replies_posted', 0)} replies; "
                f"{stats.get('replies_failed', 0)} failed."
            )
        elif task == "generate_new_comment":
            generated = state.get("generated_new_comments") or []
            if generated:
                sections.append(
                    f"Generated new video comment: {generated[0].get('comment_text', '')}"
                )
        elif task == "post_new_comment":
            stats = state.get("reply_statistics") or {}
            sections.append(
                f"Posted {stats.get('new_comments_posted', 0)} new video comment(s); "
                f"{stats.get('new_comments_failed', 0)} failed."
            )
        elif task == "generate_pdf":
            sections.append(state.get("pdf_result", ""))
        elif task == "generate_html":
            sections.append(state.get("html_result", ""))
        elif task == "email_report":
            sections.append(state.get("email_result", ""))

    return AIMessage(content="\n\n".join(sections).strip())
