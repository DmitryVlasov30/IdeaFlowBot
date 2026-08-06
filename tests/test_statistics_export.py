from zipfile import ZipFile

import pytest

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
    assert "Channel A" in sheet_xml
    assert "<v>123</v>" in sheet_xml
    assert "<v>7</v>" in sheet_xml


def test_statistics_delta_days_validation() -> None:
    assert validate_statistics_delta_days("14") == 14

    with pytest.raises(ValueError):
        validate_statistics_delta_days("15")

    with pytest.raises(ValueError):
        validate_statistics_delta_days("abc")
