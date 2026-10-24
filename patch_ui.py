import ctypes
from pathlib import Path

target_file = Path(r"H:\VIZOR\src\clip_watcher.py")
content = target_file.read_text(encoding="utf-8")

new_overlay_code = '''def apply_dark_titlebar(window):
    try:
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass

def show_preview_overlay(files: list, commands: list):
    root = tk.Tk()
    root.title("VIZOR Studio — Подтверждение изменений")
    root.geometry("780x580")
    root.attributes("-topmost", True)
    root.configure(bg="#181818")
    apply_dark_titlebar(root)

    # Верхний статус-бар
    top_bar = tk.Frame(root, bg="#1e1e1e", padx=16, pady=12)
    top_bar.pack(fill="x")

    badge_frame = tk.Frame(top_bar, bg="#1e1e1e")
    badge_frame.pack(side="left", fill="x", expand=True)

    tk.Label(
        badge_frame, text="⚡ VIZOR", font=("Segoe UI", 10, "bold"),
        fg="#00e676", bg="#252526", padx=8, pady=2
    ).pack(side="left", padx=(0, 10))

    tk.Label(
        badge_frame, text=f"Проект: {BASE_DIR.name}",
        font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e"
    ).pack(side="left")

    # Панель метаданных (Файлы и команды)
    meta_box = tk.Frame(root, bg="#222222", padx=16, pady=10)
    meta_box.pack(fill="x", padx=16, pady=(0, 8))

    files_list = [f["path"] for f in files] if files else []
    files_str = "  •  ".join(files_list) if files_list else "без изменений файлов"
    cmds_str = " && ".join([normalize_command(c) for c in commands]) if commands else "нет команд"

    f_row = tk.Frame(meta_box, bg="#222222")
    f_row.pack(fill="x", pady=2)
    tk.Label(f_row, text="ФАЙЛЫ:", font=("Segoe UI", 8, "bold"), fg="#888888", bg="#222222", width=10, anchor="w").pack(side="left")
    tk.Label(f_row, text=files_str, font=("Segoe UI", 9, "bold"), fg="#4ec9b0", bg="#222222", anchor="w").pack(side="left")

    c_row = tk.Frame(meta_box, bg="#222222")
    c_row.pack(fill="x", pady=2)
    tk.Label(c_row, text="RUNNER:", font=("Segoe UI", 8, "bold"), fg="#888888", bg="#222222", width=10, anchor="w").pack(side="left")
    tk.Label(c_row, text=cmds_str, font=("Segoe UI", 9), fg="#9cdcfe", bg="#222222", anchor="w").pack(side="left")

    # Панель действий снизу (кнопки)
    bottom_bar = tk.Frame(root, bg="#1e1e1e", padx=16, pady=12)
    bottom_bar.pack(side="bottom", fill="x")

    def on_confirm(event=None):
        root.destroy()
        apply_confirmed_actions(files, commands)

    def on_cancel(event=None):
        root.destroy()
        print("[-] Изменения отклонены пользователем.")

    root.bind("<Return>", on_confirm)
    root.bind("<Escape>", on_cancel)

    btn_cancel = tk.Button(
        bottom_bar, text="Отмена (Esc)", font=("Segoe UI", 9),
        bg="#2d2d2d", fg="#cccccc", activebackground="#3e3e3e", activeforeground="#ffffff",
        relief="flat", padx=16, pady=6, cursor="hand2", command=on_cancel
    )
    btn_cancel.pack(side="right", padx=6)

    btn_ok = tk.Button(
        bottom_bar, text="✔ Применить (Enter)", font=("Segoe UI", 9, "bold"),
        bg="#0e639c", fg="#ffffff", activebackground="#1177bb", activeforeground="#ffffff",
        relief="flat", padx=20, pady=6, cursor="hand2", command=on_confirm
    )
    btn_ok.pack(side="right", padx=6)

    # Редактор предпросмотра с номерами строк
    editor_frame = tk.Frame(root, bg="#1e1e1e", padx=16, pady=4)
    editor_frame.pack(side="top", fill="both", expand=True)

    line_numbers = tk.Text(
        editor_frame, width=4, bg="#1e1e1e", fg="#5a5a5a",
        font=("Cascadia Code", 10), relief="flat", wrap="none", state="disabled", padx=4
    )
    line_numbers.pack(side="left", fill="y")

    preview_text = tk.Text(
        editor_frame, bg="#1e1e1e", fg="#d4d4d4", insertbackground="#aeafad",
        font=("Cascadia Code", 10), relief="flat", wrap="none", padx=8, pady=4
    )
    
    # Настройка тегов подсветки базового синтаксиса
    preview_text.tag_configure("kw", foreground="#569cd6")
    preview_text.tag_configure("def", foreground="#dcdcaa")
    preview_text.tag_configure("str", foreground="#ce9178")
    preview_text.tag_configure("comment", foreground="#6a9955")

    scroll = tk.Scrollbar(editor_frame, orient="vertical", command=preview_text.yview)
    preview_text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    preview_text.pack(side="left", fill="both", expand=True)

    raw_content = ""
    if files:
        raw_content = files[0].get("content", "")
    elif commands:
        raw_content = "# Терминальные команды к запуску:\n" + "\n".join([normalize_command(c) for c in commands])

    preview_text.insert("1.0", raw_content)

    # Подсветка ключевых слов
    for kw in ["def ", "class ", "import ", "from ", "return ", "if ", "else:", "for ", "while ", "try:", "except "]:
        start = "1.0"
        while True:
            pos = preview_text.search(kw, start, stopindex=tk.END)
            if not pos:
                break
            end = f"{pos}+{len(kw)}c"
            preview_text.tag_add("kw", pos, end)
            start = end

    # Номера строк
    num_lines = int(preview_text.index("end-1c").split(".")[0])
    line_numbers.config(state="normal")
    line_numbers.delete("1.0", tk.END)
    line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, num_lines + 1)))
    line_numbers.config(state="disabled")

    root.update_idletasks()
    w, h = 780, 580
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.mainloop()
'''

import re
pattern = r"def show_preview_overlay\(files: list, commands: list\):[\s\S]*?(?=def process_clipboard\(\):)"
updated = re.sub(pattern, new_overlay_code + "\n\n", content)

target_file.write_text(updated, encoding="utf-8")
print("[OK] Модуль оверлея успешно обновлен!")
