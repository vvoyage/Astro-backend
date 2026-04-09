#!/usr/bin/env python3
"""
Загружает базовый Astro-шаблон в бакет astro-templates (префикс base/).

Переменные окружения (как у backend):
  MINIO_ENDPOINT   — host:port, по умолчанию localhost:9000
  MINIO_ACCESS_KEY, MINIO_SECRET_KEY — по умолчанию minioadmin
  MINIO_SECURE     — true/false, по умолчанию false

Запуск из корня репозитория:
  pip install minio
  python scripts/init_minio.py
"""
from __future__ import annotations

import json
import os
import sys
from io import BytesIO

try:
    from minio import Minio
except ImportError:
    print("Install minio: pip install minio", file=sys.stderr)
    sys.exit(1)

BUCKET = "astro-templates"
PREFIX = "base/"

PACKAGE_JSON = {
    "name": "astro-base",
    "type": "module",
    "version": "0.0.1",
    "scripts": {
        "dev": "astro dev",
        "build": "astro build",
        "preview": "astro preview",
    },
    "dependencies": {
        "astro": "^4.16.0",
        "@astrojs/tailwind": "^5.1.0",
        "tailwindcss": "^3.4.17",
    },
}

ASTRO_CONFIG_MJS = """import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  integrations: [tailwind()],
});
"""

TAILWIND_CONFIG_MJS = """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: { extend: {} },
  plugins: [],
};
"""


def _put(client: Minio, object_name: str, body: bytes) -> None:
    client.put_object(BUCKET, object_name, BytesIO(body), length=len(body))


def main() -> int:
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    access = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    secure = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")

    client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)

    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        print(f"Created bucket {BUCKET}")
    else:
        print(f"Bucket {BUCKET} already exists")

    uploads = {
        f"{PREFIX}package.json": json.dumps(PACKAGE_JSON, indent=2).encode("utf-8"),
        f"{PREFIX}astro.config.mjs": ASTRO_CONFIG_MJS.encode("utf-8"),
        f"{PREFIX}tailwind.config.mjs": TAILWIND_CONFIG_MJS.encode("utf-8"),
    }

    for name, data in uploads.items():
        _put(client, name, data)
        print(f"Uploaded s3://{BUCKET}/{name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
