# LLM API

FastAPI-сервис на Llama (llama-cpp-python). Принимает prompt и генерирует/корректирует текст. Используется в пайплайне `main-backend -> worker-llama -> llm-api` через эндпоинт `/generate/`. Внутренний движок: `backend/llama_engine.py` (LlamaEngine).

## Возможности

- Исправление грамматических и орфографических ошибок в тексте
- Настраиваемый выбор модели Llama (`llama-3.2-3b-instruct` / `llama-3.1-8b-instruct` / другие)
- Переключение CPU↔GPU через переменные окружения
- JSON API для простой интеграции
- Health-check эндпоинты для Kubernetes/Prometheus
- Структурированное логирование с Request ID tracking

## Быстрый старт

1. Соберите образ (модель `llama-3.2-3b-instruct` загружается и кешируется во время сборки):

   ```bash
   cd llm-api
   docker build -t llm-api .
   ```

   **Важно**: Модель скачивается во время сборки образа (~2 GB), поэтому первая сборка займет несколько минут. Последующие запуски контейнера будут мгновенными.

2. Запуск контейнера:

   - **CPU** (рекомендуется для начала)
     ```bash
     docker run --rm -p 8000:8000 llm-api
     ```

   - **Со сменой модели**
     ```bash
     docker run --rm -p 8000:8000 \
       -e LLAMA_MODEL=llama-3.1-8b-instruct \
       llm-api
     ```
     
     Примечание: Если модель не была предзагружена при сборке, она загрузится при первом запуске.

   - **GPU** (значительно быстрее)
     ```bash
     docker run --rm -p 8000:8000 \
       --gpus all \
       -e GPU_ENABLED=true \
       llm-api
     ```

     Требуется установленный NVIDIA-драйвер и Docker GPU runtime.

3. Проверка работы:

   Откройте в браузере **интерактивную документацию API**:
   - Swagger UI: http://localhost:8000/docs
   - Health check: http://localhost:8000/health/live

## API

**Интерактивная документация API:**
- Swagger UI: http://localhost:8000/docs 

### POST /generate/

Универсальный эндпоинт генерации текста с параметрами Llama.

**Request Body (JSON):**
```json
{
  "prompt": "Write a short haiku about autumn",
  "max_tokens": 128,
  "temperature": 0.7,
  "top_p": 0.95,
  "stop": ["###"],
  "echo": false
}
```

**Response (JSON):**
```json
{
  "text": "Crimson leaves descend\nWhispering through quiet streets\nAutumn breathes anew",
  "finish_reason": "stop",
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 24,
    "total_tokens": 36
  }
}
```

**Параметры:**
- `prompt` — обязательный, до 16000 символов.
- `max_tokens` — 1–4096, по умолчанию `MAX_TOKENS` (переменная окружения, дефолт 512).
- `temperature` — 0.0–2.0, по умолчанию 0.7.
- `top_p` — 0.0–1.0, по умолчанию 0.9.
- `stop` — список до 4 строк, опционально.
- `echo` — вернуть prompt вместе с ответом, по умолчанию `false`.

**Коды ответов:**
- `200 OK`: Успешная генерация
- `400 Bad Request`: Пустой prompt или некорректные параметры
- `422 Unprocessable Entity`: Неверный формат запроса
- `500 Internal Server Error`: Ошибка модели или внутренняя ошибка


### Использование для исправления текста (через `/generate/`)

- Для более детерминированной коррекции рекомендуются параметры: `temperature=0.1`, `top_p=0.9`, `max_tokens=512`, `echo=false`, `stop` не задавать.

### Health Checks

| Method | Path            | Назначение                |
|--------|-----------------|---------------------------|
| GET    | `/health/live`  | Контейнер жив             |
| GET    | `/health/ready` | Приложение готово к трафику (модель загружена при старте) |

**Примечание**: Модель Llama инициализируется при старте приложения, поэтому readiness probe всегда возвращает статус "ready" после запуска контейнера.

## Примеры использования

### cURL

```bash
# Проверка работоспособности
curl http://localhost:8000/health/live

# Генерация/коррекция через /generate/
curl -X POST "http://localhost:8000/generate/" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Please correct grammar: I has a cat and it like to play with ball.", "temperature": 0.1, "top_p": 0.9, "max_tokens": 512}'
```

### JavaScript (fetch)

```javascript
const response = await fetch('http://localhost:8000/generate/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt: 'Please correct grammar: He go to school everyday and he study hard.',
    temperature: 0.1,
    top_p: 0.9,
    max_tokens: 512
  })
});

const data = await response.json();
console.log(data.text);
```

## Переменные окружения

| Переменная         | По умолчанию | Описание |
|--------------------|--------------|----------|
| `LOG_LEVEL`        | `INFO`       | Уровень логов (`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`). |
| `LOG_JSON`         | `true`       | Формат логов: `true` → JSON, `false` → человекочитаемый. |
| `LLAMA_MODEL`      | `llama-3.2-3b-instruct` | Модель для исправления (`llama-3.2-3b-instruct`, `llama-3.1-8b-instruct`, `llama-3-8b-instruct`, `llama-2-7b-chat`). |
| `GPU_ENABLED`      | `false`      | `true` включает CUDA. При отсутствии GPU сервис работает на CPU. |
| `CONTEXT_SIZE`     | `2048`       | Размер контекста модели (в токенах). |
| `MAX_TOKENS`       | `512`        | Максимальное количество токенов в ответе. |
| `LOCAL_MODEL_PATH` | -            | Путь к локальной GGUF модели (если не указан, загружается из HuggingFace). |

## Порты

- HTTP (контейнер): `8000`  

## Примечания

- **Модель предзагружается при сборке**: `python -m backend.download_model` выполняется в Dockerfile, что обеспечивает мгновенный старт контейнера
- **Инициализация при старте**: Модель Llama загружается в память при импорте модуля, приложение готово к работе сразу после запуска
- **Структурированное логирование**: `structlog` с автоматическим добавлением `request_id` для трассировки запросов
- **GGUF формат**: Модели скачиваются из HuggingFace в формате GGUF с 4-bit квантизацией (Q4_K_M) для баланса качества и производительности
- **Production рекомендации**: 
  - Используйте `llama-3.1-8b-instruct` или больше для лучшего качества
  - Включите GPU для приемлемой скорости ответа
  - Настройте `CONTEXT_SIZE` и `MAX_TOKENS` под ваши задачи
- **Системные зависимости**: В Dockerfile устанавливаются build-essential и cmake для компиляции llama-cpp-python

## Производительность

Примерное время обработки на разных конфигурациях:

| Модель                    | Устройство | Текст (100 слов) |
|---------------------------|------------|------------------|
| llama-3.2-3b-instruct     | CPU        | ~5-10 сек        |
| llama-3.2-3b-instruct     | GPU        | ~1-2 сек         |
| llama-3.1-8b-instruct     | CPU        | ~15-30 сек       |
| llama-3.1-8b-instruct     | GPU        | ~2-4 сек         |

*Время зависит от конкретного железа

## Troubleshooting

### Ошибка при сборке образа: Модель не загружается / Таймауты HuggingFace CDN

```
Error: HTTPSConnectionPool(host='cas-bridge.xethub.hf.co', port=443): Read timed out
```

Проблема: HuggingFace CDN может быть медленным или недоступным из вашего региона.

**Решение 1: Включить VPN** (почти точно поможет)

**Решение 2: Пересобрать образ с увеличенным таймаутом**
```bash
docker build --build-arg HF_HUB_DOWNLOAD_TIMEOUT=600 -t llm-api .
```

**Решение 3: Пропустить загрузку при сборке и загрузить при первом запуске**
Закомментируйте строку `RUN python -m backend.download_model` в Dockerfile. Модель загрузится при первом запуске контейнера (старт займет больше времени).

### Медленная работа

**Решение:** 
- Включите GPU через `GPU_ENABLED=true` (требуется NVIDIA GPU)
- Используйте меньшую модель (`llama-3.2-3b-instruct`)
- Уменьшите `CONTEXT_SIZE` и `MAX_TOKENS`

### Out of Memory

**Решение:**
- Уменьшите `CONTEXT_SIZE`
- Используйте меньшую модель
- На CPU: добавьте swap память
- На GPU: используйте GPU с большим объемом VRAM


Если нужен универсальный Llama-сервис для генерации в любом проекте:

1) Запуск сервиса  
- Локально: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`  
- В контейнере: `docker build -t llm-api .` и `docker run -p 8000:8000 llm-api`

2) Настройка модели  
- Обязательно задать `LLAMA_MODEL` (или `LOCAL_MODEL_PATH` для своей GGUF)  
- При наличии GPU: `GPU_ENABLED=true`, подобрать `CONTEXT_SIZE` и `MAX_TOKENS` под задачу

3) Использование эндпоинта `/generate/`  
- Тело запроса: `{"prompt": "...", "max_tokens": N, "temperature": T, "top_p": P, "stop": ["..."], "echo": false}`  
- Возвращает: `text`, `finish_reason`, `usage`  
- Подходит для любых задач: чат, суммаризация, рерайт, извлечение данных — задавайте нужный prompt

4) Интеграция  
- Любой клиент, делающий HTTP POST (curl, fetch, httpx, requests).  
- Добавьте заголовок `Content-Type: application/json`; при необходимости прокидывайте `X-Request-ID` для трейсинга.

5) Производственные рекомендации  
- Оборачивайте вызовы в таймауты и ретраи на стороне клиента.  
- Горизонтально масштабируйте под нагрузку; используйте readiness/liveness пробы из сервиса.  
- Кэшируйте ответы для статичных или часто повторяющихся промптов.

## Использование другой LLM

1) Если есть GGUF под llama-cpp  
   - Укажите `LOCAL_MODEL_PATH=/path/to/model.gguf` **или** `LLAMA_MODEL=<алиас>` (см. поддерживаемые модели).  
   - Остальной сервис менять не нужно.

2) Если рантайм другой (OpenAI/Claude/vLLM/Transformers/PyTorch)  
   - Замените `backend/llama_engine.py` на клиент выбранного движка, оставив публичный метод `generate(prompt, max_tokens, temperature, top_p, stop, echo)` и формат ответа (`text`, `finish_reason`, `usage`, `raw_response`).  
   - Обновите зависимости (`requirements.txt`) и Dockerfile (CUDA/PyTorch/vLLM и т.п.).  
   - Добавьте/переименуйте переменные окружения (базовый URL, ключи, модель) и прокиньте их в новый движок.  
   - При желании адаптируйте warmup (`backend/download_model.py`) или уберите, если модель не требует предзагрузки.

