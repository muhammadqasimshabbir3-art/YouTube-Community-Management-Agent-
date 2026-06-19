"""Decision agent: plan YouTube community management tasks."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.config import resolve_target_channel
from agent.routing import (
    extract_channel_name,
    extract_channel_url,
    wants_email_report,
    wants_pdf_report,
    wants_youtube_analysis,
)


@dataclass
class TaskPlan:
    """Ordered list of tasks the agent should perform."""

    tasks: list[str] = field(default_factory=list)
    user_text: str = ""
    channel_url: str = ""
    channel_name: str = ""
    workflow_action: str = "analyze"

    @property
    def is_youtube_workflow(self) -> bool:
        return bool(self.tasks)

    def summary(self) -> str:
        labels = {
            "login": "Login to YouTube",
            "fetch_channel": "Scrape all comments from latest video",
            "analyze": "Analyze all comments",
            "select_reply_targets": "Select top positive reply targets",
            "generate_replies": "Generate humorous AI replies",
            "post_replies": "Post replies (if enabled)",
            "generate_new_comment": "Generate new top-level video comment",
            "post_new_comment": "Post new comment (if enabled)",
            "generate_pdf": "Generate PDF report",
            "generate_html": "Generate HTML dashboard report",
            "email_report": "Email HTML + PDF reports",
        }
        steps = [labels.get(task, task) for task in self.tasks]
        return " → ".join(steps) if steps else "General conversation"


def plan_tasks(
    user_text: str,
    channel_url: str = "",
    channel_name: str = "",
    workflow_action: str = "",
) -> TaskPlan:
    """Analyze the user query and decide which YouTube tasks to run."""
    plan = TaskPlan(user_text=user_text)
    plan.channel_url, plan.channel_name = resolve_target_channel(
        channel_url or extract_channel_url(user_text),
        channel_name or extract_channel_name(user_text),
    )
    plan.workflow_action = workflow_action or "analyze"

    text_url = channel_url or extract_channel_url(user_text)
    text_name = channel_name or extract_channel_name(user_text)
    explicit_intent = bool(workflow_action) or wants_youtube_analysis(
        user_text, text_url, text_name
    )
    has_target = bool(plan.channel_url or plan.channel_name)

    if not explicit_intent or not has_target:
        return plan

    plan.tasks = [
        "login",
        "fetch_channel",
        "analyze",
        "select_reply_targets",
        "generate_replies",
        "post_replies",
        "generate_new_comment",
        "post_new_comment",
        "generate_html",
    ]

    if wants_pdf_report(user_text) or workflow_action in ("report", "email"):
        plan.tasks.append("generate_pdf")
        plan.tasks.append("generate_html")

    if wants_email_report(user_text) or workflow_action == "email":
        plan.tasks.append("email_report")

    return plan


def is_youtube_workflow_request(
    user_text: str,
    channel_url: str = "",
    channel_name: str = "",
) -> bool:
    """Return True when the request should run the YouTube workflow."""
    return plan_tasks(user_text, channel_url, channel_name).is_youtube_workflow
