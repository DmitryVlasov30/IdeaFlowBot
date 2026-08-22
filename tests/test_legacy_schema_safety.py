from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core_database.database import POSTGRES_BIGINT_COLUMNS, _ensure_postgres_bigint_columns
from src.editorial.services import legacy_source
from src.editorial.services.legacy_source import LegacyCollectorReader


class _EmptyResult:
    def mappings(self):
        return self

    def all(self):
        return []

    def first(self):
        return None


class _ConnectionContext:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


@pytest.mark.asyncio
async def test_legacy_reader_never_bootstraps_or_mutates_schema(monkeypatch) -> None:
    connection = SimpleNamespace(execute=AsyncMock(return_value=_EmptyResult()))
    read_only_engine = SimpleNamespace(
        connect=lambda: _ConnectionContext(connection),
    )
    monkeypatch.setattr(legacy_source.legacy_db_helper, "engine", read_only_engine)

    reader = LegacyCollectorReader()
    assert await reader.fetch_sender_rows() == []
    assert await reader.fetch_sender_rows_by_ids([1]) == []
    assert await reader.find_sender_row_by_review_message(1, 2, 3) is None
    assert connection.execute.await_count == 3


@pytest.mark.asyncio
async def test_bigint_schema_check_executes_no_ddl_when_types_are_current() -> None:
    rows = [
        (table_name, column_name, "int8")
        for table_name, column_names in POSTGRES_BIGINT_COLUMNS.items()
        for column_name in column_names
    ]
    result = SimpleNamespace(fetchall=lambda: rows)
    connection = SimpleNamespace(exec_driver_sql=AsyncMock(return_value=result))

    await _ensure_postgres_bigint_columns(connection)

    connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
async def test_bigint_schema_check_converts_only_outdated_columns() -> None:
    result = SimpleNamespace(
        fetchall=lambda: [("sender_info", "message_id", "int4")]
    )
    connection = SimpleNamespace(exec_driver_sql=AsyncMock(return_value=result))

    await _ensure_postgres_bigint_columns(connection)

    assert connection.exec_driver_sql.await_count == 2
    ddl = connection.exec_driver_sql.await_args_list[1].args[0]
    assert 'ALTER TABLE "sender_info"' in ddl
    assert 'ALTER COLUMN "message_id" TYPE BIGINT' in ddl
