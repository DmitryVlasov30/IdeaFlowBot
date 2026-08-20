from datetime import date, datetime, timezone
from zipfile import ZipFile

import pytest

from src.panel_markups import build_extra_panel
from src.editorial.services.admin_statistics_export import (
    AdminModerationDetailRow,
    AdminStatisticsExportService,
    admin_statistics_month_bounds,
    parse_admin_statistics_month,
)


def _detail(case_id: int, moderator_id: int, decision: str, source_user_id: int):
    return AdminModerationDetailRow(
        case_id=case_id,
        canonical_submission_id=case_id + 100,
        moderator_id=moderator_id,
        moderator_label=f"@admin{moderator_id}",
        decision=decision,
        finalized_at=datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc),
        channel_label="Test channel",
        source_user_id=source_user_id,
        source_username=f"user{source_user_id}",
        source_first_name="User",
        source_message_id=case_id + 1000,
        source="panel",
        action="approve_submission" if decision == "approved" else "reject_submission",
        message_text=f"Proposal {case_id}",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08", date(2026, 8, 1)),
        ("08.2026", date(2026, 8, 1)),
        ("текущий", date(2026, 8, 1)),
    ],
)
def test_parse_admin_statistics_month(value, expected):
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    assert parse_admin_statistics_month(value, now=now) == expected


def test_month_bounds_use_moscow_calendar_month():
    started_at, ended_at = admin_statistics_month_bounds(date(2026, 8, 1))
    assert started_at == datetime(2026, 7, 31, 21, 0, tzinfo=timezone.utc)
    assert ended_at == datetime(2026, 8, 31, 21, 0, tzinfo=timezone.utc)


def test_summary_counts_each_case_once_and_flags_self_submissions():
    details = [
        _detail(1, 100, "approved", 500),
        _detail(2, 100, "rejected", 100),
    ]

    rows = AdminStatisticsExportService._build_summary_rows(
        details,
        admin_labels={100: "@moderator", 200: "@without_actions"},
    )

    moderator = next(row for row in rows if row.moderator_id == 100)
    empty_admin = next(row for row in rows if row.moderator_id == 200)
    assert moderator.approved_count == 1
    assert moderator.rejected_count == 1
    assert moderator.total_count == 2
    assert moderator.self_submission_count == 1
    assert "Proposal 1" in moderator.approved_messages
    assert "Proposal 2" in moderator.rejected_messages
    assert empty_admin.total_count == 0


def test_admin_statistics_xlsx_contains_summary_and_full_details(tmp_path):
    service = AdminStatisticsExportService(tmp_path)
    details = [_detail(1, 100, "approved", 100)]
    summaries = service._build_summary_rows(details, admin_labels={100: "@moderator"})
    path = tmp_path / "admin_statistics.xlsx"

    service._write_xlsx(
        path,
        month=date(2026, 8, 1),
        summaries=summaries,
        details=details,
    )

    with ZipFile(path) as archive:
        names = set(archive.namelist())
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        summary = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        detail = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "xl/worksheets/sheet1.xml" in names
    assert "xl/worksheets/sheet2.xml" in names
    assert "Сводка" in workbook
    assert "Детализация" in workbook
    assert "@moderator" in summary
    assert "Proposal 1" in detail
    assert "ДА" in detail


def test_admin_statistics_button_is_only_shown_to_general_admin():
    general_callbacks = {
        button.callback_data
        for row in build_extra_panel(is_general_admin=True).keyboard
        for button in row
    }
    moderator_callbacks = {
        button.callback_data
        for row in build_extra_panel(is_general_admin=False).keyboard
        for button in row
    }

    assert "panel:admin_stats_export" in general_callbacks
    assert "panel:admin_stats_export" not in moderator_callbacks
