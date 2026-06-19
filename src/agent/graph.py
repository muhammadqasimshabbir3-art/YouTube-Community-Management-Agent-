"""YouTube Community Manager Agent - LangGraph workflow."""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import NotRequired, TypedDict

from agent.async_utils import run_in_thread, run_playwright
from agent.config import apply_runtime_overrides, get_youtube_config, resolve_target_channel
from agent.custom_tools.email_tools import send_email
from agent.custom_tools.html_report_generator import (
    generate_html_report as generate_html_report_tool,
)
from agent.custom_tools.pdf_generator import generate_pdf_report, generate_table_report
from agent.routing import (
    build_analysis_summary,
    extract_channel_name,
    extract_channel_url,
    get_latest_user_text,
    is_empty_ai_message,
    wants_email_report,
    wants_pdf_report,
    wants_youtube_analysis,
)
from agent.task_planner import is_youtube_workflow_request, plan_tasks
from agent.workflow_executor import (
    execute_analyze_comments,
    execute_email_report,
    execute_fetch_channel_data,
    execute_generate_html_report,
    execute_generate_new_comment,
    execute_generate_pdf_report,
    execute_generate_replies,
    execute_post_new_comment,
    execute_post_replies,
    execute_select_reply_targets,
    execute_task_plan,
    execute_youtube_login,
)

load_dotenv()

SYSTEM_PROMPT = (
    "You are the YouTube Community Manager Agent. "
    "You help manage YouTube channel communities: analyze latest video comments, "
    "generate replies, create HTML dashboard and PDF reports, and email them. "
    "Use tools when the user asks for PDF generation or email delivery."
)

GRAPH_RUN_CONFIG = {"recursion_limit": 100}

AgentRoute = Literal[
    "youtube_workflow",
    "execute_workflow",
    "call_model",
]


class State(TypedDict):
    """State for the YouTube Community Manager graph."""

    messages: Annotated[list[AnyMessage], add_messages]
    user_input: NotRequired[str]
    workflow_action: NotRequired[str]
    youtube_channel_name: NotRequired[str]
    youtube_channel_url: NotRequired[str]
    youtube_channel_id: NotRequired[str]
    latest_video: NotRequired[dict]
    video_metadata: NotRequired[dict]
    comments: NotRequired[list[dict]]
    analyzed_comments: NotRequired[list[dict]]
    positive_comments: NotRequired[list[dict]]
    negative_comments: NotRequired[list[dict]]
    neutral_comments: NotRequired[list[dict]]
    question_comments: NotRequired[list[dict]]
    suggestion_comments: NotRequired[list[dict]]
    spam_comments: NotRequired[list[dict]]
    unanswered_comments: NotRequired[list[dict]]
    reply_targets: NotRequired[list[dict]]
    generated_replies: NotRequired[list[dict]]
    failed_replies: NotRequired[list[dict]]
    generated_new_comments: NotRequired[list[dict]]
    failed_new_comments: NotRequired[list[dict]]
    reply_history: NotRequired[list[dict]]
    reply_statistics: NotRequired[dict]
    pdf_path: NotRequired[str]
    html_path: NotRequired[str]
    llm_summary: NotRequired[str]
    task_plan_summary: NotRequired[str]
    agent_route: NotRequired[AgentRoute]
    max_replies_per_video: NotRequired[int]
    email_recipient: NotRequired[str]
    max_videos_to_scan: NotRequired[int]
    max_comments_per_video: NotRequired[int]
    reply_personality: NotRequired[str]
    enable_comment_replies: NotRequired[bool]
    enable_new_comments: NotRequired[bool]
    new_comment_text: NotRequired[str]
    max_new_comments: NotRequired[int]
    keep_browser_open: NotRequired[bool]
    reply_to_positive: NotRequired[bool]
    reply_to_negative: NotRequired[bool]
    reply_to_neutral: NotRequired[bool]
    reply_to_questions: NotRequired[bool]
    reply_to_suggestions: NotRequired[bool]
    reply_to_spam: NotRequired[bool]
    email_reports: NotRequired[bool]
    logged_in: NotRequired[bool]
    youtube_login_detail: NotRequired[str]


_model_instance = None


def _init_model():
    global _model_instance
    if _model_instance is not None:
        return _model_instance

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")

    _model_instance = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        api_key=api_key,
    )
    return _model_instance


