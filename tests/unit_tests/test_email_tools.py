"""Unit tests for SMTP email tools."""

from unittest.mock import MagicMock, patch

from agent.custom_tools.email_tools import send_smtp_email


def test_missing_smtp_user(monkeypatch):
    monkeypatch.delenv("GMAIL_SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "secret")

    result = send_smtp_email("Subject", "Body")
    assert "GMAIL_SMTP_USER is not set" in result


def test_missing_app_password(monkeypatch):
    monkeypatch.setenv("GMAIL_SMTP_USER", "user@gmail.com")
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    result = send_smtp_email("Subject", "Body")
    assert "GMAIL_APP_PASSWORD is not set" in result


def test_missing_attachment(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_SMTP_USER", "user@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "secret")
    monkeypatch.setenv("GMAIL_DEFAULT_RECIPIENT", "recipient@gmail.com")

    missing = tmp_path / "missing.pdf"
    result = send_smtp_email(
        "Subject",
        "Body",
        attachment_paths=str(missing),
    )
    assert "Attachment not found" in result


@patch("agent.custom_tools.email_tools.smtplib.SMTP")
def test_send_email_success(mock_smtp, tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("GMAIL_DEFAULT_RECIPIENT", "recipient@gmail.com")

    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"%PDF-1.4 test")

    server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = server

    result = send_smtp_email(
        "Monthly Report",
        "Please find the attached report.",
        attachment_paths=str(attachment),
    )

    assert "Email sent successfully to recipient@gmail.com" in result
    assert "report.pdf" in result
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("sender@gmail.com", "app-password")
    server.sendmail.assert_called_once()
