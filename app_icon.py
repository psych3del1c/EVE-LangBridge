"""Иконка приложения.

Берём логотип из папки icons (logo-16/32/100.png) и масштабируем под
нужный размер. Если файлов нет — рисуем запасную плитку ELB, чтобы
приложение всё равно запускалось.
"""

import os
import tkinter as tk

import paths

# Запасная пиксельная иконка (14x8): одна строка = один ряд пикселей.
APP_ICON_BITS = (
    "1111.1000.1111",
    "1000.1000.1001",
    "1000.1000.1001",
    "1110.1000.1110",
    "1000.1000.1001",
    "1000.1000.1001",
    "1000.1000.1001",
    "1111.1111.1111",
)
ICON_BG = "#1a1a1a"
ICON_FG = "#fca311"

LOGO_FILES = {
    16: "icons/logo-16.png",
    32: "icons/logo-32.png",
    64: "icons/logo-64.png",
    100: "icons/logo-100.png",
}


def _logo_path(size):
    """Какой исходник ближе всего к запрошенному размеру."""
    if size <= 16:
        key = 16
    elif size <= 32:
        key = 32
    elif size <= 64:
        key = 64
    else:
        key = 100
    return paths.resource_path(LOGO_FILES[key])


def _load_logo(size):
    """Логотип нужного размера или None, если файла нет."""
    try:
        from PIL import Image

        path = _logo_path(size)
        if not os.path.exists(path):
            return None
        with Image.open(path) as image:
            image = image.convert("RGBA")
            if image.size != (size, size):
                image = image.resize((size, size), Image.LANCZOS)
            return image.copy()
    except Exception:
        return None


def icon_rects(size):
    """Прямоугольники надписи ELB для запасной иконки."""
    bits_w = len(APP_ICON_BITS[0])
    bits_h = len(APP_ICON_BITS)
    scale = max(1, min(size // bits_w, size // bits_h))
    width = bits_w * scale
    height = bits_h * scale
    left = (size - width) // 2
    top = (size - height) // 2
    rects = []
    for row, line in enumerate(APP_ICON_BITS):
        for col, bit in enumerate(line):
            if bit != "1":
                continue
            x = left + col * scale
            y = top + row * scale
            rects.append((x, y, x + scale, y + scale))
    return rects


def _fallback_pil(size):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (size, size), ICON_BG)
    draw = ImageDraw.Draw(image)
    for x1, y1, x2, y2 in icon_rects(size):
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=ICON_FG)
    return image


def make_tk_icon(size=32):
    """Иконка для Tk (заголовки окон, трей-окно)."""
    # Для стандартных размеров грузим готовый PNG напрямую — без ImageTk,
    # чтобы иконка работала и в собранном exe.
    path = _logo_path(size)
    if size in LOGO_FILES and os.path.exists(path):
        try:
            return tk.PhotoImage(file=path)
        except Exception:
            pass

    logo = _load_logo(size)
    if logo is not None:
        try:
            from PIL import ImageTk

            return ImageTk.PhotoImage(logo)
        except Exception:
            pass

    icon = tk.PhotoImage(width=size, height=size)
    icon.put(ICON_BG, to=(0, 0, size, size))
    for x1, y1, x2, y2 in icon_rects(size):
        icon.put(ICON_FG, to=(x1, y1, x2, y2))
    return icon


def make_pil_image(size=64):
    """Иконка картинкой Pillow — для трея и .ico."""
    logo = _load_logo(size)
    if logo is not None:
        return logo
    return _fallback_pil(size)
