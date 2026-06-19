"""Tests for LangGraph workflow structure shown in LangSmith Studio."""

from agent.graph import graph


def test_graph_workflow_nodes_for_langsmith():
    nodes = set(graph.get_graph().nodes.keys())
    expected = {
        "__start__",
        "__end__",
        "prepare_agent",
        "decide_agent",
        "login_youtube",
        "fetch_channel_data",
        "analyze_comments",
        "select_reply_targets",
        "generate_replies",
        "post_replies",
        "generate_new_comment",
        "post_new_comment",
        "generate_html_report",
        "generate_pdf_report",
        "email_report",
        "execute_workflow",
        "call_tool",
        "tools",
    }
    assert expected.issubset(nodes)


def test_graph_main_pipeline_edges():
    edge_pairs = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    pipeline = [
        ("__start__", "prepare_agent"),
        ("prepare_agent", "decide_agent"),
        ("login_youtube", "fetch_channel_data"),
        ("fetch_channel_data", "analyze_comments"),
        ("analyze_comments", "select_reply_targets"),
        ("select_reply_targets", "generate_replies"),
        ("generate_new_comment", "post_new_comment"),
        ("post_new_comment", "generate_html_report"),
        ("generate_html_report", "generate_pdf_report"),
        ("generate_pdf_report", "email_report"),
        ("email_report", "__end__"),
    ]
    for source, target in pipeline:
        assert (source, target) in edge_pairs, f"Missing edge {source} -> {target}"
