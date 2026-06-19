"""Tests for report file output helpers."""

from agent.custom_tools.report_io import prepare_report_output_path


def test_prepare_report_output_path_removes_existing_file(tmp_path):
    report_path = tmp_path / "reports" / "channel_dashboard_report.html"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("old content", encoding="utf-8")

    prepared = prepare_report_output_path(report_path)

    assert prepared == report_path
    assert report_path.parent.is_dir()
    assert not report_path.exists()


def test_prepare_report_output_path_creates_missing_directory(tmp_path):
    report_path = tmp_path / "reports" / "channel_community_report.pdf"

    prepared = prepare_report_output_path(report_path)

    assert prepared == report_path
    assert report_path.parent.is_dir()
    assert not report_path.exists()
