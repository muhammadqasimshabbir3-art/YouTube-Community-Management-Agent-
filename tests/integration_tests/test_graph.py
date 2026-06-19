# """Integration tests for the YouTube Community Manager graph."""
#
# import pytest
# from langchain_core.messages import HumanMessage
#
# from agent import graph
# from agent.graph import decision_agent, _pick_route
#
# pytestmark = pytest.mark.anyio
#
#
# @pytest.mark.langsmith
# async def test_agent_initialization() -> None:
#     """Test that the agent graph is initialized correctly."""
#     assert graph is not None
#     assert graph.invoke is not None
#
#
# @pytest.mark.langsmith
# async def test_agent_with_simple_query() -> None:
#     """Test agent with a simple chat query routes to call_model, not YouTube login."""
#     inputs = {
#         "messages": [HumanMessage(content="Hello, what can you help me with?")],
#         "user_input": "Hello, what can you help me with?",
#     }
#     result = await graph.ainvoke(inputs)
#     assert result is not None
#     assert "messages" in result
#     assert len(result["messages"]) > 0
#     assert result.get("agent_route", "call_model") == "call_model"
#
#
# @pytest.mark.langsmith
# async def test_decision_agent_routes_youtube_workflow() -> None:
#     """Test decision agent selects youtube_workflow for explicit analyze requests."""
#     state = {
#         "messages": [HumanMessage(content="Analyze YouTube channel comments")],
#         "user_input": "Analyze YouTube channel comments",
#         "youtube_channel_url": "https://www.youtube.com/@example",
#         "workflow_action": "analyze",
#     }
#     decision = await decision_agent(state)
#     assert decision.get("agent_route") == "youtube_workflow"
#
#
# def test_pick_route_ignores_env_channel_for_general_chat() -> None:
#     """General chat must not enter YouTube workflow when only .env has a channel."""
#     messages = [HumanMessage(content="Hello, what can you help me with?")]
#     state = {
#         "youtube_channel_name": "MrBeast",
#         "youtube_channel_url": "https://www.youtube.com/@mrbeast",
#     }
#     route = _pick_route(state, messages, "Hello, what can you help me with?")
#     assert route == "call_model"
#
#
# @pytest.mark.langsmith
# async def test_agent_youtube_workflow_with_mocks() -> None:
#     """Test full YouTube workflow completes with stubbed browser/fetch."""
#     inputs = {
#         "messages": [HumanMessage(content="Analyze YouTube channel comments")],
#         "user_input": "Analyze YouTube channel comments",
#         "youtube_channel_url": "https://www.youtube.com/@example",
#         "workflow_action": "analyze",
#     }
#     result = await graph.ainvoke(inputs)
#     assert result is not None
#     assert result.get("agent_route") == "youtube_workflow"
#     assert result.get("comments")
#     assert result.get("html_path")
