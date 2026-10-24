import re
import os
import sys
import json
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from datetime import datetime

import httpx
import pyperclip
import keyboard
from PIL import Image, ImageDraw
import pystray
from windows_toasts import Toast, WindowsToaster

CONFIG_PATH = Path(r"H:\VIZOR\config.json")
OLLAMA_ENDPOINTS = [
    "http://127.0.0.1:11434/api/generate",
    "http://127.0.0.1:47474/api/generate"
]
toaster = WindowsToaster("VIZOR Agent")
tray_icon_ref = None

def load_config():
    default_cfg = {
        "active_project": r"H:\VIZOR",
        "recent_projects": [r"H:\VIZOR"],
        "model_name": "qwen2.5-coder:7b"
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Config Save Error] {e}")

config = load_config()
BASE_DIR = Path(config.get("active_project", r"H:\VIZOR"))
MODEL_NAME = config.get("model_name", "qwen2.5-coder:7b")

def get_backup_dir():
    return BASE_DIR / ".vizor_history"

def show_toast(title: str, message: str):
    try:
        new_toast = Toast()
        new_toast.text_fields = [str(title), str(message)]
        toaster.show_toast(new_toast)
    except Exception as e:
        print(f"[Toast Error] {e}")

def set_active_project(new_path: str):
    global BASE_DIR, config
    p = Path(new_path).resolve()
    if not p.exists() or not p.is_dir():
        show_toast("VIZOR Ошибка", f"Папка не существует:\n{new_path}")
        return

    BASE_DIR = p
    config["active_project"] = str(p)
    recents = config.get("recent_projects", [])
    if str(p) in recents:
        recents.remove(str(p))
    recents.insert(0, str(p))
    config["recent_projects"] = recents[:5]
    save_config(config)

    show_toast("VIZOR: Проект переключен", f"Активная папка:\n{BASE_DIR.name}\n({BASE_DIR})")
    if tray_icon_ref:
        tray_icon_ref.menu = build_menu()

def pick_folder_dialog():
    def _open():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Выберите директорию проекта для VIZOR", initialdir=str(BASE_DIR))
        root.destroy()
        if selected:
            set_active_project(selected)
    threading.Thread(target=_open, daemon=True).start()

def get_project_files():
    ignored = {".git", ".venv", ".vizor_history", "node_modules", "__pycache__", ".idea", ".vscode"}
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
        dest = get_backup_dir() / f"{rel}.{timestamp}.bak"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)

def git_commit_changes(file_names: list):
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        return
    try:
        files_str = ", ".join(file_names[:2])
        if len(file_names) > 2:
            files_str += f" (+{len(file_names) - 2})"
        commit_msg = f"vizor(auto): updated {files_str}"
        subprocess.run(["git", "add", "."], cwd=str(BASE_DIR), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(BASE_DIR), capture_output=True, check=True)
    except Exception as e:
        print(f"[Git Commit Error] {e}")

def git_undo_last_action():
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        show_toast("VIZOR: Откат", "В текущей папке проекта нет репозитория Git.")
        return
    try:
        log_res = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8"
        )
        last_msg = log_res.stdout.strip()
        if last_msg.startswith("vizor(auto):"):
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=str(BASE_DIR), check=True)
            show_toast("VIZOR: Откат выполнен", f"Отменен коммит:\n{last_msg}")
        else:
            subprocess.run(["git", "restore", "."], cwd=str(BASE_DIR), check=True)
            subprocess.run(["git", "clean", "-fd"], cwd=str(BASE_DIR), check=True)
            show_toast("VIZOR: Откат выполнен", "Файлы возвращены к последнему ручному коммиту.")
    except Exception as e:
        show_toast("VIZOR: Ошибка отката", str(e))

