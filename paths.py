"""Пути приложения.

Правило простое: всё изменяемое (config, модели, рантайм, логи) лежит
рядом с программой, в папке data. Так пользователь, поставивший
приложение на D:, не получает 2 ГБ моделей на C:.

Если писать рядом нельзя (Program Files, флешка только для чтения),
уходим в %LOCALAPPDATA%\\EVE LangBridge.
"""

import os
import sys

APP_NAME = "EVE LangBridge"
DATA_DIR_NAME = "data"

_base_dir = None
_data_dir = None


def is_frozen():
    """Запущены ли мы как собранный exe (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """Папка с exe (или с исходниками при запуске из репозитория)."""
    global _base_dir
    if _base_dir is None:
        if is_frozen():
            _base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            _base_dir = os.path.dirname(os.path.abspath(__file__))
    return _base_dir


def resource_path(*parts):
    """Ресурс, упакованный с приложением (иконки и т.п.).

    При сборке PyInstaller распаковывает их во временную папку _MEIPASS."""
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, *parts)


def _ensure_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _fallback_dir():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, APP_NAME)


def data_dir():
    """Каталог для изменяемых данных (config, models, runtime, logs)."""
    global _data_dir
    if _data_dir is not None:
        return _data_dir

    portable = os.path.join(app_dir(), DATA_DIR_NAME)
    if _ensure_writable(portable):
        _data_dir = portable
    else:
        fallback = _fallback_dir()
        os.makedirs(fallback, exist_ok=True)
        _data_dir = fallback
    return _data_dir


def subdir(name):
    path = os.path.join(data_dir(), name)
    os.makedirs(path, exist_ok=True)
    return path


def models_dir():
    return subdir("models")


def runtime_dir():
    return subdir("runtime")


def logs_dir():
    return subdir("logs")


def config_path():
    return os.path.join(data_dir(), "config.json")


def documents_dir():
    """Настоящая папка «Документы» (учитывает OneDrive и локализацию)."""
    if os.name == "nt":
        try:
            import ctypes
            buffer = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL = 5
            result = ctypes.windll.shell32.SHGetFolderPathW(
                None, 5, None, 0, buffer)
            if result == 0 and buffer.value:
                return buffer.value
        except Exception:
            pass
    return os.path.expanduser("~/Documents")


def resolve_input_path(path):
    """Раскрывает '~' и '%VAR%' с учётом перенаправленных «Документов».

    EVE пишет логи в системную папку «Документы», которая на Windows
    может лежать в OneDrive, а не в профиле пользователя."""
    path = (path or "").strip()
    if not path:
        return path
    if path.startswith("~"):
        rest = path[1:].lstrip("/\\")
        lowered = rest.lower()
        if lowered.startswith("documents"):
            rest = rest[len("documents"):].lstrip("/\\")
            path = os.path.join(documents_dir(), rest) if rest else documents_dir()
        else:
            path = os.path.expanduser(path)
    return os.path.expandvars(path)


def find_chatlogs(configured):
    """Ищет папку логов EVE, если настроенная не существует.

    «Документы» на Windows часто перенаправлены в OneDrive, поэтому
    проверяем несколько вероятных мест и берём первое с логами."""
    resolved = resolve_input_path(configured)
    candidates = [
        resolved,
        os.path.join(documents_dir(), "EVE", "logs", "Chatlogs"),
        os.path.expanduser(r"~\Documents\EVE\logs\Chatlogs"),
        os.path.expanduser(r"~\OneDrive\Documents\EVE\logs\Chatlogs"),
        os.path.expanduser(r"~\OneDrive\Документы\EVE\logs\Chatlogs"),
    ]
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        try:
            if os.path.isdir(path) and any(
                    name.lower().endswith(".txt") for name in os.listdir(path)):
                return path
        except OSError:
            continue
    return resolved


def legacy_config_path():
    """Старый config.json рядом с исходниками — только для переезда."""
    return os.path.join(app_dir(), "config.json")


def legacy_config_usable():
    """Есть ли старый конфиг, который ещё не перенесли."""
    legacy = legacy_config_path()
    return os.path.exists(legacy) and not os.path.exists(config_path())
