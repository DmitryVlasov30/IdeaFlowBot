from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import re
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core_database.config import BASE_DIR
from src.editorial.models.channel import Channel
from src.editorial.models.moderation_case import ModerationCase
from src.editorial.services.moderation_case_service import MODERATION_APPROVED, MODERATION_REJECTED


STATISTICS_TIMEZONE = ZoneInfo("Europe/Moscow")
EXCEL_CELL_TEXT_LIMIT = 32_000
INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def parse_admin_statistics_month(value: str, now: datetime | None = None) -> date:
    cleaned = value.strip().lower()
    local_now = (now or datetime.now(timezone.utc)).astimezone(STATISTICS_TIMEZONE)
    if cleaned in {"", "текущий", "текущий месяц"}:
        return date(local_now.year, local_now.month, 1)
    for fmt in ("%Y-%m", "%m.%Y"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        return date(parsed.year, parsed.month, 1)
    raise ValueError("Введите месяц в формате ГГГГ-ММ или ММ.ГГГГ, например 2026-08")


def admin_statistics_month_bounds(month: date) -> tuple[datetime, datetime]:
    started_local = datetime(month.year, month.month, 1, tzinfo=STATISTICS_TIMEZONE)
    if month.month == 12:
        ended_local = datetime(month.year + 1, 1, 1, tzinfo=STATISTICS_TIMEZONE)
    else:
        ended_local = datetime(month.year, month.month + 1, 1, tzinfo=STATISTICS_TIMEZONE)
    return started_local.astimezone(timezone.utc), ended_local.astimezone(timezone.utc)


@dataclass(slots=True)
class AdminModerationDetailRow:
    case_id: int
    canonical_submission_id: int | None
    moderator_id: int
    moderator_label: str
    decision: str
    finalized_at: datetime
    channel_label: str
    source_user_id: int | None
    source_username: str | None
    source_first_name: str | None
    source_message_id: int | None
    source: str
    action: str
    message_text: str

    @property
    def is_self_submission(self) -> bool:
        return self.source_user_id is not None and self.source_user_id == self.moderator_id


@dataclass(slots=True)
class AdminModerationSummaryRow:
    moderator_id: int
    moderator_label: str
    approved_count: int
    rejected_count: int
    self_submission_count: int
    approved_messages: str
    rejected_messages: str

    @property
    def total_count(self) -> int:
        return self.approved_count + self.rejected_count


class AdminStatisticsExportService:
    def __init__(self, export_dir: Path | None = None) -> None:
        self.export_dir = export_dir or (BASE_DIR / "exports")

    async def export_admin_statistics(
        self,
        session: AsyncSession,
        *,
        month: date,
        admin_labels: dict[int, str] | None = None,
    ) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        admin_labels = admin_labels or {}
        started_at, ended_at = admin_statistics_month_bounds(month)
        details = await self._build_detail_rows(
            session,
            started_at=started_at,
            ended_at=ended_at,
            admin_labels=admin_labels,
        )
        summaries = self._build_summary_rows(details, admin_labels=admin_labels)
        path = self.export_dir / f"admin_statistics_{month:%Y_%m}.xlsx"
        self._write_xlsx(path, month=month, summaries=summaries, details=details)
        return path

    @staticmethod
    async def _build_detail_rows(
        session: AsyncSession,
        *,
        started_at: datetime,
        ended_at: datetime,
        admin_labels: dict[int, str],
    ) -> list[AdminModerationDetailRow]:
        result = await session.execute(
            select(ModerationCase, Channel.title, Channel.short_code)
            .outerjoin(Channel, Channel.id == ModerationCase.channel_id)
            .where(
                ModerationCase.finalized_at >= started_at,
                ModerationCase.finalized_at < ended_at,
                ModerationCase.voided_at.is_(None),
                ModerationCase.decision.in_({MODERATION_APPROVED, MODERATION_REJECTED}),
                ModerationCase.source != "mcp_codex",
            )
            .order_by(ModerationCase.moderator_id.asc(), ModerationCase.finalized_at.asc())
        )
        rows: list[AdminModerationDetailRow] = []
        for case, channel_title, channel_short_code in result.all():
            channel_label = channel_title or channel_short_code or (
                str(case.channel_tg_id) if case.channel_tg_id is not None else "-"
            )
            rows.append(
                AdminModerationDetailRow(
                    case_id=case.id,
                    canonical_submission_id=case.canonical_submission_id,
                    moderator_id=int(case.moderator_id),
                    moderator_label=admin_labels.get(int(case.moderator_id), str(case.moderator_id)),
                    decision=case.decision,
                    finalized_at=case.finalized_at,
                    channel_label=channel_label,
                    source_user_id=case.source_user_id,
                    source_username=case.source_username,
                    source_first_name=case.source_first_name,
                    source_message_id=case.source_message_id,
                    source=case.source,
                    action=case.action,
                    message_text=case.message_text,
                )
            )
        return rows

    @staticmethod
    def _build_summary_rows(
        details: list[AdminModerationDetailRow],
        *,
        admin_labels: dict[int, str],
    ) -> list[AdminModerationSummaryRow]:
        grouped: dict[int, list[AdminModerationDetailRow]] = defaultdict(list)
        for row in details:
            grouped[row.moderator_id].append(row)
        for admin_id in admin_labels:
            grouped.setdefault(admin_id, [])

        summaries: list[AdminModerationSummaryRow] = []
        for moderator_id in sorted(grouped):
            rows = grouped[moderator_id]
            approved = [row for row in rows if row.decision == MODERATION_APPROVED]
            rejected = [row for row in rows if row.decision == MODERATION_REJECTED]
            summaries.append(
                AdminModerationSummaryRow(
                    moderator_id=moderator_id,
                    moderator_label=admin_labels.get(
                        moderator_id,
                        rows[0].moderator_label if rows else str(moderator_id),
                    ),
                    approved_count=len(approved),
                    rejected_count=len(rejected),
                    self_submission_count=sum(row.is_self_submission for row in rows),
                    approved_messages=AdminStatisticsExportService._message_list(approved),
                    rejected_messages=AdminStatisticsExportService._message_list(rejected),
                )
            )
        return summaries

    @staticmethod
    def _message_list(rows: list[AdminModerationDetailRow]) -> str:
        parts = []
        for row in rows:
            author = f"@{row.source_username}" if row.source_username else str(row.source_user_id or "-")
            compact_text = " ".join((row.message_text or "").split())
            parts.append(f"case #{row.case_id}, автор {author}: {compact_text}")
        value = "\n".join(parts)
        if len(value) > EXCEL_CELL_TEXT_LIMIT:
            return value[: EXCEL_CELL_TEXT_LIMIT - 35] + "\n…полный список на листе Детализация"
        return value

    def _write_xlsx(
        self,
        path: Path,
        *,
        month: date,
        summaries: list[AdminModerationSummaryRow],
        details: list[AdminModerationDetailRow],
    ) -> None:
        period_label = f"{month:%m.%Y}"
        summary_rows: list[list[object | None]] = [
            [f"Статистика обработки предложек за {period_label}"],
            ["Учитывается одна текущая итоговая запись на одну предложку или медиагруппу"],
            [
                "Администратор",
                "Telegram ID",
                "Одобрено",
                "Отклонено",
                "Всего обработано",
                "Своих предложек",
                "Одобренные сообщения",
                "Отклонённые сообщения",
            ],
        ]
        summary_rows.extend(
            [
                row.moderator_label,
                row.moderator_id,
                row.approved_count,
                row.rejected_count,
                row.total_count,
                row.self_submission_count,
                row.approved_messages,
                row.rejected_messages,
            ]
            for row in summaries
        )

        detail_rows: list[list[object | None]] = [
            [f"Детализация обработки предложек за {period_label}"],
            ["Строки со значением ДА в столбце «Сам себе» требуют проверки"],
            [
                "Администратор",
                "ID администратора",
                "Решение",
                "Дата решения",
                "Канал",
                "Case ID",
                "Submission ID",
                "ID автора",
                "Username автора",
                "Имя автора",
                "Сам себе",
                "ID сообщения автора",
                "Источник модерации",
                "Действие",
                "Текст предложки",
            ],
        ]
        detail_rows.extend(
            [
                row.moderator_label,
                row.moderator_id,
                "Одобрено" if row.decision == MODERATION_APPROVED else "Отклонено",
                row.finalized_at,
                row.channel_label,
                row.case_id,
                row.canonical_submission_id,
                row.source_user_id,
                f"@{row.source_username}" if row.source_username else "-",
                row.source_first_name or "-",
                "ДА" if row.is_self_submission else "нет",
                row.source_message_id,
                row.source,
                row.action,
                row.message_text,
            ]
            for row in details
        )

        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", self._content_types_xml())
            archive.writestr("_rels/.rels", self._root_rels_xml())
            archive.writestr("xl/workbook.xml", self._workbook_xml())
            archive.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml())
            archive.writestr("xl/styles.xml", self._styles_xml())
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                self._sheet_xml(
                    summary_rows,
                    widths=[24, 18, 14, 14, 18, 18, 58, 58],
                    alert_column=6,
                    wrap_columns={7, 8},
                    data_row_height=54,
                ),
            )
            archive.writestr(
                "xl/worksheets/sheet2.xml",
                self._sheet_xml(
                    detail_rows,
                    widths=[24, 18, 14, 20, 24, 12, 15, 16, 22, 22, 12, 18, 18, 24, 72],
                    alert_column=11,
                    wrap_columns={15},
                    data_row_height=42,
                ),
            )

    @staticmethod
    def _cell_ref(row_index: int, col_index: int) -> str:
        letters = ""
        value = col_index
        while value:
            value, remainder = divmod(value - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row_index}"

    def _sheet_xml(
        self,
        rows: list[list[object | None]],
        *,
        widths: list[int],
        alert_column: int | None = None,
        wrap_columns: set[int] | None = None,
        data_row_height: int = 18,
    ) -> str:
        wrap_columns = wrap_columns or set()
        row_xml: list[str] = []
        for row_index, row in enumerate(rows, start=1):
            cells: list[str] = []
            for col_index, value in enumerate(row, start=1):
                ref = self._cell_ref(row_index, col_index)
                style_id = 4 if row_index == 1 else 1 if row_index == 3 else 0
                if row_index > 3 and col_index in wrap_columns:
                    style_id = 5
                if row_index > 3 and alert_column == col_index and value not in {None, 0, "нет"}:
                    style_id = 3
                style = f' s="{style_id}"' if style_id else ""
                if value is None:
                    cells.append(f'<c r="{ref}"{style}/>')
                elif isinstance(value, datetime):
                    local_value = value.astimezone(STATISTICS_TIMEZONE).replace(tzinfo=None)
                    serial = (local_value - datetime(1899, 12, 30)).total_seconds() / 86400
                    cells.append(f'<c r="{ref}" s="2"><v>{serial:.10f}</v></c>')
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
                else:
                    text = escape(INVALID_XML_CHARS.sub("", str(value)))
                    cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{text}</t></is></c>')
            height = f' ht="{data_row_height}" customHeight="1"' if row_index > 3 else ""
            row_xml.append(f'<row r="{row_index}"{height}>{"".join(cells)}</row>')

        max_col = self._cell_ref(1, max(len(widths), 1))[:-1]
        filter_ref = f"A3:{max_col}{max(len(rows), 3)}"
        cols = "".join(
            f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
            for index, width in enumerate(widths, start=1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheetViews><sheetView workbookViewId="0" showGridLines="0">'
            '<pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
            f'<cols>{cols}</cols>'
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
            '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
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
            '<sheets>'
            '<sheet name="Сводка" sheetId="1" r:id="rId1"/>'
            '<sheet name="Детализация" sheetId="2" r:id="rId2"/>'
            '</sheets>'
            '</workbook>'
        )

    @staticmethod
    def _workbook_rels_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _styles_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="3">'
            '<font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="14"/><name val="Calibri"/></font>'
            '</fonts>'
            '<fills count="4">'
            '<fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>'
            '</fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="6">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
            '<xf numFmtId="22" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>'
            '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
            '</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )
