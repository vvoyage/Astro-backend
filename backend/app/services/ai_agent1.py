from typing import Optional
from openai import OpenAI
from openai.types.chat import ChatCompletion
from app.core.config import settings
import json

class ArchitectAgent:
    """
    ИИ-агент для генерации архитектурной спецификации.
    Преобразует список подзадач в архитектурное описание проекта.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация агента.
        
        Args:
            api_key (Optional[str]): API ключ OpenAI. Если не указан, берется из настроек.
        """
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
    def generate_architecture(self, tasks_json: str) -> str:
        """
        Генерирует архитектурную спецификацию на основе списка задач.
        
        Args:
            tasks_json (str): JSON строка с списком задач
            
        Returns:
            str: JSON строка с архитектурной спецификацией
            
        Raises:
            ValueError: Если входные данные некорректны
            Exception: При ошибках API
        """
        if not tasks_json.strip():
            raise ValueError("JSON с задачами не может быть пустым")
            
        try:
            # Проверяем что входные данные - валидный JSON
            tasks = json.loads(tasks_json)
            if not isinstance(tasks.get("tasks"), list):
                raise ValueError("Неверный формат JSON с задачами")
        except json.JSONDecodeError:
            raise ValueError("Невалидный JSON с задачами")
            
        system_prompt = """Ты опытный архитектор веб-приложений. Твоя задача - создавать детальные архитектурные спецификации на основе списка задач.

        Спецификация должна включать:
        1. Структуру страниц с компонентами и их свойствами
        2. Глобальные настройки (тема, цвета, etc.)
        3. Компоненты и их взаимосвязи
        4. Файловую структуру проекта

        Возвращай только валидный JSON в формате:
        {
          "pages": [{
            "name": string,
            "route": string,
            "components": [{
              "type": string,
              "props": object
            }]
          }],
          "global": {
            "theme": string,
            "colors": object
          },
          "components": [{
            "name": string,
            "dependencies": string[],
            "description": string
          }],
          "fileStructure": {
            "directories": [{
              "name": string,
              "files": string[],
              "subdirectories": array
            }]
          }
        }"""
        
        user_message = f"На основе следующих задач создай архитектурную спецификацию: {tasks_json}"
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={ "type": "json_object" }
            )
            
            result = response.choices[0].message.content
            
            if not result:
                raise Exception("Получен пустой ответ от API")
                
            # Проверяем что результат - валидный JSON
            try:
                json.loads(result)
            except json.JSONDecodeError:
                raise Exception("API вернул невалидный JSON")
                
            return result
            
        except Exception as e:
            raise Exception(f"Ошибка при генерации архитектуры: {str(e)}")
