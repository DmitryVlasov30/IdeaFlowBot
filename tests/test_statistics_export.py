from zipfile import ZipFile

from src.editorial.services.statistics_export import ChannelStatisticsRow, StatisticsExportService


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
                weekly_delta=7,
            )
        ],
    )

    with ZipFile(export_path) as archive:
        names = set(archive.namelist())
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "xl/workbook.xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "Название канала" in sheet_xml
    assert "Channel A" in sheet_xml
    assert "<v>123</v>" in sheet_xml
    assert "<v>7</v>" in sheet_xml
