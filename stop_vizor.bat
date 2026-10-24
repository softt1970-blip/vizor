@echo off
chcp 65001 >nul
echo ==================================================
echo [VIZOR] Завершение сессии...
echo ==================================================

:: 1. Выгрузка VIZOR из трея
taskkill /F /IM pythonw.exe 2>nul
echo [+] Агент VIZOR остановлен.

:: 2. Выгрузка Ollama и освобождение видеопамяти
taskkill /F /IM ollama.exe 2>nul
taskkill /F /IM ollama_app.exe 2>nul
echo [+] Ollama остановлена, память GPU освобождена.

echo ==================================================
echo [✓] Сессия завершена.
echo ==================================================
timeout /t 2 >nul
