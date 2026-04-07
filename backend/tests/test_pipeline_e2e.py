"""
E2E-интеграционный тест — полный pipeline генерации (21 шаг).

Соответствует docs/pipeline-test-status.md.

Запуск:
    cd backend
    python tests/test_pipeline_e2e.py

    # Кастомные параметры:
    API_URL=http://127.0.0.1:8001 USER_ID=<uuid> python tests/test_pipeline_e2e.py

Требования (реальная инфраструктура должна быть запущена):
    - Uvicorn:  127.0.0.1:8001
    - Redis:    localhost:6379
    - PostgreSQL: localhost:5432
    - MinIO:    localhost:9000
    - RabbitMQ: localhost:5672
    - Celery worker (--pool=solo)
    - minikube (для этапа сборки)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Конфигурация — переопределяй через env vars
# ---------------------------------------------------------------------------

API_URL       = os.getenv("API_URL",       "http://127.0.0.1:8001")
REDIS_URL     = os.getenv("REDIS_URL",     "redis://localhost:6379/0")
DB_URL        = os.getenv("DB_URL",        "postgresql://postgres:postgres@localhost:5432/astro")
MINIO_ENDPOINT= os.getenv("MINIO_ENDPOINT","localhost:9000")
MINIO_ACCESS  = os.getenv("MINIO_ACCESS",  "minioadmin")
MINIO_SECRET  = os.getenv("MINIO_SECRET",  "minioadmin")
MINIO_BUCKET  = os.getenv("MINIO_BUCKET",  "astro-projects")
USER_ID       = os.getenv("USER_ID",       "33a951dc-3268-498c-ba66-cde648b9fe24")
PROMPT        = os.getenv("PROMPT",        "Лендинг для кофейни с красивым минималистичным дизайном и кнопкой заказа")
AI_MODEL      = os.getenv("AI_MODEL",      "gpt-5.4-mini")

K8S_NAMESPACE    = os.getenv("K8S_NAMESPACE",    "default")

# Таймауты
PIPELINE_TIMEOUT = int(os.getenv("PIPELINE_TIMEOUT", "120"))   # сек на pipeline генерации
BUILD_TIMEOUT    = int(os.getenv("BUILD_TIMEOUT",    "300"))    # сек на сборку K8s
POLL_INTERVAL    = float(os.getenv("POLL_INTERVAL",  "2"))      # сек между проверками

# ---------------------------------------------------------------------------
# Отслеживание результатов
# ---------------------------------------------------------------------------

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
RESET = "\033[0m"
BOLD  = "\033[1m"


@dataclass
class StepResult:
    num: int
    name: str
    status: str = "SKIP"   # OK | FAIL | SKIP | WARN
    details: str = ""
    elapsed: float = 0.0


_results: list[StepResult] = []


def step(num: int, name: str, status: str, details: str = "", elapsed: float = 0.0) -> StepResult:
    r = StepResult(num=num, name=name, status=status, details=details, elapsed=elapsed)
    _results.append(r)
    icon = {"OK": f"{GREEN}✅{RESET}", "FAIL": f"{RED}❌{RESET}",
            "SKIP": f"{YELLOW}⏭ {RESET}", "WARN": f"{YELLOW}⚠ {RESET}"}[status]
    elapsed_str = f" [{elapsed:.1f}с]" if elapsed > 0 else ""
    print(f"  {icon}  Шаг {num:>2}  {name}{elapsed_str}")
    if details:
        print(f"           {details}")
    return r


def _fail_all_remaining(from_step: int, reason: str) -> None:
    """Помечает все шаги после from_step как SKIP с причиной."""
    print(f"\n{RED}{BOLD}ПРЕРВАНО на шаге {from_step}: {reason}{RESET}\n")


# ---------------------------------------------------------------------------
# Ленивые импорты (библиотеки могут не стоять в dev-окружении)
# ---------------------------------------------------------------------------

def _import_redis():
    try:
        import redis as redis_lib
        return redis_lib
    except ImportError:
        print(f"{RED}pip install redis{RESET}")
        sys.exit(1)


def _import_requests():
    try:
        import requests
        return requests
    except ImportError:
        print(f"{RED}pip install requests{RESET}")
        sys.exit(1)


def _import_minio():
    try:
        from minio import Minio
        return Minio
    except ImportError:
        return None


def _import_psycopg2():
    try:
        import psycopg2
        return psycopg2
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _redis_client():
    redis_lib = _import_redis()
    return redis_lib.from_url(REDIS_URL, decode_responses=True)


def _minio_client():
    Minio = _import_minio()
    if Minio is None:
        return None
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS,
        secret_key=MINIO_SECRET,
        secure=False,
    )


def _get_project_status_from_db(project_id: str) -> str | None:
    """Прямой SELECT из PostgreSQL (psycopg2)."""
    pg = _import_psycopg2()
    if pg is None:
        return None
    try:
        conn = pg.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT status FROM projects WHERE id = %s", (project_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as exc:
        return f"error:{exc}"


def _wait_redis_stage(
    r, project_id: str, target_stages: set[str], timeout: int, poll: float = POLL_INTERVAL
) -> tuple[str, float]:
    """Ждёт пока Redis stage попадёт в target_stages. Возвращает (stage, elapsed)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = r.get(f"generation:{project_id}:status")
        if raw:
            payload = json.loads(raw)
            stage = payload.get("stage", "")
            if stage in target_stages:
                return stage, time.time() - (deadline - timeout)
        time.sleep(poll)
    return "timeout", timeout


