"""Информация о системе и сбор диагностики для удалённых тестов.

Диагностика намеренно НЕ включает содержимое чата — только версии,
железо, настройки и технические логи движка.
"""

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile

import paths
from version import VERSION

CREATE_NO_WINDOW = 0x08000000

_gpu_cache = None


def ram_gb():
    """Объём оперативной памяти в ГБ."""

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / 1024 ** 3, 1)
    except Exception:
        pass
    return 0.0


def _run(command, timeout=6):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
        return (result.stdout or "").strip()
    except Exception:
        return ""


def gpus():
    """[(имя, ГБ видеопамяти или 0)] — кэшируется, вызов небыстрый."""
    global _gpu_cache
    if _gpu_cache is not None:
        return _gpu_cache

    found = []
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits"])
    for line in out.splitlines():
        name, _, memory = line.rpartition(",")
        if not name:
            continue
        try:
            found.append((name.strip(), round(int(memory) / 1024, 1)))
        except ValueError:
            found.append((line.strip(), 0.0))

    if not found and os.name == "nt":
        # WMI умеет отдавать только 32-битный AdapterRAM, но имя GPU верное.
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "ForEach-Object { $_.Name }"])
        for line in out.splitlines():
            name = line.strip()
            if name:
                found.append((name, 0.0))

    _gpu_cache = found
    return found


def gpu_summary(lang="ru"):
    unit = "ГБ" if lang == "ru" else "GB"
    items = gpus()
    if not items:
        return {"ru": "не определена", "en": "not detected",
                "zh": "未检测到"}.get(lang, "not detected")
    parts = []
    for name, vram in items:
        parts.append(f"{name} ({vram:g} {unit})" if vram else name)
    return ", ".join(parts)


def disk_free_gb(path=None):
    try:
        usage = shutil.disk_usage(path or paths.data_dir())
        return round(usage.free / 1024 ** 3, 1)
    except OSError:
        return 0.0


def hardware_summary(lang="ru"):
    """Короткая строка для мастера первого запуска."""
    units = {
        "ru": ("ГБ", "свободно {v} ГБ"),
        "en": ("GB", "{v} GB free"),
        "zh": ("GB", "可用 {v} GB"),
    }
    gb, free_format = units.get(lang, units["en"])
    parts = [f"{ram_gb():g} {gb} RAM", gpu_summary(lang)]
    free = disk_free_gb()
    if free:
        parts.append(free_format.format(v=f"{free:g}"))
    return " · ".join(parts)


def engine_state_text(status, tr=None):
    """Человеческое описание состояния движка."""
    tr = tr or {}
    state = (status or {}).get("state", "stopped")
    labels = {
        "stopped": tr.get("engine_state_stopped", "Остановлен"),
        "starting": tr.get("engine_state_starting", "Запускается…"),
        "running": tr.get("engine_state_running", "Работает"),
        "error": tr.get("engine_state_error", "Ошибка"),
    }
    text = labels.get(state, state)
    mode = (status or {}).get("mode")
    if state == "running" and mode:
        text += " · " + ("GPU" if mode == "gpu" else "CPU")
    message = (status or {}).get("message")
    if message and state == "error":
        text += ": " + message
    return text


def system_text(engine_status=None):
    lines = [
        f"EVE LangBridge {VERSION}",
        f"Собрано: {platform.platform()}",
        f"Python: {sys.version.split()[0]}",
        f"Папка данных: {paths.data_dir()}",
        f"RAM: {ram_gb():g} ГБ",
        f"GPU: {gpu_summary()}",
        f"Свободно на диске: {disk_free_gb():g} ГБ",
        f"Движок: {json.dumps(engine_status or {}, ensure_ascii=False)}",
        f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    return "\n".join(lines)


def build_diagnostics(config, engine_status=None):
    """Собирает zip с отчётом и логами. Возвращает путь к файлу."""
    folder = os.path.join(paths.data_dir(), "diagnostics")
    os.makedirs(folder, exist_ok=True)
    name = f"EVE-LangBridge-diag-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    archive = os.path.join(folder, name)

    safe_config = json.loads(json.dumps(config or {}))
    # Каналы и содержимое чата в отчёт не попадают.
    safe_config.pop("chats", None)

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system.txt", system_text(engine_status))
        zf.writestr("config.json",
                    json.dumps(safe_config, ensure_ascii=False, indent=2))
        logs = paths.logs_dir()
        for entry in os.listdir(logs):
            path = os.path.join(logs, entry)
            if not os.path.isfile(path):
                continue
            try:
                size = os.path.getsize(path)
                with open(path, "rb") as f:
                    if size > 200 * 1024:
                        f.seek(size - 200 * 1024)
                    zf.writestr(f"logs/{entry}", f.read())
            except OSError:
                pass
    return archive


def open_folder(path):
    try:
        os.startfile(path)
    except Exception:
        pass
