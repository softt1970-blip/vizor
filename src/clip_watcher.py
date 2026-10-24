import difflib
import shutil
import json
import re
import os
import sys
import json
import socket
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from datetime import datetime

# Одиночный экземпляр
try:
    _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _lock.bind(("127.0.0.1", 49222))
except OSError:
    print("[!] Экземпляр VIZOR уже запущен.")
    sys.exit(0)

import httpx
import pyperclip
import keyboard
from PIL import Image, ImageDraw
import pystray
from windows_toasts import Toast, WindowsToaster

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
OLLAMA_ENDPOINTS = [
    "http://127.0.0.1:11434/api/generate",
    "http://127.0.0.1:47474/api/generate"
]
toaster = WindowsToaster("VIZOR Agent")
tray_icon_ref = None

def load_config():
    cfg = {"active_project": str(ROOT_DIR), "recent_projects": [str(ROOT_DIR)], "model_name": "qwen2.5-coder:7b"}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

config = load_config()
BASE_DIR = Path(config.get("active_project", str(ROOT_DIR)))
MODEL_NAME = config.get("model_name", "qwen2.5-coder:7b")

def show_toast(title, msg):
    try:
        t = Toast()
        t.text_fields = [str(title), str(msg)]
        toaster.show_toast(t)
    except Exception:
        pass

def open_in_vscode():
    try:
        subprocess.Popen(["code", str(BASE_DIR)], shell=True)
    except Exception:
        pass

def set_active_project(new_path):
    global BASE_DIR, config
    p = Path(new_path).resolve()
    if p.exists() and p.is_dir():
        BASE_DIR = p
        config["active_project"] = str(p)
        rec = [x for x in config.get("recent_projects", []) if x != str(p)]
        config["recent_projects"] = [str(p)] + rec[:4]
        save_config(config)
        show_toast("VIZOR: Проект", BASE_DIR.name)
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
    fl = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in ignored]
        for f in files:
            fl.append(str((Path(root) / f).relative_to(BASE_DIR)).replace("\\", "/"))
    return fl

def git_commit_changes(names):
    if not (BASE_DIR / ".git").exists(): return
    try:
        subprocess.run(["git", "add", "."], cwd=str(BASE_DIR), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", f"vizor(auto): updated {', '.join(names[:2])}"], cwd=str(BASE_DIR), capture_output=True, check=True)
    except Exception:
        pass

def git_undo():
    if not (BASE_DIR / ".git").exists(): return
    try:
        log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8").stdout.strip()
        if log.startswith("vizor(auto):"):
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=str(BASE_DIR), check=True)
            show_toast("VIZOR Откат", "Коммит отменен")
        else:
            subprocess.run(["git", "restore", "."], cwd=str(BASE_DIR), check=True)
            subprocess.run(["git", "clean", "-fd"], cwd=str(BASE_DIR), check=True)
            show_toast("VIZOR Откат", "Файлы восстановлены")
    except Exception as e:
        show_toast("VIZOR Ошибка отката", str(e))

def parse_with_local_llm(text, files):
    f_str = "\n".join(files) if files else "Пусто"
    prompt = f"""Ты — системный диспетчер VIZOR.
Файлы проекта ({BASE_DIR.name}):
{f_str}

Инструкции:
1. Если файл новый — обязательно создай его и укажи путь в path (например: app.py). Не отказывай в создании!
2. В content передавай чистый код без markdown.
3. В commands передавай терминальные команды запуска (если есть).

JSON:
{{"files": [{{"path": "file.ext", "content": "код"}}], "commands": []}}

Текст:
{text}"""
    for ep in OLLAMA_ENDPOINTS:
        try:
            with httpx.Client(timeout=40.0) as client:
                r = client.post(ep, json={"model": MODEL_NAME, "prompt": prompt, "stream": False, "format": "json"})
                if r.status_code == 200:
                    return json.loads(r.json()["response"].strip())
        except Exception:
            continue
    return {"files": [], "commands": []}

def normalize_cmd(c):
    if isinstance(c, dict): c = c.get("command") or c.get("cmd") or str(c)
    return re.sub(r"^(?:powershell|pwsh)\s+(?:-Command\s+)?", "", str(c), flags=re.I).strip()



# --- VIZOR ENHANCED MODULES ---
UNDO_DIR = BASE_DIR / ".vizor_undo"
UNDO_DIR.mkdir(exist_ok=True)

