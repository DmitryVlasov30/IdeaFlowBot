# Деплой И Сервер

## 1. Какой Сервер Нужен

Для такой системы достаточно обычного VPS.

Минимально разумно:

- 2 vCPU
- 4 GB RAM
- 30-40 GB SSD

Если каналов много и generation используется активно, лучше 4 vCPU и 8 GB RAM.

## 2. Какие Компоненты Запускаются

Проект состоит из нескольких процессов:

- `collector-bot` — старый Telegram collector
- `editorial-api` — HTTP API для review/import/manual actions
- `editorial-importer` — переносит новые legacy сообщения в `submissions`
- `editorial-scheduler` — раскладывает approved контент по слотам
- `editorial-publisher` — публикует scheduled контент в Telegram
- `postgres` — новая editorial база
- `redis` — резерв под фоновые задачи и расширение системы

## 3. Почему Здесь Есть И SQLite, И PostgreSQL

SQLite остаётся только для старого collector-слоя.

PostgreSQL нужен для новой редакционной системы, потому что там:

- больше таблиц;
- больше индексов;
- нужен `pg_trgm` для анти-повторов;
- нужна нормальная схема для scheduler/review/paste library.

## 4. Запуск Через Docker Compose

1. Скопируй `.env.example` в `.env`
2. Заполни обязательные переменные
3. Запусти:

```bash
docker compose up --build -d
```

После этого:

- PostgreSQL и Redis поднимутся как отдельные контейнеры
- API само прогонит `alembic upgrade head`
- importer/scheduler/publisher стартуют в цикле
- collector-bot поднимется отдельно
- `./data` будет общим volume для collector/importer/publisher, поэтому legacy SQLite не разъедется по разным контейнерам

## 5. Если Хочешь Запускать Процессы Вручную

Миграции:

```bash
alembic upgrade head
```

Collector:

```bash
python main.py
```

API:

```bash
uvicorn src.editorial.api.app:app --host 0.0.0.0 --port 8080
```

Importer:

```bash
python -m src.editorial.cli import-legacy
```

Scheduler:

```bash
python -m src.editorial.cli sync-channel-profiles
python -m src.editorial.cli auto-slots
python -m src.editorial.cli schedule
```

`editorial-scheduler` in `docker-compose.yml` runs auto-slot planning before every scheduler pass. The planner changes only channels with `auto_slots_enabled=true` and skips a channel/date after a successful plan.

Each scheduler pass preloads active slots, paste cooldown history, reservations, and tag rules in bulk. `EDITORIAL_SCHEDULER_COMMIT_BATCH_SIZE` controls how many database-only scheduling changes are committed together (default: `25`). This does not change slot or paste eligibility rules.

`editorial-profile-sync` in `docker-compose.yml` updates channel subscriber counts and applies subscriber-based profiles once per hour.

Publisher:

```bash
python -m src.editorial.cli publish
```

Generation:

```bash
python -m src.editorial.cli generate --channel-id 1
```

## 6. Что Важно Настроить Перед Боевым Запуском

- `BOT_API_TOKEN`
- `GENERAL_ADMIN`
- `PUBLICATION_SIGNATURE_SKIP_IF_ADMIN_BOT_USERNAME`, если подпись нужно отключать в каналах, где уже админит отдельный бот подписей
- `EDITORIAL_POSTGRES_DSN`
- `EDITORIAL_REVIEW_API_KEY`
- `OPENROUTER_API_KEY`, если нужен OpenRouter
- слоты публикации `channel_slots`

Рекомендуемые настройки защиты от сетевых зависаний Telegram:

```env
TELEGRAM_REQUEST_TIMEOUT_SECONDS=15
TELEGRAM_RETRY_DELAY_SECONDS=60
EDITORIAL_PUBLISHER_RETRY_BASE_SECONDS=60
EDITORIAL_PUBLISHER_RETRY_MAX_SECONDS=900
```

Без слотов scheduler ничего не запланирует, и это нормально.

Если пока хочешь жить без генерации, просто выставь:

```env
EDITORIAL_GENERATION_ENABLED=false
```

## 7. Как Понять, Что Всё Работает

Порядок проверки:

1. Collector продолжает принимать сообщения.
2. Importer создаёт `submissions`.
3. Через API видно pending submissions/content items.
4. Approved item попадает в `scheduled`.
5. Publisher отправляет пост в Telegram канал.
6. В `publication_log` появляется `sent`.

## 8. Более Простой Повседневный Сценарий

После локального запуска открой в Telegram главного бота и используй `/panel`.

Что умеет панель:

- модератор:
  - импорт новых сообщений;
  - просмотр incoming submissions;
  - approve / reject / hold / publish now;
  - создание paste из submission;
  - запуск scheduler/publisher;
  - создание стандартных слотов канала.
- генеральный админ:
  - всё вышеперечисленное;
  - добавление и удаление динамических модераторов;
  - добавление и удаление сабботов кнопками.
