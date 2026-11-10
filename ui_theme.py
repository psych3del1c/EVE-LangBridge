"""Классические (Win32-подобные) виджеты для окон настроек и мастера.

Вынесены отдельно, чтобы окно настроек и мастер первого запуска
выглядели одинаково и не дублировали палитру.
"""

import tkinter as tk

CLASSIC_BG = "#f0f0f0"
CLASSIC_BTN = "#c0c0c0"
CLASSIC_BTN_ACTIVE = "#d4d4d4"
CLASSIC_BTN_PRESSED = "#a8a8a8"
CLASSIC_TEXT = "#000000"
CLASSIC_FONT = ("Tahoma", 9)


def classic_label(parent, text, bold=False, bg=CLASSIC_BG, wrap=0):
    font = (CLASSIC_FONT[0], CLASSIC_FONT[1], "bold") if bold else CLASSIC_FONT
    return tk.Label(
        parent, text=text, bg=bg, fg=CLASSIC_TEXT, font=font,
        anchor="w", justify="left", wraplength=wrap
    )


def classic_button(parent, text, command, width=None):
    options = dict(
        text=text, command=command, bg=CLASSIC_BTN, fg=CLASSIC_TEXT,
        activebackground=CLASSIC_BTN_ACTIVE, activeforeground=CLASSIC_TEXT,
        relief="raised", bd=2, highlightthickness=0, takefocus=0,
        font=CLASSIC_FONT, padx=8, pady=3
    )
    if width is not None:
        options["width"] = width
    return tk.Button(parent, **options)


def classic_check(parent, text, variable, command, bg=CLASSIC_BG):
    return tk.Checkbutton(
        parent, text=text, variable=variable, command=command,
        bg=bg, fg=CLASSIC_TEXT, activebackground=bg,
        activeforeground=CLASSIC_TEXT, selectcolor="#ffffff",
        font=CLASSIC_FONT, anchor="w", highlightthickness=0,
        bd=0, takefocus=0
    )


def classic_radio(parent, text, variable, value, bg=CLASSIC_BG):
    return tk.Radiobutton(
        parent, text=text, variable=variable, value=value,
        bg=bg, fg=CLASSIC_TEXT, activebackground=bg,
        activeforeground=CLASSIC_TEXT, selectcolor="#ffffff",
        font=CLASSIC_FONT, anchor="w", highlightthickness=0,
        bd=0, takefocus=0
    )


def classic_option(parent, variable, values, command, width=22):
    option = tk.OptionMenu(parent, variable, *values, command=command)
    option.configure(
        bg=CLASSIC_BTN, fg=CLASSIC_TEXT,
        activebackground=CLASSIC_BTN_ACTIVE, activeforeground=CLASSIC_TEXT,
        relief="raised", bd=1, highlightthickness=0, takefocus=0,
        font=CLASSIC_FONT, width=width, anchor="w"
    )
    option["menu"].configure(
        font=CLASSIC_FONT, bg="#ffffff", fg=CLASSIC_TEXT,
        activebackground="#000080", activeforeground="#ffffff"
    )
    return option


def classic_entry(parent, textvariable, width=32, show=None):
    entry = tk.Entry(
        parent, textvariable=textvariable, width=width,
        bg="#ffffff", fg=CLASSIC_TEXT, insertbackground=CLASSIC_TEXT,
        relief="sunken", bd=1, highlightthickness=0, font=CLASSIC_FONT
    )
    if show:
        entry.configure(show=show)
    return entry


def center_on_parent(window, parent, offset_y=40):
    """Ставит окно по центру родительского и не даёт уехать за экран."""
    window.update_idletasks()
    width = max(window.winfo_width(), window.winfo_reqwidth())
    height = max(window.winfo_height(), window.winfo_reqheight())
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + offset_y
    x = max(0, min(x, window.winfo_screenwidth() - width))
    y = max(0, min(y, window.winfo_screenheight() - height))
    window.geometry(f"{width}x{height}+{x}+{y}")
