import asyncio
import aio_pika
import json
from app.core.config import settings
from app.services.generate_project import ProjectGenerationService

async def process_generation_task(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            # Получаем данные из сообщения
            data = json.loads(message.body.decode())
            user_id = data["user_id"]
            project_id = data["project_id"]
            prompt = data["prompt"]
            
            # Создаем сервис и генерируем проект
            generation_service = ProjectGenerationService()
            success = await generation_service.generate_project(
                user_id=user_id,
                project_id=project_id,
                prompt=prompt
            )
            
            if not success:
                # Обработка ошибки
                print(f"Failed to generate project for user {user_id}")
                
        except Exception as e:
            # Логирование ошибки
            print(f"Error processing message: {str(e)}")

async def run_worker():
    # Подключаемся к RabbitMQ
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    
    # Создаем канал
    channel = await connection.channel()
    
    # Объявляем очередь
    queue = await channel.declare_queue(
        "project_generation",
        durable=True
    )
    
    # Начинаем обработку сообщений
    await queue.consume(process_generation_task)
    
    try:
        # Держим воркер запущенным
        await asyncio.Future()
    finally:
        await connection.close()

if __name__ == "__main__":
    asyncio.run(run_worker())