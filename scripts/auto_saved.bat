REM path: H:\VIZOR\scripts\clean_registry.bat
@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  Очистка реестра с предварительным бэкапом
REM  ЗАПУСКАТЬ ОТ ИМЕНИ АДМИНИСТРАТОРА
REM ============================================================

REM --- 1. Настройки ---
set "BACKUP_DIR=H:\VIZOR\backup"
set "STAMP=%DATE:~-4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%-%TIME:~3,2%-%TIME:~6,2%"
set "STAMP=%STAMP: =0%"

REM --- 2. Создаём папку для бэкапов ---
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

echo [*] Папка бэкапов: %BACKUP_DIR%
echo [*] Метка времени: %STAMP%
echo.

REM --- 3. Делаем бэкап затрагиваемых веток ---
echo [*] Бэкап HKCU\Software ...
reg export "HKCU\Software" "%BACKUP_DIR%\HKCU_Software_%STAMP%.reg" /y >nul
if errorlevel 1 (
    echo [!] ОШИБКА бэкапа HKCU. Прерываем.
    goto :error
)

echo [*] Бэкап HKLM\SOFTWARE ...
reg export "HKLM\SOFTWARE" "%BACKUP_DIR%\HKLM_SOFTWARE_%STAMP%.reg" /y >nul
if errorlevel 1 (
    echo [!] ОШИБКА бэкапа HKLM. Прерываем.
    goto :error
)

echo [+] Бэкап создан успешно.
echo.

REM --- 4. СПИСОК КЛЮЧЕЙ НА УДАЛЕНИЕ ---
REM  Впишите свои пути. Пример ниже — замените на реальные!
set "KEYS_TO_DELETE=HKCU\Software\ExampleApp HKLM\SOFTWARE\ExampleApp"

echo [*] Ключи к удалению:
for %%K in (%KEYS_TO_DELETE%) do echo     - %%K
echo.

REM --- 5. Подтверждение ---
set /p "CONFIRM=Продолжить удаление? (yes/no): "
if /i not "%CONFIRM%"=="yes" (
    echo [*] Отменено пользователем. Бэкап сохранён.
    goto :end
)

REM --- 6. Удаление ---
echo.
for %%K in (%KEYS_TO_DELETE%) do (
    echo [*] Удаляю: %%K
    reg delete "%%K" /f >nul 2>&1
    if errorlevel 1 (
        echo     [!] Не найден или ошибка: %%K
    ) else (
        echo     [+] Удалён.
    )
)

echo.
echo [+] Готово. Бэкап: %BACKUP_DIR%
goto :end

:error
echo.
echo [!] Скрипт остановлен из-за ошибки бэкапа. Ничего не удалено.

:end
echo.
pause
endlocal
