from typing import Optional
from openai import OpenAI
from openai.types.chat import ChatCompletion
from app.core.config import settings
import json

class CodeGeneratorAgent:
    """
    ИИ-агент для генерации кода проекта.
    Преобразует архитектурную спецификацию в готовый код на Astro.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация агента.
        
        Args:
            api_key (Optional[str]): API ключ OpenAI. Если не указан, берется из настроек.
        """
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
    def generate_code(self, spec_json: str) -> str:
        """
        Генерирует код проекта на основе архитектурной спецификации.
        
        Args:
            spec_json (str): JSON строка с архитектурной спецификацией
            
        Returns:
            str: JSON строка с кодом проекта
            
        Raises:
            ValueError: Если входные данные некорректны
            Exception: При ошибках API
        """
        if not spec_json.strip():
            raise ValueError("JSON со спецификацией не может быть пустым")
            
        try:
            # Проверяем что входные данные - валидный JSON
            spec = json.loads(spec_json)
            if not isinstance(spec, dict):
                raise ValueError("Неверный формат JSON спецификации")
        except json.JSONDecodeError:
            raise ValueError("Невалидный JSON спецификации")
            
        system_prompt = """Ты опытный разработчик на фреймворке Astro.
        Твоя задача - создавать код для каждого файла проекта на основе архитектурной спецификации.
        
        Используй:
        - Tailwind CSS для стилизации
        - Современные практики разработки
        - Компонентный подход
        - Типизацию где это возможно
        
        Возвращай только валидный JSON в формате:
        {
          "src": {
            "pages": {
              "index.astro": "код страницы",
              "about.astro": "код страницы"
            },
            "components": {
              "Header.astro": "код компонента",
              "Footer.astro": "код компонента"
            },
            "layouts": {
              "Layout.astro": "код лейаута"
            }
          }
        }
        
        Каждый файл должен содержать полный, готовый к использованию код."""
        
        user_message = f"На основе следующей архитектурной спецификации создай код проекта: {spec_json}"
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.2,  # Низкая температура для более консистентного кода
                max_tokens=4000,
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
            raise Exception(f"Ошибка при генерации кода: {str(e)}")
