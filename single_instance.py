"""Один экземпляр приложения.

Второй запуск не открывает новое окно, а просит уже работающее
показаться: мьютекс Windows определяет «уже запущено», локальный сокет
передаёт сигнал первому экземпляру.
"""

import ctypes
import os
import socket
import threading
import time

MUTEX_NAME = "EVE_LangBridge_SingleInstance"
ERROR_ALREADY_EXISTS = 183
HOST = "127.0.0.1"
PORT = 47654

_handle = None


def acquire():
    """True, если мы первый экземпляр. Мьютекс живёт до конца процесса."""
    global _handle
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        _handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def send_show(timeout=2.0):
    """Просит первый экземпляр показать окно. True, если сигнал ушёл."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.3) as conn:
                conn.sendall(b"show")
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_server(callback):
    """Слушает сигнал «show» в фоне и вызывает callback в главном потоке."""

    def serve():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen(5)
        except OSError:
            try:
                server.close()
            except OSError:
                pass
            return

        while True:
            try:
                conn, _addr = server.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.recv(16)
                except OSError:
                    pass
            try:
                callback()
            except Exception:
                pass

    threading.Thread(target=serve, daemon=True).start()
