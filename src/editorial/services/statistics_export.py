from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core_database.config import BASE_DIR
from src.editorial.models.channel import Channel, ChannelSubscriberSnapshot


@dataclass(slots=True)
class ChannelStatisticsRow:
    title: str
    tag: str
    subscriber_count: int | None
    weekly_delta: int | None


class StatisticsExportService:
    def __init__(self, export_dir: Path | None = None) -> None:
        self.export_dir = export_dir or (BASE_DIR / "exports")

    async def export_channel_statistics(
        self,
        session: AsyncSession,
        *,
        channel_titles: dict[int, str | None] | None = None,
        channel_tags: dict[int, str | None] | None = None,
        now: datetime | None = None,
    ) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        now = now or datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        export_path = self.export_dir / f"channel_statistics_{timestamp}.xlsx"

        rows = await self._build_rows(
            session,
            channel_titles=channel_titles or {},
            channel_tags=channel_tags or {},
            now=now,
        )
        self._write_xlsx(export_path, rows)
        return export_path

    async def _build_rows(
        self,
        session: AsyncSession,
        *,
        channel_titles: dict[int, str | None],
        channel_tags: dict[int, str | None],
        now: datetime,
    ) -> list[ChannelStatisticsRow]:
        channels = list(
            (
                await session.execute(
                    select(Channel)
                    .where(Channel.is_active.is_(True))
                    .order_by(Channel.id.asc())
                )
            ).scalars().all()
        )
        week_ago = now - timedelta(days=7)
        rows: list[ChannelStatisticsRow] = []

        for channel in channels:
            current_count = channel.subscriber_count
            if current_count is None:
                latest_snapshot = await self._latest_snapshot(session, channel.id, before=None)
                current_count = latest_snapshot.subscriber_count if latest_snapshot is not None else None

            baseline = await self._latest_snapshot(session, channel.id, before=week_ago)
            weekly_delta = None
            if current_count is not None:
                weekly_delta = current_count - baseline.subscriber_count if baseline is not None else 0

            title = (
                channel_titles.get(channel.id)
                or channel.title
                or channel.short_code
                or str(channel.tg_channel_id)
            )
            tag = channel_tags.get(channel.id) or channel.short_code or str(channel.tg_channel_id)
            rows.append(
                ChannelStatisticsRow(
                    title=title,
                    tag=tag,
                    subscriber_count=current_count,
                    weekly_delta=weekly_delta,
                )
            )
        return rows

    @staticmethod
    async def _latest_snapshot(
        session: AsyncSession,
        channel_id: int,
        before: datetime | None,
    ) -> ChannelSubscriberSnapshot | None:
        stmt = (
            select(ChannelSubscriberSnapshot)
            .where(ChannelSubscriberSnapshot.channel_id == channel_id)
            .order_by(desc(ChannelSubscriberSnapshot.checked_at))
            .limit(1)
        )
        if before is not None:
            stmt = stmt.where(ChannelSubscriberSnapshot.checked_at <= before)
        return await session.scalar(stmt)

    def _write_xlsx(self, path: Path, rows: list[ChannelStatisticsRow]) -> None:
        sheet_rows: list[list[str | int | None]] = [
            ["Название канала", "Тэг канала", "Подписчики", "Изменение за неделю"],
        ]
        sheet_rows.extend(
            [row.title, row.tag, row.subscriber_count, row.weekly_delta]
            for row in rows
        )

        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", self._content_types_xml())
            archive.writestr("_rels/.rels", self._root_rels_xml())
            archive.writestr("xl/workbook.xml", self._workbook_xml())
            archive.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml())
            archive.writestr("xl/styles.xml", self._styles_xml())
            archive.writestr("xl/worksheets/sheet1.xml", self._sheet_xml(sheet_rows))

    @staticmethod
    def _cell_ref(row_index: int, col_index: int) -> str:
        letters = ""
        value = col_index
        while value:
            value, remainder = divmod(value - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row_index}"

    def _sheet_xml(self, rows: list[list[str | int | None]]) -> str:
        row_xml = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                ref = self._cell_ref(row_index, col_index)
                style = ' s="1"' if row_index == 1 else ""
                if value is None:
                    cells.append(f'<c r="{ref}"{style}/>')
                elif isinstance(value, int):
                    cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
                else:
                    text = escape(str(value))
                    cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>')
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        filter_ref = f"A1:D{max(len(rows), 1)}"
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
            'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            '<cols>'
            '<col min="1" max="1" width="34" customWidth="1"/>'
            '<col min="2" max="2" width="24" customWidth="1"/>'
            '<col min="3" max="4" width="18" customWidth="1"/>'
            '</cols>'
            f'<sheetData>{"".join(row_xml)}</sheetData>'
            f'<autoFilter ref="{filter_ref}"/>'
            '</worksheet>'
        )

    @staticmethod
    def _content_types_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )

    @staticmethod
    def _root_rels_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _workbook_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Статистика" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        )

    @staticmethod
    def _workbook_rels_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _styles_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )
