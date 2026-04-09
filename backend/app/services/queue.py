import aio_pika
import json
from app.core.config import settings

class QueueService:
    def __init__(self):
        self.connection = None
        self.channel = None

    async def connect(self):
        if not self.connection:
            self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()

    async def close(self):
        """Закрывает соединение с RabbitMQ"""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.channel = None

    async def send_generation_task(self, user_id: str, project_id: str, prompt: str):
        """Отправляет задачу на генерацию в очередь"""
        await self.connect()
        
        # Объявляем очередь
        queue = await self.channel.declare_queue(
            "project_generation",
            durable=True  # Очередь сохраняется при перезапуске RabbitMQ
        )
        
        message = {
            "user_id": user_id,
            "project_id": project_id,
            "prompt": prompt
        }
        
        # Создаем сообщение
        message_body = aio_pika.Message(
            body=json.dumps(message).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        
        # Публикуем через default exchange
        await self.channel.default_exchange.publish(
            message_body,
            routing_key="project_generation"  # Имя очереди используется как routing key
        )

    async def process_generation_tasks(self, callback):
        """
        Начинает обработку сообщений из очереди
        
        Args:
            callback: асинхронная функция, которая будет вызываться для каждого сообщения
        """
        await self.connect()
        
        queue = await self.channel.declare_queue(
            "project_generation",
            durable=True
        )
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    data = json.loads(message.body.decode())
                    await callback(data)
                except Exception as e:
                    # В реальном приложении здесь должно быть логирование
                    print(f"Error processing message: {str(e)}")
        
        await queue.consume(process_message)