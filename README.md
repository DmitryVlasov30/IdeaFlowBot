# IdeaFlowBot

IdeaFlowBot - Telegram-бот для сети каналов формата "подслушано": бот принимает сообщения из предложек, помогает модераторам разбирать входящие, хранит библиотеку паст, планирует публикации по слотам и умеет фильтровать пасты по тегам для разных каналов.

Проект состоит из двух слоёв:

- legacy collector - существующая рабочая часть, которая принимает сообщения от пользователей, управляет сабботами и хранит старые данные в SQLite;
- editorial layer - новый слой на PostgreSQL, где живут submissions, review, контент, пасты, теги, расписание, публикации и генерация;
- Telegram-панель - основное место управления через кнопки в главном боте.

Главный рабочий поток:

```text
пользователь -> бот-предложка -> legacy collector -> importer -> editorial panel -> review -> schedule -> publish
```

## Возможности

- Подключение нескольких сабботов: один саббот обычно соответствует одной предложке и одному каналу.
- Приём сообщений из предложек и перенос их в editorial-базу.
- Telegram-панель для админа и модераторов.
- Просмотр новых и уже обработанных сообщений.
- Approve / hold / reject / publish now.
- Сохранение сообщений как паст.
- Ручное добавление паст в библиотеку.
- Автоматические и ручные теги у паст.
- Управление словарём тегов и ключевых слов через панель.
- Include/exclude теги для конкретного канала.
- Глобальные include/exclude теги сразу для всех каналов.
- Временные глобальные правила тегов, например `summer до 2026-08-31`.
- Слоты публикаций по каналам.
- Scheduler и publisher для автоматической публикации.
- Импорт истории канала, чтобы бот понимал, какие пасты уже публиковались.
- Экспорт базы и SQL/CSV-инструменты в панели.
- Опциональная генерация черновиков через OpenRouter.

## Основные Папки

- [`main.py`](main.py) - входная точка legacy collector.
- [`src/master.py`](src/master.py) - главный бот и Telegram-панель.
- [`src/worker.py`](src/worker.py) - логика сабботов/предложек.
- [`src/core_database`](src/core_database) - legacy SQLite-слой.
- [`src/editorial/models`](src/editorial/models) - PostgreSQL-модели.
- [`src/editorial/services`](src/editorial/services) - бизнес-логика editorial-слоя.
- [`src/editorial/api/app.py`](src/editorial/api/app.py) - FastAPI-приложение.
- [`alembic/versions`](alembic/versions) - миграции базы.
- [`docs`](docs) - подробная документация.

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

Минимально важные параметры:

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

Для большой сети, например около 150 предложек/каналов:

```env
SUP_BOT_LIMIT=700
MAX_SUBBOTS=150
TELEGRAM_CONNECTIONS_PER_BOT=4
TELEGRAM_CONNECTION_OVERHEAD=50
```

Запуск основных сервисов:

```bash
docker compose up -d --build
```

Проверить состояние:

```bash
docker compose ps
```

Обычно должны быть `Up` или `healthy` у:

- `postgres`
- `redis`
- `collector-bot`
- `editorial-importer`
- `editorial-api`

Если порт `8080` уже занят, поменяй в [`docker-compose.yml`](docker-compose.yml) проброс API:

```yaml
ports:
  - "8081:8080"
```

После изменения:

```bash
docker compose up -d editorial-api
```

## Обновление На Сервере

Если код уже скачан:

```bash
cd ~/IdeaFlowBot
git pull
docker compose up -d --build
```

Если нужно отдельно прогнать миграции:

```bash
docker compose run --rm editorial-migrate
docker compose up -d
```

Посмотреть логи главного бота:

```bash
docker compose logs -f collector-bot
```

Посмотреть логи API:

```bash
docker compose logs -f editorial-api
```

## Как Пользоваться Панелью

1. Открой главного Telegram-бота.
2. Отправь `/start` или `/panel`.
3. Если твой числовой Telegram ID указан в `GENERAL_ADMIN` или `MODERATORS`, бот покажет панель.

Главные разделы:

- `Поступившие сообщения` - новые сообщения из предложек.
- `Все сообщения` - журнал уже импортированных submissions.
- `Черновики на review` - готовые черновики перед публикацией.
- `Пасты` - библиотека паст.
- `Каналы и слоты` - настройки каналов, слотов, генерации и тегов паст.
- `Теги` - словарь тегов, ключевые слова и массовые правила.
- `Мои каналы` - отправка ручного сообщения в выбранные каналы.
- `Сабботы` - добавление/удаление ботов-предложек.
- `Модераторы` - управление доступом к панели.
- `Дополнительные функции` - выгрузки и служебные инструменты.

Подробнее см. [`docs/TELEGRAM_PANEL.md`](docs/TELEGRAM_PANEL.md).

## Сабботы И Каналы

Саббот - это отдельный Telegram-бот, который принимает сообщения для конкретной предложки. Обычно схема такая:

```text
1 саббот = 1 предложка = 1 канал подслушки
```

Добавление делается через панель:

```text
Сабботы -> Добавить саббота
```

Бот попросит строку:

```text
<api_token_саббота> @channel_username
```

После добавления можно настроить канал:

- включить/выключить получение сообщений;
- включить/выключить уведомления;
- создать слоты публикаций;
- настроить параметры паст;
- настроить include/exclude теги паст;
- импортировать историю канала.

## Пасты

Пасты - это библиотека готовых текстов, которые можно публиковать в каналы по расписанию. Паста может появиться двумя способами:

