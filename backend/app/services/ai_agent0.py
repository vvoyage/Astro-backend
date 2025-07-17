from typing import Optional
from openai import OpenAI
from openai.types.chat import ChatCompletion
from app.core.config import settings

class TaskDecomposerAgent:
    """
    ИИ-агент для декомпозиции задач на подзадачи.
    Использует OpenAI GPT для анализа и структурирования задач.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация агента.
        
        Args:
            api_key (Optional[str]): API ключ OpenAI. Если не указан, берется из настроек.
        """
        self.client = OpenAI(settings.OPENAI_API_KEY)
        
    async def decompose_task(self, user_prompt: str) -> str:
        """
        Разбивает задачу пользователя на подзадачи используя OpenAI API.
        
        Args:
            user_prompt (str): Описание задачи от пользователя
            
        Returns:
            str: JSON строка с списком подзадач в формате: {"tasks": ["подзадача1", "подзадача2", ...]}
            
        Raises:
            ValueError: Если входные данные некорректны
            Exception: При ошибках API
        """
        if not user_prompt.strip():
            raise ValueError("Prompt не может быть пустым")
            
        system_prompt = """Ты - эксперт по декомпозиции задач. Твоя работа - разбивать задачи на логические подзадачи.
        Анализируй задачу и создавай четкие, конкретные подзадачи.
        Ты должен возвращать только валидный JSON в формате: {"tasks": ["подзадача1", "подзадача2", ...]}
        Каждая подзадача должна быть:
        1. Конкретной и измеримой
        2. Независимой от других подзадач где это возможно
        3. Достаточно детальной для выполнения"""
        
        user_message = f'Разбей следующую задачу на подзадачи: "{user_prompt}"'
        
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=1000,
                response_format={ "type": "json_object" }
            )
            
            # Получаем JSON строку из ответа
            result = response.choices[0].message.content
            
            if not result:
                raise Exception("Получен пустой ответ от API")
                
            return result
            
        except Exception as e:
            raise Exception(f"Ошибка при декомпозиции задачи: {str(e)}") 