# Домовой

Self-hosted PWA для семейных дел, покупок, хранения вещей и обслуживания дома. Репозиторий сейчас
содержит завершённую основу Этапа 1: пять контейнеров, API и миграции, отдельный worker,
адаптивный клиент по дизайну «Тихий семейный ритм» и базовый тестовый контур.

## Быстрый запуск

Требования: Linux, Docker Engine и Docker Compose v2.

Для первой локальной проверки достаточно одной команды:

```bash
docker compose up -d --build --wait
```

Откройте <http://localhost>. Проверки API:

```bash
curl http://localhost/health/live
curl http://localhost/api/v1/health/ready
```

Для установки на сервер сначала создайте закрытый `.env` с уникальными секретами, указав IP:

```bash
./scripts/setup-env.sh http://192.168.1.100
docker compose up -d --build --wait
```

После появления домена замените `APP_ADDRESS` в `.env` на имя домена без `http://`, например
`home.example.org`, и выполните `docker compose up -d`. Caddy запросит и будет обновлять TLS.

## Проверка сохранности данных

Сквозной скрипт поднимает проект, проверяет health endpoints и миграцию, создаёт контрольную запись,
перезапускает PostgreSQL и подтверждает, что запись сохранилась:

```bash
./scripts/verify-stack.sh http://localhost
```

Скрипт не удаляет контейнеры и volumes. Остановить сервисы без удаления данных:

```bash
docker compose down
```

## Локальная разработка

Нужны Python 3.12+, Node.js 24+ и npm.

```bash
make install
make check
```

Отдельный frontend dev server:

```bash
npm --prefix apps/frontend run dev
```

API локально ожидает PostgreSQL по `DATABASE_URL`. Миграции и запуск:

```bash
cd apps/api
../../.venv/bin/alembic upgrade head
../../.venv/bin/uvicorn app.main:app --reload
```

## Основные документы

- [Полная спецификация](docs/spec.md)
- [Архитектура](docs/architecture.md)
- [Правила работы агентов](AGENTS.md)

## Текущие границы

Этап 1 намеренно не содержит вход, пользователей и постоянные доменные данные. Экран «Сегодня» —
интерактивный дизайн-shell, на котором проверяются адаптивность и базовые состояния. Авторизация и
семья относятся к Этапу 2; задачи, повторы и серверные данные экрана «Сегодня» — к Этапу 3.
