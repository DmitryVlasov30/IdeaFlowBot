# IdeaFlowBot

IdeaFlowBot - Telegram-бот для сети каналов формата "подслушано". Он принимает сообщения из ботов-предложек, даёт модераторам Telegram-панель, хранит библиотеку паст, планирует публикации по слотам и фильтрует пасты по тегам для разных каналов.

## Как Сейчас Устроен Проект

В проекте есть два логических слоя, но при обычном Docker-запуске они работают с одной PostgreSQL-базой:

- collector layer - главный бот и сабботы, которые принимают сообщения, хранят технические данные ботов, админов, пользователей, отложенных постов и входящих сообщений;
- editorial layer - модерация, submissions, content items, пасты, теги, слоты, scheduler, publisher, история публикаций и генерация;
- Telegram-панель - основной интерфейс управления прямо в главном боте.

Старые названия `legacy`, `core_database` и команда `import-legacy` в коде означают не обязательную SQLite-базу, а совместимый collector-слой и перенос данных из collector-таблиц в editorial-таблицы.

SQLite сейчас используется только в двух случаях:

- как fallback, если вообще не задан `EDITORIAL_POSTGRES_DSN` / `LEGACY_DATABASE_URL`;
- как источник одноразовой миграции старого файла `data/bot_network_db.db`, если он есть и PostgreSQL ещё пустой.

На новом сервере с Docker основная рабочая база - PostgreSQL.

Рабочий поток:

```text
пользователь -> бот-предложка -> collector tables -> importer -> submissions -> review -> schedule -> publish
```

## Возможности

- Подключение многих сабботов.
- Один саббот обычно соответствует одной предложке и одному каналу.
- Приём входящих сообщений из предложек.
- Telegram-панель для админа и модераторов.
- Разбор новых и уже обработанных сообщений.
- Approve / hold / reject / publish now.
- Сохранение сообщения как пасты.
- Ручное добавление паст.
- Автоматические и ручные теги у паст.
- Управление тегами и ключевыми словами через панель.
- Include/exclude теги для конкретного канала.
- Глобальные include/exclude теги сразу для всех каналов.
- Временные глобальные правила тегов, например `summer до 2026-08-31`.
- Слоты публикаций по каналам.
- Scheduler и publisher.
- Импорт истории канала.
- Экспорт базы и SQL/CSV-инструменты.
- Опциональная генерация черновиков через OpenRouter.

## Основные Файлы И Папки

- [`main.py`](main.py) - входная точка главного collector-бота.
- [`src/master.py`](src/master.py) - главный бот и Telegram-панель.
- [`src/worker.py`](src/worker.py) - логика сабботов/предложек.
- [`src/core_database`](src/core_database) - collector-таблицы и CRUD для технических данных ботов.
- [`src/editorial/models`](src/editorial/models) - PostgreSQL-модели editorial-слоя.
- [`src/editorial/services`](src/editorial/services) - бизнес-логика editorial-слоя.
- [`src/editorial/api/app.py`](src/editorial/api/app.py) - FastAPI API.
- [`alembic/versions`](alembic/versions) - миграции PostgreSQL.
- [`docs`](docs) - дополнительная документация.

## Быстрый Запуск На VPS

Клонировать репозиторий:

```bash
git clone https://github.com/DmitryVlasov30/IdeaFlowBot.git IdeaFlowBot
cd IdeaFlowBot
```

Создать `.env`:

```bash
cp .env.example .env
nano .env
```

Минимальный `.env` для чистого сервера:

```env
BOT_API_TOKEN=токен_главного_бота
GENERAL_ADMIN=твой_telegram_id
MODERATORS=твой_telegram_id

POSTGRES_DB=ideaflow_editorial
POSTGRES_USER=postgres
POSTGRES_PASSWORD=сложный_пароль_базы
EDITORIAL_POSTGRES_DSN=postgresql+asyncpg://postgres:сложный_пароль_базы@postgres:5432/ideaflow_editorial

EDITORIAL_REDIS_DSN=redis://redis:6379/0
EDITORIAL_API_HOST=0.0.0.0
EDITORIAL_API_PORT=8080
EDITORIAL_LOG_LEVEL=INFO

EDITORIAL_GENERATION_ENABLED=false
OPENROUTER_API_KEY=
```

Пароль в `POSTGRES_PASSWORD` и внутри `EDITORIAL_POSTGRES_DSN` должен совпадать.

Для сети примерно на 150 каналов/предложек:

```env
SUP_BOT_LIMIT=700
MAX_SUBBOTS=150
TELEGRAM_CONNECTIONS_PER_BOT=4
TELEGRAM_CONNECTION_OVERHEAD=50
```

