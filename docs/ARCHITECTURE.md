# Архитектура

## 1. Как Проект Устроен Сейчас

В проекте есть два слоя.

### Legacy collector

Это старый бот, который уже работал до доработки:

- [main.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/main.py:1) — точка входа
- [src/master.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/master.py:18) — главный бот-оркестратор
- [src/worker.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/worker.py:21) — логика саб-ботов для каналов
- [src/core_database](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/core_database) — старая SQLite-база

Этот слой:

- принимает сообщения из предложки;
- пишет данные в старые таблицы;
- умеет модерировать и публиковать в старом формате;
- остаётся источником legacy-сообщений.

### Editorial layer

Это новый слой, который построен поверх старого collector:

- [src/editorial/config.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/config.py:1) — конфиг новой подсистемы
- [src/editorial/db](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/db) — подключение к PostgreSQL
- [src/editorial/models](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/models) — ORM-модели новой схемы
- [src/editorial/services/import_legacy.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/import_legacy.py:1) — импорт из старой SQLite в `submissions`
- [src/editorial/services/moderation.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/moderation.py:1) — review flow
- [src/editorial/services/paste_service.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/paste_service.py:1) — библиотека паст
- [src/editorial/services/scheduler.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/scheduler.py:1) — планировщик
- [src/editorial/services/publisher.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/publisher.py:1) — отправка в Telegram
- [src/editorial/services/generation](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/generation) — простая генерация черновиков
- [src/editorial/api/app.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/api/app.py:1) — минимальный HTTP API для управления

## 2. Почему Новый Слой Вынесен Отдельно

Старый бот уже умеет:

- собирать входящие сообщения;
- хранить их в своей SQLite-базе;
- работать с Telegram;
- обслуживать сеть саб-ботов.

Если всё это переписать с нуля, легко сломать живую систему. Поэтому новая логика не встроена грубо внутрь старого кода, а добавлена рядом:

- старый слой продолжает собирать;
- новый слой импортирует и нормализует;
- весь editorial pipeline живёт в PostgreSQL.

## 3. Новые Основные Сущности

### `channels`

Хранит правила канала:

- Telegram channel id
- short code
- таймзону
- лимиты публикаций
- cooldown-правила
- флаги `allow_generated` и `allow_pastes`

### `channel_slots`

Слоты публикации по дням недели и времени.

### `submissions`

Нормализованные сообщения, импортированные из legacy `sender_info`.

### `content_items`

Единый публикуемый объект. Именно он проходит review и планирование.

### `reviews`

История решений модераторов по content items.

### `publication_log`

История планирования и реальных отправок в Telegram.

### `paste_library` и `paste_usage`

Библиотека повторно используемых паст и история их применения.

### `generation_runs`

История AI-генерации черновиков.

## 4. Как Данные Переходят Между Слоями

1. Старый бот пишет сообщение в `sender_info` SQLite.
2. `LegacyImporter` забирает новые строки.
3. Сообщение превращается в `submissions`.
4. Модератор создаёт `content_item` из submission или сохраняет пасту.
5. `content_item` проходит review.
6. `SchedulerService` выбирает approved item и ставит его в `scheduled`.
7. `PublisherService` публикует его в Telegram и пишет `publication_log`.

## 5. Где Что Лучше Менять

- Приём сообщений: старый collector
- Review и editorial flow: `src/editorial/services`
- Модели PostgreSQL: `src/editorial/models`
- Миграции: `alembic/versions`
- HTTP endpoints: `src/editorial/api/app.py`
- Нормализация текста: `src/editorial/utils/text.py`

