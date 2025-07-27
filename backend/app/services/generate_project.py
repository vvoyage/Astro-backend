from .ai_agent0 import TaskDecomposerAgent
from .ai_agent1 import ArchitectAgent
from .ai_agent2 import CodeGeneratorAgent
from .storage import StorageService
import json
import os
from typing import Union, Optional
from io import BytesIO

class ProjectGenerationService:
    def __init__(self):
        self.task_decomposer = TaskDecomposerAgent()
        self.architect = ArchitectAgent()
        self.code_generator = CodeGeneratorAgent()
        self.storage = StorageService()

    @staticmethod
    def normalize_path(*parts):
        """Нормализует путь, убирая двойные слеши и пустые части"""
        return '/'.join(filter(None, '/'.join(parts).split('/')))

    async def generate_project(self, user_id: str, project_id: str, prompt: str) -> bool:
        try:
            print(f"\n=== Starting project generation ===")
            print(f"User ID: {user_id}")
            print(f"Project ID: {project_id}")
            print(f"Prompt: {prompt}")
            
            # 1. Декомпозиция задачи
            print("\n1. Task decomposition...")
            tasks_json = self.task_decomposer.decompose_task(prompt)
            print(f"Tasks: {tasks_json}")
            
            # 2. Создание архитектуры
            print("\n2. Architecture generation...")
            architecture_json = self.architect.generate_architecture(tasks_json)
            print(f"Architecture: {architecture_json}")
            
            # 3. Генерация кода
            print("\n3. Code generation...")
            code_json = self.code_generator.generate_code(architecture_json)
            
            # 4. Создание базовой структуры согласно ТЗ
            base_dirs = [
                f"projects/{user_id}/{project_id}/src",
                f"projects/{user_id}/{project_id}/build",
                f"projects/{user_id}/{project_id}/snapshots"
            ]
            
            for dir_path in base_dirs:
                normalized_path = ProjectGenerationService.normalize_path(dir_path)
                await self.storage.create_directory("projects", normalized_path)
                print(f"Created directory: {normalized_path}")

            # 5. Сохранение конфигурационных файлов в src
            config_files = {
                "astro.config.mjs": """
import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
    integrations: [tailwind()],
});
                """.strip(),
                
                "package.json": """
{
    "name": "astro-project",
    "version": "0.1.0",
    "private": true,
    "scripts": {
        "dev": "astro dev",
        "build": "astro build",
        "preview": "astro preview"
    },
    "dependencies": {
        "astro": "^4.0.0",
        "@astrojs/tailwind": "^5.0.0"
    }
}
                """.strip(),
                
                "tailwind.config.js": """
module.exports = {
    content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
    theme: {
        extend: {},
    },
    plugins: [],
}
                """.strip()
            }

            # Сохраняем конфиг файлы в src директорию
            for file_name, content in config_files.items():
                full_path = ProjectGenerationService.normalize_path(f"projects/{user_id}/{project_id}/src", file_name)
                print(f"Saving config file: {full_path}")
                file_data = BytesIO(content.encode('utf-8'))
                await self.storage.save_file(
                    bucket_type="projects",
                    object_name=full_path,
                    data=file_data,
                    length=len(content.encode('utf-8'))
                )

            # 6. Сохранение сгенерированных файлов
            try:
                generated_files = json.loads(code_json)
                
                # Проверяем структуру сгенерированных файлов
                if "src" not in generated_files:
                    print("Warning: Generated files don't have 'src' root directory, wrapping...")
                    generated_files = {"src": generated_files}

                async def save_files_recursive(directory: dict, current_path: str):
                    for key, value in directory.items():
                        if isinstance(value, dict):
                            # Это директория
                            new_path = ProjectGenerationService.normalize_path(current_path, key)
                            await save_files_recursive(value, new_path)
                        elif isinstance(value, str):
                            # Это файл
                            full_path = ProjectGenerationService.normalize_path(f"projects/{user_id}/{project_id}", current_path, key)
                            print(f"Saving generated file: {full_path}")
                            file_data = BytesIO(value.encode('utf-8'))
                            await self.storage.save_file(
                                bucket_type="projects",
                                object_name=full_path,
                                data=file_data,
                                length=len(value.encode('utf-8'))
                            )

                # Начинаем сохранение с корневой директории
                await save_files_recursive(generated_files, "")

            except json.JSONDecodeError as e:
                print(f"Error parsing generated files: {str(e)}")
                print(f"Raw code_json: {code_json[:200]}...")  # Показываем только начало для отладки
                return False
            except Exception as e:
                print(f"Error processing generated files: {str(e)}")
                return False

            print("\n=== Project generation completed ===")
            return True
                
        except Exception as e:
            print(f"\n❌ Error generating project: {str(e)}")
            return False