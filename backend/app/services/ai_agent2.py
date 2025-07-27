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
        Твоя задача - создать полноценный проект со следующей структурой:
        
        {
          "src": {
            "pages": {
              "index.astro": "код главной страницы",
              "about.astro": "код страницы о нас",
              "contact.astro": "код страницы контактов"
            },
            "components": {
              "Header.astro": "код компонента шапки",
              "Footer.astro": "код компонента подвала",
              "Navigation.astro": "код компонента навигации"
            },
            "layouts": {
              "Layout.astro": "код основного шаблона"
            },
            "styles": {
              "global.css": "глобальные стили"
            }
          }
        }
        
        Требования:
        1. Все файлы должны содержать реальный, рабочий код
        2. Использовать Tailwind CSS для стилей
        3. Компоненты должны быть переиспользуемыми
        4. Код должен быть типизирован где это возможно
        5. Возвращай только JSON в указанном формате
        6. Все пути к файлам должны быть относительно src директории
        7. Используй современные практики Astro
        8. Добавляй JSDoc комментарии к компонентам
        9. Учитывай SEO-оптимизацию в компонентах
        10. Обеспечь доступность (a11y) компонентов
        """
        
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
