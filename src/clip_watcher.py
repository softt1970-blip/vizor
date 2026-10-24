import re
import os
import sys
import json
import shutil
import subprocess
import httpx
import pyperclip
import keyboard
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw
import pystray
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
        new_toast.text_fields = [str(title), str(message)]
        toaster.show_toast(new_toast)
    except Exception as e:
        print(f"[Toast Error] {e}")

def get_project_files():
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
    if file_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rel = file_path.relative_to(BASE_DIR)
        dest = BACKUP_DIR / f"{rel}.{timestamp}.bak"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)

def parse_with_local_llm(text: str, existing_files: list):
    files_str = "\n".join(existing_files) if existing_files else "Проект пуст"
    prompt = f"""Ты — файловый диспетчер проекта VIZOR.
Пользователь скопировал текст из чата ИИ с кодом или инструкцией.
Сопоставь код с существующими файлами проекта или укажи правильный путь.

СПИСОК СУЩЕСТВУЮЩИХ ФАЙЛОВ В ПРОЕКТЕ:
{files_str}

ПРАВИЛА:
1. Если код обновляет существующий файл — верни СТРОГО путь этого файла из списка.
2. Если файла еще нет — выбери подходящий относительный путь.
3. Команды для выполнения верни строгим списком (без префикса powershell, чистые команды).

Ответь СТРОГО валидным JSON без markdown:
{{
  "files": [
    {{"path": "путь/к_файлу.ext", "content": "код"}}
  ],
  "commands": ["команда_1"]
}}

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
                    raw = resp.json()["response"].strip()
                    return json.loads(raw)
        except Exception:
            continue
    return {"files": [], "commands": []}

def normalize_command(cmd_raw) -> str:
    if isinstance(cmd_raw, dict):
        cmd = cmd_raw.get("command") or cmd_raw.get("cmd") or str(cmd_raw)
    else:
        cmd = str(cmd_raw).strip()
    
    # Убираем дублирующий вызов powershell / pwsh в начале строки
    cmd = re.sub(r"^(?:powershell|pwsh)\s+(?:-Command\s+)?", "", cmd, flags=re.IGNORECASE)
    return cmd.strip()

def execute_command_with_feedback(cmd_raw):
    cmd = normalize_command(cmd_raw)
    if not cmd:
        return

    show_toast("VIZOR Runner", f"Выполняется:\n{cmd}")
    
    # Оборачиваем вызов так, чтобы любые исключения PowerShell гарантированно попадали в stdout/stderr
    ps_wrapped = f"$ErrorActionPreference = 'Continue'; try {{ {cmd} }} catch {{ Write-Error$_ }}"
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_wrapped],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        stdout_clean = result.stdout.strip()
        stderr_clean = result.stderr.strip()
        
        # Проверяем признаки ошибки
        has_error = (result.returncode != 0) or bool(stderr_clean) or ("Cannot find path" in stdout_clean)
        
        if not has_error:
            out_preview = stdout_clean[:100] if stdout_clean else "Успешно"
            show_toast("VIZOR Runner", f"Успешно: {cmd}\n{out_preview}")
        else:
            err_details = stderr_clean if stderr_clean else stdout_clean
            if not err_details:
                err_details = f"Команда вернула код ошибки {result.returncode}"
                
            fix_prompt = (
                f"При выполнении команды в VIZOR:\n"
                f"`{cmd}`\n\n"
                f"Возникла ошибка:\n"
                f"```text\n{err_details}\n```\n\n"
                f"Объясни причину и дай исправленный код или команду."
            )
            pyperclip.copy(fix_prompt)
            show_toast("VIZOR Ошибка! Запрос в буфере", "Текст ошибки скопирован! Нажмите Ctrl+V в чате.")
    except Exception as e:
        pyperclip.copy(f"Ошибка вызова: {e}")
        show_toast("VIZOR Runner Ошибка", str(e))

def process_clipboard():
    text = pyperclip.paste()
    if not text.strip():
        return

    existing_files = get_project_files()
    data = parse_with_local_llm(text, existing_files)
    files = data.get("files", [])
    commands = data.get("commands", [])

    if not files and not commands:
        return

    updated_files = []
    for item in files:
        rel_path = item["path"].lstrip("\\/").replace("/", os.sep)
        full_path = (BASE_DIR / rel_path).resolve()
        
        is_update = full_path.exists()
        backup_file(full_path)
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(item["content"].strip() + "\n")
            
        action = "Обновлен" if is_update else "Создан"
        updated_files.append(f"{action}: {rel_path}")

    if updated_files:
        show_toast("VIZOR: Файлы применены", "\n".join(updated_files[:3]))

    for cmd_item in commands:
        execute_command_with_feedback(cmd_item)

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color=(25, 25, 25))
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill=(0, 200, 100))
    d.polygon([(32, 20), (20, 44), (44, 44)], fill=(255, 255, 255))

    def on_process(icon, item):
        process_clipboard()

    def on_exit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Обработать буфер (Alt+V)", on_process),
        pystray.MenuItem("Выход", on_exit)
    )
    return pystray.Icon("VIZOR", image, "VIZOR Agent", menu)

if __name__ == "__main__":
    keyboard.add_hotkey('alt+v', process_clipboard)
    show_toast("VIZOR Запущен", f"Модель: {MODEL_NAME}\nГорячая клавиша: Alt + V")
    icon = create_tray_icon()
    icon.run()
