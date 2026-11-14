"""Экран исходящего перевода.

Открывается кнопкой в заголовке окна. Занимает настраиваемую долю высоты
окна (по умолчанию 2/3): сверху ручка-разделитель, история переводов,
снизу ручка и многострочное поле ввода со скруглёнными углами.
"""

import time
import tkinter as tk

MIN_PANEL_HEIGHT = 150
MIN_CHAT_HEIGHT = 60
MIN_INPUT_HEIGHT = 42
MAX_INPUT_HEIGHT = 260
MIN_HISTORY_HEIGHT = 110
DIVIDER_GRIP_HEIGHT = 12
INPUT_GRIP_HEIGHT = 10
DIVIDER_HEIGHT = 2
DEFAULT_SPLIT = 2 / 3
DEFAULT_INPUT_HEIGHT = 42

BG = "#141414"
TEXT_BG = "#0d0d0d"
TEXT_FG = "#d0d0d0"
MUTED = "#7a7a7a"
BORDER = "#2b2b2b"
FIELD_BORDER = "#3a3a3a"
ACCENT = "#fca311"
ACCENT_HOVER = "#ffc04d"
SENDER = "#888888"
ERROR = "#ff6b6b"

LANGUAGES = ("ru", "en", "zh")

# Контур самолётика: нос вправо, хвост с выемкой.
_PLANE = ((1.0, 0.0), (-0.8, -0.8), (-0.42, 0.0), (-0.8, 0.8))