- модератор нажал `Save as paste` у сообщения из предложки;
- модератор вручную добавил пасту в разделе `Пасты`.

У пасты есть:

- текст;
- статус;
- список тегов;
- основной тег;
- ограничения по каналам;
- cooldown, чтобы не публиковать одно и то же слишком часто.

Через панель у пасты можно:

- добавить ручной тег;
- убрать ручной тег;
- пересчитать auto-теги;
- выбрать основной тег;
- удалить пасту из активной работы.

## Система Тегов

Теги используются для двух разных задач:

- разметить сообщения/пасты по смыслу;
- управлять тем, какие пасты в какие каналы можно публиковать.

Тег состоит из:

- `slug` - техническое имя, например `summer`, `tech`, `art`;
- названия;
- списка ключевых слов;
- статуса активности.

Через `Теги` в панели можно:

- создать новый тег;
- включить или выключить тег;
- добавить ключевые слова;
- выключить отдельное ключевое слово;
- открыть массовые правила паст.

Пример создания тега:

```text
summer :: Лето
```

Пример ключевых слов:

```text
лето, каникулы, июль, жара
```

## Теги Паст Для Конкретного Канала

В карточке канала есть раздел `Теги паст`.

Там есть два списка:

- `Только с тегами` / include - если список не пустой, канал берёт только пасты с одним из этих тегов;
- `Запрещённые теги` / exclude - пасты с этими тегами не публикуются в этот канал.

Пример:

```text
Канал художественного вуза:
include: art
exclude: tech
```

Это значит: в канал проходят пасты с художественным тегом, но не проходят технические.

Запрет сильнее разрешения. Если паста имеет одновременно `summer` и `tech`, а `tech` стоит в exclude, паста не пройдёт.

## Массовые Правила Тегов Для Всех Каналов

В разделе:

```text
Теги -> Массовые правила паст
```

есть глобальные правила:

- `Поставить Include для всех`;
- `Убрать Include для всех`;
- `Поставить Exclude для всех`;
- `Убрать Exclude для всех`.

Это нужно для сезонных или общесетевых режимов.

Например, летом можно поставить:

```text
summer до 2026-08-31
```

Тогда все каналы будут брать только пасты с тегом `summer` до конца указанной даты.

Можно поставить без срока:

```text
summer
```

Удаление делается соответствующей кнопкой `Убрать Include для всех` или `Убрать Exclude для всех`, после чего нужно отправить slug тега:

```text
summer
```

Глобальные правила и канальные правила работают вместе:

- глобальный exclude запрещает пасту во всех каналах;
- канальный exclude запрещает пасту только в конкретном канале;
- глобальный include требует нужный тег для всех каналов;
- канальный include дополнительно требует подходящий тег для конкретного канала.

Например:

```text
Глобально include: summer
Канал include: art
```

Паста должна подходить под оба фильтра: быть летней и подходить под художественный канал.

## Scheduler И Publisher

Scheduler выбирает, что и когда публиковать. Он учитывает:

- активность канала;
- слоты публикаций;
- лимиты публикаций в день;
- cooldown паст;
- include/exclude теги;
- историю публикаций;
- наличие готовых approved content items.

Publisher отправляет запланированные публикации в Telegram.

В Docker эти сервисы описаны отдельно:

- `editorial-scheduler`
- `editorial-publisher`

Их можно запускать через compose:

```bash
docker compose up -d editorial-scheduler editorial-publisher
```

Или вручную:

```bash
docker compose run --rm collector-bot python -m src.editorial.cli schedule
docker compose run --rm collector-bot python -m src.editorial.cli publish
```

## Генерация

Генерация черновиков опциональна. Если OpenRouter-ключа нет, лучше выключить:

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

После этого генерацию можно запускать через панель канала или CLI.

## Полезные CLI Команды

Импортировать сообщения из legacy SQLite:

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

## База Данных И Данные

В проекте используется две базы:

- legacy SQLite: `data/bot_network_db.db`;
- editorial PostgreSQL: контейнер `postgres`.

В Docker `./data` пробрасывается в контейнеры, чтобы legacy collector, importer и publisher видели одну и ту же SQLite-базу.

На новом сервере база будет чистой, если:

- не переносить `data/bot_network_db.db`;
- использовать новый Docker volume PostgreSQL;
- не импортировать старые дампы.

## Документация

- [Архитектура](docs/ARCHITECTURE.md)
- [Поток контента](docs/CONTENT_FLOW.md)
- [Деплой и сервер](docs/DEPLOYMENT.md)
- [Telegram-панель](docs/TELEGRAM_PANEL.md)

## Типичные Команды Обслуживания

Проверить контейнеры:

```bash
docker compose ps
```

Перезапустить все сервисы:

```bash
docker compose up -d
```

Пересобрать после обновления кода:

```bash
docker compose up -d --build
```

Остановить:

```bash
docker compose down
```

Посмотреть последние логи:

```bash
docker compose logs --tail=100 collector-bot
```

Следить за логами:

```bash
docker compose logs -f collector-bot
```

## Важные Замечания

- `.env` не нужно коммитить в GitHub.
- Токены ботов и пароли базы должны храниться только на сервере.
- После изменения `.env` контейнеры нужно пересоздать: `docker compose up -d`.
- После `git pull` с новыми миграциями запускай `docker compose up -d --build`; compose сам поднимет `editorial-migrate`.
- Если API-порт занят, можно заменить `8080:8080` на `8081:8080`.
- Для работы через сервер удобнее использовать SSH-клиент вроде Termius, а не веб-консоль провайдера.