def get_model():
    return _init_model()


llm_tools = [
    generate_pdf_report,
    generate_table_report,
    generate_html_report_tool,
    send_email,
]

tool_node = ToolNode(llm_tools)


def _is_fresh_user_turn(messages: list[AnyMessage]) -> bool:
    if not messages:
        return False
    last_message = messages[-1]
    return (
        isinstance(last_message, HumanMessage)
        or getattr(last_message, "type", None) == "human"
    )


def _default_workflow_prompt(channel_name: str = "", channel_url: str = "") -> str:
    """Build the default analysis prompt from configured target channel."""
    if channel_name:
        prompt = f"Analyze latest video comments for {channel_name}"
    else:
        prompt = "Analyze latest video comments on configured YouTube channel"
    if channel_url:
        prompt = f"{prompt} ({channel_url})"
    return prompt


def _prepare_messages(state: State) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """Build conversation messages and any new messages to append to state."""
    existing_messages = list(state.get("messages") or [])
    state_updates: list[AnyMessage] = []

    if existing_messages:
        return existing_messages, state_updates

    user_input = (state.get("user_input") or "").strip()
    if not user_input:
        channel_url, channel_name = resolve_target_channel(
            state.get("youtube_channel_url", ""),
            state.get("youtube_channel_name", ""),
        )
        if channel_name or channel_url or state.get("workflow_action"):
            user_input = _default_workflow_prompt(channel_name, channel_url)
        else:
            raise ValueError(
                "No channel configured. Set YOUTUBE_CHANNEL_NAME or "
                "YOUTUBE_CHANNEL_URL in .env, or pass messages/user_input."
            )

    human_message = HumanMessage(content=user_input)
    state_updates.append(human_message)
    return [human_message], state_updates


def _state_as_dict(state: State) -> dict[str, Any]:
    return dict(state)


def _pick_route(state: State, messages: list[AnyMessage], user_text: str) -> AgentRoute:
    """Decide which graph branch should handle the request."""
    if not _is_fresh_user_turn(messages) and not state.get("workflow_action"):
        return "call_model"

    workflow_action = state.get("workflow_action", "")
    if workflow_action:
        return "youtube_workflow"

    text_url = extract_channel_url(user_text)
    text_name = extract_channel_name(user_text)
    if wants_youtube_analysis(user_text):
        return "youtube_workflow"

    if is_youtube_workflow_request(user_text, text_url, text_name):
        return "execute_workflow"

    return "call_model"


async def prepare_input(state: State) -> dict[str, Any]:
    """Normalize input, load .env channel defaults, and bootstrap workflow runs."""
    apply_runtime_overrides(dict(state))
    updates: dict[str, Any] = {}

    channel_url = state.get("youtube_channel_url", "")
    channel_name = state.get("youtube_channel_name", "")
    resolved_url, resolved_name = resolve_target_channel(channel_url, channel_name)
    if resolved_url:
        updates["youtube_channel_url"] = resolved_url
    if resolved_name:
        updates["youtube_channel_name"] = resolved_name

    merged: dict[str, Any] = {**state, **updates}
    user_input = (state.get("user_input") or "").strip()
    has_messages = bool(state.get("messages"))

    if (
        not state.get("workflow_action")
        and (resolved_url or resolved_name)
        and not has_messages
        and not user_input
    ):
        updates["workflow_action"] = "analyze"
        merged["workflow_action"] = "analyze"

    _, state_updates = _prepare_messages(merged)  # type: ignore[arg-type]
    if state_updates:
        updates["messages"] = state_updates

    user_text = user_input
    if not user_text and state_updates:
        user_text = str(state_updates[0].content)
    elif not user_text and has_messages:
        user_text = get_latest_user_text(state.get("messages") or [])

    channel_url = updates.get("youtube_channel_url", channel_url)
    channel_name = updates.get("youtube_channel_name", channel_name)
    if user_text and not channel_url:
        url = extract_channel_url(user_text)
        if url:
            channel_url = url
            updates["youtube_channel_url"] = url
    if user_text and not channel_name:
        name = extract_channel_name(user_text)
        if name:
            channel_name = name
            updates["youtube_channel_name"] = name

    workflow_action = updates.get("workflow_action") or state.get("workflow_action", "")
    should_resolve = bool(workflow_action) or wants_youtube_analysis(user_text)
    if should_resolve:
        resolved_url, resolved_name = resolve_target_channel(channel_url, channel_name)
        if resolved_url:
            updates["youtube_channel_url"] = resolved_url
        if resolved_name:
            updates["youtube_channel_name"] = resolved_name

    return updates


