"""Иконка приложения: тёмная плитка с жёлтой надписью ELB.

Рисуется вручную по пиксельной сетке, чтобы не зависеть от рендера
шрифтов и одинаково выглядеть в заголовке окна, в трее и в exe.
"""

import tkinter as tk

# Одна строка = один ряд пикселей (14x8). Точка — прозрачный пиксель.
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


def icon_rects(size):
    """Прямоугольники надписи ELB, отмасштабированные под size x size."""
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


def make_tk_icon(size=32):
    """Иконка для Tk (заголовок окна настроек, трей-окно)."""
    icon = tk.PhotoImage(width=size, height=size)
    icon.put(ICON_BG, to=(0, 0, size, size))
    for x1, y1, x2, y2 in icon_rects(size):
        icon.put(ICON_FG, to=(x1, y1, x2, y2))
    return icon


def make_pil_image(size=64):
    """Та же иконка картинкой Pillow — для трея и .ico."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (size, size), ICON_BG)
    draw = ImageDraw.Draw(image)
    for x1, y1, x2, y2 in icon_rects(size):
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=ICON_FG)
    return image
