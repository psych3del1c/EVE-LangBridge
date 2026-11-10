@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   EVE LangBridge - Установка
echo ============================================
echo.

REM --- 1. Проверка Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo.
    echo Установи Python 3.10+ с https://www.python.org/downloads/
    echo ВАЖНО: при установке поставь галочку "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Найден Python %PYVER%
echo.

REM --- 2. Создание venv ---
if exist "venv\Scripts\activate.bat" (
    echo [OK] Папка venv уже существует, пропускаем создание.
) else (
    echo [..] Создаю виртуальное окружение venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv.
        echo Попробуй запустить от имени администратора или проверь права на папку.
        pause
        exit /b 1
    )
    echo [OK] venv создан.
)
echo.

REM --- 3. Установка зависимостей ---
if not exist "requirements.txt" (
    echo [ОШИБКА] Файл requirements.txt не найден рядом с install.bat.
    pause
    exit /b 1
)

echo [..] Обновляю pip...
call "venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось обновить pip, продолжаю со старой версией.
)
echo.

echo [..] Устанавливаю зависимости (это может занять минуту)...
call "venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости.
    echo Проверь интернет-соединение и попробуй снова.
    pause
    exit /b 1
)
echo.

echo ============================================
echo   УСТАНОВКА ЗАВЕРШЕНА!
echo ============================================
echo.
echo Теперь запускай start.bat (или просто дважды кликни по нему).
echo.
pause