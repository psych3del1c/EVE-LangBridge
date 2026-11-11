import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
import json
import os
import queue
import sys
import threading
import time
import webbrowser
import paths
import local_engine
import slang as slang_mod
import system_info
import updater
import app_log
from core import TranslatorEngine
from wizard import SetupWizard
from providers import create_backend, resolve_model, store_backend_config
from version import VERSION
from composer import Composer
from app_icon import (
    make_tk_icon as _make_app_icon,
    make_pil_image as _make_app_image,
)
from ui_theme import (
    CLASSIC_BG, CLASSIC_BTN, CLASSIC_BTN_ACTIVE, CLASSIC_BTN_PRESSED,
    CLASSIC_TEXT, CLASSIC_FONT,
    classic_label as _classic_label,
    classic_button as _classic_button,
    classic_check as _classic_check,
    classic_option as _classic_option,
    classic_radio as _classic_radio,
    classic_entry as _classic_entry,
    center_on_parent as _center_on_parent,
)

# Иконка в системном трее. Если pystray/Pillow нет — приложение работает
# как раньше, просто без значка в трее.
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except Exception:  # pragma: no cover - зависит от окружения
    pystray = None
    Image = ImageDraw = None
    TRAY_AVAILABLE = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

APP_NAME = "EVE LangBridge"
APP_SHORT = "E-LB"

# Внутренние id цветов -> hex. Подписи берутся из LANGS, поэтому
# названия цветов переводятся вместе с интерфейсом.
COLOR_IDS = {
    "white": "#ffffff", "blue": "#3b8ed0", "cyan": "#00bfff",
    "green": "#00ff7f", "yellow": "#fca311", "red": "#ff4444", "gray": "#aaaaaa"
}

# Языки показываем их самоназваниями — так принято в переключателях языка.
LANG_LABELS = {"ru": "Русский", "en": "English", "zh": "中文"}
LANG_CODES = {label: code for code, label in LANG_LABELS.items()}

# Языки, на которых можно показывать названия EVE в переводе.
TERMS_LANG_LABELS = {"en": "English", "ru": "Русский", "zh": "中文"}
TERMS_LANG_CODES = {label: code for code, label in TERMS_LANG_LABELS.items()}

# Палитра и классические виджеты — в ui_theme.py, чтобы мастер первого
# запуска и окно настроек выглядели одинаково.

# Замок: в закрытом состоянии подсвечиваем спокойным песочным цветом
# (яркий #fca311 слишком отвлекал внимание от чата).
LOCK_BG = "#333333"
LOCK_FG = "#c8c8c8"
LOCK_BG_HOVER = "#444444"
LOCK_BG_LOCKED = "#2e2e2e"
LOCK_FG_LOCKED = "#d8b26a"
LOCK_HOVER_LOCKED = "#3a3a3a"

# Единая палитра кнопок в заголовке: бледный песочный акцент,
# скруглённая плашка и мягкая окантовка.
TITLE_ACCENT = "#cf9d45"
TITLE_ACCENT_HOVER = "#dcae5c"
TITLE_ACTIVE_BG = "#2b2110"
TITLE_ACTIVE_BG_HOVER = "#362a14"
TITLE_ACTIVE_BORDER = "#5a4620"

TAB_FONT_FAMILY = "Segoe UI"
TAB_TEXT_PADX = 6


# Курсоры для изменения размера (имена, поддерживаемые Tk на Windows).
# Для диагоналей используются size_nw_se / size_ne_sw — size_se/size_sw
# на Windows не существуют и курсор не менялся.
RESIZE_CURSORS = {
    "sw": "size_ne_sw",
    "se": "size_nw_se",
    "nw": "size_nw_se",
    "ne": "size_ne_sw",
    "w": "size_we",
    "e": "size_we",
    "s": "size_ns",
    "n": "size_ns",
}

LANGS = {
    "ru": {
        "title": "Настройки", "font": "Шрифт:", "alpha": "Прозрачность:",
        "color_orig": "Цвет оригинала:", "color_trans": "Цвет перевода:",
        "chats": "Отображаемые чаты", "no_chats": "Пока нет доступных чатов",
        "lang_ui": "Язык интерфейса:", "lang_target": "Язык перевода:",
        "terms_lang_label": "Названия EVE:",
        "model_label": "Модель перевода:",
        "hide_orig": "Скрыть оригинал (оставить только перевод)",
        "prompt_label": "Промпт для нейросети:",
        "save_prompt": "Сохранить промпт",
        "close_tab": "Закрыть вкладку",
        "clear_chats": "Очистить список чатов",
        "lock": "Unlocked", "unlock": "Locked",
        "cat_translate": "Перевод", "cat_interface": "Интерфейс",
        "cat_prompt": "Промпт", "cat_chats": "Чаты",
        "cat_about": "О программе", "cat_dictionary": "Словарь",
        "log_dir_label": "Папка логов:",
        "log_dir_missing": "не найдена",
        "log_dir_files": "файлов: {n}",
        "empty_hint": ("Ожидание новых сообщений из EVE…\n"
                       "Логи: {path}\nФайлов: {n}\n\n"
                       "Запустите игру и напишите в чат — сообщения появятся здесь."),
        "replay_setting": "Показывать последние сообщения при запуске",
        "composer_placeholder": "Напишите сообщение…",
        "composer_translating": "Перевод…",
        "composer_error": "Не удалось перевести",
        "composer_copied": "Скопировано",
        "composer_autocopy": "Автоматически копировать перевод",
        "composer_you": "вы:",
        "composer_title": "Перевод",
        "dict_phrase": "Слово", "dict_action": "Действие",
        "dict_value": "Замена", "dict_lang": "Язык",
        "dict_source": "Источник", "dict_keep": "Не переводить",
        "dict_replace": "Заменять на…", "dict_add": "Добавить",
        "dict_edit": "Изменить", "dict_delete": "Удалить",
        "dict_open": "Открыть файл", "dict_filter": "Поиск:",
        "dict_builtin": "встроенный", "dict_user": "свой",
        "dict_hint": ("«Не переводить» оставляет слово как есть. «Заменять на…» "
                      "подставляет текст до перевода (gj → good job). Свои записи "
                      "лежат в data\\slang.user.json и не теряются при обновлении."),
        "dict_add_title": "Новая запись", "dict_edit_title": "Изменить запись",
        "dict_ok": "OK", "dict_cancel": "Отмена",
        "dict_need_phrase": "Укажите слово",
        "dict_need_value": "Укажите замену",
        "provider_label": "Провайдер:",
        "backend_builtin": "Встроенный движок",
        "backend_lmstudio": "LM Studio",
        "backend_ollama": "Ollama",
        "backend_openai": "OpenAI-совместимый",
        "gpu_label": "Режим:",
        "gpu_auto": "Авто", "gpu_gpu": "Только GPU", "gpu_cpu": "Только CPU",
        "status_label": "Статус:",
        "engine_state_stopped": "Остановлен",
        "engine_state_starting": "Запускается…",
        "engine_state_running": "Работает",
        "engine_state_error": "Ошибка",
        "not_downloaded": "не скачана",
        "engine_restart": "Перезапустить",
        "engine_repair": "Проверить и починить",
        "open_models": "Открыть папку моделей",
        "wizard_button": "Мастер настройки",
        "diagnostics": "Собрать диагностику",
        "url_label": "Адрес:",
        "key_label": "API-ключ:",
        "check_conn": "Проверить подключение",
        "check_ok": "Подключение есть, моделей: {n}",
        "check_fail": "Не удалось подключиться",
        "diag_saved": "Диагностика сохранена:\n{path}",
        "color_white": "Белый", "color_blue": "Синий", "color_cyan": "Голубой",
        "color_green": "Зелёный", "color_yellow": "Жёлтый",
        "color_red": "Красный", "color_gray": "Серый",
        "about_desc": "Локальный LLM-переводчик чата EVE Online.",
        "credits": "Разработано: ker Egivand и Arnold Olympus для корпорации Sognare",
        "ccp_disclaimer": "EVE Online — торговая марка CCP hf. Приложение не связано с CCP и не одобрено ею.",
        "update_checking": "Проверяем обновления…",
        "update_available": "Доступна версия {version}",
        "update_latest": "Установлена последняя версия",
        "update_error": "Не удалось проверить обновления",
        "update_download": "Скачать",
        "update_check": "Проверить обновления",
        "update_setting": "Проверять обновления",
        "app_name": APP_NAME,
        "tip_settings": "Настройки", "tip_minimize": "Свернуть",
        "tip_close": "Закрыть", "tip_lock": "Заблокировать перемещение окна",
        "tray_show": "Показать окно", "tray_exit": "Выход"
    },
    "en": {
        "title": "Settings", "font": "Font:", "alpha": "Opacity:",
        "color_orig": "Original color:", "color_trans": "Translation color:",
        "chats": "Active chats", "no_chats": "No available chats yet",
        "lang_ui": "UI Language:", "lang_target": "Target Language:",
        "terms_lang_label": "EVE names:",
        "model_label": "Translation model:",
        "hide_orig": "Hide original text (show only translation)",
        "prompt_label": "System Prompt:",
        "save_prompt": "Save prompt",
        "close_tab": "Close tab",
        "clear_chats": "Clear chat list",
        "lock": "Unlocked", "unlock": "Locked",
        "cat_translate": "Translation", "cat_interface": "Interface",
        "cat_prompt": "Prompt", "cat_chats": "Chats",
        "cat_about": "About", "cat_dictionary": "Dictionary",
        "log_dir_label": "Logs folder:",
        "log_dir_missing": "not found",
        "log_dir_files": "files: {n}",
        "empty_hint": ("Waiting for new messages from EVE…\n"
                       "Logs: {path}\nFiles: {n}\n\n"
                       "Start the game and write in chat — messages will appear here."),
        "replay_setting": "Show recent messages on startup",
        "composer_placeholder": "Type a message…",
        "composer_translating": "Translating…",
        "composer_error": "Translation failed",
        "composer_copied": "Copied",
        "composer_autocopy": "Copy translation automatically",
        "composer_you": "you:",
        "composer_title": "Translation",
        "dict_phrase": "Word", "dict_action": "Action",
        "dict_value": "Replacement", "dict_lang": "Language",
        "dict_source": "Source", "dict_keep": "Do not translate",
        "dict_replace": "Replace with…", "dict_add": "Add",
        "dict_edit": "Edit", "dict_delete": "Delete",
        "dict_open": "Open file", "dict_filter": "Search:",
        "dict_builtin": "built-in", "dict_user": "custom",
        "dict_hint": ("\"Do not translate\" keeps the word as is. \"Replace with…\" "
                      "substitutes text before translation (gj → good job). Your "
                      "entries live in data\\slang.user.json and survive updates."),
        "dict_add_title": "New entry", "dict_edit_title": "Edit entry",
        "dict_ok": "OK", "dict_cancel": "Cancel",
        "dict_need_phrase": "Enter a word",
        "dict_need_value": "Enter a replacement",
        "provider_label": "Provider:",
        "backend_builtin": "Built-in engine",
        "backend_lmstudio": "LM Studio",
        "backend_ollama": "Ollama",
        "backend_openai": "OpenAI-compatible",
        "gpu_label": "Mode:",
        "gpu_auto": "Auto", "gpu_gpu": "GPU only", "gpu_cpu": "CPU only",
        "status_label": "Status:",
        "engine_state_stopped": "Stopped",
        "engine_state_starting": "Starting…",
        "engine_state_running": "Running",
        "engine_state_error": "Error",
        "not_downloaded": "not downloaded",
        "engine_restart": "Restart",
        "engine_repair": "Check & repair",
        "open_models": "Open models folder",
        "wizard_button": "Setup wizard",
        "diagnostics": "Collect diagnostics",
        "url_label": "URL:",
        "key_label": "API key:",
        "check_conn": "Test connection",
        "check_ok": "Connected, models: {n}",
        "check_fail": "Connection failed",
        "diag_saved": "Diagnostics saved:\n{path}",
        "color_white": "White", "color_blue": "Blue", "color_cyan": "Cyan",
        "color_green": "Green", "color_yellow": "Yellow",
        "color_red": "Red", "color_gray": "Gray",
        "about_desc": "Local LLM translator for EVE Online chat.",
        "credits": "Developed by ker Egivand and Arnold Olympus for the Sognare corporation",
        "ccp_disclaimer": "EVE Online is a trademark of CCP hf. This application is not affiliated with or endorsed by CCP.",
        "update_checking": "Checking for updates…",
        "update_available": "Version {version} is available",
        "update_latest": "You have the latest version",
        "update_error": "Could not check for updates",
        "update_download": "Download",
        "update_check": "Check for updates",
        "update_setting": "Check for updates",
        "app_name": APP_NAME,
        "tip_settings": "Settings", "tip_minimize": "Minimize",
        "tip_close": "Close", "tip_lock": "Lock window position",
        "tray_show": "Show window", "tray_exit": "Exit"
    },
    "zh": {
        "title": "设置", "font": "字体:", "alpha": "透明度:",
        "color_orig": "原文颜色:", "color_trans": "翻译颜色:",
        "chats": "显示的聊天", "no_chats": "暂无可用聊天",
        "lang_ui": "界面语言:", "lang_target": "翻译语言:",
        "terms_lang_label": "EVE 名称：",
        "model_label": "翻译模型:",
        "hide_orig": "隐藏原文（仅显示翻译）",
        "prompt_label": "系统提示词:",
        "save_prompt": "保存提示词",
        "close_tab": "关闭标签页",
        "clear_chats": "清空聊天列表",
        "lock": "Unlocked", "unlock": "Locked",
        "cat_translate": "翻译", "cat_interface": "界面",
        "cat_prompt": "提示词", "cat_chats": "聊天",
        "cat_about": "关于", "cat_dictionary": "词汇表",
        "log_dir_label": "日志文件夹：",
        "log_dir_missing": "未找到",
        "log_dir_files": "文件数：{n}",
        "empty_hint": ("等待 EVE 新消息…\n"
                       "日志：{path}\n文件数：{n}\n\n"
                       "启动游戏并在聊天中发言，消息会显示在这里。"),
        "replay_setting": "启动时显示最近消息",
        "composer_placeholder": "输入消息…",
        "composer_translating": "翻译中…",
        "composer_error": "翻译失败",
        "composer_copied": "已复制",
        "composer_autocopy": "自动复制译文",
        "composer_you": "你：",
        "composer_title": "翻译",
        "dict_phrase": "词语", "dict_action": "操作",
        "dict_value": "替换为", "dict_lang": "语言",
        "dict_source": "来源", "dict_keep": "不翻译",
        "dict_replace": "替换为…", "dict_add": "添加",
        "dict_edit": "编辑", "dict_delete": "删除",
        "dict_open": "打开文件", "dict_filter": "搜索：",
        "dict_builtin": "内置", "dict_user": "自定义",
        "dict_hint": ("“不翻译”保持原样。“替换为…”会在翻译前替换文本"
                      "（gj → good job）。自定义条目保存在 "
                      "data\\slang.user.json，更新不会覆盖。"),
        "dict_add_title": "新条目", "dict_edit_title": "编辑条目",
        "dict_ok": "确定", "dict_cancel": "取消",
        "dict_need_phrase": "请输入词语",
        "dict_need_value": "请输入替换内容",
        "provider_label": "提供方：",
        "backend_builtin": "内置引擎",
        "backend_lmstudio": "LM Studio",
        "backend_ollama": "Ollama",
        "backend_openai": "OpenAI 兼容",
        "gpu_label": "模式：",
        "gpu_auto": "自动", "gpu_gpu": "仅 GPU", "gpu_cpu": "仅 CPU",
        "status_label": "状态：",
        "engine_state_stopped": "已停止",
        "engine_state_starting": "启动中…",
        "engine_state_running": "运行中",
        "engine_state_error": "错误",
        "not_downloaded": "未下载",
        "engine_restart": "重启",
        "engine_repair": "检查并修复",
        "open_models": "打开模型文件夹",
        "wizard_button": "设置向导",
        "diagnostics": "收集诊断信息",
        "url_label": "地址：",
        "key_label": "API 密钥：",
        "check_conn": "测试连接",
        "check_ok": "已连接，模型数：{n}",
        "check_fail": "连接失败",
        "diag_saved": "诊断信息已保存：\n{path}",
        "color_white": "白色", "color_blue": "蓝色", "color_cyan": "青色",
        "color_green": "绿色", "color_yellow": "黄色",
        "color_red": "红色", "color_gray": "灰色",
        "about_desc": "EVE Online 聊天本地 LLM 翻译器。",
        "credits": "开发者：ker Egivand、Arnold Olympus，Sognare 公司",
        "ccp_disclaimer": "EVE Online 是 CCP hf 的商标。本应用与 CCP 无关，也未获其认可。",
        "update_checking": "正在检查更新…",
        "update_available": "有新版本 {version}",
        "update_latest": "已是最新版本",
        "update_error": "无法检查更新",
        "update_download": "下载",
        "update_check": "检查更新",
        "update_setting": "检查更新",
        "app_name": APP_NAME,
        "tip_settings": "设置", "tip_minimize": "最小化",
        "tip_close": "关闭", "tip_lock": "锁定窗口位置",
        "tray_show": "显示窗口", "tray_exit": "退出"
    }
}