def parse_with_local_llm(text: str, existing_files: list):
    files_str = "\n".join(existing_files) if existing_files else "Проект пуст"
    prompt = f"""Ты — файловый диспетчер проекта VIZOR.
Пользователь скопировал текст из чата ИИ с кодом или инструкцией.
Сопоставь код с существующими файлами проекта или укажи правильный путь.

СПИСОК СУЩЕСТВУЮЩИХ ФАЙЛОВ В ПРОЕКТЕ ({BASE_DIR.name}):
{files_str}

ПРАВИЛА:
1. Если код обновляет существующий файл — верни СТРОГО путь этого файла из списка.
2. Если файла еще нет — выбери подходящий относительный путь.
3. Команды для выполнения верни строгим списком чистых команд без вызова powershell.

Ответь СТРОГО валидным JSON без markdown:
{{
  "files": [
    {{"path": "путь/к_файлу.ext", "content": "код"}}
  ],
  "commands": []
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
    return re.sub(r"^(?:powershell|pwsh)\s+(?:-Command\s+)?", "", cmd, flags=re.IGNORECASE).strip()

def execute_command_with_feedback(cmd_raw):
    cmd = normalize_command(cmd_raw)
    if not cmd:
        return
    show_toast("VIZOR Runner", f"[{BASE_DIR.name}] Выполняется:\n{cmd}")
    ps_wrapped = f"Continue = 'Continue'; try {{ {cmd} }} catch {{ Write-Error }}"
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
        has_error = (result.returncode != 0) or bool(stderr_clean) or ("Cannot find path" in stdout_clean)

        if not has_error:
            out_preview = stdout_clean[:100] if stdout_clean else "Успешно"
            show_toast("VIZOR Runner", f"Готово: {cmd}\n{out_preview}")
        else:
            err_details = stderr_clean if stderr_clean else stdout_clean
            if not err_details:
                err_details = f"Код ошибки {result.returncode}"
            fix_prompt = (
                f"При выполнении команды в проекте {BASE_DIR.name}:\n{cmd}\n\n"
                f"Возникла ошибка:\n`	ext\n{err_details}\n`\n\n"
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

    applied_file_names = []
    for item in files:
        rel_path = item["path"].lstrip("\\/").replace("/", os.sep)
        full_path = (BASE_DIR / rel_path).resolve()
        is_update = full_path.exists()
        backup_file(full_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(item["content"].strip() + "\n")
        applied_file_names.append(rel_path)

    if applied_file_names:
        git_commit_changes(applied_file_names)
        show_toast(f"VIZOR [{BASE_DIR.name}]: Применено", "\n".join(applied_file_names[:3]))

    for cmd_item in commands:
        execute_command_with_feedback(cmd_item)

def build_menu():
    recent_items = []
    for r in config.get("recent_projects", []):
        p_name = Path(r).name or r
        recent_items.append(
            pystray.MenuItem(f"{p_name} ({r})", lambda _, item_path=r: set_active_project(item_path))
        )

    menu_structure = [
        pystray.MenuItem(f"Проект: {BASE_DIR.name}", lambda: None, enabled=False),
        pystray.MenuItem("Выбрать папку проекта...", lambda: pick_folder_dialog()),
    ]
    if recent_items:
        menu_structure.append(pystray.MenuItem("Недавние проекты", pystray.Menu(*recent_items)))

    menu_structure.extend([
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Обработать буфер (Alt+V)", lambda: process_clipboard()),
        pystray.MenuItem("Откатить действие (Alt+Z)", lambda: git_undo_last_action()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", lambda icon, item: (icon.stop(), os._exit(0)))
    ])
    return pystray.Menu(*menu_structure)

def create_tray_icon():
    global tray_icon_ref
    image = Image.new('RGB', (64, 64), color=(25, 25, 25))
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill=(0, 200, 100))
    d.polygon([(32, 20), (20, 44), (44, 44)], fill=(255, 255, 255))

    tray_icon_ref = pystray.Icon("VIZOR", image, "VIZOR Agent", build_menu())
    return tray_icon_ref

if __name__ == "__main__":
    keyboard.add_hotkey('alt+v', process_clipboard)
    keyboard.add_hotkey('alt+z', git_undo_last_action)
    show_toast("VIZOR Запущен", f"Проект: {BASE_DIR.name}\nAlt+V: Захват | Alt+Z: Undo")
    icon = create_tray_icon()
    icon.run()