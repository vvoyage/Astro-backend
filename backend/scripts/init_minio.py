"""
Загружает базовый Astro-шаблон в MinIO: astro-templates/base/
Создаёт бакет astro-assets и загружает post-build.js.

Запуск:
    cd backend
    python scripts/init_minio.py

Переменные окружения: MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from minio import Minio

BUCKET = "astro-templates"
PREFIX = "base/"

ASSETS_BUCKET = "astro-assets"
ASSETS: dict[str, str] = {
    "pre-build.cjs": (Path(__file__).parent / "pre-build.cjs").read_text(encoding="utf-8"),
    "post-build.cjs": (Path(__file__).parent / "post-build.cjs").read_text(encoding="utf-8"),
}

TEMPLATES: dict[str, str] = {
    "package.json": """\
{
  "name": "astro-site",
  "version": "0.0.1",
  "private": true,
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview"
  },
  "dependencies": {
    "astro": "^4.0.0",
    "@astrojs/tailwind": "^5.0.0",
    "tailwindcss": "^3.4.0"
  }
}
""",
    "astro.config.mjs": """\
import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  integrations: [tailwind()],
  output: 'static',
  build: {
    assets: 'assets',
  },
});
""",
    "tailwind.config.mjs": """\
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,ts,tsx,vue,svelte}'],
  theme: {
    extend: {},
  },
  plugins: [],
};
""",
}


def _get_minio_client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    endpoint = endpoint.lstrip("http://").lstrip("https://")
    secure_raw = os.environ.get("MINIO_SECURE", "false").lower()
    secure = secure_raw in ("1", "true", "yes")
    return Minio(
        endpoint,
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=secure,
    )


def main() -> None:
    client = _get_minio_client()

    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        print(f"Created bucket: {BUCKET}")
    else:
        print(f"Bucket already exists: {BUCKET}")

    for filename, content in TEMPLATES.items():
        object_name = f"{PREFIX}{filename}"
        data = content.encode("utf-8")
        client.put_object(
            BUCKET,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type="application/octet-stream",
        )
        print(f"Uploaded: {BUCKET}/{object_name} ({len(data)} bytes)")

    if not client.bucket_exists(ASSETS_BUCKET):
        client.make_bucket(ASSETS_BUCKET)
        print(f"Created bucket: {ASSETS_BUCKET}")
    else:
        print(f"Bucket already exists: {ASSETS_BUCKET}")

    for filename, content in ASSETS.items():
        data = content.encode("utf-8")
        client.put_object(
            ASSETS_BUCKET,
            filename,
            io.BytesIO(data),
            length=len(data),
            content_type="application/javascript",
        )
        print(f"Uploaded: {ASSETS_BUCKET}/{filename} ({len(data)} bytes)")

    print("\nDone. Base Astro template and assets uploaded to MinIO.")


if __name__ == "__main__":
    main()
