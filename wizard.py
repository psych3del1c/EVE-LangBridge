"""Мастер первого запуска: выбор модели, скачивание, проверка движка.

Работает в отдельном окне в стиле окна настроек. Скачивание идёт в фоне,
интерфейс обновляется через after(), поэтому окно не подвисает.
"""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import local_engine as le
import system_info
from ui_theme import (
    CLASSIC_BG,
    classic_label, classic_button, classic_radio, center_on_parent,
)

MB = 1024 * 1024

TARGET_NAMES = {"ru": "Russian", "en": "English", "zh": "Chinese"}

TEXT = {
    "ru": {
        "title": "Настройка перевода",
        "heading": "Первый запуск",
        "intro": ("Для перевода нужен локальный движок и модель. Они скачиваются "
                  "один раз (около 1 ГБ), дальше всё работает без интернета."),
        "hardware": "Компьютер: {hw}",
        "models": "Модель:",
        "recommended": " — рекомендуется",
        "mb": "МБ",
        "download": "Скачать и запустить",
        "external": "У меня уже есть LM Studio / Ollama",
        "later": "Позже",
        "stage_runtime": "Скачивание движка llama.cpp…",
        "stage_model": "Скачивание модели…",
        "progress": "{done} / {total} МБ · {speed} МБ/с · осталось {eta}",
        "eta": "{m} мин {s} с",
        "eta_unknown": "…",
        "cancel": "Отмена",
        "starting": "Запускаю движок…",
        "success": "Готово! Движок работает ({mode}).\n\nПроверка перевода:\n{original}\n{translation}",
        "close": "Закрыть",
        "retry": "Повторить",
        "error_prefix": "Не получилось: {message}",
        "sample": "Hello! Welcome to EVE Online.",
        "cancelled": "Скачивание отменено",
    },
    "en": {
        "title": "Translation setup",
        "heading": "First run",
        "intro": ("A local engine and model are required. They are downloaded "
                  "once (~1 GB), after that everything works offline."),
        "hardware": "Computer: {hw}",
        "models": "Model:",
        "recommended": " — recommended",
        "mb": "MB",
        "download": "Download and start",
        "external": "I already have LM Studio / Ollama",
        "later": "Later",
        "stage_runtime": "Downloading llama.cpp engine…",
        "stage_model": "Downloading model…",
        "progress": "{done} / {total} MB · {speed} MB/s · {eta} left",
        "eta": "{m}m {s}s",
        "eta_unknown": "…",
        "cancel": "Cancel",
        "starting": "Starting engine…",
        "success": "Done! Engine is running ({mode}).\n\nTranslation check:\n{original}\n{translation}",
        "close": "Close",
        "retry": "Retry",
        "error_prefix": "Failed: {message}",
        "sample": "Hello! Welcome to EVE Online.",
        "cancelled": "Download cancelled",
    },
    "zh": {
        "title": "翻译设置",
        "heading": "首次运行",
        "intro": "需要本地引擎和模型。只需下载一次（约 1 GB），之后完全离线运行。",
        "hardware": "电脑：{hw}",
        "models": "模型：",
        "recommended": " — 推荐",
        "mb": "MB",
        "download": "下载并启动",
        "external": "我已经有 LM Studio / Ollama",
        "later": "以后再说",
        "stage_runtime": "正在下载 llama.cpp 引擎…",
        "stage_model": "正在下载模型…",
        "progress": "{done} / {total} MB · {speed} MB/s · 剩余 {eta}",
        "eta": "{m} 分 {s} 秒",
        "eta_unknown": "…",
        "cancel": "取消",
        "starting": "正在启动引擎…",
        "success": "完成！引擎已启动（{mode}）。\n\n翻译检查：\n{original}\n{translation}",
        "close": "关闭",
        "retry": "重试",
        "error_prefix": "失败：{message}",
        "sample": "Hello! Welcome to EVE Online.",
        "cancelled": "下载已取消",
    },
}


