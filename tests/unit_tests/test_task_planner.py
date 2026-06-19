"""Tests for YouTube task planner."""

from agent.task_planner import is_youtube_workflow_request, plan_tasks


def test_youtube_workflow_plan():
    plan = plan_tasks(
        "analyze youtube channel comments",
        channel_url="https://www.youtube.com/@testchannel",
    )
    assert plan.is_youtube_workflow
    assert "login" in plan.tasks
    assert "fetch_channel" in plan.tasks
    assert "analyze" in plan.tasks
    assert "select_reply_targets" in plan.tasks
    assert "generate_replies" in plan.tasks
    assert "generate_new_comment" in plan.tasks
    assert "generate_html" in plan.tasks


def test_report_workflow_includes_pdf():
    plan = plan_tasks(
        "analyze channel and generate pdf report",
        channel_name="Test Channel",
        workflow_action="report",
    )
    assert "generate_pdf" in plan.tasks
    assert "generate_html" in plan.tasks


def test_email_workflow_includes_email():
    plan = plan_tasks(
        "analyze channel and email report",
        channel_name="Test Channel",
        workflow_action="email",
    )
    assert "generate_pdf" in plan.tasks
    assert "generate_html" in plan.tasks
    assert "email_report" in plan.tasks


def test_non_youtube_request():
    plan = plan_tasks("hello there")
    assert not plan.is_youtube_workflow
    assert not is_youtube_workflow_request("hello there")
