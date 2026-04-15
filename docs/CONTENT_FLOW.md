# Поток Контента

## Быстрое объяснение панели

Чтобы не путаться в новых кнопках:

- `Поступившие сообщения` — это сырые входящие `submissions`, которые еще не стали постами.
- `Все сообщения` — это журнал всех `submissions`, уже лежащих в новой БД.
- `Черновики на review` — это `content_items`, то есть почти готовые посты после сборки.
- `Пасты` — это библиотека `paste_library`.

Подробное описание кнопочной панели есть в [docs/TELEGRAM_PANEL.md](docs/TELEGRAM_PANEL.md).

## 1. Legacy Inbox

Пользователь пишет в предложку. Старый бот сохраняет запись в legacy SQLite-таблицу `sender_info`.

Эти поля не ломаются и продолжают использоваться:

- `user_id`
- `channel_id`
- `bot_username`
- `username`
- `first_name`
- `message_id`
- `chat_id`
- `text_post`
- `timestamp`
- `id`

## 2. Importer

Сервис [src/editorial/services/import_legacy.py](/D:/VS%20projects/bot_pslshke/IdeaFlowBot/src/editorial/services/import_legacy.py:1):

- читает новые строки из `sender_info`;
- ищет или создаёт записи каналов в `channels`;
- чистит текст;
- строит `normalized_text` и `text_hash`;
- пытается определить простые теги;
- создаёт записи в `submissions`.

Главная идея: один legacy row импортируется только один раз через `legacy_source + legacy_row_id`.

Теперь старый collector сохраняет входящие сообщения в legacy inbox сразу при приёме, а не только после старого approve-flow. Это позволяет новой панели видеть реальные поступающие сообщения почти сразу после `import`.

## 3. Review Submissions

С `submissions` можно сделать несколько вещей:

- отклонить;
- оставить как source для генерации;
- отметить как paste candidate;
- создать `content_item`.

Сам `submission` не публикуется напрямую.

## 4. Content Items

`content_items` — это единый публикуемый объект.

Он может быть создан:

- из `submission`
- из `paste_library`
- генератором как `generated`
- вручную как `editorial`

Основные статусы:

- `draft`
- `pending_review`
- `approved`
- `scheduled`
- `published`
- `rejected`
- `hold`

## 5. Review Content Items

Модератор работает уже с `content_items`.

Можно:

- approve
- reject
- hold
- edit_and_approve

История сохраняется в таблицу `reviews`.

## 5.1 Telegram-Panel Review

Теперь для базового управления не обязательно идти в HTTP API.

Через `/panel` в главном боте модератор может кнопками:

- импортировать новые сообщения;
- открыть список pending submissions;
- approve / reject / hold;
- сделать `publish now`;
- сохранить submission как paste;
- открыть pending content items и одобрить их.

## 6. Пасты

Паста — это не AI-текст и не прямой `submission`.

Паста — отдельная библиотечная запись в `paste_library`, которую можно:

- сделать из `submission`
- сделать из `content_item`
- создать вручную

Важно:

- паста не публикуется напрямую;
- сначала из неё создаётся `content_item(source_type='paste')`;
- затем этот item проходит review и только потом может попасть в планировщик.

## 7. Генерация

Генерация сделана специально простой:

- выбираются 3-6 подходящих source submissions;
- собирается короткий prompt;
- provider создаёт 2-3 варианта;
- варианты сохраняются как `content_items(source_type='generated')`;
- статус у них всегда `pending_review`.

Автопубликации generated-контента нет.

## 8. Планировщик

Планировщик:

- смотрит активные каналы;
- смотрит их `channel_slots`;
- проверяет лимиты на день;
- учитывает min gap;
- учитывает cooldown по тегу, шаблону и пастам;
- проверяет exact/near duplicates;
- выбирает лучший `approved` item.

Приоритет выбора:

1. `submission`
2. `paste`
3. `generated`

Если для канала нет подходящего `approved` real content, scheduler теперь может сам:

- взять доступную пасту из `paste_library`;
- выбрать пасту, которая давно не использовалась;
- создать из неё `content_item(source_type='paste')`;
- автоматически поставить его в `approved`;
- и уже после этого запланировать на слот.

Если хорошего контента нет, слот остаётся пустым.

Через Telegram-панель можно отдельно:

- создать стандартные слоты для канала;
- вручную запустить scheduler;
- вручную запустить publisher.

## 9. Publisher

Publisher берёт записи со статусом `scheduled` и:

- находит bot token через legacy `bots_data`;
- отправляет текст в Telegram канал;
- при успехе ставит:
  - `content_item -> published`
  - `publication_log -> sent`
- при ошибке ставит:
  - `publication_log -> failed`
  - `content_item -> approved`

То есть после ошибки item не теряется и его можно запланировать повторно.