def _list_minio_prefix(mc, prefix: str) -> list[str]:
    try:
        objects = mc.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Вспомогательные функции kubectl
# ---------------------------------------------------------------------------

def _compute_job_name(user_id: str, project_id: str) -> str:
    return f"build-{hashlib.md5(f'{user_id}-{project_id}'.encode()).hexdigest()[:16]}"


def _kubectl(*args, timeout: int = 15) -> tuple[int, str, str]:
    """Запускает kubectl -n <namespace> <args>. Возвращает (returncode, stdout, stderr)."""
    cmd = ["kubectl", "-n", K8S_NAMESPACE] + list(args)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except FileNotFoundError:
        return -1, "", "kubectl не найден в PATH"
    except subprocess.TimeoutExpired:
        return -1, "", f"таймаут kubectl ({timeout}с)"


def _kubectl_available() -> bool:
    rc, _, _ = _kubectl("version", "--client", "--short", timeout=5)
    return rc == 0


def _wait_for_job(job_name: str, timeout: int) -> tuple[bool, str]:
    """Опрашивает kubectl пока job не появится. Возвращает (found, json_str)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        rc, out, _ = _kubectl("get", "job", job_name, "-o", "json")
        if rc == 0 and out:
            return True, out
        time.sleep(2)
    return False, ""


def _wait_for_pod_phase(job_name: str, target_phases: set[str], timeout: int) -> tuple[str, str]:
    """Опрашивает поды job_name пока фаза не окажется в target_phases.
    Возвращает (phase, pod_name). phase='timeout' при превышении дедлайна."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        rc, out, _ = _kubectl("get", "pods", "-l", f"job-name={job_name}", "-o", "json")
        if rc == 0 and out:
            try:
                items = json.loads(out).get("items", [])
            except json.JSONDecodeError:
                items = []
            if items:
                pod = items[-1]
                phase = pod.get("status", {}).get("phase", "Unknown")
                pod_name = pod.get("metadata", {}).get("name", "?")
                if phase in target_phases:
                    return phase, pod_name
        time.sleep(2)
    return "timeout", ""


def _get_pod_logs(pod_name: str) -> str:
    rc, out, _ = _kubectl("logs", pod_name)
    return out if rc == 0 else ""


def _check_log_marker(logs: str, marker: str) -> bool:
    return marker in logs


# ---------------------------------------------------------------------------
# Основной поток теста
# ---------------------------------------------------------------------------

