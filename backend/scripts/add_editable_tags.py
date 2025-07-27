from bs4 import BeautifulSoup
import os
import uuid

def add_editable_tags(html_content):
    """Добавляет data-editable-id к редактируемым элементам"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Находим все редактируемые элементы
    editable_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div'])
    
    for element in editable_elements:
        # Добавляем уникальный ID если его еще нет
        if not element.get('data-editable-id'):
            element['data-editable-id'] = str(uuid.uuid4())
    
    return str(soup)

def process_build_directory(build_dir):
    """Обрабатывает все HTML файлы в build директории"""
    for root, dirs, files in os.walk(build_dir):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                
                # Читаем файл
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Добавляем теги
                modified_content = add_editable_tags(content)
                
                # Сохраняем изменения
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)

if __name__ == "__main__":
    build_dir = "dist"  # Директория со сборкой
    process_build_directory(build_dir) 