async def decision_agent(state: State) -> dict[str, Any]:
    """Analyze the user query and choose the execution path."""
    messages, _ = _prepare_messages(state)
    user_text = get_latest_user_text(messages)
    channel_url = state.get("youtube_channel_url", "")
    channel_name = state.get("youtube_channel_name", "")
    workflow_action = state.get("workflow_action", "")
    task_plan = plan_tasks(user_text, channel_url, channel_name, workflow_action)
    route = _pick_route(state, messages, user_text)

    summary = (
        task_plan.summary() if task_plan.is_youtube_workflow else "General conversation"
    )
    return {
        "task_plan_summary": summary,
        "agent_route": route,
    }


async def execute_workflow(state: State) -> dict[str, Any]:
    """Run full YouTube workflow from task plan."""
    messages, _ = _prepare_messages(state)
    user_text = get_latest_user_text(messages)
    task_plan = plan_tasks(
        user_text,
        state.get("youtube_channel_url", ""),
        state.get("youtube_channel_name", ""),
        state.get("workflow_action", ""),
    )
    collected = await run_in_thread(
        _run_workflow_and_collect, task_plan, _state_as_dict(state)
    )
    response = await run_in_thread(execute_task_plan, task_plan, _state_as_dict(state))
    return {**collected, "messages": [response]}


def _run_workflow_and_collect(plan, initial_state: dict) -> dict:
    """Run workflow steps and return accumulated state updates."""
    state = dict(initial_state)
    handlers = [
        execute_youtube_login,
        execute_fetch_channel_data,
        execute_analyze_comments,
        execute_select_reply_targets,
        execute_generate_replies,
        execute_post_replies,
        execute_generate_new_comment,
        execute_post_new_comment,
        execute_generate_pdf_report,
        execute_generate_html_report,
        execute_email_report,
    ]
    task_map = {
        "login": 0,
        "fetch_channel": 1,
        "analyze": 2,
        "select_reply_targets": 3,
        "generate_replies": 4,
        "post_replies": 5,
        "generate_new_comment": 6,
        "post_new_comment": 7,
        "generate_pdf": 8,
        "generate_html": 9,
        "email_report": 10,
    }
    for task in plan.tasks:
        idx = task_map.get(task)
        if idx is None or idx >= len(handlers):
            continue
        updates = handlers[idx](state)
        if updates.get("error"):
            break
        state.update(updates)
    return state


async def login_youtube(state: State) -> dict[str, Any]:
    """Log in to YouTube and persist session."""
    updates = await run_playwright(execute_youtube_login, _state_as_dict(state))
    logged_in = updates.get("logged_in", False)
    content = (
        "Successfully logged in to YouTube." if logged_in else "YouTube login failed."
    )
    return {**updates, "messages": [AIMessage(content=content)]}


async def fetch_channel_data(state: State) -> dict[str, Any]:
    """Fetch comments from the target channel's latest video."""
    updates = await run_playwright(execute_fetch_channel_data, _state_as_dict(state))
    if updates.get("error"):
        return {
            "messages": [
                AIMessage(content=f"Failed to fetch channel data: {updates['error']}")
            ]
        }
    count = len(updates.get("comments") or [])
    reported = updates.get("comments_reported_count") or (
        (updates.get("video_metadata") or {}).get("comment_count_value")
    )
    latest = updates.get("latest_video") or updates.get("video_metadata") or {}
    video_title = latest.get("title", "latest video")
    msg = (
        f"Fetched {count} comments from '{updates.get('youtube_channel_name', 'channel')}' "
        f"— latest video: {video_title}."
    )
    if latest.get("video_about"):
        msg += f"\n\n**What this video is about:** {latest['video_about']}"
    description = latest.get("description") or latest.get("og_description")
    if description:
        excerpt = description[:500] + ("..." if len(description) > 500 else "")
        msg += f"\n\n**Description:** {excerpt}"
    if reported:
        msg += f" YouTube reports {reported} total comments on this video."
    if updates.get("warning"):
        msg += f" Warning: {updates['warning']}"
    return {**updates, "messages": [AIMessage(content=msg)]}