def run_test() -> int:
    print(f"\n{BOLD}=== Astro Generation Pipeline — E2E тест ==={RESET}")
    print(f"  API:    {API_URL}")
    print(f"  User:   {USER_ID}")
    print(f"  Model:  {AI_MODEL}")
    print(f"  Prompt: {PROMPT[:60]}...")
    print(f"  Время:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    requests = _import_requests()
    r_client = None
    project_id = None
    t0_global = time.time()

    # -----------------------------------------------------------------------
    # Шаг 1: POST /api/v1/generation → 202
    # -----------------------------------------------------------------------
    t0 = time.time()
    try:
        resp = requests.post(
            f"{API_URL}/api/v1/generation",
            json={"prompt": PROMPT, "ai_model": AI_MODEL},
            headers={"X-Dev-User-Id": USER_ID, "Content-Type": "application/json"},
            timeout=15,
        )
        elapsed = time.time() - t0
        if resp.status_code == 202:
            body = resp.json()
            project_id = body.get("project_id")
            step(1, "POST /api/v1/generation → 202", "OK",
                 f"project_id={project_id}  body_status={body.get('status')}", elapsed)
        else:
            step(1, "POST /api/v1/generation → 202", "FAIL",
                 f"HTTP {resp.status_code}: {resp.text[:200]}", elapsed)
            _fail_all_remaining(1, f"HTTP {resp.status_code}")
            return _print_summary()
    except Exception as exc:
        step(1, "POST /api/v1/generation → 202", "FAIL", str(exc), time.time() - t0)
        _fail_all_remaining(1, str(exc))
        return _print_summary()

    # -----------------------------------------------------------------------
    # Шаг 2: Redis generation:{id}:status = queued
    # -----------------------------------------------------------------------
    t0 = time.time()
    try:
        r_client = _redis_client()
        raw = r_client.get(f"generation:{project_id}:status")
        if raw:
            payload = json.loads(raw)
            stage = payload.get("stage", "?")
            progress = payload.get("progress", "?")
            ttl = r_client.ttl(f"generation:{project_id}:status")
            if stage == "queued":
                step(2, f"Redis generation:{project_id[:8]}...:status = queued", "OK",
                     f"progress={progress}  TTL={ttl}с", time.time() - t0)
            else:
                # Celery мог уже стартовать до проверки
                step(2, f"Redis generation:{project_id[:8]}...:status = queued", "WARN",
                     f"stage уже сменился на '{stage}' (быстрый воркер?)", time.time() - t0)
        else:
            step(2, f"Redis generation:{project_id[:8]}...:status = queued", "FAIL",
                 "Ключ не найден в Redis", time.time() - t0)
    except Exception as exc:
        step(2, "Redis generation:...:status = queued", "FAIL", str(exc), time.time() - t0)

    # -----------------------------------------------------------------------
    # Шаг 3: Celery task получен воркером (ждём pipeline start)
    # -----------------------------------------------------------------------
    t0 = time.time()
    try:
        stage, _ = _wait_redis_stage(
            r_client, project_id,
            {"generating", "optimizer", "architect", "code_generator", "saving", "building", "done", "failed"},
            timeout=30,
        )
        if stage == "timeout":
            step(3, "Celery task получен воркером", "FAIL",
                 "stage = 'queued' уже 30с — воркер не запущен?", time.time() - t0)
        elif stage == "failed":
            step(3, "Celery task получен воркером", "FAIL",
                 "Pipeline сразу упал", time.time() - t0)
        else:
            step(3, "Celery task получен воркером", "OK",
                 f"generation.run_pipeline получена, stage={stage}", time.time() - t0)
    except Exception as exc:
        step(3, "Celery task получен воркером", "FAIL", str(exc), time.time() - t0)

    # -----------------------------------------------------------------------
    # Шаг 4: DB: status → generating
    # -----------------------------------------------------------------------
    t0 = time.time()
    db_status = _get_project_status_from_db(project_id)
    if db_status is None:
        step(4, "DB: status → generating", "SKIP", "psycopg2 не установлен или БД недоступна")
    elif db_status and db_status.startswith("error:"):
        step(4, "DB: status → generating", "FAIL", db_status[6:], time.time() - t0)
    elif db_status in ("generating", "queued", "ready"):
        status_ok = db_status == "generating" or db_status == "ready"
        step(4, "DB: status → generating", "OK" if status_ok else "WARN",
             f"db status={db_status}", time.time() - t0)
    else:
        step(4, "DB: status → generating", "FAIL", f"db status={db_status}", time.time() - t0)

    # -----------------------------------------------------------------------
    # Шаги 5-7: ждём завершения A0 → A1 → A2 (pipeline = saving/building/done)
    # -----------------------------------------------------------------------
    print(f"\n  Опрашиваем pipeline (таймаут={PIPELINE_TIMEOUT}с)...")

    t0 = time.time()
    target_post_pipeline = {"saving", "building", "done", "failed"}

    # Шаг 5: A0 Optimizer
    stage, _ = _wait_redis_stage(r_client, project_id,
                                  {"architect", "code_generator"} | target_post_pipeline,
                                  timeout=PIPELINE_TIMEOUT)
    elapsed = time.time() - t0
    if stage in ("architect", "code_generator", "saving", "building", "done"):
        step(5, "A0 OptimizerAgent → LLM", "OK",
             f"stage продвинулся до '{stage}' за {elapsed:.1f}с", elapsed)
    elif stage == "failed":
        step(5, "A0 OptimizerAgent → LLM", "FAIL", "Pipeline упал на шаге optimizer", elapsed)
        return _print_summary()
    else:
        step(5, "A0 OptimizerAgent → LLM", "FAIL", f"Таймаут после {elapsed:.1f}с", elapsed)
        return _print_summary()

    # Шаг 6: A1 Architect
    t0 = time.time()
    stage, _ = _wait_redis_stage(r_client, project_id,
                                  {"code_generator"} | target_post_pipeline,
                                  timeout=PIPELINE_TIMEOUT)
    elapsed = time.time() - t0
    if stage in ("code_generator", "saving", "building", "done"):
        step(6, "A1 ArchitectAgent → файлы спланированы", "OK",
             f"stage='{stage}' за {elapsed:.1f}с", elapsed)
    elif stage == "failed":
        step(6, "A1 ArchitectAgent → файлы спланированы", "FAIL", "Pipeline упал на шаге architect", elapsed)
        return _print_summary()
    else:
        step(6, "A1 ArchitectAgent → файлы спланированы", "WARN",
             f"Не удалось подтвердить стадию architect (текущий={stage})", elapsed)

    # Шаг 7: A2 CodeGenerator
    t0 = time.time()
    stage, _ = _wait_redis_stage(r_client, project_id,
                                  {"saving", "building", "done", "failed"},
                                  timeout=PIPELINE_TIMEOUT)
    elapsed = time.time() - t0
    if stage in ("saving", "building", "done"):
        step(7, "A2 CodeGeneratorAgent (файлы параллельно)", "OK",
             f"все файлы сгенерированы, stage='{stage}' за {elapsed:.1f}с", elapsed)
    elif stage == "failed":
        step(7, "A2 CodeGeneratorAgent (файлы параллельно)", "FAIL", "Pipeline упал на шаге codegen", elapsed)
        return _print_summary()
    else:
        step(7, "A2 CodeGeneratorAgent (файлы параллельно)", "FAIL",
             f"Таймаут после {elapsed:.1f}с", elapsed)
        return _print_summary()

    # -----------------------------------------------------------------------
    # Шаг 8: Сохранение исходников в MinIO
    # -----------------------------------------------------------------------
    t0 = time.time()
    mc = _minio_client()
    if mc is None:
        step(8, "Сохранение исходников в MinIO", "SKIP", "пакет minio не установлен")
    else:
        # Дождаться stage building/done (файлы уже должны быть)
        _wait_redis_stage(r_client, project_id, {"building", "done", "failed"}, timeout=30)
        src_prefix = f"projects/{USER_ID}/{project_id}/src/"
        src_files = _list_minio_prefix(mc, src_prefix)
        if src_files:
            step(8, "Сохранение исходников в MinIO", "OK",
                 f"Сохранено {len(src_files)} файлов: {[f.split('/')[-1] for f in src_files[:5]]}",
                 time.time() - t0)
        else:
            step(8, "Сохранение исходников в MinIO", "FAIL",
                 f"Файлы не найдены по пути {src_prefix}", time.time() - t0)

    # -----------------------------------------------------------------------
    # Шаг 9: generation.run_pipeline SUCCEEDED
    # -----------------------------------------------------------------------
    t0 = time.time()
    stage, _ = _wait_redis_stage(r_client, project_id, {"building", "done", "failed"}, timeout=30)
    elapsed = time.time() - t0
    if stage in ("building", "done"):
        step(9, "generation.run_pipeline SUCCEEDED", "OK",
             f"задача сборки поставлена, stage='{stage}'", elapsed)
    elif stage == "failed":
        step(9, "generation.run_pipeline SUCCEEDED", "FAIL",
             "Pipeline упал до запуска сборки", elapsed)
        return _print_summary()
    else:
        step(9, "generation.run_pipeline SUCCEEDED", "FAIL",
             f"Таймаут ({elapsed:.1f}с), всё ещё в queued/generating", elapsed)
        return _print_summary()

    # -----------------------------------------------------------------------
    # Шаги 10-21: Этап сборки (K8s + MinIO dist + DB ready + Redis done)
    # -----------------------------------------------------------------------
    print(f"\n  Ожидаем сборку K8s (таймаут={BUILD_TIMEOUT}с)...")

    job_name = _compute_job_name(USER_ID, project_id)
    kubectl_ok = _kubectl_available()
    if not kubectl_ok:
        print(f"  {YELLOW}⚠  kubectl не найден — шаги 11-18 будут SKIP{RESET}")

    # -----------------------------------------------------------------------
    # Шаг 10: build.run task поставлена в очередь → получена воркером
    # -----------------------------------------------------------------------
    step(10, "build.run task queued → получен воркером", "OK",
         f"Вывод из stage=building в Redis  job_name={job_name}")

    # -----------------------------------------------------------------------
    # Шаг 11: K8s Job создан
    # -----------------------------------------------------------------------
    t0 = time.time()
    if not kubectl_ok:
        step(11, f"K8s Job создан ({job_name})", "SKIP", "kubectl недоступен")
    else:
        found, job_json = _wait_for_job(job_name, timeout=60)
        elapsed = time.time() - t0
        if found:
            try:
                job_data = json.loads(job_json)
                uid = job_data.get("metadata", {}).get("uid", "?")
                step(11, f"K8s Job создан ({job_name})", "OK",
                     f"uid={uid[:8]}...  [{elapsed:.1f}с]", elapsed)
            except Exception:
                step(11, f"K8s Job создан ({job_name})", "OK",
                     f"job существует  [{elapsed:.1f}с]", elapsed)
        else:
            step(11, f"K8s Job создан ({job_name})", "FAIL",
                 f"job не найден в kubectl через {elapsed:.1f}с — задача сборки не поставлена?", elapsed)

    # -----------------------------------------------------------------------
    # Шаг 12: Pod node:22 запущен (Running или Succeeded)
    # -----------------------------------------------------------------------
    t0 = time.time()
    pod_name: str = ""
    if not kubectl_ok:
        step(12, "Под node:22 запущен", "SKIP", "kubectl недоступен")
    else:
        phase, pod_name = _wait_for_pod_phase(
            job_name,
            target_phases={"Running", "Succeeded", "Failed"},
            timeout=120,
        )
        elapsed = time.time() - t0
        if phase in ("Running", "Succeeded"):
            step(12, "Под node:22 запущен", "OK",
                 f"pod={pod_name}  phase={phase}  [{elapsed:.1f}с]", elapsed)
        elif phase == "Failed":
            step(12, "Под node:22 запущен", "FAIL",
                 f"pod={pod_name} сразу перешёл в фазу Failed", elapsed)
        else:
            step(12, "Под node:22 запущен", "FAIL",
                 f"pod не достиг Running за {elapsed:.1f}с", elapsed)

    # -----------------------------------------------------------------------
    # Шаги 13-18: Парсим логи пода (ждём завершения пода)
    # -----------------------------------------------------------------------
    # Ждём Redis done/failed (сборка завершилась) и затем берём полные логи.
    t0_build = time.time()
    stage, _ = _wait_redis_stage(r_client, project_id, {"done", "failed"}, timeout=BUILD_TIMEOUT)
    build_elapsed = time.time() - t0_build

    pod_logs = ""
    if kubectl_ok and pod_name:
        pod_logs = _get_pod_logs(pod_name)
        if not pod_logs and stage == "done":
            # под мог быть удалён (ttlSecondsAfterFinished=300) — пробуем заново
            _, pod_name_final = _wait_for_pod_phase(
                job_name, target_phases={"Succeeded", "Failed"}, timeout=10
            )
            if pod_name_final and pod_name_final != "timeout":
                pod_logs = _get_pod_logs(pod_name_final)

    def _log_step(num: int, name: str, marker: str, ok_details: str = "") -> None:
        if not kubectl_ok:
            step(num, name, "SKIP", "kubectl недоступен")
        elif not pod_logs:
            step(num, name, "SKIP", "логи пода недоступны (под удалён или не запустился)")
        elif _check_log_marker(pod_logs, marker):
            step(num, name, "OK", ok_details)
        else:
            step(num, name, "FAIL", f"маркер не найден в логах: {repr(marker[:60])}")

    # Шаг 13: MinIO доступен из пода (mc alias set выполнился без ошибок)
    _log_step(13, "MinIO доступен из пода",
              marker="=== Source files in MinIO ===",
              ok_details="mc alias + ls выполнились успешно")

    # Шаг 14: Исходники скачаны из MinIO (mc ls показал файлы)
    _log_step(14, "Исходники скачаны из MinIO",
              marker=".astro",
              ok_details=".astro-файлы перечислены в логах пода")

    # Шаг 15: npx create-astro инициализация
    _log_step(15, "npx create-astro инициализация",
              marker="create-astro",
              ok_details="create-astro выполнился в поде")

    # Шаг 16: AI-файлы скопированы поверх шаблона
    _log_step(16, "AI-файлы скопированы поверх шаблона",
              marker="=== Final src/ contents ===",
              ok_details="mc cp src/ выполнился успешно, содержимое залогировано")

    # Шаг 17: npm install — npm выводит "npm warn" или "added N packages"
    if kubectl_ok and pod_logs:
        npm_ok = _check_log_marker(pod_logs, "added ") or _check_log_marker(pod_logs, "npm warn")
        if npm_ok:
            step(17, "npm install", "OK", "npm install завершился (пакеты залогированы)")
        else:
            step(17, "npm install", "FAIL", "в логах пода нет 'added N packages' или 'npm warn'")
    elif not kubectl_ok:
        step(17, "npm install", "SKIP", "kubectl недоступен")
    else:
        step(17, "npm install", "SKIP", "логи пода недоступны")

    # Шаг 18: astro build
    _log_step(18, "astro build",
              marker="=== Build complete, dist/ ===",
              ok_details="astro build выполнился успешно, dist/ залогирован")

    # -----------------------------------------------------------------------
    # Шаг 19: dist/ загружен в MinIO
    # -----------------------------------------------------------------------
    t0 = time.time()
    if mc is None:
        step(19, "dist/ загружен в MinIO", "SKIP", "пакет minio не установлен")
    elif stage == "done":
        dist_prefix = f"projects/{USER_ID}/{project_id}/build/"
        dist_files = _list_minio_prefix(mc, dist_prefix)
        has_index = any("index.html" in f for f in dist_files)
        if has_index:
            step(19, "dist/ загружен в MinIO", "OK",
                 f"{len(dist_files)} файлов: {[f.split('/')[-1] for f in dist_files[:5]]}",
                 build_elapsed)
        else:
            step(19, "dist/ загружен в MinIO", "FAIL",
                 f"index.html не найден. Файлы: {dist_files}", build_elapsed)
    elif stage == "failed":
        step(19, "dist/ загружен в MinIO", "FAIL",
             "Сборка упала — dist не загружен", build_elapsed)
        # Выводим последние 20 строк логов пода для отладки
        if pod_logs:
            tail = "\n".join(pod_logs.splitlines()[-20:])
            print(f"\n  {YELLOW}Последние строки логов пода:{RESET}\n{tail}\n")
    else:
        step(19, "dist/ загружен в MinIO", "FAIL",
             f"Таймаут сборки после {build_elapsed:.1f}с", build_elapsed)

    # Шаг 20: DB: status → ready
    t0 = time.time()
    db_status = _get_project_status_from_db(project_id)
    if db_status is None:
        step(20, "DB: status → ready", "SKIP", "psycopg2 не установлен")
    elif db_status == "ready":
        step(20, "DB: status → ready", "OK", f"db status={db_status}", time.time() - t0)
    else:
        step(20, "DB: status → ready", "FAIL", f"db status={db_status}", time.time() - t0)

    # Шаг 21: Redis generation:{id}:status = done 100%
    t0 = time.time()
    raw = r_client.get(f"generation:{project_id}:status")
    if raw:
        payload = json.loads(raw)
        final_stage = payload.get("stage", "?")
        final_progress = payload.get("progress", "?")
        if final_stage == "done" and final_progress == 100:
            step(21, f"Redis generation:{project_id[:8]}...:status = done 100%", "OK",
                 f"stage={final_stage}  progress={final_progress}", time.time() - t0)
        else:
            step(21, f"Redis generation:{project_id[:8]}...:status = done 100%",
                 "FAIL" if final_stage == "failed" else "WARN",
                 f"stage={final_stage}  progress={final_progress}", time.time() - t0)
    else:
        step(21, "Redis generation:...:status = done 100%", "FAIL",
             "Ключ не найден в Redis", time.time() - t0)

    # -----------------------------------------------------------------------
    # URL результата сборки
    # -----------------------------------------------------------------------
    result_url = (
        f"http://{MINIO_ENDPOINT}/{MINIO_BUCKET}/"
        f"projects/{USER_ID}/{project_id}/build/index.html"
    )
    print(f"\n  {BOLD}URL результата:{RESET} {result_url}")

    return _print_summary()


def _print_summary() -> int:
    ok   = sum(1 for r in _results if r.status == "OK")
    fail = sum(1 for r in _results if r.status == "FAIL")
    warn = sum(1 for r in _results if r.status == "WARN")
    skip = sum(1 for r in _results if r.status == "SKIP")
    total = len(_results)

    print(f"\n{BOLD}{'='*50}{RESET}")
    print(f"{BOLD}ИТОГ:{RESET}  "
          f"{GREEN}OK={ok}{RESET}  "
          f"{RED}FAIL={fail}{RESET}  "
          f"{YELLOW}WARN={warn} SKIP={skip}{RESET}  "
          f"(всего={total})")

    if fail == 0:
        print(f"{GREEN}{BOLD}ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ✅{RESET}")
    else:
        print(f"{RED}{BOLD}ПРОВАЛЕНО ПРОВЕРОК: {fail} ❌{RESET}")
        for r in _results:
            if r.status == "FAIL":
                print(f"  ❌  Шаг {r.num}: {r.name}")
                if r.details:
                    print(f"      {r.details}")

    print()
    return 1 if fail > 0 else 0


# ---------------------------------------------------------------------------
# Интеграция с pytest (pytest обнаруживает файл и запускает run_test как тест)
# ---------------------------------------------------------------------------

def test_pipeline_e2e():
    """Точка входа pytest — падает с перечнем проваленных шагов."""
    import pytest

    rc = run_test()
    if rc != 0:
        # Показываем какие шаги упали в выводе pytest
        failed = [r for r in _results if r.status == "FAIL"]
        msgs = [f"Шаг {r.num} ({r.name}): {r.details}" for r in failed]
        pytest.fail("\n".join(msgs))


# ---------------------------------------------------------------------------
# Точка входа (standalone)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_test())