class ToolTip:
    """Классическая всплывающая подсказка для кнопок главного окна."""

    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None
        try:
            widget.bind("<Enter>", self._schedule, add="+")
            widget.bind("<Leave>", self._hide, add="+")
            widget.bind("<ButtonPress>", self._hide, add="+")
        except Exception:
            pass

    def _schedule(self, _event=None):
        self._cancel()
        try:
            self._after_id = self.widget.after(self.delay, self._show)
        except Exception:
            pass

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._tip is not None or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.attributes("-topmost", True)
            tk.Label(
                tip, text=self.text, bg="#ffffe1", fg="#000000",
                relief="solid", bd=1, font=("Tahoma", 8), padx=4, pady=1
            ).pack()
            self._tip = tip
        except Exception:
            self._tip = None

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


DEFAULT_CONFIG = {
    "window": {"geometry": "600x450", "alpha": 0.85, "topmost": True},
    "ui": {
        "font_size": 12, "color_original": "#ffffff",
        "color_translated": "#3b8ed0", "color_highlight": "#fca311",
        "lang_ui": "ru", "lang_target": "ru",
        "terms_lang": "en",
        "check_updates": True,
        "last_update_check": 0,
        "latest_version": "",
        "replay_history": True,
        "composer_lang": "en",
        "composer_autocopy": True,
        "hide_original": False
    },
    "chats": {"all": [], "active": [], "current": None},
    # llm: активный бэкенд + его настройки. Модель у каждого своя:
    # id моделей в LM Studio и Ollama не совпадают.
    "llm": {
        "backend": "builtin",
        "temperature": 0.2,
        "max_tokens": 200,
        "system_prompt": (
            "You are a professional translator for the EVE Online MMORPG chat. "
            "Translate the text into natural, fluent {target_lang}. Focus on "
            "conveying the meaning and context. Output ONLY the translation."
        ),
        "lmstudio": {
            "base_url": "http://localhost:1234/v1",
            "api_key": "lm-studio",
            "model": "local-model",
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "model": "",
        },
        "openai": {
            "base_url": "http://localhost:8080/v1",
            "api_key": "none",
            "model": "",
        },
        "builtin": {
            "model_id": "hy-mt2-1.8b-q4",
            "context": 1024,
            "threads": 0,
            "gpu_layers": "auto",
        },
    },
    "engine": {"log_dir": "~/Documents/EVE/logs/Chatlogs", "poll_interval": 1.0}
}


def load_config():
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    raw = {}
    # Новый конфиг лежит в data/ (рядом с программой или в %LOCALAPPDATA%).
    # Пока его нет — читаем старый config.json из папки с main.py,
    # чтобы настройки не потерялись после обновления.
    path = paths.config_path()
    if not os.path.exists(path) and paths.legacy_config_usable():
        path = paths.legacy_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            _merge_dict(config, raw)
        except Exception:
            pass
    _migrate_config(config, raw)
    return config


def _migrate_config(config, raw):
    """Старый блок lm_studio -> llm."""
    if not isinstance(raw, dict) or "llm" in raw:
        return
    old = config.get("lm_studio")
    if isinstance(old, dict):
        llm = config["llm"]
        # Старый конфиг — значит человек уже настроил LM Studio,
        # встроенный движок ему не навязываем.
        llm["backend"] = "lmstudio"
        section = llm["lmstudio"]
        for key in ("base_url", "api_key", "model"):
            if old.get(key):
                section[key] = old[key]
        for key in ("temperature", "max_tokens", "system_prompt"):
            if old.get(key):
                llm[key] = old[key]
    config.pop("lm_studio", None)


def _merge_dict(base, override):
    for key, value in override.items():
        if key != key.strip():
            continue
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _merge_dict(base[key], value)
        else: base[key] = value