async def analyze_comments(state: State) -> dict[str, Any]:
    """Analyze all scraped comments with LLM classification."""
    updates = await run_in_thread(execute_analyze_comments, _state_as_dict(state))
    merged = {**_state_as_dict(state), **updates}
    summary = build_analysis_summary(merged)
    analyzed_count = len(updates.get("analyzed_comments") or [])
    positive_count = len(updates.get("positive_comments") or [])
    return {
        **updates,
        "messages": [
            AIMessage(
                content=(
                    f"Analyzed {analyzed_count} comments "
                    f"({positive_count} positive). {summary}"
                )
            )
        ],
    }


async def select_reply_targets(state: State) -> dict[str, Any]:
    """Select up to N top positive comments for reply generation."""
    updates = await run_in_thread(execute_select_reply_targets, _state_as_dict(state))
    stats = updates.get("reply_statistics") or {}
    selected = stats.get(
        "reply_targets_selected", len(updates.get("reply_targets") or [])
    )
    limit = stats.get(
        "reply_target_limit", get_youtube_config()["max_replies_per_video"]
    )
    positive_total = stats.get("positive_comments_total", 0)
    targets = updates.get("reply_targets") or []
    preview_lines = [
        f"Selected {selected} of up to {limit} top positive comments "
        f"(from {positive_total} positive total)."
    ]
    for target in targets[:5]:
        preview_lines.append(
            f"- #{target.get('reply_rank', '?')} {target.get('author', 'viewer')} "
            f"({target.get('likes', 0)} likes): {str(target.get('text', ''))[:100]}"
        )
    return {**updates, "messages": [AIMessage(content="\n".join(preview_lines))]}


async def generate_replies(state: State) -> dict[str, Any]:
    """Generate humorous AI replies for selected positive comments."""
    updates = await run_in_thread(execute_generate_replies, _state_as_dict(state))
    stats = updates.get("reply_statistics") or {}
    count = stats.get("replies_generated", 0)
    personality = stats.get("reply_personality", "humorous")
    posting = "enabled" if stats.get("posting_enabled") else "disabled in .env"
    return {
        **updates,
        "messages": [
            AIMessage(
                content=(
                    f"Generated {count} {personality} AI replies. "
                    f"YouTube posting is {posting}."
                )
            )
        ],
    }


async def post_replies(state: State) -> dict[str, Any]:
    """Post replies through browser automation when ENABLE_COMMENT_REPLIES=true."""
    apply_runtime_overrides(_state_as_dict(state))
    merged = {**_state_as_dict(state)}
    updates = await run_playwright(execute_post_replies, merged)
    stats = updates.get("reply_statistics") or merged.get("reply_statistics") or {}
    posted = stats.get("replies_posted", 0)
    failed = stats.get("replies_failed", 0)
    config = get_youtube_config()
    enable_replies = (
        state.get("enable_comment_replies")
        if state.get("enable_comment_replies") is not None
        else config["enable_comment_replies"]
    )
    if not enable_replies:
        content = "Reply posting skipped (ENABLE_COMMENT_REPLIES=false). Replies saved in report."
    elif posted and not failed:
        content = f"Posted {posted} replies to YouTube."
    elif posted:
        content = f"Posted {posted} replies; {failed} failed (see report for details)."
    elif failed:
        content = f"All {failed} reply attempt(s) failed (see report for details)."
    else:
        content = "No replies were posted (none generated or browser posting failed)."
    return {**updates, "messages": [AIMessage(content=content)]}


async def generate_new_comment(state: State) -> dict[str, Any]:
    """Generate a top-level community comment for the latest video."""
    apply_runtime_overrides(_state_as_dict(state))
    config = get_youtube_config()
    enabled = (
        state.get("enable_new_comments")
        if state.get("enable_new_comments") is not None
        else config["enable_new_comments"]
    )
    if not enabled:
        return {
            "generated_new_comments": [],
            "messages": [
                AIMessage(
                    content="New video comment skipped (ENABLE_NEW_COMMENTS=false)."
                )
            ],
        }
    updates = await run_in_thread(execute_generate_new_comment, _state_as_dict(state))
    generated = updates.get("generated_new_comments") or []
    preview = generated[0].get("comment_text", "") if generated else ""
    return {
        **updates,
        "messages": [AIMessage(content=f"Generated new video comment: {preview}")],
    }


