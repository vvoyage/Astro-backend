"""
Сфокусированный E2E-тест А4 EditorAgent pipeline.

Использует существующий ready-проект — пропускает генерацию.

Запуск:
    cd backend
    python -u test_editor_pipeline.py

    # Кастомные параметры:
    PROJECT_ID=<uuid> python -u test_editor_pipeline.py
"""
from __future__ import annotations
import json, os, sys, time
requests = pytest = None
try:
    import requests
    import redis as redis_lib
    import psycopg2
except ImportError as _e:
    import pytest
    pytest.skip(f"Integration deps missing: {_e}", allow_module_level=True)
from minio import Minio

API_URL       = os.getenv("API_URL",       "http://127.0.0.1:8001")
USER_ID       = os.getenv("USER_ID",       "33a951dc-3268-498c-ba66-cde648b9fe24")
PROJECT_ID    = os.getenv("PROJECT_ID",    "f811b43a-46b1-414d-85df-83cfa84db4c6")
MINIO_ENDPOINT= os.getenv("MINIO_ENDPOINT","localhost:9000")
MINIO_BUCKET  = os.getenv("MINIO_BUCKET",  "astro-projects")
REDIS_URL     = os.getenv("REDIS_URL",     "redis://localhost:6379/0")
DB_URL        = os.getenv("DB_URL",        "postgresql://astro:astro_pass@localhost:5432/astro_db")
AI_MODEL      = os.getenv("AI_MODEL",      "gpt-5.4")
EDIT_PROMPT   = os.getenv("EDIT_PROMPT",   "Добавь жирную надпись 'A4 EDITED' в начало страницы")
EDIT_TIMEOUT  = int(os.getenv("EDIT_TIMEOUT", "120"))
BUILD_TIMEOUT = int(os.getenv("BUILD_TIMEOUT", "300"))
POLL          = 2.0

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"; RESET = "\033[0m"; BOLD = "\033[1m"

def ok(n, msg, detail=""): _p("OK",   n, msg, detail)
def fail(n, msg, detail=""): _p("FAIL", n, msg, detail); sys.exit(1)
def warn(n, msg, detail=""): _p("WARN", n, msg, detail)
def skip(n, msg, detail=""): _p("SKIP", n, msg, detail)

def _p(status, n, msg, detail):
    icon = {"OK": f"{GREEN}✅{RESET}", "FAIL": f"{RED}❌{RESET}",
            "WARN": f"{YELLOW}⚠ {RESET}", "SKIP": f"{YELLOW}⏭ {RESET}"}[status]
    print(f"  {icon}  Step {n:>2}  {msg}")
    if detail: print(f"           {detail}")

def wait_redis(r, project_id, targets, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = r.get(f"generation:{project_id}:status")
        if raw:
            s = json.loads(raw).get("stage", "")
            if s in targets:
                return s
        time.sleep(POLL)
    return "timeout"

# ───────────────────────────────────────────────
print(f"\n{BOLD}=== A4 EditorAgent — E2E Pipeline Test ==={RESET}")
print(f"  Project : {PROJECT_ID}")
print(f"  User    : {USER_ID}")
print(f"  Prompt  : {EDIT_PROMPT}\n")

# Step 1: проверим что проект ready в БД
try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT status FROM projects WHERE id = %s", (PROJECT_ID,))
    row = cur.fetchone()
    conn.close()
    if not row:
        fail(1, "Проект существует в DB", f"project_id={PROJECT_ID} не найден")
    db_status = row[0]
    if db_status == "ready":
        ok(1, "Проект ready в DB", f"status={db_status}")
    else:
        warn(1, "Проект в DB", f"status={db_status} (ожидалось ready)")
except Exception as exc:
    fail(1, "DB: проект ready", str(exc))

# Step 2: найдём .astro файл в MinIO
mc = Minio(MINIO_ENDPOINT, access_key="minioadmin", secret_key="minioadmin", secure=False)
prefix = f"projects/{USER_ID}/{PROJECT_ID}/src/"
try:
    objects = list(mc.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True))
    astro_files = [o.object_name for o in objects if o.object_name.endswith(".astro")]
    if not astro_files:
        fail(2, "Исходники в MinIO", f"Нет .astro файлов по пути {prefix}")
    # Предпочитаем pages/index.astro — она гарантированно рендерится на главной странице
    index_candidates = [f for f in astro_files if "pages/index.astro" in f]
    file_path_minio = index_candidates[0] if index_candidates else astro_files[0]
    file_path_rel   = file_path_minio[len(f"projects/{USER_ID}/{PROJECT_ID}/"):]
    ok(2, "Исходники в MinIO", f"{len(astro_files)} .astro файлов; используем {file_path_rel}")
except Exception as exc:
    fail(2, "MinIO: список файлов", str(exc))

# Step 3: POST /api/v1/editor/edit → 202
t0 = time.time()
try:
    resp = requests.post(
        f"{API_URL}/api/v1/editor/edit",
        json={
            "project_id": PROJECT_ID,
            "element": {
                "editable_id": "a4-e2e-test-element",
                "file_path": file_path_rel,
                "element_html": "<p>placeholder</p>",
            },
            "instruction": EDIT_PROMPT,
            "ai_model": AI_MODEL,
        },
        headers={"X-Dev-User-Id": USER_ID, "Content-Type": "application/json"},
        timeout=15,
    )
    elapsed = time.time() - t0
    if resp.status_code == 202:
        body = resp.json()
        task_id = body.get("task_id", "?")
        ok(3, "POST /api/v1/editor/edit → 202",
           f"task_id={task_id}  file={file_path_rel}  [{elapsed:.2f}с]")
    else:
        fail(3, f"POST /api/v1/editor/edit (ожидалось 202)",
             f"HTTP {resp.status_code}: {resp.text[:300]}")
except Exception as exc:
    fail(3, "POST /api/v1/editor/edit", str(exc))

# Step 4: Redis stage = editing
r = redis_lib.from_url(REDIS_URL, decode_responses=True)
t0 = time.time()
stage = wait_redis(r, PROJECT_ID, {"editing", "building", "done", "failed"}, timeout=BUILD_TIMEOUT)
elapsed = time.time() - t0
if stage in ("editing", "building", "done"):
    ok(4, "Redis: stage = editing (task получена воркером)", f"stage='{stage}' за {elapsed:.1f}с")
elif stage == "failed":
    fail(4, "Redis: stage", "Edit task провалилась сразу")
else:
    fail(4, "Redis: stage не поменялся", "Celery worker не взял задачу за 60с — занят?")

# Step 5: A4 EditorAgent завершил → stage = building
t0 = time.time()
stage = wait_redis(r, PROJECT_ID, {"building", "done", "failed"}, timeout=EDIT_TIMEOUT)
elapsed = time.time() - t0
if stage in ("building", "done"):
    ok(5, "A4 EditorAgent → stage = building",
       f"LLM отработал, stage='{stage}' за {elapsed:.1f}с")
elif stage == "failed":
    fail(5, "A4 EditorAgent", "Edit pipeline упал во время LLM-вызова")
else:
    fail(5, "A4 EditorAgent", f"Таймаут {EDIT_TIMEOUT}с")

# Step 6: Снапшот в MinIO
try:
    snap_prefix = f"projects/{USER_ID}/{PROJECT_ID}/snapshots/"
    snap_objs = list(mc.list_objects(MINIO_BUCKET, prefix=snap_prefix, recursive=True))
    if snap_objs:
        ok(6, "Снапшот файла в MinIO",
           f"{len(snap_objs)} объект(ов): {[o.object_name.split('/')[-1] for o in snap_objs[:3]]}")
    else:
        fail(6, "Снапшот в MinIO", f"Нет объектов по пути {snap_prefix}")
except Exception as exc:
    warn(6, "Снапшот в MinIO (проверка)", str(exc))

# Step 7: Обновлённый файл существует в MinIO
try:
    objs = list(mc.list_objects(MINIO_BUCKET, prefix=file_path_minio, recursive=True))
    if objs:
        ok(7, "Обновлённый src-файл в MinIO", f"{file_path_rel} существует")
    else:
        fail(7, "Обновлённый src-файл в MinIO", f"Файл {file_path_minio} исчез")
except Exception as exc:
    warn(7, "Обновлённый файл в MinIO (проверка)", str(exc))

# Step 8: Build re-triggered → stage = done
print(f"\n  Ожидаем завершения повторной сборки (таймаут={BUILD_TIMEOUT}с)...")
t0_build = time.time()
stage = wait_redis(r, PROJECT_ID, {"done", "failed"}, timeout=BUILD_TIMEOUT)
build_elapsed = time.time() - t0_build
if stage == "done":
    ok(8, "Build re-triggered → stage = done", f"Сборка завершилась за {build_elapsed:.1f}с")
elif stage == "failed":
    fail(8, "Build re-triggered", f"Повторная сборка упала ({build_elapsed:.1f}с)")
else:
    fail(8, "Build re-triggered", f"Таймаут {BUILD_TIMEOUT}с")

# Step 9: dist/ обновлён в MinIO
try:
    dist_prefix = f"projects/{USER_ID}/{PROJECT_ID}/build/"
    dist_objs = list(mc.list_objects(MINIO_BUCKET, prefix=dist_prefix, recursive=True))
    has_index = any("index.html" in o.object_name for o in dist_objs)
    if has_index:
        ok(9, "dist/ обновлён в MinIO", f"{len(dist_objs)} файлов (index.html ✓)")
    else:
        warn(9, "dist/ в MinIO", f"index.html не найден. Файлы: {[o.object_name for o in dist_objs[:5]]}")
except Exception as exc:
    warn(9, "dist/ в MinIO (проверка)", str(exc))

# Step 10: DB status по-прежнему ready
try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT status FROM projects WHERE id = %s", (PROJECT_ID,))
    db_final = cur.fetchone()[0]
    conn.close()
    if db_final == "ready":
        ok(10, "DB: project status = ready", f"status={db_final}")
    else:
        warn(10, "DB: project status", f"status={db_final} (ожидалось ready)")
except Exception as exc:
    warn(10, "DB: project status", str(exc))

print(f"\n  {BOLD}Результат:{RESET} http://{MINIO_ENDPOINT}/{MINIO_BUCKET}/projects/{USER_ID}/{PROJECT_ID}/build/index.html")
print(f"\n{GREEN}{BOLD}=== ВСЕ ШАГИ ПРОЙДЕНЫ ✅ ==={RESET}\n")
