# LLM API - Локальный запуск

Инструкция по локальному запуску llm-api через Docker Compose.

## Быстрый старт

### 1. Создать конфигурацию

```bash
cd llm-api/docs/deploy/to-local-machine
cp .env.llm-api.example .env.llm-api
```

### 2. Настроить (опционально)

Отредактируйте `.env.llm-api` если нужны другие параметры:

```env
LLAMA_MODEL=llama-3.2-3b-instruct
GPU_ENABLED=false
CONTEXT_SIZE=2048
MAX_TOKENS=512
LOG_LEVEL=INFO
```

### 3. Запустить

```bash
docker compose -f docker-compose.llm-api.yml --env-file .env.llm-api up -d
```

### 4. Проверить

```bash
# Логи
docker compose -f docker-compose.llm-api.yml logs -f

# Health check
curl http://localhost:8000/health

# Статус
docker compose -f docker-compose.llm-api.yml ps
```

## Использование с worker-llama

Если вы запускаете worker-llama отдельно, llm-api должен быть запущен первым на порту 8000.

Worker будет подключаться к `http://host.docker.internal:8000` (Windows/Mac) или `http://172.17.0.1:8000` (Linux).

## Управление

```bash
# Остановка
docker compose -f docker-compose.llm-api.yml stop

# Запуск
docker compose -f docker-compose.llm-api.yml start

# Перезапуск
docker compose -f docker-compose.llm-api.yml restart

# Полное удаление
docker compose -f docker-compose.llm-api.yml down
```

## GPU поддержка

Для использования GPU:

1. Установите NVIDIA Container Toolkit
2. Раскомментируйте секцию `deploy` в `docker-compose.llm-api.yml`
3. Установите в `.env.llm-api`: `GPU_ENABLED=true`

## Требования

- Docker + Docker Compose
- 8GB RAM (для llama-3.2-3b)
- 10GB свободного места (для модели)
- (Опционально) NVIDIA GPU + Container Toolkit
