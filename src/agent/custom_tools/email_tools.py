"""SMTP email tools for sending reports and agent output via Gmail."""

from __future__ import annotations

import mimetypes
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from langchain.tools import tool

from agent.async_utils import run_in_thread


def _get_smtp_config() -> dict[str, str]:
    """Load Gmail SMTP settings from environment variables."""
    username = os.getenv("GMAIL_SMTP_USER") or os.getenv("SMTP_USERNAME", "")
    password = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASSWORD", "")
    host = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
    port = os.getenv("GMAIL_SMTP_PORT", "587")
    default_recipient = (
        os.getenv("GMAIL_DEFAULT_RECIPIENT") or os.getenv("SMTP_TO_EMAIL") or username
    )
    return {
        "username": username.strip(),
        "password": password.strip(),
        "host": host.strip(),
        "port": port.strip(),
        "default_recipient": default_recipient.strip(),
    }


def _parse_attachment_paths(attachment_paths: str | None) -> list[Path]:
    if not attachment_paths or not attachment_paths.strip():
        return []

    paths: list[Path] = []
    for raw_path in attachment_paths.split(","):
        path = Path(raw_path.strip())
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {path}")
        if not path.is_file():
            raise ValueError(f"Attachment path is not a file: {path}")
        paths.append(path)
    return paths


def send_smtp_email(
    subject: str,
    body: str,
    to_email: str = "",
    attachment_paths: str | None = None,
) -> str:
    """Send an email with optional file attachments over SMTP."""
    config = _get_smtp_config()
    if not config["username"]:
        return (
            "Email error: GMAIL_SMTP_USER is not set in .env. "
            "Add your Gmail address before sending email."
        )
    if not config["password"]:
        return (
            "Email error: GMAIL_APP_PASSWORD is not set in .env. "
            "Add your Gmail app password before sending email."
        )

    recipient = (to_email or config["default_recipient"]).strip()
    if not recipient:
        return (
            "Email error: No recipient provided. "
            "Set to_email or GMAIL_DEFAULT_RECIPIENT in .env."
        )

    try:
        attachments = _parse_attachment_paths(attachment_paths)
    except (FileNotFoundError, ValueError) as exc:
        return f"Email error: {exc}"

    message = MIMEMultipart()
    message["From"] = config["username"]
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    attached_names: list[str] = []
    for path in attachments:
        mime_type, _ = mimetypes.guess_type(path.name)
        _, subtype = (mime_type or "application/octet-stream").split("/", 1)
        with path.open("rb") as file_handle:
            part = MIMEApplication(file_handle.read(), _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        message.attach(part)
        attached_names.append(path.name)

    try:
        with smtplib.SMTP(config["host"], int(config["port"]), timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["username"], config["password"])
            server.sendmail(config["username"], [recipient], message.as_string())
    except smtplib.SMTPAuthenticationError:
        return (
            "Email error: SMTP authentication failed. "
            "Check GMAIL_SMTP_USER and GMAIL_APP_PASSWORD in .env."
        )
    except smtplib.SMTPException as exc:
        return f"Email error: SMTP send failed: {exc}"
    except OSError as exc:
        return f"Email error: Could not connect to SMTP server: {exc}"

    attachment_summary = ", ".join(attached_names) if attached_names else "none"
    return (
        f"Email sent successfully to {recipient}.\n"
        f"Subject: {subject}\n"
        f"Attachments: {attachment_summary}"
    )


@tool
async def send_email(
    subject: str,
    body: str,
    to_email: str = "",
    attachment_paths: str = "",
) -> str:
    """Send an email report via Gmail SMTP with optional PDF/file attachments.

    Use this tool when the user asks to email, share, or send a report, summary,
    or generated output. After creating a PDF with generate_pdf_report or
    generate_table_report, pass the saved file path in attachment_paths.

    Gmail credentials are read from .env:
    - GMAIL_SMTP_USER: sender Gmail address
    - GMAIL_APP_PASSWORD: Gmail app password
    - GMAIL_DEFAULT_RECIPIENT: default recipient if to_email is omitted

    Args:
        subject: Email subject line.
        body: Plain-text email body. Include the agent summary or report text here.
        to_email: Recipient email address. Leave empty to use GMAIL_DEFAULT_RECIPIENT.
        attachment_paths: Comma-separated file paths to attach (e.g. ./reports/report.pdf).

    Returns:
        Success or error message describing the send result.
    """
    paths = attachment_paths.strip() or None
    return await run_in_thread(send_smtp_email, subject, body, to_email, paths)


__all__ = ["send_email", "send_smtp_email"]
