# backend/tests/test_queue_consumer.py
import sys
import os
from pathlib import Path
import asyncio
import json

# Добавляем путь к корню проекта в PYTHONPATH
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from app.services.queue import QueueService
from app.services.project_generator import ProjectGenerationService

async def process_message(message_data: dict):
    print("\n=== Received message ===")
    print(json.dumps(message_data, indent=2))
    
    # Создаем генератор проекта
    generator = ProjectGenerationService()
    
    # Запускаем генерацию
    success = await generator.generate_project(
        user_id=message_data["user_id"],
        project_id=message_data["project_id"],
        prompt=message_data["prompt"]
    )
    
    print(f"\nGeneration {'successful' if success else 'failed'}")

async def main():
    print("Starting queue consumer...")
    queue = QueueService()
    await queue.process_generation_tasks(process_message)
    
    # Держим скрипт запущенным
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
