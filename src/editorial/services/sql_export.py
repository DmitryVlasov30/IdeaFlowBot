from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from src.core_database.config import BASE_DIR
from src.editorial.db.session import engine


@dataclass(slots=True)
class SqlExportResult:
    path: Path
    statement_type: str
    rows_written: int
    returned_rows: bool


class SqlExportService:
    def __init__(self, export_dir: Path | None = None) -> None:
        self.export_dir = export_dir or (BASE_DIR / "exports" / "sql")

    async def export_query(self, query: str, allow_mutating: bool) -> SqlExportResult:
        normalized_query = self._normalize_query(query)
        statement_type = self._statement_type(normalized_query)

        if not allow_mutating and not self._is_read_only_query(normalized_query):
            raise ValueError("Модераторам разрешены только SELECT-запросы.")

        self.export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_path = self.export_dir / f"sql_export_{statement_type}_{timestamp}.csv"

        if self._is_read_only_query(normalized_query):
            async with engine.connect() as conn:
                result = await conn.execute(text(normalized_query))
                headers = list(result.keys())
                rows = result.fetchall()

            self._write_rows_csv(export_path, headers, rows)
            return SqlExportResult(
                path=export_path,
                statement_type=statement_type,
                rows_written=len(rows),
                returned_rows=True,
            )

        async with engine.begin() as conn:
            result = await conn.execute(text(normalized_query))
            rowcount = result.rowcount if result.rowcount is not None else 0

        self._write_summary_csv(
            export_path,
            statement_type=statement_type,
            rowcount=rowcount,
        )
        return SqlExportResult(
            path=export_path,
            statement_type=statement_type,
            rows_written=1,
            returned_rows=False,
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Нужен SQL-запрос.")
        if normalized.endswith(";"):
            normalized = normalized[:-1].strip()
        if not normalized:
            raise ValueError("Нужен SQL-запрос.")
        if ";" in normalized:
            raise ValueError("Разрешён только один SQL-запрос за раз.")
        return normalized

    @staticmethod
    def _statement_type(query: str) -> str:
        stripped = SqlExportService._strip_leading_comments(query)
        return (stripped.split(maxsplit=1)[0].lower() if stripped else "query")

    @staticmethod
    def _is_read_only_query(query: str) -> bool:
        stripped = SqlExportService._strip_leading_comments(query).lower()
        return stripped.startswith("select") or stripped.startswith("with")

    @staticmethod
    def _strip_leading_comments(query: str) -> str:
        stripped = query.lstrip()
        while True:
            if stripped.startswith("--"):
                newline_index = stripped.find("\n")
                if newline_index == -1:
                    return ""
                stripped = stripped[newline_index + 1 :].lstrip()
                continue
            if stripped.startswith("/*"):
                comment_end = stripped.find("*/")
                if comment_end == -1:
                    return ""
                stripped = stripped[comment_end + 2 :].lstrip()
                continue
            return stripped

    @staticmethod
    def _normalize_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (str, int, float)):
            return str(value)
        if isinstance(value, bool):
            return "true" if value else "false"
        if hasattr(value, "value"):
            return str(value.value)
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _write_rows_csv(self, export_path: Path, headers: list[str], rows: list[Any]) -> None:
        with export_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([self._normalize_value(value) for value in row])

    def _write_summary_csv(self, export_path: Path, statement_type: str, rowcount: int) -> None:
        with export_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["status", "statement_type", "rows_affected", "executed_at_utc"])
            writer.writerow(
                [
                    "ok",
                    statement_type,
                    rowcount,
                    datetime.now(timezone.utc).isoformat(),
                ]
            )
