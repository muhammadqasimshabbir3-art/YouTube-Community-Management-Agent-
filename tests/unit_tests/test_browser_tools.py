"""Unit tests for browser login helpers."""

from agent.custom_tools import browser_tools


def test_login_timeout_defaults_to_45s(monkeypatch):
    monkeypatch.delenv("BROWSER_LOGIN_TIMEOUT_MS", raising=False)
    assert browser_tools._login_timeout_ms() == 45000


def test_login_timeout_respects_env(monkeypatch):
    monkeypatch.setenv("BROWSER_LOGIN_TIMEOUT_MS", "60000")
    assert browser_tools._login_timeout_ms() == 60000


def test_login_timeout_has_minimum(monkeypatch):
    monkeypatch.setenv("BROWSER_LOGIN_TIMEOUT_MS", "1000")
    assert browser_tools._login_timeout_ms() == 15000