class Composer(tk.Frame):
    """История исходящих переводов и многострочная строка ввода."""

    def __init__(self, master, tr_provider, on_translate, on_lang_change=None,
                 on_expanded=None, on_geometry_change=None, lang="en",
                 autocopy=True, split=DEFAULT_SPLIT,
                 input_height=DEFAULT_INPUT_HEIGHT,
                 translation_color="#00ff7f", font=None, font_size=12):
        super().__init__(master, bg=BG)
        self.pack_propagate(False)
        self._tr = tr_provider
        self._on_translate = on_translate
        self._on_lang_change = on_lang_change
        self._on_expanded = on_expanded
        self._on_geometry_change = on_geometry_change
        # Шрифт берём тот же, что в основном чате (пиксельный размер CTk).
        self._font = font if font is not None else ("Consolas", font_size)
        self.autocopy = bool(autocopy)
        self._lang = lang if lang in LANGUAGES else "en"
        self._expanded = False
        self._busy = False
        self._last_translation = ""
        self._pending_text = ""
        self._status_job = None
        self._panel_height = 0
        self._split = self._clamp_split(split)
        self._input_height = self._clamp_input(input_height)
        self._lang_popup = None
        self._drag_kind = None
        self._drag_y = 0
        self._drag_h = 0
        self._grip_widget = None

        # ---------- верхняя ручка + разделитель ----------
        self._divider = tk.Frame(
            self, bg=BG, height=DIVIDER_GRIP_HEIGHT,
            cursor="sb_v_double_arrow")
        self._divider_line = tk.Frame(
            self._divider, bg=FIELD_BORDER, height=DIVIDER_HEIGHT,
            cursor="sb_v_double_arrow")
        self._divider_line.pack(side="top", fill="x")
        self._bind_drag(self._divider, "composer")
        self._bind_drag(self._divider_line, "composer")

        # ---------- история ----------
        self._history = tk.Text(
            self, wrap="word", font=self._font,
            bg=TEXT_BG, fg=TEXT_FG, relief="flat", bd=0,
            highlightthickness=0, padx=10, pady=8, state="disabled")
        self._history.tag_config("sender", foreground=SENDER)
        self._history.tag_config("original", foreground=TEXT_FG)
        self._history.tag_config("translated", foreground=translation_color)
        self._history.bind("<Control-c>", self._copy_selection)
        self._history.bind("<Control-C>", self._copy_selection)
        self._history.bind("<Control-KeyPress>", self._history_ctrl)
        self._history.bind("<Configure>", self._on_history_resize)

        # Статус всплывает поверх истории, а не занимает место в строке.
        self._status = tk.Label(
            self._history, text="", bg="#181818", fg=ACCENT,
            font=("Segoe UI", 8), padx=6, pady=2)

        # ---------- ручка высоты поля ввода ----------
        self._input_grip = tk.Frame(
            self, height=INPUT_GRIP_HEIGHT, bg=BG,
            cursor="sb_v_double_arrow")
        self._bind_drag(self._input_grip, "input")

        # ---------- строка ввода (скруглённое поле на Canvas) ----------
        self._input_wrap = tk.Canvas(
            self, bg=BG, height=self._input_height, bd=0,
            highlightthickness=0)
        self._input_wrap.pack_propagate(False)
        self._input_wrap.bind("<Configure>", self._draw_input_bg)
        self._input_wrap.bind("<Button-1>", self._focus_entry)

        # Кнопки пакуются первыми и всегда прижаты к правому краю:
        # поле ввода получает только то, что осталось.
        self._send_btn = _IconButton(self._input_wrap, _draw_send,
                                     self.submit, TEXT_BG)
        self._send_btn.pack(side="right", anchor="s",
                            padx=(2, 8), pady=(0, 7))
        self._copy_btn = _IconButton(self._input_wrap, _draw_copy,
                                     self.copy_last, TEXT_BG)
        self._copy_btn.pack(side="right", anchor="s",
                            padx=(0, 2), pady=(0, 7))

        self._lang_btn = tk.Button(
            self._input_wrap, text=self._lang, bg=TEXT_BG,
            fg="#c8c8c8", activebackground="#1f1f1f",
            activeforeground="#ffffff", relief="flat", overrelief="flat",
            bd=0, highlightthickness=0, takefocus=0,
            font=("Segoe UI", 9), padx=6, pady=1, cursor="hand2",
            command=self._open_lang_menu)
        self._lang_btn.pack(side="left", anchor="s",
                            padx=(8, 4), pady=(0, 7))

        # Многострочное поле: Enter отправляет, Shift+Enter переносит.
        self._entry = tk.Text(
            self._input_wrap, width=1, height=1, wrap="word",
            bg=TEXT_BG, fg=TEXT_FG, insertbackground=TEXT_FG,
            relief="flat", bd=0, highlightthickness=0,
            font=self._font, padx=3, pady=2)
        self._entry.pack(side="left", fill="both", expand=True,
                         padx=(2, 4), pady=7)
        self._entry.bind("<Return>", self._on_return)
        self._entry.bind("<Shift-Return>", self._on_newline)
        self._entry.bind("<Control-Return>", self._on_return)
        self._entry.bind("<Control-c>", self._entry_copy)
        self._entry.bind("<Control-C>", self._entry_copy)
        self._entry.bind("<Control-v>", self._entry_paste)
        self._entry.bind("<Control-V>", self._entry_paste)
        self._entry.bind("<Control-x>", self._entry_cut)
        self._entry.bind("<Control-X>", self._entry_cut)
        self._entry.bind("<Control-a>", self._entry_select_all)
        self._entry.bind("<Control-A>", self._entry_select_all)
        self._entry.bind("<Control-KeyPress>", self._entry_ctrl)

        self.after_idle(self._draw_input_bg)

    # ---------- размеры / состояние ----------
    @staticmethod
    def _clamp_split(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = DEFAULT_SPLIT
        return max(0.2, min(0.9, value))

    @classmethod
    def _clamp_input(cls, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = DEFAULT_INPUT_HEIGHT
        return max(MIN_INPUT_HEIGHT, min(MAX_INPUT_HEIGHT, value))

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded, window_height=None):
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        if expanded:
            self._input_wrap.pack(side="bottom", fill="x", padx=6,
                                  pady=(0, 6))
            self._input_grip.pack(side="bottom", fill="x", padx=6)
            self._divider.pack(side="top", fill="x")
            self._history.pack(side="top", fill="both", expand=True)
            self.update_height(window_height)
            self.update_idletasks()
            self._draw_input_bg()
            self.after_idle(self._focus_entry)
        else:
            self._close_lang_menu()
            self._history.pack_forget()
            self._divider.pack_forget()
            self._input_grip.pack_forget()
            self._input_wrap.pack_forget()
            self.configure(height=1)
        if self._on_expanded:
            try:
                self._on_expanded(expanded)
            except Exception:
                pass

    def update_height(self, window_height=None):
        """Панель держит свою долю окна, поле ввода — свою высоту."""
        if not self._expanded:
            return
        if window_height is None:
            try:
                window_height = self.winfo_toplevel().winfo_height()
            except Exception:
                window_height = 450
        height = int(window_height * self._split)
        height = max(MIN_PANEL_HEIGHT, height)
        limit = max(1, int(window_height) - MIN_CHAT_HEIGHT)
        if height > limit:
            height = limit
        self._panel_height = height
        try:
            self.configure(height=height)
        except Exception:
            pass
        self._apply_input_height()

    def _apply_input_height(self):
        panel = self._panel_height or self.winfo_height() or 300
        limit = max(MIN_INPUT_HEIGHT, panel - MIN_HISTORY_HEIGHT)
        height = max(MIN_INPUT_HEIGHT,
                     min(self._input_height, limit))
        try:
            self._input_wrap.configure(height=height)
        except Exception:
            pass

    # ---------- перетаскивание ручек ----------
    def _bind_drag(self, widget, kind):
        widget.bind("<ButtonPress-1>",
                    lambda e, k=kind: self._drag_start(e, k))
        widget.bind("<Double-Button-1>", self._drag_reset)

    def _drag_start(self, event, kind):
        self._drag_kind = kind
        self._drag_y = event.y_root
        self._drag_h = (self.winfo_height() if kind == "composer"
                        else self._input_height)
        self._grip_widget = event.widget
        # Ведём перетаскивание на уровне окна: так движение не теряется,
        # когда курсор уходит с тонкой ручки.
        top = self.winfo_toplevel()
        self._drag_motion_id = top.bind(
            "<B1-Motion>", self._drag_motion, add="+")
        self._drag_end_id = top.bind(
            "<ButtonRelease-1>", self._drag_end, add="+")
        return "break"

    def _drag_motion(self, event):
        if not self._drag_kind:
            return "break"
        delta = self._drag_y - event.y_root
        if self._drag_kind == "composer":
            try:
                window_height = self.winfo_toplevel().winfo_height()
            except Exception:
                window_height = 450
            limit = max(1, window_height - MIN_CHAT_HEIGHT)
            height = max(MIN_PANEL_HEIGHT, self._drag_h + delta)
            height = min(height, limit)
            self._panel_height = height
            self.configure(height=height)
            self._split = height / max(1, window_height)
            self._apply_input_height()
        else:
            limit = max(MIN_INPUT_HEIGHT,
                        self._panel_height - MIN_HISTORY_HEIGHT)
            height = max(MIN_INPUT_HEIGHT, self._drag_h + delta)
            height = min(height, limit, MAX_INPUT_HEIGHT)
            self._input_height = height
            self._input_wrap.configure(height=height)
        return "break"

    def _drag_end(self, event):
        if not self._drag_kind:
            return "break"
        top = self.winfo_toplevel()
        for attr, seq in (("_drag_motion_id", "<B1-Motion>"),
                          ("_drag_end_id", "<ButtonRelease-1>")):
            funcid = getattr(self, attr, None)
            setattr(self, attr, None)
            if funcid:
                try:
                    top.unbind(seq, funcid)
                except Exception:
                    pass
        self._drag_kind = None
        self._grip_widget = None
        self._notify_geometry()
        return "break"

    def _drag_reset(self, event):
        self._split = DEFAULT_SPLIT
        self._input_height = DEFAULT_INPUT_HEIGHT
        self.update_height()
        self._apply_input_height()
        self._notify_geometry()
        return "break"

    def _notify_geometry(self):
        if self._on_geometry_change:
            try:
                self._on_geometry_change(self._split, self._input_height)
            except Exception:
                pass

    # ---------- настройки отображения ----------
    def set_translation_color(self, color):
        try:
            self._history.tag_config("translated", foreground=color)
        except Exception:
            pass

    def set_font(self, font):
        """Тот же шрифт, что в основном чате (например, 'Consolas -13')."""
        self._font = font
        try:
            self._entry.configure(font=font)
            self._history.configure(font=font)
        except Exception:
            pass

    def set_font_size(self, size):
        self.set_font(("Consolas", size))

    def set_language(self, code):
        if code in LANGUAGES:
            self._lang = code
            self._lang_btn.configure(text=code)

    @property
    def lang(self):
        return self._lang

    @property
    def expanded(self):
        return self._expanded

    # ---------- действия ----------
    def _focus_entry(self, event=None):
        try:
            self._entry.focus_set()
            self.after_idle(self._entry.focus_set)
        except Exception:
            pass
        return "break"

    def _on_return(self, event=None):
        self.submit()
        return "break"

    def _on_newline(self, event=None):
        try:
            self._entry.insert("insert", "\n")
        except Exception:
            pass
        return "break"

    def _entry_text(self):
        try:
            return self._entry.get("1.0", "end-1c")
        except Exception:
            return ""

    def submit(self):
        if self._busy:
            return
        text = self._entry_text().strip()
        if not text:
            return
        self._busy = True
        self._pending_text = text
        self._set_busy(True)
        self._show_status(self._tr().get("composer_translating", "…"),
                          ACCENT)
        self._on_translate(text, self._lang, self._on_result)

    def _on_result(self, text, error):
        self._busy = False
        self._set_busy(False)
        if error or not text:
            self._show_status(self._tr().get("composer_error", "Error"),
                              ERROR)
            return
        self._append_history(self._pending_text, text)
        self._last_translation = text
        if self.autocopy:
            self._copy_raw(text)
            self._show_status(self._tr().get("composer_copied", "Copied"),
                              ACCENT)
        self._clear_entry()

    def copy_last(self):
        if self._last_translation:
            self._copy_raw(self._last_translation)
            self._show_status(self._tr().get("composer_copied", "Copied"),
                              ACCENT)

    def _choose_lang(self, code):
        if code not in LANGUAGES:
            return
        self._lang = code
        self._lang_btn.configure(text=code)
        if self._on_lang_change:
            self._on_lang_change(code)

    # ---------- попап выбора языка ----------
    def _open_lang_menu(self):
        self._close_lang_menu()
        try:
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.configure(bg=FIELD_BORDER)

            body = tk.Frame(top, bg="#1f1f1f")
            body.pack(padx=1, pady=1)
            for code in LANGUAGES:
                item = tk.Label(
                    body, text=code, bg="#1f1f1f", fg="#c8c8c8",
                    font=("Segoe UI", 9), padx=22, pady=4,
                    anchor="center", cursor="hand2")
                item.pack(fill="x")
                item.bind("<Enter>", lambda e, w=item: w.configure(
                    bg="#3a3a3a", fg="#ffffff"))
                item.bind("<Leave>", lambda e, w=item: w.configure(
                    bg="#1f1f1f", fg="#c8c8c8"))
                item.bind("<Button-1>",
                          lambda e, c=code: self._pick_lang(c))

            top.update_idletasks()
            x = self._lang_btn.winfo_rootx()
            y = self._lang_btn.winfo_rooty() - top.winfo_reqheight()
            if y < 0:
                y = self._lang_btn.winfo_rooty() + \
                    self._lang_btn.winfo_height()
            top.geometry("+%d+%d" % (x, y))
            top.bind("<Escape>", lambda e: self._close_lang_menu())
            top.bind("<Button-1>", self._close_lang_menu, add="+")
            top.focus_set()
            self._lang_popup = top
            # Клик в любом месте приложения закрывает попап.
            self._popup_bind_id = self.winfo_toplevel().bind(
                "<Button-1>", self._close_lang_menu, add="+")
        except Exception:
            self._close_lang_menu()

    def _pick_lang(self, code):
        self._close_lang_menu()
        self._choose_lang(code)
        self.after_idle(self._focus_entry)

    def close_transient(self):
        """Закрывает всплывающие элементы панели."""
        self._close_lang_menu()

    def _close_lang_menu(self, event=None):
        popup = getattr(self, "_lang_popup", None)
        self._lang_popup = None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass
            bind_id = getattr(self, "_popup_bind_id", None)
            self._popup_bind_id = None
            if bind_id:
                try:
                    self.winfo_toplevel().unbind("<Button-1>", bind_id)
                except Exception:
                    pass

    # ---------- история ----------
    def _on_history_resize(self, event=None):
        try:
            self._history.see("end-1c")
        except Exception:
            pass

    def _append_history(self, original, translation):
        stamp = time.strftime("%H:%M")
        you = self._tr().get("composer_you", "you:")
        try:
            self._history.configure(state="normal")
            # Разделяем сообщения пустой строкой сверху, а не снизу:
            # иначе после последнего перевода остаётся пустая строка.
            if self._history.index("end-1c") != "1.0":
                self._history.insert("end", "\n\n", "sender")
            self._history.insert("end", f"[{stamp}] {you}\n", "sender")
            self._history.insert("end", original + "\n", "original")
            self._history.insert("end", translation, "translated")
            self._history.configure(state="disabled")
            self._history.see("end-1c")
        except Exception:
            pass

    def _copy_selection(self, event=None):
        try:
            text = self._history.get("sel.first", "sel.last")
        except Exception:
            return "break"
        if text:
            self._copy_raw(text)
        return "break"

    def _history_ctrl(self, event):
        if getattr(event, "keycode", 0) == 67:  # C на любой раскладке
            return self._copy_selection()
        return None

    def _copy_raw(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def _entry_ctrl(self, event):
        """Ctrl+C/V/X/A по коду клавиши — работает при русской раскладке."""
        code = getattr(event, "keycode", 0)
        if code == 67:
            return self._entry_copy()
        if code == 86:
            return self._entry_paste()
        if code == 88:
            return self._entry_cut()
        if code == 65:
            return self._entry_select_all()
        return None

    def _entry_copy(self, event=None):
        try:
            text = self._entry.get("sel.first", "sel.last")
        except Exception:
            return "break"
        self._copy_raw(text)
        return "break"

    def _entry_paste(self, event=None):
        try:
            text = self.clipboard_get()
        except Exception:
            return "break"
        try:
            self._entry.insert("insert", text)
        except Exception:
            pass
        return "break"

    def _entry_cut(self, event=None):
        try:
            text = self._entry.get("sel.first", "sel.last")
        except Exception:
            return "break"
        self._copy_raw(text)
        try:
            self._entry.delete("sel.first", "sel.last")
        except Exception:
            pass
        return "break"

    def _entry_select_all(self, event=None):
        self._entry.tag_add("sel", "1.0", "end-1c")
        self._entry.mark_set("insert", "end-1c")
        return "break"

    # ---------- поле ввода ----------
    def _draw_input_bg(self, event=None):
        canvas = self._input_wrap
        try:
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            if width <= 2 or height <= 2:
                return
            canvas.delete("bg")
            _round_rect(canvas, 1, 1, width - 1, height - 1,
                        10, fill=TEXT_BG, outline=FIELD_BORDER,
                        width=1, tags="bg")
            canvas.tag_lower("bg")
        except Exception:
            pass

    def _clear_entry(self):
        self._entry.delete("1.0", "end")

    def _show_status(self, text, color=ACCENT):
        if self._status_job is not None:
            try:
                self.after_cancel(self._status_job)
            except Exception:
                pass
        try:
            self._status.configure(text=text, fg=color)
            self._status.place(relx=1.0, rely=1.0, x=-10, y=-8,
                               anchor="se")
            self._status.lift()
        except Exception:
            return
        self._status_job = self.after(1800, self._clear_status)

    def _clear_status(self):
        self._status_job = None
        try:
            self._status.place_forget()
        except Exception:
            pass

    def _set_busy(self, busy):
        self._send_btn.set_enabled(not busy)


class _IconButton(tk.Canvas):
    """Плоская кнопка с нарисованной иконкой."""

    def __init__(self, parent, draw, command, bg_color):
        super().__init__(parent, width=28, height=28, bg=bg_color,
                         highlightthickness=0, cursor="hand2")
        self._bg = bg_color
        self._draw = draw
        self._command = command
        self._enabled = True
        self._render()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _render(self):
        self.delete("all")
        color = "#c8c8c8" if self._enabled else "#4a4a4a"
        self._draw(self, color, self.cget("bg"))

    def _click(self, event):
        if self._enabled and self._command:
            self._command()

    def _enter(self, event):
        self.configure(bg="#1a1a1a")
        self._render()

    def _leave(self, event):
        self.configure(bg=self._bg)
        self._render()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self._render()


def _draw_plane(canvas, color, cx, cy, size, angle):
    """Рисует самолётик, повёрнутый на angle градусов."""
    import math
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    points = []
    for x, y in _PLANE:
        rx = x * cos_a - y * sin_a
        ry = x * sin_a + y * cos_a
        points.append(cx + rx * size)
        points.append(cy + ry * size)
    canvas.create_polygon(points, fill=color, outline=color, width=1,
                          joinstyle="round")


def _round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """Скруглённый прямоугольник одним сглаженным полигоном."""
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


def _draw_copy(canvas, color, bg):
    _round_rect(canvas, 7, 7, 17, 17, 3,
                outline=color, width=1, fill="")
    _round_rect(canvas, 11, 11, 21, 21, 3,
                outline=color, width=1, fill=bg)


def _draw_send(canvas, color, bg):
    _draw_plane(canvas, color, 14, 14, 7.5, 0)
