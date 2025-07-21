from typing import Dict
import logging
from app.services.ai_agent0 import TaskDecomposerAgent
from app.services.ai_agent1 import ArchitectAgent
from app.services.ai_agent2 import CodeGeneratorAgent

logger = logging.getLogger(__name__)

def generate_project(user_prompt: str) -> Dict:
    """
    Генерирует проект на основе пользовательского промпта, используя цепочку ИИ-агентов.
    
    Args:
        user_prompt (str): Описание проекта от пользователя
        
    Returns:
        Dict: JSON с кодом готового проекта
        
    Raises:
        ValueError: Если входные данные некорректны
        Exception: При ошибках в процессе генерации
    """
    try:
        logger.info(f"Начало генерации проекта. Промпт: {user_prompt[:100]}...")
        
        # 1. Декомпозиция задачи
        decomposer = TaskDecomposerAgent()
        tasks_json = decomposer.decompose_task(user_prompt)
        logger.info("Декомпозиция задачи завершена успешно")
        
        # 2. Генерация архитектуры
        architect = ArchitectAgent()
        architecture_json = architect.generate_architecture(tasks_json)
        logger.info("Генерация архитектуры завершена успешно")
        
        # 3. Генерация кода
        generator = CodeGeneratorAgent()
        final_code = generator.generate_code(architecture_json)
        logger.info("Генерация кода завершена успешно")
        
        return final_code
        
    except ValueError as e:
        logger.error(f"Ошибка валидации: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Ошибка при генерации проекта: {str(e)}")
        raise Exception(f"Ошибка при генерации проекта: {str(e)}")