class SetupWizard(tk.Toplevel):
    """Модальное окно настройки встроенного движка (только первый запуск
    или вызов из настроек)."""

    def __init__(self, master, lang, target_lang, on_apply,
                 on_external=None, on_close=None, initial_model=None):
        super().__init__(master)
        self.lang = lang if lang in TEXT else "ru"
        self.tr = TEXT[self.lang]
        self.on_apply = on_apply
        self.on_external = on_external
        self.on_close = on_close
        self.target_lang = TARGET_NAMES.get(target_lang, "Russian")

        self.result = None
        self.model_id = tk.StringVar(
            value=initial_model if initial_model in le.MODEL_CATALOG
            else le.DEFAULT_MODEL_ID)
        self.cancel_event = threading.Event()
        self._closing = False
        self._backend = None
        self._download_started = 0.0
        self._samples = []
        self._poll_deadline = 0.0
        # Фоновые потоки кладут сюда задачи, а главный поток их выполняет.
        # Так мы не трогаем Tk из чужих потоков (after оттуда ненадёжен).
        self._queue = queue.Queue()

        self.title(self.tr["title"])
        self.configure(bg=CLASSIC_BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)
        try:
            from app_icon import make_tk_icon
            self._app_icon = make_tk_icon(32)
            self.iconphoto(True, self._app_icon)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.body = tk.Frame(self, bg=CLASSIC_BG, padx=16, pady=14)
        self.body.pack(fill="both", expand=True)

        self._show_choice()
        self.update_idletasks()
        center_on_parent(self, master, offset_y=60)
        self.after(60, self._grab)
        self.after(50, self._drain)

    def _grab(self):
        try:
            self.grab_set()
        except Exception:
            pass

    def _drain(self):
        """Выполняет задачи из фоновых потоков в главном потоке Tk."""
        if self._closing:
            return
        try:
            while True:
                func, args = self._queue.get_nowait()
                try:
                    func(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self.after(50, self._drain)
        except Exception:
            pass

    # ---------- служебное ----------
    def _clear(self):
        for widget in self.body.winfo_children():
            widget.destroy()

    def _ui(self, func, *args):
        """Вызов из фонового потока: кладём задачу и уходим."""
        if self._closing:
            return
        try:
            self._queue.put((func, args))
        except Exception:
            pass

    def _close(self):
        self._closing = True
        self.cancel_event.set()
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_close:
            self.on_close()

    # ---------- шаг 1: выбор ----------
    def _show_choice(self):
        self.result = None
        self._clear()
        tr = self.tr
        classic_label(self.body, tr["heading"], bold=True).pack(anchor="w")
        classic_label(self.body, tr["intro"], wrap=460).pack(
            anchor="w", pady=(6, 10))
        classic_label(
            self.body,
            tr["hardware"].format(hw=system_info.hardware_summary(self.lang)),
            wrap=460,
        ).pack(anchor="w", pady=(0, 12))

        classic_label(self.body, tr["models"], bold=True).pack(
            anchor="w", pady=(0, 4))

        for model_id in le.catalog_model_ids():
            info = le.model_info(model_id)
            size = info.get("size", 0) / MB
            text = f"{info['name']} — {size:.0f} {tr['mb']}"
            if info.get("default"):
                text += tr["recommended"]
            classic_radio(self.body, text, self.model_id, model_id).pack(
                anchor="w", pady=1)

        buttons = tk.Frame(self.body, bg=CLASSIC_BG)
        buttons.pack(anchor="w", pady=(18, 0))
        classic_button(buttons, tr["download"], self._start_download).pack(
            side="left")
        classic_button(buttons, tr["external"], self._use_external).pack(
            side="left", padx=(8, 0))
        classic_button(buttons, tr["later"], self._close).pack(
            side="left", padx=(8, 0))

    def _use_external(self):
        self._close()
        if self.on_external:
            self.on_external()

    # ---------- шаг 2: скачивание ----------
    def _show_download(self, stage_key):
        self._clear()
        self._stage_label = classic_label(self.body, self.tr[stage_key], bold=True)
        self._stage_label.pack(anchor="w")
        self._bar = ttk.Progressbar(self.body, maximum=100, length=470)
        self._bar.pack(anchor="w", pady=(12, 6))
        self._detail = classic_label(self.body, self.tr["eta_unknown"], wrap=470)
        self._detail.pack(anchor="w")
        classic_button(self.body, self.tr["cancel"], self._cancel).pack(
            anchor="w", pady=(16, 0))

    def _start_download(self):
        model_id = self.model_id.get()
        self.cancel_event.clear()
        self._samples = []
        self._download_started = time.monotonic()
        self._show_download("stage_runtime" if not le.runtime_installed()
                            else "stage_model")
        threading.Thread(target=self._download_worker, args=(model_id,),
                         daemon=True).start()

    def _download_worker(self, model_id):
        try:
            if not le.runtime_installed():
                le.install_runtime(progress=self._progress,
                                   cancel=self.cancel_event)
            if not le.model_installed(model_id):
                self._ui(self._set_stage, "stage_model")
                le.download_model(model_id, progress=self._progress,
                                  cancel=self.cancel_event)
        except le.DownloadCancelled:
            self._ui(self._show_choice)
            return
        except Exception as exc:
            self._ui(self._show_error, str(exc), self._start_download)
            return
        self._ui(self._start_engine)

    def _set_stage(self, stage_key):
        if self._closing or not hasattr(self, "_stage_label"):
            return
        try:
            self._stage_label.configure(text=self.tr[stage_key])
            self._bar["value"] = 0
            self._samples = []
            self._download_started = time.monotonic()
        except Exception:
            pass

    def _cancel(self):
        self.cancel_event.set()

    def _progress(self, done, total):
        """Из фонового потока; частота уже ограничена загрузчиком."""
        if self._closing:
            return
        now = time.monotonic()
        self._samples.append((now, done))
        # Держим последние 5 секунд — так скорость верна и после докачки.
        while len(self._samples) > 2 and now - self._samples[0][0] > 5:
            self._samples.pop(0)
        self._ui(self._apply_progress, done, total, now)

    def _apply_progress(self, done, total, now):
        if self._closing or not hasattr(self, "_bar"):
            return
        try:
            if not self._bar.winfo_exists():
                return
            percent = (done * 100.0 / total) if total else 0
            self._bar["value"] = min(100, percent)

            speed = 0.0
            if len(self._samples) >= 2:
                first_t, first_d = self._samples[0]
                span = now - first_t
                if span > 0.2:
                    speed = (done - first_d) / span / MB

            eta = self.tr["eta_unknown"]
            if speed > 0.1 and total > done:
                seconds = int((total - done) / MB / speed)
                eta = self.tr["eta"].format(m=seconds // 60, s=seconds % 60)

            self._detail.configure(text=self.tr["progress"].format(
                done=f"{done / MB:.1f}", total=f"{total / MB:.1f}",
                speed=f"{speed:.1f}", eta=eta))
        except Exception:
            pass

    # ---------- шаг 3: запуск и проверка ----------
    def _show_waiting(self):
        self._clear()
        classic_label(self.body, self.tr["starting"], bold=True).pack(anchor="w")
        bar = ttk.Progressbar(self.body, mode="indeterminate", length=470)
        bar.pack(anchor="w", pady=(12, 0))
        bar.start(12)

    def _start_engine(self):
        if self._closing:
            return
        self._show_waiting()
        try:
            self._backend = self.on_apply(self.model_id.get())
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._poll_deadline = time.monotonic() + 180
        self._poll_engine()

    def _poll_engine(self):
        if self._closing:
            return
        engine = getattr(self._backend, "engine", None)
        if engine is None:
            self._show_error("Внутренняя ошибка: нет движка")
            return
        if engine.state == "running":
            self._smoke_test()
            return
        if engine.state == "error":
            self._show_error(engine.message or "Движок не запустился")
            return
        if time.monotonic() > self._poll_deadline:
            self._show_error("Движок не запустился за 3 минуты")
            return
        self.after(300, self._poll_engine)

    def _smoke_test(self):
        threading.Thread(target=self._smoke_worker, daemon=True).start()

    def _smoke_worker(self):
        try:
            text = self.tr["sample"]
            translated = self._backend.chat(
                [{"role": "system",
                  "content": f"Translate the following text into "
                             f"{self.target_lang}. Only output the translation."},
                 {"role": "user", "content": text}],
                temperature=0.0, timeout=120)
        except Exception as exc:
            self._ui(self._show_error, str(exc))
            return
        mode = getattr(getattr(self._backend, "engine", None), "mode", "")
        self._ui(self._show_success, text, translated, mode)

    def _show_success(self, original, translated, mode):
        self.result = "success"
        self._clear()
        classic_label(self.body, "✓", bold=True).pack(anchor="w")
        classic_label(
            self.body,
            self.tr["success"].format(
                mode="GPU" if mode == "gpu" else "CPU",
                original=original, translation=translated),
            wrap=470,
        ).pack(anchor="w", pady=(6, 16))
        classic_button(self.body, self.tr["close"], self._close).pack(anchor="w")

    def _show_error(self, message, retry=None):
        self.result = "error"
        self._clear()
        classic_label(self.body, self.tr["error_prefix"].format(
            message=message), wrap=470).pack(anchor="w")
        classic_button(self.body, self.tr["retry"], retry or self._start_engine).pack(
            anchor="w", pady=(16, 0))
        classic_button(self.body, self.tr["close"], self._close).pack(
            anchor="w", pady=(8, 0))