Запуск основных сервисов:

```bash
docker compose up -d --build collector-bot editorial-api editorial-importer
```

Проверка:

```bash
docker compose ps
```

Обычно должны быть `Up` или `healthy` у:

- `postgres`
- `redis`
- `collector-bot`
- `editorial-api`
- `editorial-importer`

`editorial-migrate` после успешной миграции обычно будет `Exited`, это нормально. `editorial-scheduler` и `editorial-publisher` тоже есть в compose, но их можно запускать отдельно, когда уже настроены каналы, слоты и правила публикаций.

Если порт API `8080` занят, поменяй в [`docker-compose.yml`](docker-compose.yml):

```yaml
ports:
  - "8081:8080"
```

После этого:

```bash
docker compose up -d editorial-api
```

## Обновление На Сервере

После входа на сервер сначала перейди в папку проекта:

```bash
cd ~/IdeaFlowBot
```

Обновить код и пересобрать контейнеры:

```bash
git pull
docker compose up -d --build
```

Если нужно отдельно применить миграции:

```bash
docker compose run --rm editorial-migrate
docker compose up -d
```

Логи главного бота:

```bash
docker compose logs -f collector-bot
```

Логи API:

```bash
docker compose logs -f editorial-api
```

## Telegram-Панель

1. Открой главного Telegram-бота.
2. Отправь `/start` или `/panel`.
3. Если твой числовой Telegram ID указан в `GENERAL_ADMIN` или `MODERATORS`, бот покажет панель.

Основные разделы:

- `Обновить входящие` - запустить перенос новых collector-сообщений в editorial submissions.
- `Поступившие сообщения` - новые сообщения, которые ждут модерации.
- `Все сообщения` - журнал submissions.
- `Черновики на review` - готовые content items перед публикацией.
- `Пасты` - библиотека паст.
- `Каналы и слоты` - каналы, слоты, параметры публикаций и теги паст.
- `Теги` - словарь тегов, ключевые слова и массовые правила.
- `Мои каналы` - ручная отправка сообщения в выбранные каналы.
- `Сабботы` - добавление и удаление ботов-предложек.
- `Модераторы` - управление доступом.
- `Дополнительные функции` - выгрузка БД и SQL/CSV-инструменты.

Подробно: [`docs/TELEGRAM_PANEL.md`](docs/TELEGRAM_PANEL.md).

## Сабботы И Каналы

Саббот - это отдельный Telegram-бот, который принимает сообщения для конкретной предложки.

Обычно:

```text
1 саббот = 1 предложка = 1 канал подслушки
```

Добавление:

```text
Сабботы -> Добавить саббота
```

Бот попросит:

```text
<api_token_саббота> @channel_username
```

После добавления через карточку канала можно:

- включать/выключать получение сообщений;
- включать/выключать уведомления;
- создавать слоты публикаций;
- менять параметры публикаций;
- настраивать include/exclude теги паст;
- запускать генерацию;
- импортировать историю канала.

## Входящие Сообщения

Саббот сохраняет входящее сообщение в collector-таблицы. Затем `editorial-importer` или кнопка `Обновить входящие` переносит его в `submissions`.

Дальше модератор может:

- approve - создать content item;
- publish now - отправить сразу в публикационный pipeline;
- save as paste - сохранить сообщение как пасту;
- hold - отложить;
- reject - отклонить;
- ban user - заблокировать пользователя;
- ответить пользователю.

## Пасты

Пасты - библиотека готовых текстов для публикаций по расписанию.

Паста может появиться так:

- из сообщения через `Save as paste`;
- вручную через раздел `Пасты`;
- из другого content item.

У пасты есть:

- текст;
- статус;
- авто-теги;
- ручные теги;
- основной тег;
- cooldown;
- правила доступности по каналам.

В панели у пасты можно:

- добавить ручной тег;
- убрать ручной тег;
- пересчитать авто-теги;
- выбрать основной тег;
- удалить пасту из активной работы.

## Система Тегов

Теги нужны для разметки и для управления публикацией паст.

Тег имеет:

- `slug`, например `summer`, `tech`, `art`;
- название;
- ключевые слова;
- статус активности.

Создание тега:

```text
summer :: Лето
```

Ключевые слова:

```text
лето, каникулы, июль, жара
```

Если паста содержит ключевые слова, auto-tagging может проставить соответствующий тег. Админ также может вручную добавить тег конкретной пасте.

## Include/Exclude Теги Для Канала

В карточке канала есть `Теги паст`.

