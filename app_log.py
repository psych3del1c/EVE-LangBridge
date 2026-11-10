"""Простой файловый лог приложения.

Нужен, чтобы разбираться с проблемами у пользователей: консоли у exe нет.
Файл: data/logs/app.log, при разрастании старый уезжает в app.log.1.
"""

import os
import threading
import time

import paths

MAX_BYTES = 512 * 1024
_lock = threading.Lock()


def log(message):
    try:
        directory = paths.logs_dir()
        path = os.path.join(directory, "app.log")
        with _lock:
            try:
                if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
                    os.replace(path, path + ".1")
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass
