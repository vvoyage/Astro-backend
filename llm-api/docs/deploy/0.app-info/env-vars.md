## Переменные окружения

### Логи
- `LOG_LEVEL` (optional, default: `INFO`) — `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`.
- `LOG_JSON` (optional, default: `true`) — `true` для JSON логов, `false` для человекочитаемых.

### Модель / генерация
- `LLAMA_MODEL` (required, default: `llama-3.2-3b-instruct`) — алиас или HF repo-id GGUF модели. Поддержанные алиасы: `llama-3.2-3b-instruct`, `llama-3.1-8b-instruct`, `llama-3-8b-instruct`, `llama-2-7b-chat`.
- `GPU_ENABLED` (optional, default: `false`) — `true` включает GPU (`n_gpu_layers=-1`), иначе CPU.
- `CONTEXT_SIZE` (optional, default: `2048`) — размер контекста в токенах.
- `MAX_TOKENS` (optional, default: `512`) — максимум генерируемых токенов, если не передан в запросе.
- `LOCAL_MODEL_PATH` (optional, no default) — путь к локальной `*.gguf`. Если задан и файл существует, загрузка из HuggingFace не выполняется.

### Примечания
- При отсутствии `LOCAL_MODEL_PATH` сервис скачивает `*.gguf` из HuggingFace при первой инициализации/сборке образа.
- В k8s задавайте переменные через `values.yaml` (`env.app.*`) или секреты, если путь/модель приватные.
