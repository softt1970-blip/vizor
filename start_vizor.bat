@echo off
chcp 65001 >nul
echo ==================================================
echo [VIZOR] Запуск рабочей среды...
echo ==================================================

:: 1. Проверяем, запущен ли процесс Ollama
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [+] Ollama уже активна.
) else (
    echo [*] Запуск Ollama через H:\ollama-portable\start.bat...
    if exist "H:\ollama-portable\start.bat" (
        start "" /min cmd /c "cd /d H:\ollama-portable && call start.bat"
    ) else (
        echo [!] start.bat не найден, запускаем ollama serve напрямую...
        start "" /B "H:\ollama-portable\ollama.exe" serve
    )
    echo [*] Ожидание инициализации сервера моделей...
    timeout /t 5 /nobreak >nul
)

:: 2. Запуск фонового агента VIZOR
echo [*] Запуск VIZOR Agent в системный трей...
start "" "H:\VIZOR\.venv\Scripts\pythonw.exe" "H:\VIZOR\src\clip_watcher.py"

echo ==================================================
echo [+] Среда готова к работе!
echo [+] Модель: qwen2.5-coder:7b
echo [+] Горячая клавиша: Alt + V
echo ==================================================
timeout /t 3 >nul
