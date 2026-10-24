import re
import os
import json
import httpx
import pyperclip
import keyboard
from pathlib import Path

BASE_DIR = Path(r"H:\VIZOR")
# Проверяем стандартный порт Ollama и порт веб-панели 47474
OLLAMA_ENDPOINTS = [
    "http://127.0.0.1:11434/api/generate",
    "http://127.0.0.1:47474/api/generate"
]
MODEL_NAME = "qwen2.5-coder:7b"

def extract_code_blocks(text: str):
    """Поиск блоков с явно указанными путями"""
    pattern = r"```(?:[\w+-]+)?:?([^\n\r`]+)?\r?\n([\s\S]*?)```"
    matches = re.findall(pattern, text)
    extracted = []
    
    for path_hint, code in matches:
        path_hint = path_hint.strip() if path_hint else ""
        file_path = None
        
        if "/" in path_hint or "\\" in path_hint or "." in path_hint:
            file_path = path_hint
        else:
            first_line = code.strip().split("\n")[0]
            comment_match = re.match(r"^(?:#|//|--|REM|::)\s*(?:File|Path|Файл):\s*(.+)$", first_line, re.IGNORECASE)
            if comment_match:
                file_path = comment_match.group(1).strip()
                code = "\n".join(code.strip().split("\n")[1:])
        
        if file_path:
            extracted.append({"path": file_path, "content": code})
    return extracted

def parse_with_local_llm(text: str):
    """Обращение к qwen2.5-coder:7b для автоматического определения имени файла"""
    print(f"\n[VIZOR] Прямой путь не найден. Анализ через {MODEL_NAME}...")
    
    prompt = f"""Ты — файловый диспетчер проекта VIZOR.
Пользователь скопировал текст из чата ИИ. В нем содержится скрипт или код, но нет явного пути к файлу.
Определи назначение кода и выбери логичный путь и имя файла (например: scripts/clean_registry.bat, src/utils.py, docker-compose.yml).
Верни ответ СТРОГО в формате JSON без кавычек ```json и без лишних слов:
[
  {{"path": "путь/к_файлу.расширение", "content": "содержимое файла"}}
]

Текст:
{text}
"""
    for endpoint in OLLAMA_ENDPOINTS:
        try:
            with httpx.Client(timeout=40.0) as client:
                resp = client.post(endpoint, json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                })
                if resp.status_code == 200:
                    raw_resp = resp.json()["response"].strip()
                    data = json.loads(raw_resp)
                    if isinstance(data, list) and len(data) > 0:
                        return data
                    elif isinstance(data, dict) and "path" in data:
                        return [data]
        except Exception:
            continue

    print("[VIZOR] Локальная модель не ответила по API. Сохраняю в резервный файл scripts/auto_saved.bat")
    # Фолбэк, если API недоступен
    clean_code = re.sub(r"^```[\w+-]*\r?\n|```$", "", text.strip())
    return [{"path": "scripts/auto_saved.bat", "content": clean_code}]

def process_clipboard():
    text = pyperclip.paste()
    if not text.strip():
        print("[VIZOR] Буфер обмена пуст.")
        return

    # 1. Быстрый поиск пути по регулярке
    blocks = extract_code_blocks(text)
    
    # 2. Если пути нет — отдаем в qwen2.5-coder:7b
    if not blocks:
        blocks = parse_with_local_llm(text)

    if not blocks:
        print("[VIZOR] Не удалось распознать код.")
        return

    print(f"\n[VIZOR] Найдено файлов: {len(blocks)}")
    for block in blocks:
        rel_path = block["path"].lstrip("\\/").replace("/", os.sep)
        full_path = (BASE_DIR / rel_path).resolve()
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(block["content"].strip() + "\n")
        print(f"  [+] Записан файл: {full_path}")

print("==================================================")
print(f" VIZOR Watcher активен (Модель: {MODEL_NAME})")
print(" 1. Скопируйте блок из DeepSeek / браузера (Ctrl + C)")
print(" 2. Нажмите Alt + V на клавиатуре")
print("==================================================")

keyboard.add_hotkey('alt+v', process_clipboard)
keyboard.wait()
