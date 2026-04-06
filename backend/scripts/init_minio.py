"""
Загружает базовый Astro-шаблон в MinIO: astro-templates/base/

Запуск:
    cd backend
    python scripts/init_minio.py

Переменные окружения читаются из .env (через pydantic-settings).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Add backend/ to path so app imports work when running standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

BUCKET = "astro-templates"
PREFIX = "base/"

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


def main() -> None:
    endpoint = settings.MINIO_ENDPOINT.lstrip("http://").lstrip("https://")
    client = Minio(
        endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )

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

    print("\nDone. Base Astro template uploaded to MinIO.")


if __name__ == "__main__":
    main()
