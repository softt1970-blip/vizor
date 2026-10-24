import re
import os
import json
import subprocess
import httpx
import pyperclip
import keyboard
from pathlib import Path
from windows_toasts import Toast, WindowsToaster

BASE_DIR = Path(r"H:\VIZOR")
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

def parse_with_local_llm(text: str):
    print(f"\n[VIZOR] Анализ через {MODEL_NAME}...")
    
    prompt = f"""Ты — системный диспетчер проекта VIZOR.
Пользователь скопировал текст из чата ИИ. Проанализируй его и выдели:
1. Файлы для создания/обновления (относительные пути и их содержимое).
2. Команды терминала для запуска (если есть инструкции запустить скрипт, docker, pip, npm и т.д.).

Ответь СТРОГО валидным JSON-объектом без лишнего текста:
{{
  "files": [
    {{"path": "scripts/clean_registry.bat", "content": "код файла"}}
  ],
  "commands": ["команда_1", "команда_2"]
}}

Текст для разбора:
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
                    return json.loads(raw_resp)
        except Exception:
            continue

    # Фолбэк на сохранение как скрипт
    return {
        "files": [{"path": "scripts/auto_saved.bat", "content": text.strip()}],
        "commands": []
    }

def execute_command(cmd: str):
    print(f"\n[VIZOR Runner] Запуск команды: {cmd}")
    try:
        # Исполняем в окружении PowerShell 7 / Windows PowerShell
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if result.stdout:
            print("--- STDOUT ---")
            print(result.stdout.strip())
        if result.stderr:
            print("--- STDERR ---")
            print(result.stderr.strip())
            
        status = "Успешно" if result.returncode == 0 else f"Код ошибки {result.returncode}"
        show_toast("VIZOR: Выполнение завершено", f"{cmd}\n{status}")
    except Exception as e:
        print(f"[VIZOR Runner Error] {e}")

def process_clipboard():
    text = pyperclip.paste()
    if not text.strip():
        print("[VIZOR] Буфер обмена пуст.")
        return

    data = parse_with_local_llm(text)
    files = data.get("files", [])
    commands = data.get("commands", [])

    created_files = []
    for item in files:
        rel_path = item["path"].lstrip("\\/").replace("/", os.sep)
        full_path = (BASE_DIR / rel_path).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(item["content"].strip() + "\n")
        created_files.append(rel_path)
        print(f"  [+] Записан: {rel_path}")

    if created_files:
        show_toast("VIZOR: Файлы сохранены", "\n".join(created_files[:3]))

    # Обработка команд терминала
    if commands:
        print(f"\n[VIZOR] Обнаружены команды для выполнения: {commands}")
        for cmd in commands:
            # Запрос подтверждения безопасности
            print(f"\nВыполнить команду в {BASE_DIR}?")
            print(f">> {cmd}")
            choice = input("Запустить? [Y/n]: ").strip().lower()
            if choice in ["y", "yes", "д", "да", ""]:
                execute_command(cmd)
            else:
                print("Команда пропущена.")

print("==================================================")
print(f" VIZOR Engine + Safe Runner активен ({MODEL_NAME})")
print(" Скопируйте текст из чата и нажмите Alt + V")
print("==================================================")

keyboard.add_hotkey('alt+v', process_clipboard)
keyboard.wait()