def save_config(config):
    with open(paths.config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


# ==================== EVE-вкладки ====================
class EveTabBar(tk.Frame):
    """Панель вкладок на обычных tk-виджетах.

    CTk-виджеты при быстром ресайзе перерисовываются слишком дорого
    (и успевают «потерять» отрисовку), поэтому здесь только tk.
    """
    DRAG_THRESHOLD = 4

    def __init__(self, master, on_select=None, on_close=None, on_reorder=None,
                 tr_provider=None, **kwargs):
        super().__init__(master, bg="#0d0d0d", height=30, **kwargs)
        self.pack_propagate(False)
        self.on_select = on_select
        self.on_close = on_close
        self.on_reorder = on_reorder
        self.tr_provider = tr_provider or (lambda: {})
        self.tabs = {}
        self.active = None
        self._menu = None
        self._drag_name = None
        self._drag_start_x = 0
        self._drag_active = False
        self._tab_frame = tk.Frame(self, bg="#0d0d0d")
        self._tab_frame.pack(fill="both", expand=True)

        # Кэш последнего применённого шрифта: Tk присылает <Configure>
        # на каждый вложенный виджет, и без кэша шрифт всех вкладок
        # пересчитывался бы сотни раз за один ресайз.
        self._last_width = -1
        self._last_font_size = -1
        self._tab_fonts = {}

        # Привязываем изменение размера для авто-сжатия вкладок
        self.bind("<Configure>", self._on_bar_configure)

    def add_tab(self, name):
        if name in self.tabs:
            return
        col = len(self.tabs)
        container = tk.Frame(self._tab_frame, bg="#0d0d0d", height=30)
        # grid + uniform колонки: все вкладки делят ширину поровну и сжимаются,
        # чтобы поместиться, даже если окно уже их суммарной ширины
        container.grid(row=0, column=col, sticky="nsew", padx=(0, 1))
        self._tab_frame.grid_rowconfigure(0, weight=1)
        self._tab_frame.grid_columnconfigure(col, weight=1, uniform="tab")

        # tk.Label, а не tk.Button: Button после клика забирает фокус и
        # рисует вокруг текста пунктирную рамку, которую не убрать
        # через highlightthickness/takefocus.
        # Текст по центру (как вкладки в браузере), а слишком длинный
        # обрезается в _on_resize по НАЧАЛУ названия, с «…» в конце.
        btn = tk.Label(
            container, text=name, bg="#141414", fg="#c8c8c8",
            font=(TAB_FONT_FAMILY, 10, "bold"), cursor="hand2",
            padx=TAB_TEXT_PADX, pady=0, anchor="center", justify="center"
        )
        btn.pack(side="top", fill="both", expand=True)

        underline = tk.Frame(container, bg="#0d0d0d", height=3)
        underline.pack(side="bottom", fill="x")

        # title — полное имя: текст в кнопке может быть обрезан под ширину.
        self.tabs[name] = {
            "container": container, "btn": btn, "underline": underline,
            "title": name, "shown": name
        }

        # Подсветка при наведении (у активной вкладки свой цвет).
        btn.bind("<Enter>", lambda e, n=name: self._set_hover(n, True), add="+")
        btn.bind("<Leave>", lambda e, n=name: self._set_hover(n, False), add="+")

        # Перетаскивание и контекстное меню.
        self._bind_tab_events(name, container)
        self._bind_tab_events(name, btn)
        self._bind_tab_events(name, underline)

        if self.active is None:
            self.select_tab(name)

        # Вкладок стало больше — ширина на каждую изменилась, сбрасываем кэш.
        self._last_width = -1
        # Пересчитываем шрифт под новую ширину
        self.after_idle(lambda: self._on_resize(None))

    def _bind_tab_events(self, name, widget):
        try:
            widget.bind("<ButtonPress-1>",
                        lambda e, n=name: self._on_tab_press(e, n), add="+")
            widget.bind("<B1-Motion>",
                        lambda e, n=name: self._on_tab_motion(e, n), add="+")
            widget.bind("<ButtonRelease-1>",
                        lambda e, n=name: self._on_tab_release(e, n), add="+")
            widget.bind("<Button-3>",
                        lambda e, n=name: self._show_context_menu(e, n), add="+")
        except Exception:
            pass

    def _show_context_menu(self, event, name):
        tr = self.tr_provider() or {}
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(
            label=tr.get("close_tab", "Close tab"),
            command=lambda n=name: self._request_close(n)
        )
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._menu.grab_release()
            except Exception:
                pass

    # ----- перетаскивание вкладок (как в браузере) -----
    def _on_tab_press(self, event, name):
        if name not in self.tabs:
            return
        self._drag_name = name
        self._drag_start_x = event.x_root
        self._drag_active = False
        # Как в браузере: взятая вкладка сразу становится активной.
        self.select_tab(name)

    def _on_tab_motion(self, event, name):
        if self._drag_name != name or name not in self.tabs:
            return
        if not self._drag_active:
            if abs(event.x_root - self._drag_start_x) < self.DRAG_THRESHOLD:
                return
            self._drag_active = True
        self._reorder_to_pointer(event.x_root)

    def _on_tab_release(self, event, name):
        if self._drag_name != name:
            return
        if self._drag_active and self.on_reorder:
            self.on_reorder(list(self.tabs.keys()))
        self._drag_name = None
        self._drag_active = False

    def _reorder_to_pointer(self, x_root):
        name = self._drag_name
        if name is None or name not in self.tabs:
            return

        order = list(self.tabs.keys())
        x = x_root - self._tab_frame.winfo_rootx()
        others = [n for n in order if n != name]

        new_index = 0
        for other in others:
            container = self.tabs[other]["container"]
            center = container.winfo_x() + container.winfo_width() / 2
            if x > center:
                new_index += 1

        if new_index == order.index(name):
            return

        items = [(n, self.tabs[n]) for n in others]
        items.insert(new_index, (name, self.tabs[name]))
        self.tabs = dict(items)
        self._regrid()

    def _set_hover(self, name, hover):
        """Подсветка вкладки под курсором (активную не перекрашиваем)."""
        tab = self.tabs.get(name)
        if tab is None or name == self.active:
            return
        tab["btn"].configure(bg="#202020" if hover else "#141414")

    def select_tab(self, name):
        if name not in self.tabs:
            return
        for n, t in self.tabs.items():
            if n == name:
                t["btn"].configure(bg="#2b2b2b", fg="#ffffff")
                t["underline"].configure(bg="#fca311")
            else:
                t["btn"].configure(bg="#141414", fg="#c8c8c8")
                t["underline"].configure(bg="#0d0d0d")
        self.active = name
        if self.on_select:
            self.on_select(name)

    def remove_tab(self, name):
        if name not in self.tabs:
            return
        self.tabs[name]["container"].destroy()
        del self.tabs[name]
        self._regrid()
        if self.active == name:
            self.active = None
            if self.tabs:
                self.select_tab(next(iter(self.tabs)))
            elif self.on_select:
                self.on_select(None)

    def _regrid(self):
        """Раскладываем оставшиеся вкладки в непрерывные колонки 0..N-1."""
        # Число вкладок изменилось — ширина на каждую другая, сбрасываем кэш.
        self._last_width = -1
        for col in range(len(self.tabs) + len(self.tabs) + 1):
            try:
                self._tab_frame.grid_columnconfigure(col, weight=0, uniform="")
            except Exception:
                pass
        for i, t in enumerate(self.tabs.values()):
            t["container"].grid_configure(row=0, column=i, sticky="nsew", padx=(0, 1))
            self._tab_frame.grid_columnconfigure(i, weight=1, uniform="tab")
        self.after_idle(lambda: self._on_resize(None))

    def _request_close(self, name):
        if self.on_close:
            self.on_close(name)

    def _on_bar_configure(self, event):
        """Ширина панели вкладок изменилась.

        Повторные вызовы с той же шириной отсекает кэш в _on_resize."""
        if event.widget is not self:
            return
        self._on_resize(event.width)

    def _tab_font(self, size):
        """Шрифт вкладок с кэшем: нужен для измерения ширины текста."""
        font = self._tab_fonts.get(size)
        if font is None:
            font = tkfont.Font(family=TAB_FONT_FAMILY, size=size, weight="bold")
            self._tab_fonts[size] = font
        return font

    @staticmethod
    def _fit_text(text, font, max_px):
        """Обрезает текст по ширине, добавляя «…» в конце.

        Обрезка нужна, чтобы при сужении вкладки был виден НАЧАЛО названия,
        а не случайная середина (Tk сам режет текст по центру)."""
        if max_px <= 0:
            return ""
        if font.measure(text) <= max_px:
            return text
        ellipsis = "…"
        tail = font.measure(ellipsis)
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.measure(text[:mid]) + tail <= max_px:
                low = mid
            else:
                high = mid - 1
        if low <= 0:
            return ellipsis
        return text[:low].rstrip() + ellipsis

    def _on_resize(self, width=None):
        """Подбираем размер шрифта и обрезаем подписи под ширину вкладки.
        Саму ширину делит grid с uniform-колонками, поэтому все вкладки
        всегда помещаются в окно."""
        if not self.tabs:
            return

        if width is None:
            width = self.winfo_width()
        if width <= 1:
            return
        # Ширина не менялась — пересчитывать нечего.
        if width == self._last_width:
            return
        self._last_width = width

        # Ширина, которая достанется одной вкладке
        available_width = width - len(self.tabs)  # минус отступы
        if available_width <= 0:
            return
        tab_width = available_width / len(self.tabs)

        # Настраиваем размер шрифта в зависимости от ширины
        font_size = 10
        if tab_width < 70: font_size = 9
        if tab_width < 55: font_size = 8
        if tab_width < 42: font_size = 7
        if tab_width < 32: font_size = 6

        if font_size != self._last_font_size:
            self._last_font_size = font_size
            for t in self.tabs.values():
                t["btn"].configure(font=(TAB_FONT_FAMILY, font_size, "bold"))

        # Текст обрезаем всегда (ширина могла измениться при том же шрифте),
        # оставляя запас под внутренние отступы Label.
        font = self._tab_font(font_size)
        max_px = int(tab_width) - 2 * TAB_TEXT_PADX - 2
        for tab in self.tabs.values():
            text = self._fit_text(tab["title"], font, max_px)
            # Лишний configure на каждый пиксель ресайза перерисовывает Label.
            if text != tab["shown"]:
                tab["shown"] = text
                tab["btn"].configure(text=text)


class _LockButton(tk.Canvas):
    """Кнопка фиксации окна: надпись «lock», активна — оранжевая."""

    def __init__(self, parent, command, bg="#1a1a1a"):
        super().__init__(parent, width=40, height=24, bg=bg, bd=0,
                         highlightthickness=0, cursor="hand2")
        self._bg = bg
        self._command = command
        self._locked = False
        self._hover = False
        self._text = "lock"
        self._font = tkfont.Font(family="Segoe UI", size=10,
                                 weight="bold")
        self._render()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def set_locked(self, locked):
        self._locked = bool(locked)
        self._render()

    def _click(self, event):
        if self._command:
            self._command()

    def _enter(self, event):
        self._hover = True
        self._render()

    def _leave(self, event):
        self._hover = False
        self._render()

    def _render(self):
        width = self._font.measure(self._text) + 16
        height = 24
        self.configure(width=width)
        self.delete("all")
        if self._locked:
            _rounded_rect(
                self, 1, 2, width - 1, height - 2, 6,
                fill=TITLE_ACTIVE_BG_HOVER if self._hover
                else TITLE_ACTIVE_BG,
                outline=TITLE_ACTIVE_BORDER, width=1)
            color = TITLE_ACCENT_HOVER if self._hover else TITLE_ACCENT
        elif self._hover:
            _rounded_rect(self, 1, 2, width - 1, height - 2, 6,
                          fill="#333333", outline="#333333", width=1)
            color = "#ffffff"
        else:
            color = "#e0e0e0"
        self.create_text(width / 2, height / 2, text=self._text,
                         fill=color, font=self._font)


class _TranslateButton(tk.Canvas):
    """Кнопка чата перевода: «⇄ язык», с общей скруглённой плашкой."""

    def __init__(self, parent, command, bg="#1a1a1a"):
        super().__init__(parent, width=44, height=24, bg=bg, bd=0,
                         highlightthickness=0, cursor="hand2")
        self._bg = bg
        self._command = command
        self._text = "⇄ en"
        self._active = False
        self._hover = False
        self._font = tkfont.Font(family="Segoe UI", size=10,
                                 weight="bold")
        self._render()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def set_lang(self, lang):
        self._text = "⇄ %s" % lang
        self._render()

    def set_active(self, active):
        self._active = bool(active)
        self._render()

    def _click(self, event):
        if self._command:
            self._command()

    def _enter(self, event):
        self._hover = True
        self._render()

    def _leave(self, event):
        self._hover = False
        self._render()

    def _render(self):
        width = self._font.measure(self._text) + 16
        height = 24
        self.configure(width=width)
        self.delete("all")
        if self._active:
            _rounded_rect(
                self, 1, 2, width - 1, height - 2, 6,
                fill=TITLE_ACTIVE_BG_HOVER if self._hover
                else TITLE_ACTIVE_BG,
                outline=TITLE_ACTIVE_BORDER, width=1)
            color = TITLE_ACCENT_HOVER if self._hover else TITLE_ACCENT
        elif self._hover:
            _rounded_rect(self, 1, 2, width - 1, height - 2, 6,
                          fill="#333333", outline="#333333", width=1)
            color = "#e0e0e0"
        else:
            color = "#c8c8c8"
        self.create_text(width / 2, height / 2, text=self._text,
                         fill=color, font=self._font)


def _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = (
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    )
    return canvas.create_polygon(points, smooth=True, **kwargs)


class EveTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.settings_window = None
        self.context_menu = None
        # Список моделей LM Studio кэшируем на время открытого окна настроек,
        # иначе каждый переход на вкладку «Язык» ждал бы ответа сервера.
        self._models_cache = None

        self.configure(fg_color="#0d0d0d")

        win = self.config["window"]
        self.attributes("-topmost", bool(win.get("topmost", True)))
        self.attributes("-alpha", float(win.get("alpha", 0.85)))
        self.geometry(win.get("geometry", "600x450"))
        self.overrideredirect(True)
        # Disable window resize constraints for proper stretching
        self.resizable(True, True)

        # --- Переменные для перетаскивания/ресайза ---
        # Смещение курсора относительно левого верхнего угла окна в момент
        # нажатия (экранные координаты). Так позиция не зависит от того,
        # успело ли окно перерисоваться/переехать.
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._is_dragging = False
        self._move_pending = None
        self._pending_position = None
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0
        self._resize_start_posx = 0
        self._resize_start_posy = 0
        self._resize_dir = None
        self._is_locked = False
        self._collapsed = False
        self._collapsed_height = 0
        self._press_x = 0
        self._press_y = 0
        self._drag_moved = False
        self.BORDER_MARGIN = 12  # Запас для захвата краёв окна
        self.TOP_MARGIN = 6      # Верхняя кромка: уже, чтобы не мешать кнопкам
        self.CORNER_MARGIN = 30  # Увеличенная зона нижних углов (для диагонали)
        # Для корректного показа курсора ресайза: запоминаем виджет под мышью
        # и его исходный курсор, чтобы потом вернуть как было.
        self._cursor_widget = None
        self._cursor_widget_orig = ""
        # Отложенное применение геометрии при ресайзе (вариант A):
        # копим последнюю цель и применяем не чаще ~60 раз/сек.
        self._resize_pending = None
        self._pending_geometry = None

        ui_cfg = self.config["ui"]
        self.font_size = int(ui_cfg.get("font_size", 12))
        self.color_orig = ui_cfg.get("color_original", "#ffffff")
        self.color_trans = ui_cfg.get("color_translated", "#3b8ed0")
        self.color_high = ui_cfg.get("color_highlight", "#fca311")
        self.lang_ui = ui_cfg.get("lang_ui", "ru")
        self.lang_target = ui_cfg.get("lang_target", "ru")
        self.terms_lang = ui_cfg.get("terms_lang", "en")
        self.hide_original = ui_cfg.get("hide_original", False)

        chats_cfg = self.config["chats"]
        self.all_channels = list(chats_cfg.get("all", []))
        self.active_channels = [c for c in chats_cfg.get("active", []) if c in self.all_channels]
        self.last_channel = chats_cfg.get("current")

        self.textboxes = {}
        self.tab_names = set()
        self.tray_icon = None
        self.wizard_window = None
        self._wizard_shown = False
        self._status_job = None
        self._settings_status_job = None
        self._settings_page = None
        # Проверка обновлений
        self._update_info = None
        self._update_error = None
        self._update_checking = False
        self._update_checked = False
        # События из чужих потоков (перевод, трей) идут через очередь:
        # вызывать Tk из другого потока нельзя, after() там ненадёжен.
        self._ui_queue = queue.Queue()

        self._build_ui()
        self._restore_tabs()
        self._init_tray()

        engine_cfg = self.config["engine"]
        llm_cfg = self.config["llm"]
        self.system_prompt = llm_cfg.get("system_prompt", "")
        self.log_dir = paths.find_chatlogs(engine_cfg["log_dir"])
        app_log.log(f"app: log_dir raw={engine_cfg['log_dir']!r} "
                    f"resolved={self.log_dir!r} "
                    f"exists={os.path.isdir(self.log_dir)}")
        if not self.tab_names:
            self._show_empty_hint()

        # Бэкенд перевода (LM Studio / Ollama / встроенный движок).
        self.backend = create_backend(llm_cfg)
        self.backend.start()
        if not getattr(self.backend, "managed", False):
            # У встроенного движка модель выбирается из каталога, а не
            # из списка сервера — подменять её нельзя.
            self.backend.model = resolve_model(self.backend)
        store_backend_config(llm_cfg, self.backend)

        self.engine = TranslatorEngine(
            ui_callback=self.receive_message,
            backend=self.backend,
            log_dir=self.log_dir,
            poll_interval=engine_cfg["poll_interval"],
            target_lang=self.lang_target,
            system_prompt=self.system_prompt,
            terms_lang=self.terms_lang,
        )
        self.engine.start()
        app_log.log(f"app: start {VERSION}, data={paths.data_dir()}, "
                    f"backend={self.backend.kind}")
        self.after(900, self._replay_history)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.title(APP_NAME)
        self.after(40, self._drain_ui_queue)
        self._schedule_status_dot(600)
        self.after(1200, self._maybe_first_run_setup)
        self.after(2500, self._maybe_check_updates)

        # Привязка событий ресайза
        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<ButtonPress-1>", self._on_mouse_press, add="+")
        self.bind("<B1-Motion>", self._on_mouse_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_mouse_release, add="+")
        self.bind("<Configure>", self._on_window_configure, add="+")

        # Рекурсивная привязка событий к всем дочерним виджетам,
        # чтобы ресайз работал и при наведении на контент, вкладки и т.д.
        self._bind_events_recursive(self)

    # ---------- Верхний бар ----------
    TITLE_BG = "#1a1a1a"
    TITLE_BAR_HEIGHT = 30

    def _title_button(self, parent, text, command, hover_bg, font=("Segoe UI", 11), width=3):
        """Плоская «кнопка» заголовка на обычном tk.Label.

        tk.Button здесь не годится: после клика он забирает фокус и рисует
        вокруг текста пунктирную рамку (highlightthickness/takefocus её
        не убирают). Label фокус не берёт вовсе.
        CTk-кнопки тоже нельзя: при быстром ресайзе они не успевают
        перерисоваться и превращаются в чёрные/пустые прямоугольники."""
        lbl = tk.Label(
            parent, text=text, bg=self.TITLE_BG, fg="#c8c8c8",
            font=font, cursor="hand2", padx=0, pady=0, width=width
        )
        lbl.bind("<Enter>", lambda e, b=lbl, c=hover_bg: b.configure(bg=c))
        lbl.bind("<Leave>", lambda e, b=lbl, c=self.TITLE_BG: b.configure(bg=c))
        lbl.bind("<ButtonRelease-1>", lambda e, cmd=command: cmd())
        return lbl

    def _build_title_bar(self):
        bar = tk.Frame(self, bg=self.TITLE_BG, height=30)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Сократили название
        self.status_dot = tk.Label(
            bar, text="●", bg=self.TITLE_BG, fg="#5a5a5a",
            font=("Segoe UI", 9)
        )
        self.status_dot.pack(side="left", padx=(10, 0))

        self.title_label = tk.Label(
            bar, text=APP_SHORT, bg=self.TITLE_BG, fg="#c8c8c8",
            font=("Segoe UI", 11, "bold"), cursor="hand2"
        )
        self.title_label.pack(side="left", padx=(4, 0))

        close_btn = self._title_button(bar, "✕", self.on_closing, "#8b1a1a")
        close_btn.pack(side="right", padx=(0, 4), pady=4)

        # Сворачивание — в трей: у окна без рамки нет кнопки на панели задач.
        min_btn = self._title_button(bar, "—", self._minimize_to_tray, "#333333")
        min_btn.pack(side="right", padx=(0, 2), pady=4)

        self.settings_btn = self._title_button(
            bar, "⚙", self._open_settings_menu, "#333333")
        self.settings_btn.pack(side="right", padx=(0, 2), pady=4)

        # Кнопка переводчика: иконка + текущий язык панели.
        self.translate_btn = _TranslateButton(
            bar, self._toggle_composer, bg=self.TITLE_BG)
        self.translate_btn.set_lang(
            self.config["ui"].get("composer_lang", "en"))
        self.translate_btn.pack(side="left", padx=(10, 4), pady=3)

        # Фиксация окна: надпись «lock», в активном состоянии — оранжевая.
        self.lock_btn = _LockButton(
            bar, self._toggle_lock, bg=self.TITLE_BG)
        self.lock_btn.pack(side="left", padx=(0, 4), pady=3)

        for w in (bar, self.title_label):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._end_drag, add="+")

        # Клик (без перетаскивания) по логотипу сворачивает окно
        # до одной верхней панели.
        self.title_label.bind("<ButtonRelease-1>", self._on_logo_click, add="+")

        self._title_bar = bar

    # ---------- кнопка переводчика / замок ----------
    def _composer_open(self):
        composer = getattr(self, "composer", None)
        return bool(composer is not None and composer.expanded)

    def _update_translate_btn(self, expanded=None):
        btn = getattr(self, "translate_btn", None)
        if btn is None:
            return
        if expanded is None:
            expanded = self._composer_open()
        composer = getattr(self, "composer", None)
        lang = composer.lang if composer is not None else \
            self.config["ui"].get("composer_lang", "en")
        btn.set_lang(lang)
        btn.set_active(expanded)

    def _toggle_composer(self):
        composer = getattr(self, "composer", None)
        if composer is None:
            return
        if self._collapsed:
            # Окно свёрнуто до полоски: сначала возвращаем высоту.
            self._toggle_collapse()
            if not composer.expanded:
                composer.set_expanded(True)
            return
        composer.toggle()

    def _toggle_lock(self):
        self._is_locked = not self._is_locked
        self.lock_btn.set_locked(self._is_locked)
        if self._is_locked:
            self.configure(cursor="arrow")

    def _start_drag(self, event):
        # Клик по логотипу (сворачивание/разворачивание) работает и при
        # заблокированном окне, поэтому координаты запоминаем всегда.
        self._press_x = event.x_root
        self._press_y = event.y_root
        self._drag_moved = False
        if self._is_locked:
            return
        # Запоминаем, за какую точку окна «взялись»: дальше позиция считается
        # от абсолютных координат мыши, а не от winfo_x() (он может отставать).
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()
        self._is_dragging = True

    def _do_drag(self, event):
        if self._is_locked or self._resize_dir:
            return
        if abs(event.x_root - self._press_x) > 4 or \
                abs(event.y_root - self._press_y) > 4:
            self._drag_moved = True
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        # Как и при ресайзе: не двигаем окно на каждое событие мыши,
        # а держим последнюю позицию и применяем ~60 раз в секунду.
        self._pending_position = f"+{x}+{y}"
        if self._move_pending is None:
            self._move_pending = self.after(16, self._flush_move)

    def _on_logo_click(self, event=None):
        """Клик (не перетаскивание) по логотипу сворачивает окно."""
        if self._resize_dir or self._drag_moved:
            return
        self._toggle_collapse()

    def _toggle_collapse(self):
        """Свернуть окно до одной верхней панели и вернуть обратно."""
        composer = getattr(self, "composer", None)
        if composer is not None:
            try:
                composer.close_transient()
            except Exception:
                pass
        width = self.winfo_width()
        x, y = self.winfo_x(), self.winfo_y()
        if self._collapsed:
            height = max(120, self._collapsed_height or 200)
            self.geometry(f"{width}x{height}+{x}+{y}")
            self._collapsed = False
        else:
            self._collapsed_height = self.winfo_height()
            self.geometry(f"{width}x{self.TITLE_BAR_HEIGHT}+{x}+{y}")
            self._collapsed = True
        self._resize_dir = None
        self._apply_cursor("", None)

    def _flush_move(self):
        self._move_pending = None
        position = self._pending_position
        self._pending_position = None
        if position and self._is_dragging:
            try:
                self.geometry(position)
            except Exception:
                pass

    def _end_drag(self, event=None):
        if self._move_pending is not None:
            try:
                self.after_cancel(self._move_pending)
            except Exception:
                pass
            self._move_pending = None
        # Финальную позицию применяем сразу, без ожидания кадра.
        if self._pending_position:
            try:
                self.geometry(self._pending_position)
            except Exception:
                pass
            self._pending_position = None
        self._is_dragging = False

    # ---------- Иконка в системном трее ----------
    def _build_tray_menu(self):
        tr = LANGS[self.lang_ui]
        return pystray.Menu(
            pystray.MenuItem(tr["tray_show"], self._tray_show, default=True),
            pystray.MenuItem(tr["tip_settings"], self._tray_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr["tray_exit"], self._tray_exit),
        )

    def _init_tray(self):
        """Значок в трее с меню «Показать / Настройки / Выход».

        Окно без рамки (overrideredirect) не попадает на панель задач,
        поэтому после сворачивания вернуться можно только через трей."""
        if not TRAY_AVAILABLE:
            return
        try:
            self.tray_icon = pystray.Icon(
                "eve_langbridge", _make_app_image(64), APP_NAME,
                self._build_tray_menu())
            self.tray_icon.run_detached()
        except Exception:
            self.tray_icon = None

    def _update_tray_menu(self):
        """Пересобирает меню трея после смены языка интерфейса."""
        if self.tray_icon is None:
            return
        try:
            self.tray_icon.menu = self._build_tray_menu()
        except Exception:
            pass

    def _tray_show(self, *_args):
        # Колбэк pystray приходит из его потока — в Tk заходим через очередь.
        self._post_ui(self._restore_window)

    def _tray_settings(self, *_args):
        self._post_ui(self._open_settings_from_tray)

    def _tray_exit(self, *_args):
        self._post_ui(self.on_closing)

    def _restore_window(self):
        try:
            if self._collapsed:
                self._toggle_collapse()
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
        except Exception:
            pass

    def _open_settings_from_tray(self):
        self._restore_window()
        self._open_settings_menu()

    def _minimize_to_tray(self):
        """Свернуть окно: остаётся только значок в трее."""
        if self.tray_icon is None:
            # Без трея вернуться в окно было бы неоткуда (у окна без рамки
            # нет кнопки на панели задач) — лучше оставить его на экране.
            try:
                self.lift()
            except Exception:
                pass
            return
        try:
            self.withdraw()
        except Exception:
            pass

    # ---------- Бэкенд, мастер настройки, диагностика ----------
    def _apply_backend(self, llm_cfg):
        """Переключает бэкенд на лету: гасит старый, поднимает новый."""
        try:
            self.backend.stop()
        except Exception:
            pass
        self.backend = create_backend(llm_cfg)
        self.backend.start()
        if not getattr(self.backend, "managed", False):
            self.backend.model = resolve_model(self.backend)
        self.engine.backend = self.backend
        self.engine.clear_cache()
        store_backend_config(llm_cfg, self.backend)
        save_config(self.config)
        self._models_cache = None
        self._schedule_status_dot(200)
        return self.backend

    def _backend_label(self, kind):
        tr = LANGS[self.lang_ui]
        return tr.get("backend_" + kind, kind)

    def _kind_from_label(self, label):
        for kind in ("builtin", "lmstudio", "ollama", "openai"):
            if self._backend_label(kind) == label:
                return kind
        return label

    def _open_wizard(self, initial_model=None):
        existing = getattr(self, "wizard_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        self.wizard_window = SetupWizard(
            self, self.lang_ui, self.lang_target,
            on_apply=self._wizard_apply,
            on_external=self._wizard_use_external,
            on_close=self._after_wizard,
            initial_model=initial_model,
        )

    def _wizard_apply(self, model_id):
        llm = self.config["llm"]
        llm["backend"] = "builtin"
        section = llm.setdefault("builtin", {})
        if model_id in local_engine.MODEL_CATALOG:
            section["model_id"] = model_id
        section.setdefault("model_id", local_engine.DEFAULT_MODEL_ID)
        section.setdefault("context", 1024)
        section.setdefault("threads", 0)
        section.setdefault("gpu_layers", "auto")
        return self._apply_backend(llm)

    def _wizard_use_external(self):
        llm = self.config["llm"]
        llm["backend"] = "lmstudio"
        self._apply_backend(llm)
        self._open_settings_menu()
        self._show_settings_page("translate")

    def _after_wizard(self):
        self.wizard_window = None
        self._schedule_status_dot(200)
        if self.settings_window and self.settings_window.winfo_exists():
            self._show_settings_page("translate")

    def _maybe_first_run_setup(self):
        """Мастер показываем, только если встроенный движок не готов."""
        if getattr(self, "_wizard_shown", False):
            return
        if self.backend.kind != "builtin":
            return
        engine = getattr(self.backend, "engine", None)
        if engine is None:
            return
        if (local_engine.runtime_installed()
                and local_engine.model_installed(engine.model_id)):
            return
        if self.wizard_window is not None and self.wizard_window.winfo_exists():
            return
        self._wizard_shown = True
        self._open_wizard()

    # ---------- История при запуске ----------
    def _replay_history(self):
        """Показывает последние сообщения из активных каналов."""
        if not bool(self.config["ui"].get("replay_history", True)):
            return
        channels = list(self.active_channels)
        if not channels:
            return
        try:
            self.engine.replay_history(channels, limit=5)
        except Exception as exc:
            app_log.log(f"history: ошибка {exc!r}")

    def _on_replay_changed(self):
        self.config["ui"]["replay_history"] = bool(self.replay_var.get())
        save_config(self.config)

    # ---------- Проверка обновлений ----------
    def _maybe_check_updates(self):
        if not bool(self.config["ui"].get("check_updates", True)):
            return
        try:
            last = float(self.config["ui"].get("last_update_check", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        if time.time() - last < 24 * 3600:
            return
        self._check_updates(silent=True)

    def _check_updates(self, silent=False):
        if self._update_checking:
            return
        self._update_checking = True
        self._refresh_update_badge()
        threading.Thread(target=self._update_worker, args=(silent,),
                         daemon=True).start()

    def _update_worker(self, silent):
        try:
            info = updater.check(VERSION)
            self._post_ui(self._on_update_result, info, None)
        except Exception as exc:
            # При автоматической проверке молчим: нет сети — не беда.
            self._post_ui(self._on_update_result, None,
                          None if silent else str(exc))

    def _on_update_result(self, info, error):
        self._update_checking = False
        self._update_checked = True
        self._update_info = info
        self._update_error = error
        self.config["ui"]["last_update_check"] = time.time()
        self.config["ui"]["latest_version"] = info["version"] if info else ""
        save_config(self.config)
        self._refresh_update_badge()

    def _update_status_text(self):
        tr = LANGS[self.lang_ui]
        if self._update_checking:
            return tr["update_checking"]
        if not self._update_checked:
            return ""
        if self._update_info:
            return tr["update_available"].format(
                version=self._update_info.get("version", ""))
        if self._update_error:
            return tr["update_error"]
        return tr["update_latest"]

    def _refresh_update_badge(self):
        button = getattr(self, "settings_btn", None)
        if button is not None:
            try:
                button.configure(fg="#d8b26a" if self._update_info else "#c8c8c8")
            except Exception:
                pass
        status = getattr(self, "_update_status_var", None)
        if status is not None and self._settings_page == "about":
            try:
                status.set(self._update_status_text())
            except Exception:
                pass

    def _open_update_page(self):
        url = (self._update_info or {}).get("url") or updater.RELEASES_URL
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _on_check_updates_changed(self):
        self.config["ui"]["check_updates"] = bool(self.check_updates_var.get())
        save_config(self.config)

    def _on_composer_autocopy_changed(self):
        value = bool(self.composer_copy_var.get())
        self.config["ui"]["composer_autocopy"] = value
        if getattr(self, "composer", None) is not None:
            self.composer.autocopy = value
        save_config(self.config)

    # ---------- Индикатор состояния движка ----------
    def _engine_status_text(self):
        engine = getattr(self.backend, "engine", None)
        if engine is None:
            return ""
        return system_info.engine_state_text(engine.status(), LANGS[self.lang_ui])

    def _schedule_status_dot(self, delay=2000):
        job = getattr(self, "_status_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        try:
            self._status_job = self.after(delay, self._update_status_dot)
        except Exception:
            self._status_job = None

    def _update_status_dot(self):
        self._status_job = None
        dot = getattr(self, "status_dot", None)
        if dot is None:
            return
        engine = getattr(getattr(self, "backend", None), "engine", None)
        try:
            if engine is None:
                if dot.winfo_manager():
                    dot.pack_forget()
            else:
                if not dot.winfo_manager():
                    dot.pack(side="left", padx=(10, 0),
                             before=self.title_label)
                dot.configure(fg={
                    "running": "#3fbf5f",
                    "starting": "#d8b26a",
                    "error": "#e05a5a",
                    "stopped": "#5a5a5a",
                }.get(engine.state, "#5a5a5a"))
        except Exception:
            pass
        self._schedule_status_dot(2000)

    # ---------- Страница «Движок» ----------
    def _build_engine_page(self, c, start_row=0):
        tr = LANGS[self.lang_ui]
        kinds = ["builtin", "lmstudio", "ollama", "openai"]
        labels = [self._backend_label(k) for k in kinds]
        self.provider_var = tk.StringVar(value=self._backend_label(self.backend.kind))

        row = start_row
        _classic_label(c, tr["provider_label"]).grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=3)
        _classic_option(c, self.provider_var, labels,
                        self._on_provider_changed, width=26).grid(
            row=row, column=1, sticky="w", pady=3)

        row += 1
        if self.backend.kind == "builtin":
            names = {}
            for model_id in local_engine.catalog_model_ids():
                info = local_engine.model_info(model_id)
                label = info["name"]
                if not local_engine.model_installed(model_id):
                    label += " — " + tr["not_downloaded"]
                names[label] = model_id
            self._engine_model_map = names
            current = local_engine.model_info(self.backend.model_id)["name"]
            if current not in names:
                current = next(iter(names))
            self._engine_model_var = tk.StringVar(value=current)
            _classic_label(c, tr["model_label"]).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            _classic_option(c, self._engine_model_var, list(names.keys()),
                            self._on_engine_model_changed, width=26).grid(
                row=row, column=1, sticky="w", pady=3)
            row += 1

            mode_labels = [tr["gpu_auto"], tr["gpu_gpu"], tr["gpu_cpu"]]
            gpu_layers = self.backend.gpu_layers
            if gpu_layers in (0, "0"):
                current_mode = tr["gpu_cpu"]
            elif gpu_layers in ("auto", None, ""):
                current_mode = tr["gpu_auto"]
            else:
                current_mode = tr["gpu_gpu"]
            self._gpu_var = tk.StringVar(value=current_mode)
            _classic_label(c, tr["gpu_label"]).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            _classic_option(c, self._gpu_var, mode_labels,
                            self._on_gpu_mode_changed, width=18).grid(
                row=row, column=1, sticky="w", pady=3)
            row += 1

            self._engine_status_var = tk.StringVar(value=self._engine_status_text())
            status_box = tk.Frame(c, bg=CLASSIC_BG)
            status_box.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
            tk.Label(status_box, text=tr["status_label"], bg=CLASSIC_BG,
                     fg=CLASSIC_TEXT, font=CLASSIC_FONT).pack(side="left")
            tk.Label(status_box, textvariable=self._engine_status_var,
                     bg=CLASSIC_BG, fg=CLASSIC_TEXT,
                     font=CLASSIC_FONT).pack(side="left", padx=(4, 0))
            row += 1

            buttons = tk.Frame(c, bg=CLASSIC_BG)
            buttons.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
            _classic_button(buttons, tr["engine_restart"],
                            self._restart_backend).pack(side="left")
            _classic_button(buttons, tr["engine_repair"],
                            self._repair_engine).pack(side="left", padx=(6, 0))
            _classic_button(buttons, tr["open_models"],
                            lambda: system_info.open_folder(paths.models_dir())
                            ).pack(side="left", padx=(6, 0))
        else:
            self._url_var = tk.StringVar(value=self.backend.base_url)
            self._key_var = tk.StringVar(value=self.backend.api_key)
            self._conn_var = tk.StringVar(value="")

            _classic_label(c, tr["url_label"]).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            url_entry = _classic_entry(c, self._url_var, width=34)
            url_entry.grid(row=row, column=1, sticky="w", pady=3)
            url_entry.bind("<Return>", lambda e: self._test_connection())
            row += 1

            _classic_label(c, tr["key_label"]).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            key_entry = _classic_entry(c, self._key_var, width=34, show="*")
            key_entry.grid(row=row, column=1, sticky="w", pady=3)
            key_entry.bind("<Return>", lambda e: self._test_connection())
            row += 1

            models = self._available_models()
            self._models_var = tk.StringVar(
                value=self.engine.backend.model or (models[0] if models else ""))
            _classic_label(c, tr["model_label"]).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            _classic_option(c, self._models_var, models or [""],
                            self._on_model_changed, width=26).grid(
                row=row, column=1, sticky="w", pady=3)
            row += 1

            buttons = tk.Frame(c, bg=CLASSIC_BG)
            buttons.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
            _classic_button(buttons, tr["check_conn"],
                            self._test_connection).pack(side="left")
            tk.Label(buttons, textvariable=self._conn_var, bg=CLASSIC_BG,
                     fg=CLASSIC_TEXT, font=CLASSIC_FONT).pack(
                side="left", padx=(10, 0))
            row += 1

        bottom = tk.Frame(c, bg=CLASSIC_BG)
        bottom.grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(16, 0))
        _classic_button(bottom, tr["wizard_button"], self._open_wizard).pack(
            side="left")
        _classic_button(bottom, tr["diagnostics"],
                        self._collect_diagnostics).pack(side="left", padx=(6, 0))

        self._schedule_engine_status_tick()

    def _schedule_engine_status_tick(self):
        job = getattr(self, "_settings_status_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._settings_status_job = self.after(800, self._tick_engine_status)

    def _tick_engine_status(self):
        self._settings_status_job = None
        if not (self.settings_window and self.settings_window.winfo_exists()):
            return
        if getattr(self, "_settings_page", None) != "engine":
            return
        try:
            if getattr(self, "_engine_status_var", None) is not None:
                self._engine_status_var.set(self._engine_status_text())
        except Exception:
            pass
        self._settings_status_job = self.after(1500, self._tick_engine_status)

    def _on_provider_changed(self, label):
        kind = self._kind_from_label(label)
        if kind == self.backend.kind:
            return
        if kind == "builtin":
            model_id = self.config["llm"].get("builtin", {}).get(
                "model_id", local_engine.DEFAULT_MODEL_ID)
            if not (local_engine.runtime_installed()
                    and local_engine.model_installed(model_id)):
                self._open_wizard(model_id)
                self._show_settings_page("translate")
                return
        self.config["llm"]["backend"] = kind
        self._apply_backend(self.config["llm"])
        self._show_settings_page("translate")

    def _model_id_by_label(self, label):
        model_id = getattr(self, "_engine_model_map", {}).get(label)
        if model_id:
            return model_id
        for candidate in local_engine.catalog_model_ids():
            if local_engine.model_info(candidate)["name"] == label:
                return candidate
        return None

    def _on_engine_model_changed(self, label):
        model_id = self._model_id_by_label(label)
        if not model_id or model_id == self.backend.model_id:
            return
        if not local_engine.model_installed(model_id):
            self._open_wizard(model_id)
            self._show_settings_page("translate")
            return
        self.config["llm"].setdefault("builtin", {})["model_id"] = model_id
        self._apply_backend(self.config["llm"])
        self._show_settings_page("translate")

    def _on_gpu_mode_changed(self, label):
        tr = LANGS[self.lang_ui]
        value = {tr["gpu_auto"]: "auto", tr["gpu_gpu"]: 99,
                 tr["gpu_cpu"]: 0}.get(label, "auto")
        self.config["llm"].setdefault("builtin", {})["gpu_layers"] = value
        self._apply_backend(self.config["llm"])
        self._show_settings_page("translate")

    def _restart_backend(self):
        try:
            self.backend.stop()
        except Exception:
            pass
        self.backend.start()
        self._models_cache = None
        self._schedule_status_dot(200)

    def _repair_engine(self):
        llm = self.config["llm"]
        engine = getattr(self.backend, "engine", None)
        if engine is not None:
            missing = []
            if not local_engine.runtime_installed():
                missing.append("движок")
            if not local_engine.model_installed(engine.model_id):
                missing.append("модель")
            if missing:
                self._open_wizard(engine.model_id)
                return
        self._restart_backend()
        messagebox.showinfo(APP_NAME, self._engine_status_text() or "OK")

    def _test_connection(self):
        tr = LANGS[self.lang_ui]
        section = self.config["llm"].setdefault(self.backend.kind, {})
        section["base_url"] = self._url_var.get().strip()
        section["api_key"] = self._key_var.get().strip()
        self._apply_backend(self.config["llm"])
        models = self.engine.list_models()
        self._conn_var.set(tr["check_ok"].format(n=len(models))
                           if models else tr["check_fail"])

    def _collect_diagnostics(self):
        status = {}
        if hasattr(self.backend, "engine"):
            status = self.backend.engine.status()
        try:
            path = system_info.build_diagnostics(self.config, status)
        except Exception as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return
        messagebox.showinfo(
            APP_NAME, LANGS[self.lang_ui]["diag_saved"].format(path=path))
        system_info.open_folder(os.path.dirname(path))

    # ---------- Ресайз (только вправо, влево, вниз и нижние углы) ----------
    def _event_xy(self, event):
        """Координаты мыши в системе координат главного окна.
        Работает одинаково, даже если событие пришло от дочернего виджета
        (текст, полоса прокрутки и т.п.)."""
        return (event.x_root - self.winfo_rootx(),
                event.y_root - self.winfo_rooty())

    def _is_scrollbar(self, widget):
        """Является ли виджет (или его родитель) полосой прокрутки."""
        node = widget
        for _ in range(4):
            if node is None:
                return False
            try:
                if isinstance(node, (ctk.CTkScrollbar, tk.Scrollbar)):
                    return True
                if "scrollbar" in node.winfo_class().lower():
                    return True
            except Exception:
                pass
            node = getattr(node, "master", None)
        return False

    def _is_in_tab_bar(self, widget):
        """Находится ли виджет внутри панели вкладок."""
        try:
            return str(widget).startswith(str(self.tab_bar))
        except Exception:
            return False

    def _get_resize_dir(self, x, y, widget=None):
        w, h = self.winfo_width(), self.winfo_height()
        m = self.BORDER_MARGIN
        cm = self.CORNER_MARGIN

        # В панели вкладок ресайз не перехватываем: иначе правый край окна
        # мешает брать вкладки и перетаскивать их.
        if widget is not None and self._is_in_tab_bar(widget):
            return None

        # Свёрнутое окно — это одна полоса: тянем только ширину.
        left = x < m
        right = x > w - m
        if self._collapsed:
            if left:
                return "w"
            if right:
                return "e"
            return None

        # Тонкие зоны у самих граней
        top = y < self.TOP_MARGIN
        bottom = y > h - m

        # Широкие зоны в углах — чтобы удобно было тянуть по диагонали
        near_left = x < cm
        near_right = x > w - cm
        near_top = y < self.TOP_MARGIN
        near_bottom = y > h - cm

        is_sb = widget is not None and self._is_scrollbar(widget)

        # Сначала углы (широкая зона): тянем и ширину, и высоту одновременно
        if near_top and near_left:
            return "nw"
        if near_top and near_right:
            return "ne"
        if near_bottom and near_left:
            return "sw"
        if near_bottom and near_right:
            return "se"

        # Над полосой прокрутки не перехватываем боковые грани
        # (чтобы прокрутка работала), но нижнюю грань оставляем
        if is_sb:
            if bottom:
                return "s"
            return "n" if top else None

        if left: return "w"
        if right: return "e"
        if bottom: return "s"
        if top: return "n"
        return None

    def _widget_under(self, event):
        try:
            return self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            return None

    def _apply_cursor(self, cursor, widget):
        """Показывает курсор ресайза на виджете под мышью (а не только на
        главном окне), иначе дочерние виджеты перекрывают его своим курсором."""
        # Курсор не нужен — возвращаем прежний курсор и сбрасываем всё
        if not cursor:
            if self._cursor_widget is not None:
                try:
                    self._cursor_widget.configure(cursor=self._cursor_widget_orig or "")
                except Exception:
                    pass
                self._cursor_widget = None
            try:
                self.configure(cursor="")
            except Exception:
                pass
            return

        # Мышь перешла на другой виджет — восстановим курсор предыдущему
        if self._cursor_widget is not None and self._cursor_widget is not widget:
            try:
                self._cursor_widget.configure(cursor=self._cursor_widget_orig or "")
            except Exception:
                pass
            self._cursor_widget = None

        if widget is not None:
            if self._cursor_widget is not widget:
                try:
                    self._cursor_widget_orig = widget.cget("cursor")
                except Exception:
                    self._cursor_widget_orig = ""
                self._cursor_widget = widget
            try:
                widget.configure(cursor=cursor)
            except Exception:
                pass

        # Дублируем на окно — на случай, если мышь над «пустым» местом
        try:
            self.configure(cursor=cursor)
        except Exception:
            pass

    def _on_mouse_move(self, event):
        # Во время перетаскивания окна не считаем края и не дёргаем курсоры.
        if self._is_locked or self._resize_dir or self._is_dragging:
            return
        widget = self._widget_under(event)
        x, y = self._event_xy(event)
        d = self._get_resize_dir(x, y, widget)
        self._apply_cursor(RESIZE_CURSORS.get(d, ""), widget)

    def _on_mouse_press(self, event):
        if self._is_locked:
            return
        widget = self._widget_under(event)
        x, y = self._event_xy(event)
        d = self._get_resize_dir(x, y, widget)
        if d:
            self._resize_dir = d
            self._resize_start_x = event.x_root
            self._resize_start_y = event.y_root
            self._resize_start_w = self.winfo_width()
            self._resize_start_h = self.winfo_height()
            self._resize_start_posx = self.winfo_x()
            self._resize_start_posy = self.winfo_y()

            # Держим иконку ресайза, пока тянем
            self._apply_cursor(RESIZE_CURSORS.get(d, ""), widget)

            # Поднимаем окно на передний план при ресайзе
            self.lift()

    def _on_mouse_drag(self, event):
        if self._is_locked or not self._resize_dir:
            return

        # Курсор на виджете под мышью, чтобы иконка не пропадала при движении
        self._apply_cursor(RESIZE_CURSORS.get(self._resize_dir, "sizing"),
                           self._widget_under(event))

        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        w, h = self._resize_start_w, self._resize_start_h
        x, y = self._resize_start_posx, self._resize_start_posy

        # Минимальный размер: только под панель кнопок (и чуть-чуть вкладок)
        min_w, min_h = 100, 30

        if "e" in self._resize_dir:
            w = max(min_w, self._resize_start_w + dx)
        if "w" in self._resize_dir:
            new_w = max(min_w, self._resize_start_w - dx)
            x = self._resize_start_posx + (self._resize_start_w - new_w)
            w = new_w
        if "s" in self._resize_dir:
            h = max(min_h, self._resize_start_h + dy)
        if "n" in self._resize_dir:
            new_h = max(min_h, self._resize_start_h - dy)
            y = self._resize_start_posy + (self._resize_start_h - new_h)
            h = new_h

        # Вариант A: не дёргаем geometry() на каждое движение мыши,
        # а применяем последнюю цель не чаще ~60 раз/сек.
        self._pending_geometry = f"{w}x{h}+{x}+{y}"
        if self._resize_pending is None:
            self._resize_pending = self.after(16, self._flush_resize)

    def _flush_resize(self):
        self._resize_pending = None
        geometry = self._pending_geometry
        self._pending_geometry = None
        if geometry:
            try:
                self.geometry(geometry)
                # Дорисовываем кадр сразу, иначе при быстром ресайзе
                # часть окна остаётся неперерисованной (чёрные полосы).
                self.update_idletasks()
            except Exception:
                pass

    def _on_mouse_release(self, event):
        if self._resize_pending is not None:
            try:
                self.after_cancel(self._resize_pending)
            except Exception:
                pass
            self._resize_pending = None
        # Финальный размер применяем сразу, без ожидания кадра.
        if self._pending_geometry:
            try:
                self.geometry(self._pending_geometry)
                self.update_idletasks()
            except Exception:
                pass
            self._pending_geometry = None
        self._resize_dir = None
        self._end_drag()
        # Возвращаем обычный курсор
        self._apply_cursor("", None)

    def _bind_events_recursive(self, widget):
        """Рекурсивно привязывает события мыши ко всем дочерним виджетам,
        чтобы ресайз окна работал даже при наведении на контент, вкладки и др."""
        try:
            widget.bind("<Motion>", self._on_mouse_move, add="+")
            widget.bind("<ButtonPress-1>", self._on_mouse_press, add="+")
            widget.bind("<B1-Motion>", self._on_mouse_drag, add="+")
            widget.bind("<ButtonRelease-1>", self._on_mouse_release, add="+")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_events_recursive(child)

    # ---------- Основной UI ----------
    def _build_ui(self):
        self._build_title_bar()

        self.tab_bar = EveTabBar(
            self,
            on_select=self._on_tab_selected,
            on_close=self._close_tab_from_menu,
            on_reorder=self._on_tabs_reordered,
            tr_provider=lambda: LANGS[self.lang_ui],
        )
        self.tab_bar.pack(fill="x", padx=0, pady=(0, 0))

        # Панель исходящего перевода. В свёрнутом виде не занимает места:
        # остаётся только плавающая кнопка поверх чата. При раскрытии
        # пакуется снизу на две трети высоты окна.
        self.chat_font = ctk.CTkFont(family="Consolas", size=self.font_size)
        self.composer = Composer(
            self,
            tr_provider=lambda: LANGS[self.lang_ui],
            on_translate=self._request_outgoing,
            on_lang_change=self._on_composer_lang,
            on_expanded=self._on_composer_expanded,
            lang=self.config["ui"].get("composer_lang", "en"),
            autocopy=bool(self.config["ui"].get("composer_autocopy", True)),
            translation_color=self.color_trans,
            font=self.chat_font,
        )

        # Content frame fills everything below the title bar and tab bar.
        # pack(fill="both", expand=True) сам растягивает его до низа окна,
        # без ручного позиционирования и без выезда за границы.
        # Тоже обычный tk.Frame: при ресайзе такая подложка не перерисовывается
        # (у CTkFrame на каждый пиксель уходит перерисовка canvas).
        self.content_frame = tk.Frame(self, bg="#000000")
        self.content_frame.pack(fill="both", expand=True)

        # Заглушка в пустом окне: пользователь должен видеть, что программа
        # работает и где лежат логи, а не чёрный прямоугольник.
        self.empty_hint = tk.Label(
            self.content_frame, text="", bg="#000000", fg="#6a6a6a",
            font=("Segoe UI", 10), justify="center")
        self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")

        # Панель вкладок сама следит за своей шириной (<Configure>),
        # дополнительный обработчик на окне только дублировал пересчёт.

        self._current_tab = None
        # Шрифт панели подтягиваем, когда вкладки уже созданы.
        self._update_translate_btn(False)
        self.after_idle(self._sync_composer_font)

    def _show_empty_hint(self):
        hint = getattr(self, "empty_hint", None)
        if hint is None:
            return
        try:
            log_dir = getattr(self, "log_dir", "")
            count = 0
            if log_dir and os.path.isdir(log_dir):
                count = len([name for name in os.listdir(log_dir)
                             if name.lower().endswith(".txt")])
            tr = LANGS[self.lang_ui]
            hint.configure(text=tr["empty_hint"].format(path=log_dir, n=count))
            hint.place(relx=0.5, rely=0.5, anchor="center")
        except Exception:
            pass

    def _hide_empty_hint(self):
        hint = getattr(self, "empty_hint", None)
        if hint is not None:
            try:
                hint.place_forget()
            except Exception:
                pass

    # ---------- Панель исходящего перевода ----------
    def _request_outgoing(self, text, lang, callback):
        """Перевод исходящего текста в фоне, ответ — в главный поток."""

        def worker():
            try:
                result = self.engine.translate_outgoing(text, lang)
                self._post_ui(callback, result, None)
            except Exception as exc:
                app_log.log(f"outgoing: {exc!r}")
                self._post_ui(callback, None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_composer_lang(self, code):
        self.config["ui"]["composer_lang"] = code
        save_config(self.config)
        self._update_translate_btn()

    def _on_composer_expanded(self, expanded):
        """Показывает панель снизу на 2/3 окна или отдаёт место чату."""
        composer = getattr(self, "composer", None)
        content = getattr(self, "content_frame", None)
        if composer is None or content is None:
            return
        if expanded:
            composer.update_height(self.winfo_height())
            composer.pack(side="bottom", fill="x", before=content)
            self.update_idletasks()
        else:
            composer.pack_forget()
        self._update_translate_btn(expanded)

    def _on_window_configure(self, event):
        if event.widget is not self:
            return
        composer = getattr(self, "composer", None)
        if composer is not None:
            composer.update_height(event.height)

    def _on_tab_selected(self, name):
        for n, tb in self.textboxes.items():
            tb.pack_forget()
        self._current_tab = name
        if name and name in self.textboxes:
            self.textboxes[name].pack(fill="both", expand=True)
            self._hide_empty_hint()
        else:
            self._show_empty_hint()

    def _on_tabs_reordered(self, order):
        """Пользователь перетащил вкладки — запоминаем новый порядок."""
        order = [name for name in order if name in self.active_channels]
        rest = [name for name in self.active_channels if name not in order]
        self.active_channels = order + rest
        self.config["chats"]["active"] = list(self.active_channels)

        all_order = [name for name in order if name in self.all_channels]
        all_rest = [name for name in self.all_channels if name not in all_order]
        self.all_channels = all_order + all_rest
        self.config["chats"]["all"] = list(self.all_channels)
        save_config(self.config)

    def _ensure_tab(self, channel_name):
        if channel_name in self.tab_names:
            return self.textboxes[channel_name]
        self.tab_bar.add_tab(channel_name)
        textbox = ctk.CTkTextbox(
            self.content_frame, fg_color="#000000", text_color="#b8b8b8",
            font=("Consolas", self.font_size), wrap="word",
            border_width=0, corner_radius=0
        )
        textbox.pack(fill="both", expand=True)
        self._reapply_tags(textbox)
        textbox.configure(state="disabled")
        
        # Биндим Ctrl+C для копирования из неактивного чата. Нажатие
        # приходит во внутренний tk.Text, поэтому биндим и на него.
        textbox.bind("<Control-c>", lambda e, t=textbox: self._copy_text_from_textbox(t))
        textbox.bind("<Control-C>", lambda e, t=textbox: self._copy_text_from_textbox(t))
        inner_text = getattr(textbox, "_textbox", None)
        if inner_text is not None:
            inner_text.bind("<Control-c>", lambda e, t=textbox: self._copy_text_from_textbox(t))
            inner_text.bind("<Control-C>", lambda e, t=textbox: self._copy_text_from_textbox(t))
            # Ctrl+C по коду клавиши — срабатывает и на русской раскладке.
            inner_text.bind(
                "<Control-KeyPress>",
                lambda e, t=textbox: self._copy_on_ctrl(e, t))
        textbox.bind(
            "<Control-KeyPress>",
            lambda e, t=textbox: self._copy_on_ctrl(e, t))
        self._bind_events_recursive(textbox)
        
        self.textboxes[channel_name] = textbox
        self.tab_names.add(channel_name)
        self._sync_composer_font()
        if self._current_tab and self._current_tab != channel_name:
            textbox.pack_forget()
        return textbox

    def _copy_text_from_textbox(self, textbox):
        try:
            selected_text = textbox.get("sel.first", "sel.last")
            if selected_text:
                self.clipboard_clear()
                self.clipboard_append(selected_text)
        except Exception:
            pass 
        return "break"

    def _copy_on_ctrl(self, event, textbox):
        """Ctrl+C независимо от раскладки (VK_C = 67)."""
        if getattr(event, "keycode", 0) == 67:
            return self._copy_text_from_textbox(textbox)
        return None

    def _sync_composer_font(self):
        """Берёт фактический шрифт чата (пиксельный) и отдаёт панели."""
        composer = getattr(self, "composer", None)
        if composer is None:
            return
        spec = None
        for tb in self.textboxes.values():
            inner = getattr(tb, "_textbox", None)
            if inner is not None:
                spec = inner.cget("font")
                break
        if not spec:
            spec = ("Consolas", self.font_size)
        composer.set_font(spec)

    def _remove_tab(self, channel_name):
        if channel_name not in self.tab_names:
            return
        tb = self.textboxes.pop(channel_name, None)
        if tb: tb.destroy()
        self.tab_bar.remove_tab(channel_name)
        self.tab_names.discard(channel_name)

    def _restore_tabs(self):
        for ch in self.active_channels:
            self._ensure_tab(ch)
        if self.active_channels:
            self.tab_bar.select_tab(self.active_channels[0])
        # Ensure tabs get proper widths after being added
        self.tab_bar._on_resize(None)

    def _close_tab_from_menu(self, tab_name):
        if tab_name in self.active_channels:
            self.active_channels.remove(tab_name)
        self._remove_tab(tab_name)
        if self.settings_window and self.settings_window.winfo_exists():
            self._open_settings_menu()

    # ---------- Окно настроек ----------
    def _open_settings_menu(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        job = getattr(self, "_settings_status_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._settings_status_job = None

        tr = LANGS[self.lang_ui]
        menu = tk.Toplevel(self)
        menu.title(tr["title"])
        menu.configure(bg=CLASSIC_BG)
        menu.resizable(False, False)
        menu.attributes("-topmost", True)
        menu.transient(self)
        # Пока строим страницы и меряем их размер, окно скрыто (без мигания).
        menu.withdraw()
        # Вместо стандартного «пёрышка» Tk — своя маленькая иконка.
        # Ссылку держим на окне, иначе PhotoImage соберёт сборщик мусора.
        try:
            app_icon = _make_app_icon()
            menu.iconphoto(True, app_icon)
            menu._app_icon = app_icon
        except Exception:
            pass
        self.settings_window = menu
        self._models_cache = None

        # Левая колонка — классические кнопки-категории.
        left = tk.Frame(menu, bg=CLASSIC_BG)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)

        pages = [
            ("translate", tr["cat_translate"]),
            ("interface", tr["cat_interface"]),
            ("dictionary", tr["cat_dictionary"]),
            ("prompt", tr["cat_prompt"]),
            ("chats", tr["cat_chats"]),
            ("about", tr["cat_about"]),
        ]
        self._settings_buttons = {}
        for page_id, label in pages:
            btn = _classic_button(
                left, label,
                lambda p=page_id: self._show_settings_page(p),
                width=12
            )
            btn.configure(font=(CLASSIC_FONT[0], CLASSIC_FONT[1], "bold"))
            btn.pack(fill="x", pady=(0, 1))
            self._settings_buttons[page_id] = btn

        # Правая панель — утопленная рамка с содержимым страницы.
        right = tk.Frame(menu, bg=CLASSIC_BG, relief="sunken", bd=1)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)

        self._settings_content = tk.Frame(right, bg=CLASSIC_BG)
        self._settings_content.pack(fill="both", expand=True, padx=10, pady=10)

        # Окно ровно под содержимое: строим по очереди все страницы и берём
        # максимальный требуемый размер. Так нет пустых полей, как у окна
        # фиксированного размера 600x560, и страницы не «прыгают» по высоте.
        menu_w = menu_h = 1
        for page_id, _label in pages:
            self._show_settings_page(page_id)
            menu.update_idletasks()
            menu_w = max(menu_w, menu.winfo_reqwidth())
            menu_h = max(menu_h, menu.winfo_reqheight())

        self._show_settings_page("translate")

        # Ставим окно по центру главного окна и не даём уехать за экран
        # (учитываем DPI-масштабирование — берём реальные размеры).
        x = self.winfo_rootx() + (self.winfo_width() - menu_w) // 2
        y = self.winfo_rooty() + 40
        x = max(0, min(x, menu.winfo_screenwidth() - menu_w))
        y = max(0, min(y, menu.winfo_screenheight() - menu_h))
        menu.geometry(f"{menu_w}x{menu_h}+{x}+{y}")
        menu.deiconify()
        menu.lift()
        menu.grab_set()

    def _available_models(self):
        """Список моделей активного бэкенда (с кэшем на время окна настроек)."""
        if self._models_cache is None:
            models = list(self.engine.list_models())
            current = self.engine.backend.model
            if not getattr(self.engine.backend, "managed", False):
                if not models:
                    models = [current]
                elif current and current not in models:
                    models.insert(0, current)
            self._models_cache = [m for m in models if m]
        return self._models_cache

    # ---------- Страницы настроек: перевод, интерфейс, словарь ----------
    def _build_translate_page(self, c):
        tr = LANGS[self.lang_ui]
        labels = list(LANG_LABELS.values())

        _classic_label(c, tr["lang_target"]).grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=3)
        self.target_lang_var = tk.StringVar(
            value=LANG_LABELS.get(self.lang_target, LANG_LABELS["ru"]))
        _classic_option(c, self.target_lang_var, labels,
                        self._on_target_lang_changed, width=18).grid(
            row=0, column=1, sticky="w", pady=3)

        _classic_label(c, tr["terms_lang_label"]).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=3)
        self.terms_lang_var = tk.StringVar(
            value=TERMS_LANG_LABELS.get(self.terms_lang, "English"))
        _classic_option(c, self.terms_lang_var,
                        list(TERMS_LANG_LABELS.values()),
                        self._on_terms_lang_changed, width=18).grid(
            row=1, column=1, sticky="w", pady=3)

        self._build_engine_page(c, start_row=2)

    def _build_interface_page(self, c):
        tr = LANGS[self.lang_ui]
        labels = list(LANG_LABELS.values())

        self.hide_orig_var = tk.BooleanVar(value=self.hide_original)
        _classic_check(
            c, tr["hide_orig"], self.hide_orig_var,
            self._on_hide_original_changed
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.check_updates_var = tk.BooleanVar(
            value=bool(self.config["ui"].get("check_updates", True)))
        _classic_check(
            c, tr["update_setting"], self.check_updates_var,
            self._on_check_updates_changed
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.composer_copy_var = tk.BooleanVar(
            value=bool(self.config["ui"].get("composer_autocopy", True)))
        _classic_check(
            c, tr["composer_autocopy"], self.composer_copy_var,
            self._on_composer_autocopy_changed
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

        _classic_label(c, tr["lang_ui"]).grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=3)
        self.ui_lang_var = tk.StringVar(
            value=LANG_LABELS.get(self.lang_ui, LANG_LABELS["ru"]))
        _classic_option(c, self.ui_lang_var, labels,
                        self._on_ui_lang_changed, width=18).grid(
            row=3, column=1, sticky="w", pady=3)

        _classic_label(c, tr["font"]).grid(
            row=4, column=0, sticky="w", padx=(0, 12), pady=3)
        self.font_var = tk.StringVar(value=str(self.font_size))
        _classic_option(
            c, self.font_var,
            ["10", "11", "12", "13", "14", "16", "18", "20"],
            self._on_font_size_changed, width=8
        ).grid(row=4, column=1, sticky="w", pady=3)

        _classic_label(c, tr["alpha"]).grid(
            row=5, column=0, sticky="w", padx=(0, 12), pady=3)
        alpha_box = tk.Frame(c, bg=CLASSIC_BG)
        alpha_box.grid(row=5, column=1, sticky="ew", pady=3)
        self.alpha_label = tk.Label(
            alpha_box,
            text=f"{int(float(self.config['window']['alpha']) * 100)}%",
            bg=CLASSIC_BG, fg=CLASSIC_TEXT, font=CLASSIC_FONT,
            width=4, anchor="e"
        )
        self.alpha_label.pack(side="right", padx=(6, 0))

        self.alpha_slider = tk.Scale(
            alpha_box, from_=0.2, to=1.0, resolution=0.01,
            orient="horizontal", command=self._on_alpha_changed,
            bg=CLASSIC_BG, troughcolor="#ffffff",
            activebackground=CLASSIC_BTN_ACTIVE,
            highlightthickness=0, bd=1, relief="sunken",
            showvalue=0, sliderrelief="raised", font=CLASSIC_FONT
        )
        self.alpha_slider.set(float(self.config["window"]["alpha"]))
        self.alpha_slider.pack(side="left", fill="x", expand=True)

        color_labels = [self._color_label(cid) for cid in COLOR_IDS]

        _classic_label(c, tr["color_orig"]).grid(
            row=6, column=0, sticky="w", padx=(0, 12), pady=3)
        self.color_orig_var = tk.StringVar(
            value=self._color_label(self._get_color_id(self.color_orig)))
        _classic_option(
            c, self.color_orig_var, color_labels,
            self._on_color_orig_changed, width=16
        ).grid(row=6, column=1, sticky="w", pady=3)

        _classic_label(c, tr["color_trans"]).grid(
            row=7, column=0, sticky="w", padx=(0, 12), pady=3)
        self.color_trans_var = tk.StringVar(
            value=self._color_label(self._get_color_id(self.color_trans)))
        _classic_option(
            c, self.color_trans_var, color_labels,
            self._on_color_trans_changed, width=16
        ).grid(row=6, column=1, sticky="w", pady=3)

    # ---------- Словарь сленга ----------
    def _build_dictionary_page(self, c):
        tr = LANGS[self.lang_ui]
        self._dict_bundled = slang_mod._read(slang_mod.bundled_path())
        self._dict_user = slang_mod.user_data()
        self._dict = slang_mod.load_slang()
        self._dict_rows = {}

        _classic_label(c, tr["dict_filter"]).grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        self._dict_filter = tk.StringVar()
        _classic_entry(c, self._dict_filter, width=28).grid(
            row=0, column=1, sticky="w")
        self._dict_filter.trace_add(
            "write", lambda *args: self._fill_dictionary_table())

        table = ttk.Treeview(
            c, columns=("phrase", "action", "value", "lang", "source"),
            show="headings", height=10)
        for column, title, width in (
            ("phrase", tr["dict_phrase"], 140),
            ("action", tr["dict_action"], 120),
            ("value", tr["dict_value"], 150),
            ("lang", tr["dict_lang"], 70),
            ("source", tr["dict_source"], 90),
        ):
            table.heading(column, text=title)
            table.column(column, width=width, anchor="w", stretch=False)
        table.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 6))
        scroll = ttk.Scrollbar(c, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=2, sticky="ns", pady=(6, 6))
        table.bind("<Double-1>", lambda event: self._edit_dictionary_entry())
        c.grid_rowconfigure(1, weight=1)
        self._dict_table = table

        buttons = tk.Frame(c, bg=CLASSIC_BG)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w")
        _classic_button(buttons, tr["dict_add"],
                        lambda: self._edit_dictionary_entry(new=True)).pack(
            side="left")
        _classic_button(buttons, tr["dict_edit"],
                        self._edit_dictionary_entry).pack(side="left", padx=(6, 0))
        _classic_button(buttons, tr["dict_delete"],
                        self._delete_dictionary_entry).pack(side="left", padx=(6, 0))
        _classic_button(buttons, tr["dict_open"],
                        self._open_slang_file).pack(side="left", padx=(6, 0))

        _classic_label(c, tr["dict_hint"], wrap=520).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self._fill_dictionary_table()

    def _fill_dictionary_table(self):
        table = getattr(self, "_dict_table", None)
        if table is None or not table.winfo_exists():
            return
        tr = LANGS[self.lang_ui]
        for item in table.get_children():
            table.delete(item)
        self._dict_rows = {}

        needle = ""
        if getattr(self, "_dict_filter", None) is not None:
            needle = self._dict_filter.get().strip().lower()

        bundled = self._dict_bundled
        user = self._dict_user
        user_expand = user.get("expand") or {}
        user_keep = {str(k).lower() for k in (user.get("keep") or [])}

        rows = []
        for lang in slang_mod.LANGS:
            user_keys = {str(k).lower() for k in (user_expand.get(lang) or {})}
            for phrase, value in sorted(self._dict.expand[lang].items()):
                source = tr["dict_user"] if phrase.lower() in user_keys \
                    else tr["dict_builtin"]
                rows.append((lang, phrase, "replace", value, source))
        for phrase in self._dict.keep:
            source = tr["dict_user"] if phrase.lower() in user_keep \
                else tr["dict_builtin"]
            rows.append(("", phrase, "keep", "", source))

        rows.sort(key=lambda row: (row[0], row[1].lower()))
        for lang, phrase, kind, value, source in rows:
            if needle and needle not in phrase.lower() \
                    and needle not in value.lower():
                continue
            iid = table.insert("", "end", values=(
                phrase,
                tr["dict_keep"] if kind == "keep" else "→",
                value,
                lang.upper() if lang else "—",
                source,
            ))
            self._dict_rows[iid] = (lang, phrase, kind, value, source)

    def _selected_dictionary_entry(self):
        table = getattr(self, "_dict_table", None)
        if table is None:
            return None
        selection = table.selection()
        if not selection:
            return None
        return self._dict_rows.get(selection[0])

    def _edit_dictionary_entry(self, new=False):
        tr = LANGS[self.lang_ui]
        current = None
        if not new:
            current = self._selected_dictionary_entry()
            if current is None:
                return

        parent = self.settings_window or self
        dialog = tk.Toplevel(parent)
        dialog.title(tr["dict_add_title"] if new else tr["dict_edit_title"])
        dialog.configure(bg=CLASSIC_BG)
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.transient(parent)

        body = tk.Frame(dialog, bg=CLASSIC_BG, padx=14, pady=12)
        body.pack(fill="both", expand=True)

        lang_var = tk.StringVar(value=(current[0] if current and current[0] else "en"))
        phrase_var = tk.StringVar(value=current[1] if current else "")
        value_var = tk.StringVar(value=current[3] if current else "")
        kind_var = tk.StringVar(
            value=(tr["dict_keep"] if current and current[2] == "keep"
                   else tr["dict_replace"]))

        _classic_label(body, tr["dict_lang"]).grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        _classic_option(body, lang_var, ["en", "ru", "zh"], None,
                        width=6).grid(row=0, column=1, sticky="w", pady=4)

        _classic_label(body, tr["dict_phrase"]).grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        phrase_entry = _classic_entry(body, phrase_var, width=30)
        phrase_entry.grid(row=1, column=1, sticky="w", pady=4)

        _classic_label(body, tr["dict_action"]).grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        kind_option = _classic_option(
            body, kind_var, [tr["dict_keep"], tr["dict_replace"]], None, width=18)
        kind_option.grid(row=2, column=1, sticky="w", pady=4)

        _classic_label(body, tr["dict_value"]).grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        value_entry = _classic_entry(body, value_var, width=30)
        value_entry.grid(row=3, column=1, sticky="w", pady=4)

        error_var = tk.StringVar(value="")
        tk.Label(body, textvariable=error_var, bg=CLASSIC_BG, fg="#a00000",
                 font=CLASSIC_FONT, anchor="w").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(2, 6))

        def update_state(*_args):
            keep = kind_var.get() == tr["dict_keep"]
            value_entry.configure(state="disabled" if keep else "normal")

        kind_var.trace_add("write", update_state)
        update_state()

        def save():
            phrase = phrase_var.get().strip()
            if not phrase:
                error_var.set(tr["dict_need_phrase"])
                return
            kind = "keep" if kind_var.get() == tr["dict_keep"] else "replace"
            value = value_var.get().strip()
            if kind == "replace" and not value:
                error_var.set(tr["dict_need_value"])
                return
            self._save_dictionary_entry(lang_var.get(), phrase, kind, value)
            dialog.destroy()
            self._fill_dictionary_table()

        buttons = tk.Frame(body, bg=CLASSIC_BG)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(6, 0))
        _classic_button(buttons, tr["dict_ok"], save).pack(side="right")
        _classic_button(buttons, tr["dict_cancel"], dialog.destroy).pack(
            side="right", padx=(0, 6))

        phrase_entry.focus_set()
        dialog.bind("<Return>", lambda event: save())
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.update_idletasks()
        _center_on_parent(dialog, parent, offset_y=80)

    def _save_dictionary_entry(self, lang, phrase, kind, value):
        data = slang_mod.user_data()
        low = phrase.lower()
        for code in slang_mod.LANGS:
            for key in [k for k in data["expand"].get(code, {})
                        if k.lower() == low]:
                data["expand"][code].pop(key, None)
        data["keep"] = [k for k in data["keep"] if k.lower() != low]
        data["disabled"] = [item for item in data["disabled"]
                            if not str(item).lower().endswith(":" + low)]

        bundled = slang_mod._read(slang_mod.bundled_path())
        if kind == "keep":
            data["keep"].append(phrase)
            for code in slang_mod.LANGS:
                if any(k.lower() == low
                       for k in (bundled.get("expand", {}).get(code) or {})):
                    data["disabled"].append(f"{code}:{low}")
        else:
            data["expand"].setdefault(lang, {})[phrase] = value
            if any(str(k).lower() == low for k in (bundled.get("keep") or [])):
                data["disabled"].append("keep:" + low)
        slang_mod.save_user_data(data)
        self._reload_dictionary()

    def _delete_dictionary_entry(self):
        current = self._selected_dictionary_entry()
        if current is None:
            return
        lang, phrase, kind, _value, _source = current
        low = phrase.lower()
        data = slang_mod.user_data()
        bundled = slang_mod._read(slang_mod.bundled_path())

        if kind == "keep":
            data["keep"] = [k for k in data["keep"] if k.lower() != low]
            # Снимаем отключения этой фразы и отключаем встроенную запись,
            # если она была (тогда «не переводить» действительно исчезнет).
            data["disabled"] = [item for item in data["disabled"]
                                if not str(item).lower().endswith(":" + low)]
            if any(str(k).lower() == low for k in (bundled.get("keep") or [])):
                data["disabled"].append("keep:" + low)
        else:
            for key in [k for k in data["expand"].get(lang, {})
                        if k.lower() == low]:
                data["expand"][lang].pop(key, None)
            data["disabled"] = [item for item in data["disabled"]
                                if not str(item).lower().endswith(":" + low)]
            if any(k.lower() == low
                   for k in (bundled.get("expand", {}).get(lang) or {})):
                data["disabled"].append(f"{lang}:{low}")
        slang_mod.save_user_data(data)
        self._reload_dictionary()
        self._fill_dictionary_table()

    def _reload_dictionary(self):
        self._dict = slang_mod.load_slang()
        self._dict_user = slang_mod.user_data()
        self.engine.reload_slang()

    def _open_slang_file(self):
        try:
            path = slang_mod.ensure_user_file()
            os.startfile(path)
        except Exception as exc:
            messagebox.showwarning(APP_NAME, str(exc))

    def _show_settings_page(self, page):
        if not (self.settings_window and self.settings_window.winfo_exists()):
            return
        for page_id, btn in self._settings_buttons.items():
            if page_id == page:
                btn.configure(relief="sunken", bg=CLASSIC_BTN_PRESSED)
            else:
                btn.configure(relief="raised", bg=CLASSIC_BTN)

        for widget in self._settings_content.winfo_children():
            widget.destroy()

        tr = LANGS[self.lang_ui]
        c = self._settings_content
        self._settings_page = page

        # Сбрасываем сетку перед построением новой страницы.
        for row in range(12):
            c.grid_rowconfigure(row, weight=0)
        for col in range(2):
            c.grid_columnconfigure(col, weight=0)
        c.grid_columnconfigure(1, weight=1)

        if page == "translate":
            self._build_translate_page(c)
        elif page == "interface":
            self._build_interface_page(c)
        elif page == "dictionary":
            self._build_dictionary_page(c)
        elif page == "prompt":
            _classic_label(c, tr["prompt_label"], bold=True).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
            c.grid_rowconfigure(1, weight=1)

            text_frame = tk.Frame(c, bg=CLASSIC_BG, relief="sunken", bd=1)
            text_frame.grid(row=1, column=0, columnspan=2,
                            sticky="nsew", pady=(0, 8))

            self.prompt_textbox = tk.Text(
                text_frame, width=1, height=11, wrap="word",
                font=("Consolas", 9),
                bg="#ffffff", fg=CLASSIC_TEXT, insertbackground=CLASSIC_TEXT,
                relief="flat", bd=0, highlightthickness=0
            )
            self.prompt_textbox.pack(fill="both", expand=True)
            self.prompt_textbox.insert("1.0", self.system_prompt)
            self._bind_text_shortcuts(self.prompt_textbox)

            _classic_button(c, tr["save_prompt"], self._save_prompt).grid(
                row=2, column=0, columnspan=2, sticky="e")

        elif page == "chats":
            log_exists = os.path.isdir(self.log_dir)
            count = 0
            if log_exists:
                try:
                    count = len([name for name in os.listdir(self.log_dir)
                                 if name.lower().endswith(".txt")])
                except OSError:
                    count = 0
            status = (tr["log_dir_files"].format(n=count) if log_exists
                      else tr["log_dir_missing"])
            _classic_label(
                c, f"{tr['log_dir_label']} {self.log_dir} ({status})",
                wrap=520).grid(row=0, column=0, columnspan=2, sticky="w")

            self.replay_var = tk.BooleanVar(
                value=bool(self.config["ui"].get("replay_history", True)))
            _classic_check(c, tr["replay_setting"], self.replay_var,
                           self._on_replay_changed).grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(4, 4))

            _classic_button(c, tr["clear_chats"], self._clear_all_chats).grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(4, 8))
            c.grid_rowconfigure(3, weight=1)

            frame = tk.Frame(c, bg=CLASSIC_BG, relief="sunken", bd=1)
            frame.grid(row=3, column=0, columnspan=2, sticky="nsew")

            canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=0, bd=0,
                               width=300, height=140)
            scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            inner = tk.Frame(canvas, bg="#ffffff")
            window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
            inner.bind(
                "<Configure>",
                lambda e, cv=canvas: cv.configure(scrollregion=cv.bbox("all")))
            canvas.bind(
                "<Configure>",
                lambda e, cv=canvas, wid=window_id: cv.itemconfigure(
                    wid, width=cv.winfo_width()))

            if not self.all_channels:
                _classic_label(inner, tr["no_chats"], bg="#ffffff").pack(
                    anchor="w", padx=6, pady=8)
            else:
                for channel in self.all_channels:
                    var = tk.BooleanVar(value=(channel in self.active_channels))
                    _classic_check(
                        inner, channel, var,
                        lambda ch=channel, v=var: self._toggle_channel(ch, v),
                        bg="#ffffff"
                    ).pack(anchor="w", padx=6, pady=2)

            def _wheel(event, cv=canvas):
                if cv.winfo_exists():
                    cv.yview_scroll(-1 if event.delta > 0 else 1, "units")

            def _bind_wheel(widget):
                widget.bind("<MouseWheel>", _wheel, add="+")
                for child in widget.winfo_children():
                    _bind_wheel(child)

            _bind_wheel(frame)

        elif page == "about":
            _classic_label(c, APP_NAME, bold=True).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
            _classic_label(c, f"v{VERSION}").grid(
                row=1, column=0, columnspan=2, sticky="w")
            _classic_label(c, tr["about_desc"], wrap=320).grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
            _classic_label(c, tr["credits"], wrap=320).grid(
                row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
            tk.Label(c, text=tr["ccp_disclaimer"], bg=CLASSIC_BG,
                     fg="#555555", font=CLASSIC_FONT, anchor="w",
                     justify="left", wraplength=320).grid(
                row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

            self._update_status_var = tk.StringVar(
                value=self._update_status_text())
            status_row = tk.Frame(c, bg=CLASSIC_BG)
            status_row.grid(row=5, column=0, columnspan=2, sticky="w",
                            pady=(14, 0))
            tk.Label(status_row, textvariable=self._update_status_var,
                     bg=CLASSIC_BG, fg=CLASSIC_TEXT,
                     font=CLASSIC_FONT).pack(side="left")

            update_row = tk.Frame(c, bg=CLASSIC_BG)
            update_row.grid(row=6, column=0, columnspan=2, sticky="w",
                            pady=(6, 0))
            _classic_button(update_row, tr["update_download"],
                            self._open_update_page).pack(side="left")
            _classic_button(update_row, tr["update_check"],
                            lambda: self._check_updates(silent=False)).pack(
                side="left", padx=(6, 0))

    def _bind_text_shortcuts(self, widget):
        widget.bind("<Control-c>", lambda e: widget.event_generate("<<Copy>>"))
        widget.bind("<Control-C>", lambda e: widget.event_generate("<<Copy>>"))
        widget.bind("<Control-v>", lambda e: widget.event_generate("<<Paste>>"))
        widget.bind("<Control-V>", lambda e: widget.event_generate("<<Paste>>"))
        widget.bind("<Control-x>", lambda e: widget.event_generate("<<Cut>>"))
        widget.bind("<Control-X>", lambda e: widget.event_generate("<<Cut>>"))
        widget.bind("<Control-a>", lambda e: self._select_all_prompt())
        widget.bind("<Control-A>", lambda e: self._select_all_prompt())

        # Те же действия по коду клавиши: работает на любой раскладке.
        def on_ctrl(event):
            code = getattr(event, "keycode", 0)
            if code == 67:
                widget.event_generate("<<Copy>>")
                return "break"
            if code == 86:
                widget.event_generate("<<Paste>>")
                return "break"
            if code == 88:
                widget.event_generate("<<Cut>>")
                return "break"
            if code == 65:
                return self._select_all_prompt()
            return None

        widget.bind("<Control-KeyPress>", on_ctrl)

    def _select_all_prompt(self):
        self.prompt_textbox.tag_add("sel", "1.0", "end-1c")
        return "break"

    # ---------- Обработчики ----------
    def _clear_all_chats(self):
        for ch in list(self.tab_names):
            self._remove_tab(ch)
        self.active_channels.clear()
        self.all_channels.clear()
        self._open_settings_menu()

    def _save_prompt(self):
        self.system_prompt = self.prompt_textbox.get("1.0", "end-1c").strip()
        self.config["llm"]["system_prompt"] = self.system_prompt
        self.engine.system_prompt = self.system_prompt
        self.engine.clear_cache()
        save_config(self.config)
        self._open_settings_menu()

    def _on_hide_original_changed(self):
        self.hide_original = self.hide_orig_var.get()
        self.config["ui"]["hide_original"] = self.hide_original
        save_config(self.config)

    # ---------- Цвета: внутренний id <-> локализованная подпись ----------
    def _get_color_id(self, hex_code):
        for color_id, value in COLOR_IDS.items():
            if value == hex_code:
                return color_id
        return "white"

    def _color_label(self, color_id):
        return LANGS[self.lang_ui].get("color_" + color_id, color_id)

    def _color_id_from_label(self, label):
        tr = LANGS[self.lang_ui]
        for color_id in COLOR_IDS:
            if tr.get("color_" + color_id) == label:
                return color_id
        return label if label in COLOR_IDS else None

    def _on_target_lang_changed(self, val):
        self.lang_target = LANG_CODES.get(val, "ru")
        self.config["ui"]["lang_target"] = self.lang_target
        self.engine.target_lang = self.lang_target
        self.engine.clear_cache()
        save_config(self.config)

    def _on_terms_lang_changed(self, val):
        code = TERMS_LANG_CODES.get(val, "en")
        if code == self.terms_lang:
            return
        self.terms_lang = code
        self.config["ui"]["terms_lang"] = code
        self.engine.set_terms_lang(code)
        save_config(self.config)

    def _on_model_changed(self, val):
        if not val or getattr(self.engine.backend, "managed", False):
            return
        self.engine.backend.model = val
        self.engine.clear_cache()
        store_backend_config(self.config["llm"], self.engine.backend)
        save_config(self.config)

    def _on_ui_lang_changed(self, val):
        self.lang_ui = LANG_CODES.get(val, "ru")
        self.config["ui"]["lang_ui"] = self.lang_ui
        save_config(self.config)
        self._update_tray_menu()
        self._open_settings_menu()

    def _on_alpha_changed(self, value):
        # tk.Scale передаёт строку, CTkSlider передавал float.
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.attributes("-alpha", value)
        if hasattr(self, "alpha_label") and self.alpha_label.winfo_exists():
            self.alpha_label.configure(text=f"{int(value * 100)}%")
        self.config["window"]["alpha"] = value

    def _on_font_size_changed(self, value):
        self.font_size = int(value)
        self.config["ui"]["font_size"] = self.font_size
        for tb in self.textboxes.values():
            tb.configure(font=("Consolas", self.font_size))
            self._reapply_tags(tb)
        if getattr(self, "composer", None) is not None:
            self._sync_composer_font()

    def _on_color_orig_changed(self, label):
        color_id = self._color_id_from_label(label)
        if color_id is None:
            return
        self.color_orig = COLOR_IDS[color_id]
        self.config["ui"]["color_original"] = self.color_orig
        for tb in self.textboxes.values():
            self._reapply_tags(tb)

    def _on_color_trans_changed(self, label):
        color_id = self._color_id_from_label(label)
        if color_id is None:
            return
        self.color_trans = COLOR_IDS[color_id]
        self.config["ui"]["color_translated"] = self.color_trans
        for tb in self.textboxes.values():
            self._reapply_tags(tb)
        if getattr(self, "composer", None) is not None:
            self.composer.set_translation_color(self.color_trans)

    def _reapply_tags(self, tb):
        tb.tag_config("original", foreground=self.color_orig)
        tb.tag_config("translated", foreground=self.color_trans)
        tb.tag_config("highlight", foreground=self.color_high)
        tb.tag_config("sender", foreground="#888888")

    def _toggle_channel(self, channel, var):
        if var.get():
            if channel not in self.active_channels:
                self.active_channels.append(channel)
                self._ensure_tab(channel)
        else:
            if channel in self.active_channels:
                self.active_channels.remove(channel)
                self._remove_tab(channel)

    # ---------- События из фоновых потоков ----------
    def _post_ui(self, func, *args):
        """Кладёт задачу в очередь; выполняет её главный поток Tk."""
        try:
            self._ui_queue.put_nowait((func, args))
        except Exception:
            pass

    def _drain_ui_queue(self):
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self.after(40, self._drain_ui_queue)
        except Exception:
            pass

    # ---------- Приём сообщений ----------
    def receive_message(self, channel_name, msg_data, kept_words, msg_type):
        self._post_ui(self._update_ui, channel_name, msg_data, kept_words,
                      msg_type)

    def _update_ui(self, channel_name, msg_data, kept_words, msg_type):
        if channel_name not in self.all_channels:
            self.all_channels.append(channel_name)
            self.active_channels.append(channel_name)
            self._ensure_tab(channel_name)

        if channel_name not in self.tab_names: return
        textbox = self.textboxes[channel_name]
        
        is_at_bottom = False
        try:
            is_at_bottom = textbox.yview()[1] >= 0.99
        except Exception:
            pass

        textbox.configure(state="normal")

        header = msg_data.get("header", "")
        orig_text = msg_data.get("original", "")
        trans_text = msg_data.get("translation", "").rstrip()

        # Пустая строка между сообщениями — сверху, а не после последнего:
        # так низ окна не «съедает» пустая строка.
        if textbox.index("end-1c") != "1.0":
            textbox.insert("end", "\n\n", "original")

        textbox.insert("end", header + "\n", "sender")

        if not trans_text or msg_type == "original":
            self._insert_highlighted_text(textbox, orig_text, "original")
        else:
            if not self.hide_original and orig_text:
                self._insert_highlighted_text(textbox, orig_text, "original")
                textbox.insert("end", "\n", "original")

            self._insert_highlighted_text(textbox, trans_text, "translated")

        if is_at_bottom:
            textbox.see("end-1c")
            
        try:
            if int(textbox.index("end-1c").split(".")[0]) > 500:
                textbox.delete("1.0", "51.0")
        except Exception: pass
        textbox.configure(state="disabled")

    def _insert_highlighted_text(self, textbox, text, base_tag):
        """Вставляет текст, подсвечивая термины из keep_ci + keep_en.
        Диапазоны считает TermGuard.find_spans (те же правила, что при
        защите терминов), поэтому локализованные названия из map не красятся."""
        if not text:
            return

        spans = []
        try:
            spans = self.engine.guard.find_spans(text)
        except Exception:
            spans = []

        position = 0
        length = len(text)
        for start, end in spans:
            if start < position or end <= start:
                continue
            if start > position:
                textbox.insert("end", text[position:start], base_tag)
            textbox.insert("end", text[start:end], "highlight")
            position = end
        if position < length:
            textbox.insert("end", text[position:], base_tag)

    # ---------- Закрытие ----------
    def on_closing(self):
        try:
            if self.tab_bar.active:
                self.last_channel = self.tab_bar.active
        except Exception:
            pass
        self.config["window"]["geometry"] = self.geometry()
        self.config["chats"]["all"] = self.all_channels
        self.config["chats"]["active"] = self.active_channels
        self.config["chats"]["current"] = self.last_channel
        save_config(self.config)
        # Сначала гасим встроенный движок, потом лог-вотчер.
        try:
            self.backend.stop()
        except Exception:
            pass
        self.engine.stop()
        # Значок в трее нужно убрать, иначе он останется висеть после выхода.
        try:
            if self.tray_icon is not None:
                self.tray_icon.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    from single_instance import acquire, send_show, start_server

    if not acquire():
        # Приложение уже запущено: показываем его окно и выходим.
        send_show()
        sys.exit(0)

    app = EveTranslatorApp()
    start_server(lambda: app._post_ui(app._restore_window))
    app.mainloop()
