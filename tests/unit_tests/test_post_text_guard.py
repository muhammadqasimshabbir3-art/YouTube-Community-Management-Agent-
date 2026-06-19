"""Tests for blocked post text and reply helpers."""

from agent.custom_tools.youtube_tools import _is_blocked_post_text


def test_blocked_post_text_rejects_diagnostics():
    assert _is_blocked_post_text("Automated test comment - please ignore (agent diagnostic)")
    assert _is_blocked_post_text("test comment from automation")
    assert not _is_blocked_post_text("Thanks for vibing with this track — what part hit you hardest?")
