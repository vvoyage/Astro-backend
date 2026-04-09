# backend/tests/test_minio_files.py
import sys
import os
from pathlib import Path
import asyncio

# Добавляем путь к корню проекта в PYTHONPATH
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from app.services.storage import StorageService

async def list_project_files(user_id: str, project_id: str = "000"):
    print(f"\n=== Файлы проекта {project_id} ===")
    storage = StorageService()
    
    try:
        # Получаем список всех файлов проекта
        files = await storage.list_files(
            bucket_type="projects",
            prefix=f"projects/{user_id}/{project_id}/"
        )
        
        print("\nНайденные файлы:")
        for file in files:
            print(f"- {file}")
            
            # Пробуем прочитать содержимое файла
            if not file.endswith('/'):  # Пропускаем директории
                content = await storage.get_file("projects", file)
                print(f"  Размер: {len(content)} байт")
                
    except Exception as e:
        print(f"Ошибка: {str(e)}")

if __name__ == "__main__":
    # ID пользователя из предыдущего вывода
    USER_ID = "28895aa2-82c5-4aa2-a114-03e5490e4572"
    asyncio.run(list_project_files(USER_ID))
