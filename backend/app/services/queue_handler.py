from app.services.project_generator import ProjectGenerationService
from app.services.kubernetes import KubernetesService
from app.services.queue import QueueService
import asyncio
import json

class QueueHandler:
    def __init__(self):
        self.queue = QueueService()
        self.project_generator = ProjectGenerationService()
        self.kubernetes = KubernetesService()

    async def start(self):
        """Запускает обработчик очереди"""
        await self.queue.process_generation_tasks(self.handle_generation_task)

    async def handle_generation_task(self, message_data: dict):
        """
        Обрабатывает задачу генерации проекта
        
        Args:
            message_data: словарь с данными задачи
        """
        user_id = message_data["user_id"]
        project_id = message_data["project_id"]
        prompt = message_data["prompt"]

        try:
            # 1. Генерация проекта через AI агентов
            generation_success = await self.project_generator.generate_project(
                user_id=user_id,
                project_id=project_id,
                prompt=prompt
            )
            
            if not generation_success:
                raise Exception("Failed to generate project")

            # 2. Запуск сборки в Kubernetes
            job_name = await self.kubernetes.create_build_job(
                user_id=user_id,
                project_id=project_id
            )

        except Exception as e:
            # В реальном приложении здесь должно быть логирование
            print(f"Error processing generation task: {str(e)}")
