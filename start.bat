@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\pythonw.exe" (
    echo [ОШИБКА] Окружение venv не найдено.
    echo Сначала запусти install.bat
    pause
    exit /b 1
)

start /b venv\Scripts\pythonw.exe main.py
exit