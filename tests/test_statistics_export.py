from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import pytest

from src.editorial.models.channel import Channel
from src.editorial.services.statistics_export import (
    ChannelStatisticsRow,
    StatisticsExportService,
    validate_statistics_delta_days,
)


def test_statistics_export_writes_minimal_xlsx(tmp_path) -> None:
    export_path = tmp_path / "stats.xlsx"
    service = StatisticsExportService(export_dir=tmp_path)

    service._write_xlsx(
        export_path,
        [
            ChannelStatisticsRow(
                title="Channel A",
                tag="@channel_a",
                subscriber_count=123,
                delta_count=7,
                submission_count=11,
            )
        ],
        delta_days=10,
    )

    with ZipFile(export_path) as archive:
        names = set(archive.namelist())
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "xl/workbook.xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "Название канала" in sheet_xml
    assert "Изменение за 10 дн." in sheet_xml
    assert "Сообщений в предложку за 10 дн." in sheet_xml
    assert "Channel A" in sheet_xml
    assert "<v>123</v>" in sheet_xml
    assert "<v>7</v>" in sheet_xml
    assert "<v>11</v>" in sheet_xml
    assert 'autoFilter ref="A1:E2"' in sheet_xml


@pytest.mark.asyncio
async def test_statistics_rows_count_real_submissions_in_requested_period() -> None:
    now = datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)
    channel = Channel(
        id=42,
        tg_channel_id=-100123,
        title="Channel A",
        short_code="channel_a",
        subscriber_count=123,
    )
    channel_without_submissions = Channel(
        id=43,
        tg_channel_id=-100124,
        title="Channel B",
        short_code="channel_b",
        subscriber_count=456,
    )
    channels_result = MagicMock()
    channels_result.scalars.return_value.all.return_value = [channel, channel_without_submissions]
    counts_result = MagicMock()
    counts_result.all.return_value = [(channel.id, 5)]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[channels_result, counts_result])
    session.scalar = AsyncMock(return_value=None)

    rows = await StatisticsExportService()._build_rows(
        session,
        channel_titles={},
        channel_tags={},
        delta_days=5,
        now=now,
    )

    assert rows == [
        ChannelStatisticsRow(
            title="Channel A",
            tag="channel_a",
            subscriber_count=123,
            delta_count=None,
            submission_count=5,
        ),
        ChannelStatisticsRow(
            title="Channel B",
            tag="channel_b",
            subscriber_count=456,
            delta_count=None,
            submission_count=0,
        ),
    ]
    count_stmt = session.execute.await_args_list[1].args[0]
    compiled_params = list(count_stmt.compile().params.values())
    assert now - timedelta(days=5) in compiled_params
    assert now in compiled_params
    assert [channel.id, channel_without_submissions.id] in compiled_params
    sql = str(count_stmt)
    assert "submissions.created_at >=" in sql
    assert "submissions.created_at <=" in sql
    assert "GROUP BY submissions.channel_id" in sql
    assert "submissions.source_chat_id IS NULL" in sql


@pytest.mark.asyncio
async def test_submission_counts_skip_query_without_channels() -> None:
    session = MagicMock()
    session.execute = AsyncMock()

    counts = await StatisticsExportService._submission_counts(
        session,
        channel_ids=[],
        started_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        ended_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )

    assert counts == {}
    session.execute.assert_not_awaited()


def test_statistics_delta_days_validation() -> None:
    assert validate_statistics_delta_days("14") == 14

    with pytest.raises(ValueError):
        validate_statistics_delta_days("15")

    with pytest.raises(ValueError):
        validate_statistics_delta_days("abc")
