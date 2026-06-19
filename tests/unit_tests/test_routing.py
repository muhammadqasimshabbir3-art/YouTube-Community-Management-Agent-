"""Unit tests for YouTube routing helpers."""

from agent.routing import (
    extract_channel_name,
    extract_channel_url,
    wants_email_report,
    wants_pdf_report,
    wants_youtube_analysis,
)


def test_extract_channel_url():
    text = "Analyze https://www.youtube.com/@TestChannel comments"
    assert extract_channel_url(text) == "https://www.youtube.com/@TestChannel"


def test_extract_channel_name():
    text = "Analyze the Test Creator channel comments"
    assert extract_channel_name(text) == "Test Creator"


def test_youtube_analysis_intent():
    assert wants_youtube_analysis("analyze youtube comments for my channel")
    assert not wants_youtube_analysis(
        "", state_channel_url="https://www.youtube.com/@test"
    )
    assert not wants_youtube_analysis("what is the weather today")


def test_pdf_report_intent():
    assert wants_pdf_report("generate a pdf report")
    assert not wants_pdf_report("hello")


def test_email_report_intent():
    assert wants_email_report("email me the report")
    assert not wants_email_report("hello")
