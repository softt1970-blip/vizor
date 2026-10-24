import re
import os
import json
import shutil
import subprocess
import httpx
import pyperclip
import keyboard
from pathlib import Path
from datetime import datetime
from windows_toasts import Toast, WindowsToaster

BASE_DIR = Path(r"H:\VIZOR")
BACKUP_DIR = BASE_DIR / ".vizor_history"
OLLAMA_ENDPOINTS = [
    "http://127.0.0.1:11434/api/generate",
    "http://127.0.0.1:47474/api/generate"
]
MODEL_NAME = "qwen2.5-coder:7b"
toaster = WindowsToaster("VIZOR Agent")

def show_toast(title: str, message: str):
    try:
        new_toast = Toast()
        new_toast.text_fields = [title, message]
        toaster.show_toast(new_toast)
    except Exception as e:
        print(f"[VIZOR Toast Error] {e}")

def get_project_files():
    """Сбор списка существующих рабочих файлов проекта (исключая служебные папки)"""
    ignored = {".git", ".venv", ".vizor_history", "node_modules", "__pycache__"}
    file_list = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in ignored]
        for f in files:
            full = Path(root) / f
            rel = full.relative_to(BASE_DIR)
            file_list.append(str(rel).replace("\\", "/"))
    return file_list

def backup_file(file_path: Path):
    """Создает резервную копию перед перезаписью"""
    if file_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rel = file_path.relative_to(BASE_DIR)
        dest = BACKUP_DIR / f"{rel}.{timestamp}.bak"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)
        print(f"  [Резервная копия] {dest.name}")

def parse_with_local_llm(text: str, existing_files: list):
    print(f"\n[VIZOR] Анализ через {MODEL_NAME} с учетом дерева проекта...")
    
    files_str = "\n".join(existing_files) if existing_files else "Проект пуст"
    
    prompt = f"""Ты — файловый диспетчер проекта VIZOR.
Пользователь скопировал текст из чата ИИ с кодом или исправлением.
Твоя задача: сопоставить код с существующими файлами проекта или указать правильный путь.

СПИСОК СУЩЕСТВУЮЩИХ ФАЙЛОВ В ПРОЕКТЕ:
{files_str}

ПРАВИЛА:
1. Если код является исправлением или новой версией существующего файла (например, html, css, js, py) — верни СТРОГО путь этого файла из списка выше.
2. Если файла еще нет, выбери наиболее логичное имя и относительный путь.
3. Извлеки сопутствующие команды запуска (если они есть).

Ответь СТРОГО валидным JSON-объектом без лишних слов:
{{
  "files": [
    {{"path": "относительный/путь/к_файлу.расширение", "content": "полный код файла"}}
  ],
  "commands": []
}}

Текст из чата:
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
                    raw = resp.json()["response"].strip()
                    return json.loads(raw)
        except Exception:
            continue

    return {"files": [], "commands": []}

def process_clipboard():
    text = pyperclip.paste()
    if not text.strip():
        print("[VIZOR] Буфер обмена пуст.")
        return

    existing_files = get_project_files()
    data = parse_with_local_llm(text, existing_files)
    files = data.get("files", [])
    commands = data.get("commands", [])

    if not files:
        print("[VIZOR] Код для записи не найден.")
        return

    updated_files = []
    for item in files:
        rel_path = item["path"].lstrip("\\/").replace("/", os.sep)
        full_path = (BASE_DIR / rel_path).resolve()
        
        # Если файл уже существовал, делаем бэкап перед перезаписью
        is_update = full_path.exists()
        backup_file(full_path)
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(item["content"].strip() + "\n")
            
        action = "Обновлен (перезаписан)" if is_update else "Создан"
        print(f"  [+] {action}: {rel_path}")
        updated_files.append(f"{action}: {rel_path}")

    show_toast("VIZOR: Файлы применены", "\n".join(updated_files[:3]))

print("==================================================")
print(f" VIZOR Auto-Replace активен ({MODEL_NAME})")
print(" Существующие файлы будут обновляться напрямую.")
print("==================================================")

keyboard.add_hotkey('alt+v', process_clipboard)
keyboard.wait()
