"""Streamlit UI for the YouTube Community Manager Agent.

Dashboard for channel analysis, PDF reports, and email delivery.
Run with: streamlit run streamlit_ui.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from agent import GRAPH_RUN_CONFIG, graph
from agent.config import get_youtube_config, resolve_target_channel
from agent.custom_tools.reply_history import get_reply_history

load_dotenv()


def init_session_state() -> None:
    """Initialize Streamlit session state."""
    config = get_youtube_config()
    defaults = {
        "messages": [],
        "query_count": 0,
        "channel_url": config["channel_url"],
        "channel_name": config["channel_name"],
        "analysis_result": {},
        "workflow_running": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def build_langchain_messages(history: list[dict]) -> list:
    """Convert UI chat history to LangChain messages."""
    lc_messages = []
    for msg in history:
        if msg.get("role") == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
    return lc_messages


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def run_workflow(workflow_action: str = "analyze") -> dict:
    """Invoke the LangGraph workflow with current channel inputs."""
    channel_url, channel_name = resolve_target_channel(
        st.session_state.channel_url.strip(),
        st.session_state.channel_name.strip(),
    )

    if not channel_url and not channel_name:
        st.error(
            "Provide a target Channel Name or Channel URL, "
            "or set YOUTUBE_CHANNEL_NAME in .env."
        )
        return {}

    prompt = "Analyze YouTube channel latest video comments"
    if channel_name:
        prompt += f" for {channel_name}"
    if channel_url:
        prompt += f" ({channel_url})"
    if workflow_action == "report":
        prompt += " and generate PDF report"
    elif workflow_action == "email":
        prompt += " and generate PDF report and email it"

    inputs = {
        "messages": build_langchain_messages(st.session_state.messages),
        "user_input": prompt,
        "youtube_channel_url": channel_url,
        "youtube_channel_name": channel_name,
        "workflow_action": workflow_action,
    }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(graph.ainvoke(inputs, config=GRAPH_RUN_CONFIG))


def _comment_dataframe(comments: list[dict], include_reply: bool = False) -> list[dict]:
    """Format comments for st.dataframe display."""
    rows = []
    for comment in comments:
        row = {
            "Author": comment.get("author", ""),
            "Category": comment.get("category", ""),
            "Priority": comment.get("engagement_priority", ""),
            "Sentiment": comment.get("sentiment_score", ""),
            "Likes": comment.get("likes", 0),
            "Time": comment.get("timestamp", ""),
            "Comment": comment.get("text", ""),
            "Replied": "Yes" if comment.get("replied") else "No",
        }
        if include_reply:
            row["AI Reply"] = comment.get("reply_text", "")
            row["Posted"] = "Yes" if comment.get("posted") else "No"
        rows.append(row)
    return rows


def display_video_metadata(result: dict) -> None:
    """Show all available video metadata fields."""
    video = result.get("video_metadata") or result.get("latest_video") or {}
    if not video:
        st.info("No video metadata available yet. Run **Analyze** first.")
        return

    col_img, col_meta = st.columns([1, 2])
    with col_img:
        thumb = video.get("thumbnail_url", "")
        if thumb:
            st.image(thumb, caption=video.get("title", "Video"), use_container_width=True)

    fields = [
        ("Title", video.get("title")),
        ("Video URL", video.get("url")),
        ("Video ID", video.get("video_id")),
        ("Views", video.get("views")),
        ("Likes", video.get("likes")),
        ("Dislikes", video.get("dislikes")),
        ("Duration", video.get("duration")),
        ("Published", video.get("published")),
        ("Comment count", video.get("comment_count")),
        ("Channel on video", video.get("channel_on_video")),
        ("Subscribers", video.get("subscribers")),
        ("Category", video.get("category")),
        ("Hashtags", video.get("hashtags")),
        ("Game / topic", video.get("game_title")),
        ("Chapters", video.get("chapters")),
    ]

    with col_meta:
        for label, value in fields:
            if value:
                st.markdown(f"**{label}:** {value}")
            else:
                st.markdown(f"**{label}:** _not available_")

    about = video.get("video_about", "")
    if about:
        st.markdown("**What this video is about**")
        st.info(about)

    description = video.get("description") or video.get("og_description", "")
    if description:
        st.markdown("**Full description**")
        st.text(description[:3000])
    elif not about:
        st.caption("No description was available from YouTube for this video.")


def display_comment_tab(comments: list[dict], empty_msg: str = "No comments in this category.") -> None:
    """Render a comment category tab."""
    if not comments:
        st.caption(empty_msg)
        return
    st.dataframe(_comment_dataframe(comments), use_container_width=True, hide_index=True)


def display_reply_history(result: dict) -> None:
    """Show persistent log of what was replied to what."""
    session_records = result.get("reply_history") or []
    channel = result.get("youtube_channel_name", "")
    video = result.get("video_metadata") or result.get("latest_video") or {}
    persisted = get_reply_history(
        channel_name=channel,
        video_id=video.get("video_id", ""),
    )
    records = session_records or persisted

    if not records:
        st.caption("No replies recorded yet. Generate or post replies to build history.")
        return

    rows = []
    for record in records:
        rows.append(
            {
                "When": record.get("recorded_at", ""),
                "Video": record.get("video_title", ""),
                "Author": record.get("comment_author", ""),
                "Category": record.get("comment_category", ""),
                "Original Comment": record.get("comment_text", ""),
                "Our Reply": record.get("reply_text", ""),
                "Status": record.get("status", ""),
                "Posted": "Yes" if record.get("posted") else "No",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(f"History file: `./data/reply_history.json` · {len(records)} record(s)")


def display_dashboard(result: dict) -> None:
    """Render analysis metrics dashboard with detail tabs."""
    comments = result.get("comments") or []
    analyzed = result.get("analyzed_comments") or comments
    total = len(analyzed)
    positive = len(result.get("positive_comments") or [])
    negative = len(result.get("negative_comments") or [])
    neutral = len(result.get("neutral_comments") or [])
    questions = len(result.get("question_comments") or [])
    suggestions = len(result.get("suggestion_comments") or [])
    spam = len(result.get("spam_comments") or [])
    unanswered = len(result.get("unanswered_comments") or [])
    stats = result.get("reply_statistics") or {}
    replies_generated = stats.get("replies_generated", len(result.get("generated_replies") or []))
    replies_posted = stats.get("replies_posted", 0)
    replies_failed = stats.get("replies_failed", len(result.get("failed_replies") or []))

    st.subheader("Community Dashboard")
    latest_video = result.get("latest_video") or result.get("video_metadata") or {}
    if latest_video:
        caption = (
            f"Target channel: **{result.get('youtube_channel_name', 'N/A')}** · "
            f"Latest video: **{latest_video.get('title', 'N/A')}**"
        )
        if latest_video.get("published"):
            caption += f" · Published: {latest_video['published']}"
        st.caption(caption)
        if latest_video.get("video_about"):
            st.info(latest_video["video_about"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Comments", total)
    c2.metric("Positive %", f"{_pct(positive, total)}%")
    c3.metric("Negative %", f"{_pct(negative, total)}%")
    c4.metric("Neutral %", f"{_pct(neutral, total)}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Questions", questions)
    c6.metric("Suggestions", suggestions)
    c7.metric("Spam", spam)
    c8.metric("Unanswered", unanswered)

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Replies Generated", replies_generated)
    c10.metric("Replies Posted", replies_posted)
    c11.metric("Replies Failed", replies_failed)
    c12.metric(
        "New Comments",
        stats.get("new_comments_posted", len(result.get("generated_new_comments") or [])),
    )
    reply_targets = result.get("reply_targets") or result.get("generated_replies") or []
    if reply_targets:
        st.caption(
            f"Reply workflow targets the top {len(reply_targets)} positive comment(s) "
            f"after analyzing all {total} scraped comments."
        )

    if result.get("pdf_path"):
        st.success(f"PDF report: {result['pdf_path']}")
    if result.get("html_path"):
        st.success(f"HTML dashboard: {result['html_path']}")
        with open(result["html_path"], encoding="utf-8") as html_file:
            st.download_button(
                "Download HTML Report",
                html_file.read(),
                file_name=Path(result["html_path"]).name,
                mime="text/html",
            )

    st.divider()

    tabs = st.tabs(
        [
            "Video Info",
            f"Positive ({positive})",
            f"Negative ({negative})",
            f"Neutral ({neutral})",
            f"Questions ({questions})",
            f"Suggestions ({suggestions})",
            f"Spam ({spam})",
            "Reply Log",
            f"All Comments ({total})",
            "AI Replies",
        ]
    )

    with tabs[0]:
        display_video_metadata(result)

    with tabs[1]:
        display_comment_tab(result.get("positive_comments") or [], "No positive comments.")

    with tabs[2]:
        display_comment_tab(result.get("negative_comments") or [], "No negative comments.")

    with tabs[3]:
        display_comment_tab(result.get("neutral_comments") or [], "No neutral comments.")

    with tabs[4]:
        display_comment_tab(result.get("question_comments") or [], "No questions found.")

    with tabs[5]:
        display_comment_tab(result.get("suggestion_comments") or [], "No suggestions found.")

    with tabs[6]:
        display_comment_tab(result.get("spam_comments") or [], "No spam detected.")

    with tabs[7]:
        display_reply_history(result)

    with tabs[8]:
        analyzed = result.get("analyzed_comments") or comments
        display_comment_tab(analyzed, "No comments collected.")

    with tabs[9]:
        generated = result.get("generated_replies") or []
        if generated:
            st.dataframe(
                _comment_dataframe(generated, include_reply=True),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No AI replies generated for this run.")


def display_sidebar() -> None:
    """Display sidebar configuration."""
    config = get_youtube_config()

    with st.sidebar:
        st.title("⚙️ Configuration")

        st.subheader("API Status")
        st.success("✓ Groq API") if os.getenv("GROQ_API_KEY") else st.error("✗ Groq API")
        if config["email"] and config["password"]:
            st.success("✓ YouTube Credentials")
        else:
            st.warning("✗ YouTube Credentials")
        if os.getenv("GMAIL_SMTP_USER") and os.getenv("GMAIL_APP_PASSWORD"):
            st.success("✓ Gmail SMTP")
        else:
            st.warning("✗ Gmail SMTP")

        st.divider()
        st.subheader("Target Channel")
        if config["channel_name"]:
            st.write(f"**Name:** {config['channel_name']}")
        if config["channel_url"]:
            st.write(f"**URL:** {config['channel_url']}")
        if not config["channel_name"] and not config["channel_url"]:
            st.caption("Set YOUTUBE_CHANNEL_NAME in .env")

        st.divider()
        st.subheader("Reply Filters")
        st.caption("Configured via .env")
        for label, key in (
            ("Positive", "reply_to_positive"),
            ("Negative", "reply_to_negative"),
            ("Neutral", "reply_to_neutral"),
            ("Questions", "reply_to_questions"),
            ("Suggestions", "reply_to_suggestions"),
            ("Spam", "reply_to_spam"),
        ):
            enabled = "✓" if config[key] else "✗"
            st.write(f"{enabled} {label}")

        st.divider()
        st.subheader("Automation")
        st.write(f"Post replies: {'On' if config['enable_comment_replies'] else 'Off'}")
        st.write(f"Post new comments: {'On' if config['enable_new_comments'] else 'Off'}")
        st.write(f"Email reports: {'On' if config['email_reports'] else 'Off'}")
        st.metric("Queries processed", st.session_state.query_count)


def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(
        page_title="YouTube Community Manager",
        page_icon="▶️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()
    display_sidebar()

    st.title("YouTube Community Manager Agent")
    st.markdown(
        "Analyze **any target channel's latest video**: scrape comments, classify sentiment, "
        "generate replies, build PDF reports, and email summaries. "
        "Set `YOUTUBE_CHANNEL_NAME` in `.env` or enter a channel below."
    )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.session_state.channel_url = st.text_input(
            "Channel URL (optional)",
            value=st.session_state.channel_url,
            placeholder="https://www.youtube.com/@channelname",
            help="Optional if Channel Name is set. Overrides .env YOUTUBE_CHANNEL_URL.",
        )
    with col2:
        st.session_state.channel_name = st.text_input(
            "Channel Name",
            value=st.session_state.channel_name,
            placeholder="e.g. MrBeast",
            help="Target channel to open. Defaults to YOUTUBE_CHANNEL_NAME from .env.",
        )

    btn1, btn2, btn3 = st.columns(3)
    with btn1:
        analyze_clicked = st.button("Analyze", use_container_width=True, type="primary")
    with btn2:
        report_clicked = st.button("Generate Report", use_container_width=True)
    with btn3:
        email_clicked = st.button("Send Report", use_container_width=True)

    if analyze_clicked:
        with st.spinner("Opening target channel latest video and analyzing comments..."):
            try:
                result = run_workflow("analyze")
                st.session_state.analysis_result = result
                st.session_state.query_count += 1
                if result.get("messages"):
                    st.session_state.messages.append(
                        {"role": "assistant", "content": str(result["messages"][-1].content)}
                    )
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

    if report_clicked:
        with st.spinner("Generating PDF report..."):
            try:
                result = run_workflow("report")
                st.session_state.analysis_result = result
                st.session_state.query_count += 1
            except Exception as exc:
                st.error(f"Report generation failed: {exc}")

    if email_clicked:
        with st.spinner("Generating and emailing report..."):
            try:
                result = run_workflow("email")
                st.session_state.analysis_result = result
                st.session_state.query_count += 1
            except Exception as exc:
                st.error(f"Email workflow failed: {exc}")

    if st.session_state.analysis_result:
        display_dashboard(st.session_state.analysis_result)

        with st.expander("Workflow Output"):
            messages = st.session_state.analysis_result.get("messages") or []
            if messages:
                st.markdown(str(messages[-1].content))
            if st.session_state.analysis_result.get("email_result"):
                st.info(st.session_state.analysis_result["email_result"])

    st.divider()

    with st.expander("🔍 Environment Check"):
        config = get_youtube_config()
        checks = {
            "GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
            "YOUTUBE_EMAIL": bool(config["email"]),
            "YOUTUBE_PASSWORD": bool(config["password"]),
            "YOUTUBE_CHANNEL_NAME": bool(config["channel_name"]),
            "GMAIL_SMTP_USER": bool(os.getenv("GMAIL_SMTP_USER")),
            "GMAIL_APP_PASSWORD": bool(os.getenv("GMAIL_APP_PASSWORD")),
        }
        for key, ok in checks.items():
            st.write(f"{key}: {'✓' if ok else '✗'}")


if __name__ == "__main__":
    main()
