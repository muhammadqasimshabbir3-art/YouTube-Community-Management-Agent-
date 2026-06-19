"""Tests for graph routing with env channel defaults."""

from langchain_core.messages import HumanMessage

from agent.graph import _pick_route


def test_general_chat_not_routed_to_youtube_with_env_channel_in_state():
    messages = [HumanMessage(content="Hello there")]
    state = {
        "youtube_channel_name": "MrBeast",
        "youtube_channel_url": "https://www.youtube.com/@mrbeast",
    }
    assert _pick_route(state, messages, "Hello there") == "call_model"


def test_workflow_action_routes_to_youtube():
    messages = [HumanMessage(content="run analysis")]
    state = {"workflow_action": "analyze", "youtube_channel_name": "MrBeast"}
    assert _pick_route(state, messages, "run analysis") == "youtube_workflow"