Там два типа правил:

- include / `Только с тегами` - если список не пустой, канал берёт только пасты с одним из этих тегов;
- exclude / `Запрещённые теги` - пасты с этими тегами не публикуются в этот канал.

Пример:

```text
Художественный вуз:
include: art
exclude: tech
```

Запрет сильнее разрешения. Если паста имеет `art` и `tech`, а `tech` стоит в exclude, паста не пройдёт.

## Массовые Правила Для Всех Каналов

В разделе:

```text
Теги -> Массовые правила паст
```

есть глобальные правила:

- `Поставить Include для всех`;
- `Убрать Include для всех`;
- `Поставить Exclude для всех`;
- `Убрать Exclude для всех`.

Это удобно для сезонных режимов.

Например:

```text
summer до 2026-08-31
```

Так все каналы временно будут брать только пасты с тегом `summer`.

Можно без срока:

```text
summer
```

Удаление:

```text
Убрать Include для всех -> summer
```

или:

```text
Убрать Exclude для всех -> tech
```

Глобальные и канальные правила складываются:

- глобальный exclude запрещает тег во всех каналах;
- канальный exclude запрещает тег только в выбранном канале;
- глобальный include требует тег для всей сети;
- канальный include дополнительно требует тег для конкретного канала.

Например:

```text
Глобально include: summer
Канал include: art
```

Паста должна иметь летний тег и подходить под художественный канал.

## Scheduler И Publisher

Scheduler выбирает, что поставить в очередь публикаций. Он учитывает:

- активность канала;
- слоты;
- дневные лимиты;
- cooldown паст;
- include/exclude теги;
- историю публикаций;
- готовые content items.

Publisher отправляет запланированное в Telegram.

Запуск отдельных сервисов:

```bash
docker compose up -d editorial-scheduler editorial-publisher
```

Разовый запуск через CLI:

```bash
docker compose run --rm collector-bot python -m src.editorial.cli schedule
docker compose run --rm collector-bot python -m src.editorial.cli publish
```

## Генерация

Генерация опциональна. Если OpenRouter-ключа нет:

```env
EDITORIAL_GENERATION_ENABLED=false
```

Если генерация нужна:

```env
EDITORIAL_GENERATION_ENABLED=true
EDITORIAL_GENERATION_PROVIDER=openrouter
OPENROUTER_API_KEY=твой_ключ
EDITORIAL_GENERATION_MODEL=z-ai/glm-4.5-air:free
```

После этого генерацию можно запускать из карточки канала или через CLI.

## База Данных

Основная база при Docker-запуске - PostgreSQL.

В ней находятся:

- collector-таблицы из `src/core_database`;
- editorial-таблицы из `src/editorial/models`;
- данные каналов, сабботов, входящих сообщений, паст, тегов, слотов и публикаций.

Файл `data/bot_network_db.db` нужен только если ты переносишь старую локальную SQLite-базу. Если сервер должен быть чистым, этот файл переносить не нужно.

Переменные, которые влияют на источник collector-таблиц:

- `EDITORIAL_POSTGRES_DSN` - обычный режим, collector и editorial работают в PostgreSQL;
- `LEGACY_DATABASE_URL` - явное переопределение базы collector-слоя;
- `LEGACY_SQLITE_SOURCE_PATH` - путь к старому SQLite-файлу для одноразового переноса.

## Полезные CLI Команды

Перенести новые collector-сообщения в submissions:

```bash
python -m src.editorial.cli import-legacy
```

Создать слоты:

```bash
python -m src.editorial.cli seed-slots --channel-id 1 --slot 10:00 --slot 15:00 --slot 20:00
```

Запустить scheduler:

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
- [Telegram-панель](docs/TELEGRAM_PANEL.md)

## Обслуживание

Проверить контейнеры:

```bash
docker compose ps
```

Перезапустить:

```bash
docker compose up -d
```

Пересобрать:

```bash
docker compose up -d --build
```

Остановить:

```bash
docker compose down
```

Последние логи:

```bash
docker compose logs --tail=100 collector-bot
```

Следить за логами:

```bash
docker compose logs -f collector-bot
```

## Важные Замечания

- `.env` не коммитится в GitHub.
- Токены ботов и пароли базы должны храниться только на сервере.
- После изменения `.env` перезапусти контейнеры: `docker compose up -d`.
- После `git pull` с новыми миграциями запускай `docker compose up -d --build`.
- Если API-порт занят, замени `8080:8080` на `8081:8080`.
- Для работы с VPS удобнее SSH-клиент вроде Termius, а не веб-консоль провайдера.