async def post_new_comment(state: State) -> dict[str, Any]:
    """Post a new top-level comment when ENABLE_NEW_COMMENTS=true."""
    apply_runtime_overrides(_state_as_dict(state))
    updates = await run_playwright(execute_post_new_comment, _state_as_dict(state))
    stats = updates.get("reply_statistics") or {}
    posted = stats.get("new_comments_posted", 0)
    failed = stats.get("new_comments_failed", 0)
    config = get_youtube_config()
    enabled = (
        state.get("enable_new_comments")
        if state.get("enable_new_comments") is not None
        else config["enable_new_comments"]
    )
    if not enabled:
        content = "New comment posting skipped (ENABLE_NEW_COMMENTS=false). Text saved in report."
    elif posted and not failed:
        content = f"Posted {posted} new top-level comment on the video."
    elif failed:
        content = (
            f"Failed to post new comment ({failed} attempt(s)). See report for details."
        )
    else:
        content = "No new comment was posted."
    return {**updates, "messages": [AIMessage(content=content)]}


async def generate_html_report(state: State) -> dict[str, Any]:
    """Generate comprehensive HTML dashboard report."""
    merged = {**_state_as_dict(state)}
    updates = await run_playwright(execute_generate_html_report, merged)
    html_result = updates.get("html_result", "HTML report generated.")
    return {**updates, "messages": [AIMessage(content=html_result)]}


async def generate_pdf_report(state: State) -> dict[str, Any]:
    """Generate PDF community management report."""
    action = state.get("workflow_action", "")
    if action not in ("report", "email") and not wants_pdf_report(
        get_latest_user_text(state.get("messages") or [])
    ):
        return {
            "messages": [
                AIMessage(content="PDF generation skipped for analyze-only run.")
            ]
        }
    updates = await run_in_thread(execute_generate_pdf_report, _state_as_dict(state))
    pdf_result = updates.get("pdf_result", "PDF generated.")
    return {**updates, "messages": [AIMessage(content=pdf_result)]}


async def email_report(state: State) -> dict[str, Any]:
    """Email HTML dashboard and PDF reports when enabled."""
    apply_runtime_overrides(_state_as_dict(state))
    action = state.get("workflow_action", "")
    config = get_youtube_config()
    should_email = (
        action == "email"
        or wants_email_report(get_latest_user_text(state.get("messages") or []))
        or state.get("email_reports") is True
        or (state.get("email_reports") is not False and config["email_reports"])
    )
    if not should_email:
        html_path = _state_as_dict(state).get("html_path", "")
        if html_path:
            return {
                "email_result": "Email skipped — HTML dashboard saved",
                "messages": [
                    AIMessage(
                        content=f"Email skipped. HTML dashboard saved: {html_path}"
                    )
                ],
            }
        return {
            "email_result": "Email skipped for this run",
            "messages": [AIMessage(content="Email step skipped.")],
        }
    updates = await run_in_thread(execute_email_report, _state_as_dict(state))
    email_result = updates.get("email_result", "Email step completed.")
    return {**updates, "messages": [AIMessage(content=email_result)]}


async def call_model(state: State) -> dict[str, Any]:
    """LLM path for general chat and dynamic tool selection."""
    messages, _ = _prepare_messages(state)

    has_system_message = any(
        getattr(message, "type", None) == "system" for message in messages
    )
    llm_messages = (
        [SystemMessage(content=SYSTEM_PROMPT), *messages]
        if not has_system_message
        else messages
    )

    model_with_tools = get_model().bind_tools(llm_tools)
    response = await model_with_tools.ainvoke(llm_messages)

    if isinstance(response, AIMessage) and is_empty_ai_message(response):
        if response.tool_calls:
            tool_names = ", ".join(
                tc.get("name", "tool")
                if isinstance(tc, dict)
                else getattr(tc, "name", "tool")
                for tc in response.tool_calls
            )
            response.content = f"Calling tools: {tool_names}"
        else:
            response.content = (
                "I can help analyze YouTube channel comments, generate replies, "
                "create PDF reports, and email them. Provide a channel URL or name to start."
            )

    return {"messages": [response]}


