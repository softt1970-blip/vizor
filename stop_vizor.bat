@echo off
echo ==================================================
echo [VIZOR] Stopping environment...
echo ==================================================

taskkill /F /IM pythonw.exe 2>nul
echo [+] VIZOR Agent stopped.

taskkill /F /IM ollama.exe 2>nul
taskkill /F /IM ollama_app.exe 2>nul
echo [+] Ollama stopped, GPU VRAM freed.

echo ==================================================
echo [OK] Session finished.
echo ==================================================
timeout /t 2 >nul
