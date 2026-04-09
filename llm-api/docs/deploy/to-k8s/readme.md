## Деплой в k8s

### Чарт / ArgoCD
- Чарт: `charts/llm-api` (этот репозиторий), деплой через ArgoCD.
- Service: `ClusterIP`, порт `80` → контейнер `8000`.
- Ingress включён по умолчанию: host `llm-api.veryred.ru`, класс `nginx`, TLS `llm-api-tls`.

### Минимальные values/секреты
- `env.app.LOG_LEVEL`, `env.app.LOG_JSON`.
- `env.app.LLAMA_MODEL`, `env.app.GPU_ENABLED`, `env.app.CONTEXT_SIZE`, `env.app.MAX_TOKENS`.
- `env.app.LOCAL_MODEL_PATH` — опционально, если модель уже на диске узла/volume.
- Секреты/ExternalSecret не требуются; сеть до HuggingFace нужна, если модель не предзагружена в образ.

### Ресурсы/скейл
- Requests: `cpu=500m`, `memory=1Gi`; Limits: `cpu=4`, `memory=8Gi` (под 3B модель).
- HPA опционален (`autoscaling.*`).
- GPU: включите `env.app.GPU_ENABLED=true` и настройте nodeSelector/tolerations под GPU-узлы.

### Пример ручной установки Helm
```bash
helm upgrade --install llm-api ./charts/llm-api \
  -n default \
  -f values.override.yaml
```

### Сетевые/пробы
- HTTP эндпоинты: `/generate/`, `/health/live`, `/health/ready`.
- Liveness/Readiness вынесены в `backend.main` (см. 0.app-info/probes.md).