def route_after_decision(state: State) -> AgentRoute:
    """Route from decide_agent to the chosen execution node."""
    return state.get("agent_route", "call_model")


def route_after_generate_replies(
    state: State,
) -> Literal["post_replies", "generate_new_comment", "generate_html_report"]:
    """Skip browser reply posting when disabled; skip new comment when disabled."""
    apply_runtime_overrides(_state_as_dict(state))
    config = get_youtube_config()
    replies = state.get("generated_replies") or []
    if state.get("enable_comment_replies") is not None:
        enable_replies = bool(state.get("enable_comment_replies"))
    else:
        enable_replies = config["enable_comment_replies"]
    if state.get("enable_new_comments") is True:
        enable_new = True
    elif state.get("enable_new_comments") is False:
        enable_new = False
    else:
        enable_new = config["enable_new_comments"]
    if enable_replies and replies:
        return "post_replies"
    if enable_new:
        return "generate_new_comment"
    return "generate_html_report"


def route_after_post_replies(
    state: State,
) -> Literal["generate_new_comment", "generate_html_report"]:
    """Skip new comment generation when ENABLE_NEW_COMMENTS=false."""
    apply_runtime_overrides(_state_as_dict(state))
    config = get_youtube_config()
    if state.get("enable_new_comments") is True or (
        state.get("enable_new_comments") is not False and config["enable_new_comments"]
    ):
        return "generate_new_comment"
    return "generate_html_report"


def route_after_model(state: State) -> Literal["tools", END]:
    """Route from call_model to tools or end."""
    messages = state.get("messages") or []
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return END


graph_builder = StateGraph(State)

graph_builder.add_node("prepare_agent", prepare_input)
graph_builder.add_node("decide_agent", decision_agent)
graph_builder.add_node("execute_workflow", execute_workflow)
graph_builder.add_node("login_youtube", login_youtube)
graph_builder.add_node("fetch_channel_data", fetch_channel_data)
graph_builder.add_node("analyze_comments", analyze_comments)
graph_builder.add_node("select_reply_targets", select_reply_targets)
graph_builder.add_node("generate_replies", generate_replies)
graph_builder.add_node("post_replies", post_replies)
graph_builder.add_node("generate_new_comment", generate_new_comment)
graph_builder.add_node("post_new_comment", post_new_comment)
graph_builder.add_node("generate_html_report", generate_html_report)
graph_builder.add_node("generate_pdf_report", generate_pdf_report)
graph_builder.add_node("email_report", email_report)
graph_builder.add_node("call_tool", call_model)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "prepare_agent")
graph_builder.add_edge("prepare_agent", "decide_agent")
graph_builder.add_conditional_edges(
    "decide_agent",
    route_after_decision,
    {
        "youtube_workflow": "login_youtube",
        "execute_workflow": "execute_workflow",
        "call_model": "call_tool",
    },
)
graph_builder.add_edge("login_youtube", "fetch_channel_data")
graph_builder.add_edge("fetch_channel_data", "analyze_comments")
graph_builder.add_edge("analyze_comments", "select_reply_targets")
graph_builder.add_edge("select_reply_targets", "generate_replies")
graph_builder.add_conditional_edges(
    "generate_replies",
    route_after_generate_replies,
    {
        "post_replies": "post_replies",
        "generate_new_comment": "generate_new_comment",
        "generate_html_report": "generate_html_report",
    },
)
graph_builder.add_conditional_edges(
    "post_replies",
    route_after_post_replies,
    {
        "generate_new_comment": "generate_new_comment",
        "generate_html_report": "generate_html_report",
    },
)
graph_builder.add_edge("generate_new_comment", "post_new_comment")
graph_builder.add_edge("post_new_comment", "generate_html_report")
graph_builder.add_edge("generate_html_report", "generate_pdf_report")
graph_builder.add_edge("generate_pdf_report", "email_report")
graph_builder.add_edge("email_report", END)
graph_builder.add_edge("execute_workflow", END)
graph_builder.add_conditional_edges("call_tool", route_after_model)
graph_builder.add_edge("tools", "call_tool")

graph = graph_builder.compile(name="YouTube Community Manager Agent")