def speak_async(phrase: str):
    try:
        cmd = f"(New-Object -ComObject SAPI.SpVoice).Speak('{phrase}')"
        subprocess.Popen(["powershell", "-NoProfile", "-Command", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def backup_files_for_undo(files_dict):
    try:
        manifest = {}
        for fpath in files_dict.keys():
            if fpath.exists():
                b_name = fpath.name + ".bak"
                shutil.copy2(fpath, UNDO_DIR / b_name)
                manifest[str(fpath)] = str(UNDO_DIR / b_name)
            else:
                manifest[str(fpath)] = None
        (UNDO_DIR / "last_undo.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def perform_undo():
    manifest_file = UNDO_DIR / "last_undo.json"
    if not manifest_file.exists():
        show_toast("VIZOR Undo", "Нет доступных действий для отката")
        speak_async("Нет действий для отката")
        return
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        for orig_str, bak_str in manifest.items():
            orig_path = Path(orig_str)
            if bak_str is None:
                if orig_path.exists():
                    orig_path.unlink()
            else:
                bak_path = Path(bak_str)
                if bak_path.exists():
                    shutil.copy2(bak_path, orig_path)
        manifest_file.unlink()
        show_toast("VIZOR Undo", "Изменения успешно отменены!")
        speak_async("Изменения отменены")
    except Exception as e:
        show_toast("VIZOR Undo Ошибка", str(e))

def compute_diff_view(fpath: Path, new_content: str) -> str:
    if not fpath.exists():
        lines = new_content.splitlines()
        return "\n".join(f"+ {line}" for line in lines[:80])
    
    old_content = fpath.read_text(encoding="utf-8", errors="replace")
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{fpath.name}", tofile=f"b/{fpath.name}", lineterm=""))
    if not diff:
        return "[Без изменений] Содержимое файла идентично"
    return "\n".join(diff[:120])

def capture_project_context():
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"], capture_output=True, text=True, encoding="utf-8")
        cb_text = res.stdout.strip()
        target = BASE_DIR / cb_text if cb_text else BASE_DIR
        
        prompt_parts = [f"# Контекст проекта: {BASE_DIR.name}"]
        if target.is_file() and target.exists():
            body = target.read_text(encoding="utf-8", errors="replace")
            prompt_parts.append(f"## Файл: `{target.relative_to(BASE_DIR)}`\n```python\n{body}\n```")
        else:
            files_list = [str(x.relative_to(BASE_DIR)) for x in BASE_DIR.rglob("*") if x.is_file() and ".git" not in x.parts and ".venv" not in x.parts][:40]
            items = "\n".join(f"- {f}" for f in files_list)
            prompt_parts.append(f"## Структура проекта:\n{items}")
            
        prompt_parts.append("\nЗадача: ")
        full_p = "\n\n".join(prompt_parts)
        set_win_clipboard(full_p)
        show_toast("VIZOR Context", "Контекст проекта скопирован в буфер!")
        speak_async("Контекст скопирован")
    except Exception as e:
        show_toast("VIZOR Context Ошибка", str(e))
# ------------------------------

def set_win_clipboard(text_to_copy):
    try:
        subprocess.run(["clip.exe"], input=text_to_copy.encode("utf-16le"), check=True)
        return True
    except Exception:
        return False

def make_error_prompt(cmd, error_text):
    target_file = None
    for part in cmd.split():
        clean = part.strip("'")
        if clean.endswith(('.py', '.js', '.ts', '.go', '.sh', '.bat')):
            fpath = BASE_DIR / clean
            if fpath.exists():
                target_file = fpath
                break

    file_context = ""
    if target_file and target_file.exists():
        try:
            body = target_file.read_text(encoding="utf-8", errors="replace")
            file_context = f"\n\nКод файла `{target_file.name}`:\n```python\n{body}\n```"
        except Exception:
            pass

    return (
        f"При выполнении команды `{cmd}` в проекте `{BASE_DIR.name}` возникла ошибка:\n\n"
        f"```stderr\n{error_text.strip()}\n```"
        f"{file_context}\n\n"
        f"Исправь ошибку и выдай обновленный код файла с указанием имени файла в формате `# File: <путь>`."
    )

def exec_cmd(c_raw):
    cmd = normalize_cmd(c_raw)
    if not cmd: return
    show_toast("VIZOR Runner", cmd)
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or res.stderr.strip():
            raw_err = res.stderr.strip() or res.stdout.strip()
            prompt = make_error_prompt(cmd, raw_err)
            set_win_clipboard(prompt)
            speak_async("Ошибка выполнения")
            show_toast("VIZOR Ошибка", "Промпт с ошибкой и кодом скопирован в буфер!")
    except Exception as e:
        show_toast("VIZOR Ошибка Runner", str(e))

def apply_actions(files, commands):
    backup_files_for_undo(files)
    app = []
    for it in files:
        rel = it["path"].lstrip("\\/").replace("/", os.sep)
        full = (BASE_DIR / rel).resolve()
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(it["content"].strip() + "\n")
        app.append(rel)
    if app:
        git_commit_changes(app)
        show_toast(f"VIZOR [{BASE_DIR.name}]", "\n".join(app[:3]))
    for c in commands: exec_cmd(c)

def show_preview_overlay(files, commands):
    root = tk.Tk()
    root.title("VIZOR HUD")
    root.geometry("840x580")
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    root.configure(bg="#2d2d2d")

    main_frame = tk.Frame(root, bg="#1e1e1e", bd=1, highlightbackground="#007acc", highlightthickness=1)
    main_frame.pack(fill="both", expand=True)

    title_bar = tk.Frame(main_frame, bg="#252526", padx=12, pady=8)
    title_bar.pack(fill="x")

    def start_move(e): root.x = e.x; root.y = e.y
    def do_move(e): root.geometry(f"+{root.winfo_pointerx() - root.x}+{root.winfo_pointery() - root.y}")
    title_bar.bind("<Button-1>", start_move)
    title_bar.bind("<B1-Motion>", do_move)

    badge = tk.Label(title_bar, text="⚡ VIZOR HUD", font=("Segoe UI", 9, "bold"), fg="#00e676", bg="#1b1b1b", padx=6, pady=2)
    badge.pack(side="left", padx=(0, 10))

    t_lbl = tk.Label(title_bar, text=f"Проект: {BASE_DIR.name}  ({BASE_DIR})", font=("Segoe UI", 9), fg="#cccccc", bg="#252526")
    t_lbl.pack(side="left")
    t_lbl.bind("<Button-1>", start_move)
    t_lbl.bind("<B1-Motion>", do_move)

    btn_x = tk.Label(title_bar, text="✕", font=("Segoe UI", 10, "bold"), fg="#888888", bg="#252526", padx=8, cursor="hand2")
    btn_x.pack(side="right")
    btn_x.bind("<Button-1>", lambda e: root.destroy())

    meta_box = tk.Frame(main_frame, bg="#181818", padx=16, pady=10)
    meta_box.pack(fill="x", padx=12, pady=(10, 4))

    files_summary = ", ".join([f["path"] for f in files]) if files else "нет"
    cmds_summary = " && ".join([normalize_cmd(c) for c in commands]) if commands else "нет"

    f_row = tk.Frame(meta_box, bg="#181818")
    f_row.pack(fill="x", pady=2)
    tk.Label(f_row, text="ФАЙЛЫ:", font=("Segoe UI", 8, "bold"), fg="#777777", bg="#181818", width=10, anchor="w").pack(side="left")
    tk.Label(f_row, text=files_summary, font=("Consolas", 10, "bold"), fg="#4ec9b0", bg="#181818", anchor="w").pack(side="left")

    c_row = tk.Frame(meta_box, bg="#181818")
    c_row.pack(fill="x", pady=2)
    tk.Label(c_row, text="RUNNER:", font=("Segoe UI", 8, "bold"), fg="#777777", bg="#181818", width=10, anchor="w").pack(side="left")
    tk.Label(c_row, text=cmds_summary, font=("Consolas", 9), fg="#ce9178", bg="#181818", anchor="w").pack(side="left")

    bottom_bar = tk.Frame(main_frame, bg="#252526", padx=16, pady=10)
    bottom_bar.pack(side="bottom", fill="x")

    def confirm(e=None): root.destroy(); apply_actions(files, commands)
    def cancel(e=None): root.destroy()
    root.bind("<Return>", confirm)
    root.bind("<Escape>", cancel)

    tk.Button(bottom_bar, text="Отмена (Esc)", font=("Segoe UI", 9), bg="#333333", fg="#dddddd", relief="flat", padx=16, pady=6, cursor="hand2", command=cancel).pack(side="right", padx=6)
    tk.Button(bottom_bar, text="✔ Применить (Enter)", font=("Segoe UI", 9, "bold"), bg="#007acc", fg="#ffffff", relief="flat", padx=20, pady=6, cursor="hand2", command=confirm).pack(side="right", padx=6)

    editor_container = tk.Frame(main_frame, bg="#181818", padx=12, pady=6)
    editor_container.pack(side="top", fill="both", expand=True, padx=12, pady=6)

    line_nums = tk.Text(editor_container, width=4, bg="#181818", fg="#555555", font=("Cascadia Code", 10), relief="flat", wrap="none", state="disabled", padx=4, pady=4)
    line_nums.pack(side="left", fill="y")

    preview_text = tk.Text(editor_container, bg="#181818", fg="#d4d4d4", insertbackground="#ffffff", font=("Cascadia Code", 10), relief="flat", wrap="none", padx=8, pady=4)
    preview_text.tag_configure("kw", foreground="#569cd6")
    preview_text.tag_configure("string", foreground="#ce9178")
    preview_text.pack(side="left", fill="both", expand=True)

    raw_code = files[0].get("content", "") if files else ("# Команды:\n" + "\n".join([normalize_cmd(c) for c in commands]))
    preview_text.insert("1.0", raw_code)

    for kw in ["def ", "class ", "import ", "from ", "return ", "if ", "else:", "for ", "while ", "try:", "except "]:
        pos = "1.0"
        while True:
            pos = preview_text.search(kw, pos, stopindex=tk.END)
            if not pos: break
            end = f"{pos}+{len(kw)}c"
            preview_text.tag_add("kw", pos, end)
            pos = end

    total_lines = int(preview_text.index("end-1c").split(".")[0])
    line_nums.config(state="normal")
    line_nums.delete("1.0", tk.END)
    line_nums.insert("1.0", "\n".join(str(i) for i in range(1, total_lines + 1)))
    line_nums.config(state="disabled")

    def on_mousewheel(event):
        preview_text.yview_scroll(int(-1 * (event.delta / 120)), "units")
        line_nums.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    preview_text.bind("<MouseWheel>", on_mousewheel)
    line_nums.bind("<MouseWheel>", on_mousewheel)

    root.update_idletasks()
    root.geometry(f"840x580+{(root.winfo_screenwidth() - 840)//2}+{(root.winfo_screenheight() - 580)//2}")
    root.mainloop()

def process_clip():
    txt = pyperclip.paste()
    if not txt.strip(): return
    data = parse_with_local_llm(txt, get_project_files())
    files = data.get("files", [])
    commands = data.get("commands", [])
    if files or commands:
        threading.Thread(target=show_preview_overlay, args=(files, commands), daemon=True).start()

def build_menu():
    recents = config.get("recent_projects", [])
    recent_items = []
    for r in recents:
        p_name = Path(r).name or r
        recent_items.append(
            pystray.MenuItem(f"{p_name} ({r})", lambda _, item_path=r: set_active_project(item_path))
        )

    menu_structure = [
        pystray.MenuItem(f"Проект: {BASE_DIR.name}", lambda: None, enabled=False),
        pystray.MenuItem("Открыть в VS Code", lambda: open_in_vscode()),
        pystray.MenuItem("Выбрать папку проекта...", lambda: pick_folder_dialog()),
    ]
    if recent_items:
        menu_structure.append(pystray.MenuItem("Недавние проекты", pystray.Menu(*recent_items)))

    menu_structure.extend([
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Обработать буфер (Alt+V)", lambda: process_clip()),
        pystray.MenuItem("Откатить действие (Alt+Z)", lambda: git_undo()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", lambda icon, item: (icon.stop(), os._exit(0)))
    ])
    return pystray.Menu(*menu_structure)

def create_tray():
    global tray_icon_ref
    img = Image.new('RGB', (64, 64), (25, 25, 25))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 16, 48, 48], fill=(0, 200, 100))
    d.polygon([(32, 20), (20, 44), (44, 44)], fill=(255, 255, 255))
    tray_icon_ref = pystray.Icon("VIZOR", img, "VIZOR HUD", build_menu())
    return tray_icon_ref

if __name__ == "__main__":
    keyboard.add_hotkey('alt+v', process_clip)
    try:
        keyboard.add_hotkey('alt+z', perform_undo)
        keyboard.add_hotkey('alt+c', capture_project_context)
    except Exception:
        pass

    keyboard.add_hotkey('alt+z', git_undo)
    print(f"[VIZOR HUD] Запущен. Проект: {BASE_DIR.name}")
    print(f"[VIZOR HUD] Alt+V: оверлей | Alt+Z: откат")
    create_tray().run()