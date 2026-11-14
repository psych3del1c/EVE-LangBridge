"""Помощники для окна-оверлея на Windows.

Позволяют показывать окно поверх игры, не забирая у неё фокус:
WS_EX_NOACTIVATE + показ/поднятие через SetWindowPos с SWP_NOACTIVATE.
На не-Windows все функции — заглушки.
"""

import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
GA_ROOT = 2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SW_SHOWNOACTIVATE = 4

if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM)

    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int,
                                       ctypes.c_long]
    _user32.SetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                          WNDPROC]
    _user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM]
    _user32.CallWindowProcW.restype = LRESULT
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    GWLP_WNDPROC = -4
    WM_MOUSEACTIVATE = 0x0021
    MA_NOACTIVATE = 3
    _subclassed = {}
    _old_procs = {}

    def _overlay_wndproc(hwnd, msg, wparam, lparam):
        # Не даём Windows активировать окно по клику. Все остальные
        # сообщения передаём родному обработчику Tk.
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        old = _old_procs.get(hwnd)
        if old:
            return _user32.CallWindowProcW(
                old, hwnd, msg, wparam, lparam)
        return 0

    _PROC = WNDPROC(_overlay_wndproc)
else:
    _PROC = None


def _subclass_hwnd(hwnd):
    """Перехватывает WM_MOUSEACTIVATE у окна по HWND."""
    if not IS_WINDOWS or not hwnd or hwnd in _subclassed:
        return hwnd
    try:
        old = _user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, _PROC)
        _old_procs[hwnd] = old
        _subclassed[hwnd] = True
    except Exception:
        pass
    return hwnd


def _subclass_client(widget):
    """Перехватывает WM_MOUSEACTIVATE у клиентского окна Tk."""
    if not IS_WINDOWS:
        return None
    try:
        return _subclass_hwnd(widget.winfo_id())
    except Exception:
        return None


def root_hwnd(widget):
    """HWND верхнего окна Tk-виджета (или None)."""
    if not IS_WINDOWS:
        return None
    try:
        return _user32.GetAncestor(widget.winfo_id(), GA_ROOT) or None
    except Exception:
        return None


def install_noactivate(widget):
    """Полный режим «не забирать фокус» для окна Tk.

    Ставит WS_EX_NOACTIVATE на обёртку и клиент, а клиенту подменяет
    WndProc, чтобы WM_MOUSEACTIVATE возвращал MA_NOACTIVATE.
    """
    if not IS_WINDOWS:
        return None
    root = root_hwnd(widget)
    client = _subclass_client(widget)
    set_noactivate(root, True)
    set_noactivate(client, True)
    _subclass_hwnd(root)
    return root


def forget(widget):
    """Убирает записи о временном окне (попап) из кэша."""
    if not IS_WINDOWS:
        return
    try:
        for hwnd in (widget.winfo_id(), root_hwnd(widget)):
            _subclassed.pop(hwnd, None)
            _old_procs.pop(hwnd, None)
    except Exception:
        pass


def foreground_hwnd():
    if not IS_WINDOWS:
        return None
    try:
        return _user32.GetForegroundWindow() or None
    except Exception:
        return None


def set_noactivate(hwnd, enabled=True):
    """Включает/выключает WS_EX_NOACTIVATE у окна."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_NOACTIVATE
        else:
            style &= ~WS_EX_NOACTIVATE
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


def set_topmost(hwnd):
    """Поднимает окно поверх всех, не активируя его."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        _user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


def show_noactivate(hwnd):
    """Показывает окно, не забирая фокус."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    except Exception:
        pass
    set_topmost(hwnd)


def activate(hwnd):
    """Осознанно активирует окно (для ввода текста)."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        fg = _user32.GetForegroundWindow()
        current = _kernel32.GetCurrentThreadId()
        fg_thread = 0
        if fg:
            fg_thread = _user32.GetWindowThreadProcessId(fg, None)
        attached = False
        if fg_thread and fg_thread != current:
            attached = bool(_user32.AttachThreadInput(
                current, fg_thread, True))
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        if attached:
            _user32.AttachThreadInput(current, fg_thread, False)
    except Exception:
        pass
