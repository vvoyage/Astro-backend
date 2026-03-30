# GPU Support для LLM-API

## Что было изменено

### 1. Dockerfile
- **Базовый образ**: `python:3.11-slim` → `nvidia/cuda:12.1.0-devel-ubuntu22.04`
- **GPU_ENABLED**: `false` → `true`
- **llama-cpp-python**: Установка с поддержкой CUDA через `CMAKE_ARGS="-DGGML_CUDA=on"`
- **Python 3.11**: Установка вручную из deadsnakes PPA

### 2. Docker Compose
- **GPU_ENABLED**: Дефолт изменён с `false` на `true`
- **GPU config**: Уже настроен `deploy.resources.reservations.devices` для GPU

### 3. Helm Chart (values.yaml)
- **GPU_ENABLED**: `false` → `true`
- **Resources**: Добавлен запрос `nvidia.com/gpu: 1`
- **NodeSelector & Tolerations**: Добавлены комментарии для GPU нод

### 4. Environment Config
- **env.example**: `GPU_ENABLED=false` → `GPU_ENABLED=true`

## Требования для работы GPU

### Локальный запуск (Docker)

1. **NVIDIA GPU** с поддержкой CUDA (GTX 1060+, RTX series, и т.д.)

2. **NVIDIA Driver** (версия 525.60.13+):
```bash
# Проверка
nvidia-smi
```

3. **NVIDIA Container Toolkit**:
```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

```powershell
# Windows с Docker Desktop
# Включите WSL2 и установите NVIDIA драйвер для Windows
# Docker Desktop автоматически использует GPU через WSL2
```

4. **Проверка GPU в Docker**:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### Kubernetes

1. **GPU Nodes** с NVIDIA драйверами
2. **NVIDIA Device Plugin** для Kubernetes:
```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml
```

3. **Раскомментируйте** в `values.yaml` при необходимости:
```yaml
nodeSelector:
  nvidia.com/gpu: "true"

tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: "true"
    effect: NoSchedule
```

## Запуск

### Docker Compose
```bash
cd llm-api/docs/deploy/to-local-machine

# Создать .env из примера
cp env.example .env

# Проверить что GPU_ENABLED=true в .env

# Билд с CUDA (займёт 10-15 минут)
docker compose -f docker-compose.llm-api.yml build --no-cache

# Запуск
docker compose -f docker-compose.llm-api.yml up -d

# Проверка логов
docker compose -f docker-compose.llm-api.yml logs -f
```

### Проверка GPU использования

В логах при старте должно быть:
```
loading_llama_model_gpu | model=... | n_gpu_layers=-1 | context_size=2048
```

Где `n_gpu_layers=-1` означает что ВСЕ слои модели загружены на GPU.

Если видите `loading_llama_model_cpu` - GPU не используется.

### Мониторинг GPU
```bash
# Во время работы модели
watch -n 1 nvidia-smi

# Вы должны увидеть:
# - Использование GPU Memory (3-4 GB для llama-3.2-3b)
# - GPU Utilization при inference
```

## Производительность

**CPU режим** (старый):
- Генерация: ~2-5 токенов/сек
- Latency: 5-10 секунд на запрос

**GPU режим** (новый):
- Генерация: ~50-100 токенов/сек (10-20x ускорение)
- Latency: 0.5-2 секунды на запрос

## Troubleshooting

### "Could not find CUDA"
```bash
# Убедитесь что драйвер установлен
nvidia-smi

# Проверьте Docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### "Failed to initialize CUDA"
- Перезапустите Docker daemon
- Проверьте что GPU не занят другими процессами
- Попробуйте уменьшить модель (используйте llama-3.2-1b)

### "Out of Memory"
- Уменьшите `CONTEXT_SIZE` (с 2048 до 1024)
- Используйте меньшую модель
- Закройте другие GPU приложения

### Откат на CPU режим
В `.env` или docker-compose:
```bash
GPU_ENABLED=false
```

## Память

| Модель | VRAM (GPU) | RAM (CPU) |
|--------|------------|-----------|
| llama-3.2-1b | ~2 GB | ~4 GB |
| llama-3.2-3b | ~4 GB | ~6 GB |
| llama-3.1-8b | ~8 GB | ~12 GB |

Убедитесь что у вас достаточно VRAM!

