"""Tests for env-driven graph input bootstrap."""

import pytest
from langchain_core.messages import HumanMessage

from agent.graph import _pick_route, prepare_input


@pytest.mark.anyio
async def test_prepare_input_bootstraps_from_env(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CHANNEL_NAME", "MrBeast")
    monkeypatch.setenv("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@mrbeast")
    from agent.config import get_youtube_config

    get_youtube_config.cache_clear()

    updates = await prepare_input({})

    get_youtube_config.cache_clear()
    assert updates["workflow_action"] == "analyze"
    assert updates["youtube_channel_name"] == "MrBeast"
    assert updates["youtube_channel_url"] == "https://www.youtube.com/@mrbeast"
    assert updates["messages"]
    assert isinstance(updates["messages"][0], HumanMessage)


@pytest.mark.anyio
async def test_env_only_run_routes_to_youtube_workflow(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CHANNEL_NAME", "MrBeast")
    from agent.config import get_youtube_config

    get_youtube_config.cache_clear()
    updates = await prepare_input({})
    get_youtube_config.cache_clear()

    state = {**updates}
    messages = state["messages"]
    user_text = messages[0].content
    route = _pick_route(state, messages, user_text)
    assert route == "youtube_workflow"
