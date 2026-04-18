from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from sqlalchemy import select, text

import src.core_database.database  # noqa: F401
from src.core_database.config import BASE_DIR, settings as legacy_settings
from src.core_database.models.base import Base as LegacyBase
from src.core_database.models.db_helper import db_helper as legacy_db_helper
import src.editorial.models  # noqa: F401
from src.editorial.db.base import EditorialBase
from src.editorial.db.session import engine


class DatabaseExportService:
    def __init__(self, export_dir: Path | None = None) -> None:
        self.export_dir = export_dir or (BASE_DIR / "exports")

    async def export_snapshot(self) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_path = self.export_dir / f"ideaflow_snapshot_{timestamp}.db"
        if export_path.exists():
            export_path.unlink()

        target_conn = sqlite3.connect(export_path)
        try:
            self._ensure_meta_tables(target_conn)
            await self._append_tables(
                conn=target_conn,
                source_engine=legacy_db_helper.engine,
                tables=self._export_tables(LegacyBase.metadata),
                source_label="postgres",
            )
            await self._append_editorial_tables(target_conn)
            target_conn.commit()
        finally:
            target_conn.close()

        return export_path

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return f"\"{identifier.replace('\"', '\"\"')}\""

    @staticmethod
    def _export_tables(metadata) -> list:
        # Export writes plain SQLite tables without FK constraints, so we can use
        # the declared table order directly and avoid SQLAlchemy cycle warnings.
        return list(metadata.tables.values())

    @staticmethod
    def _normalise_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            return value
        if isinstance(value, bool):
            return int(value)
        if hasattr(value, "value"):
            return value.value
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _ensure_meta_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS export_info (
                export_created_at TEXT NOT NULL,
                database_url TEXT NOT NULL,
                export_kind TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM export_info")
        conn.execute(
            """
            INSERT INTO export_info (export_created_at, database_url, export_kind)
            VALUES (?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                legacy_settings.database_url,
                "project_snapshot",
            ),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS export_manifest (
                source TEXT NOT NULL,
                table_name TEXT NOT NULL,
                row_count INTEGER NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM export_manifest")

    async def _append_tables(self, conn, source_engine, tables, source_label: str, prefix: str = "") -> None:
        async with source_engine.connect() as source_conn:
            for table in tables:
                table_name = f"{prefix}{table.name}"
                column_names = [column.name for column in table.columns]
                create_sql = ", ".join(
                    f"{self._quote_identifier(column_name)} TEXT" for column_name in column_names
                )
                conn.execute(f"DROP TABLE IF EXISTS {self._quote_identifier(table_name)}")
                conn.execute(
                    f"CREATE TABLE {self._quote_identifier(table_name)} ({create_sql})"
                )

                result = await source_conn.execute(select(table))
                rows = result.mappings().all()
                if rows:
                    placeholders = ", ".join("?" for _ in column_names)
                    insert_sql = (
                        f"INSERT INTO {self._quote_identifier(table_name)} "
                        f"({', '.join(self._quote_identifier(name) for name in column_names)}) "
                        f"VALUES ({placeholders})"
                    )
                    payload = [
                        tuple(self._normalise_value(row[column_name]) for column_name in column_names)
                        for row in rows
                    ]
                    conn.executemany(insert_sql, payload)

                conn.execute(
                    "INSERT INTO export_manifest (source, table_name, row_count) VALUES (?, ?, ?)",
                    (source_label, table.name, len(rows)),
                )

    async def _append_editorial_tables(self, conn: sqlite3.Connection) -> None:
        await self._append_tables(
            conn=conn,
            source_engine=engine,
            tables=self._export_tables(EditorialBase.metadata),
            source_label="postgres",
        )
        async with engine.connect() as editorial_conn:
            version_result = await editorial_conn.execute(text("SELECT version_num FROM alembic_version"))
            version_rows = version_result.fetchall()
            conn.execute("DROP TABLE IF EXISTS alembic_version")
            conn.execute('CREATE TABLE alembic_version ("version_num" TEXT)')
            if version_rows:
                conn.executemany(
                    'INSERT INTO alembic_version ("version_num") VALUES (?)',
                    [(self._normalise_value(row[0]),) for row in version_rows],
                )
            conn.execute(
                "INSERT INTO export_manifest (source, table_name, row_count) VALUES (?, ?, ?)",
                ("postgres", "alembic_version", len(version_rows)),
            )
