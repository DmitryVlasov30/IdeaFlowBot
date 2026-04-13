# IdeaFlowBot

Это Telegram-бот для сети каналов формата "подслушано". В репозитории теперь живут две части:

- старый collector-бот, который принимает сообщения и не ломается;
- новый editorial layer, который строит поверх collector полноценный pipeline:
  `submission -> content_item -> review -> approved -> scheduled -> published`.

Основная идея проекта:

- реальные сообщения из предложки остаются главным источником контента;
- старый SQLite-слой остаётся как legacy collector;
- новая PostgreSQL-схема хранит editorial-сущности, review, пасты, публикации и генерацию;
- публикация идёт только через review и планировщик;
- пасты и AI-генерация разделены логически.

## Что Уже Есть В Репозитории

- Legacy collector в [main.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/main.py:1), [src/master.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/master.py:18), [src/worker.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/worker.py:21)
- Legacy SQLite models в [src/core_database](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/core_database)
- Новый editorial API в [src/editorial/api/app.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/api/app.py:1)
- Новый importer и сервисы в [src/editorial/services](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services)
- PostgreSQL-модели в [src/editorial/models](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/models)
- Alembic миграции в [alembic](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/alembic)

## Быстрый Старт Локально

1. Скопируй `.env.example` в `.env`.
2. Заполни `BOT_API_TOKEN`, `GENERAL_ADMIN` и остальные важные переменные.
3. Подними инфраструктуру:

```bash
docker compose up --build
```

4. Примени миграции вручную, если запускаешь не через compose:

```bash
alembic upgrade head
```

5. Запусти legacy collector:

```bash
python main.py
```

6. Запусти editorial API:

```bash
uvicorn src.editorial.api.app:app --host 0.0.0.0 --port 8080
```

## Полезные CLI Команды

Импорт legacy сообщений:

```bash
python -m src.editorial.cli import-legacy
```

Создать ежедневные слоты публикации для канала:

```bash
python -m src.editorial.cli seed-slots --channel-id 1 --slot 10:00 --slot 15:00 --slot 20:00
```

Запустить планировщик:

```bash
python -m src.editorial.cli schedule
```

Запустить publisher:

```bash
python -m src.editorial.cli publish
```

Сгенерировать черновики:

```bash
python -m src.editorial.cli generate --channel-id 1 --variants 3 --sources 5
```

## Документация

- [Архитектура](docs/ARCHITECTURE.md)
- [Поток контента](docs/CONTENT_FLOW.md)
- [Деплой и сервер](docs/DEPLOYMENT.md)

