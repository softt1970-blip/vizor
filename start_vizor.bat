@echo off
echo ==================================================
echo [VIZOR] Starting local environment...
echo ==================================================

tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [+] Ollama is already running.
) else (
    echo [*] Starting Ollama from H:\ollama-portable\start.bat...
    if exist "H:\ollama-portable\start.bat" (
        start "" /min cmd /c "cd /d H:\ollama-portable && call start.bat"
    ) else (
        echo [!] start.bat not found, launching ollama serve directly...
        start "" /B "H:\ollama-portable\ollama.exe" serve
    )
    timeout /t 5 /nobreak >nul
)

echo [*] Starting VIZOR Tray Agent...
start "" "H:\VIZOR\.venv\Scripts\pythonw.exe" "H:\VIZOR\src\clip_watcher.py"

echo ==================================================
echo [+] Environment ready.
echo [+] Hotkeys: Alt + V (Capture) | Alt + Z (Undo)
echo ==================================================
timeout /t 3 >nul
