import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from app.services.ai_agent0 import TaskDecomposerAgent
from app.services.ai_agent1 import ArchitectAgent
from app.services.ai_agent2 import CodeGeneratorAgent
from app.services.generate_project import generate_project

# Настройка логирования
def setup_logging():
    # Создаем директорию для логов если её нет
    log_dir = Path("tests/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Создаем имя файла с текущей датой и временем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"agent_test_{timestamp}.log"
    
    # Настраиваем формат логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Также выводим в консоль
        ]
    )
    return logging.getLogger(__name__)

def test_individual_agent(agent_name: str, agent, method_name: str, input_data: str, logger):
    """Тестирование отдельного агента с логированием"""
    try:
        logger.info(f"\n{'='*50}\nТестирование {agent_name}")
        logger.info(f"Входные данные:\n{input_data}")
        
        # Вызываем метод агента
        method = getattr(agent, method_name)
        result = method(input_data)
        
        # Логируем результат в красивом формате
        try:
            formatted_result = json.dumps(json.loads(result), indent=2, ensure_ascii=False)
        except:
            formatted_result = result
            
        logger.info(f"Результат:\n{formatted_result}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании {agent_name}: {str(e)}")
        return None

def test_full_pipeline(prompt: str, logger):
    """Тестирование полного пайплайна генерации"""
    try:
        logger.info(f"\n{'='*50}\nТестирование полного пайплайна")
        logger.info(f"Входной промпт:\n{prompt}")
        
        result = generate_project(prompt)
        
        # Логируем результат в красивом формате
        formatted_result = json.dumps(result, indent=2, ensure_ascii=False)
        logger.info(f"Финальный результат:\n{formatted_result}")
        
    except Exception as e:
        logger.error(f"Ошибка в пайплайне: {str(e)}")

def main():
    logger = setup_logging()
    
    # Тестовые промпты
    prompts = [
        "Создать простой блог с главной страницей и страницей статей",
        "Сделать лендинг для продажи курсов по программированию",
        # Добавьте свои промпты здесь
    ]
    
    for prompt in prompts:
        # Тест отдельных агентов
        decomposer = TaskDecomposerAgent()
        architect = ArchitectAgent()
        generator = CodeGeneratorAgent()
        
        # Последовательное тестирование
        tasks_json = test_individual_agent(
            "TaskDecomposerAgent", 
            decomposer, 
            "decompose_task", 
            prompt,
            logger
        )
        
        if tasks_json:
            arch_json = test_individual_agent(
                "ArchitectAgent",
                architect,
                "generate_architecture",
                tasks_json,
                logger
            )
            
            if arch_json:
                test_individual_agent(
                    "CodeGeneratorAgent",
                    generator,
                    "generate_code",
                    arch_json,
                    logger
                )
        
        # Тест полного пайплайна
        test_full_pipeline(prompt, logger)
        
        logger.info(f"\n{'='*50}\nЗавершено тестирование для промпта: {prompt}\n{'='*50}\n")

if __name__ == "__main__":
    main() 