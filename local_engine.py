"""Встроенный движок перевода: llama.cpp (llama-server) + GGUF-модель.

Скачивает рантайм и модели, запускает сервер на свободном порту,
следит за ним и умеет откатываться с GPU на CPU, если не хватило
видеопамяти. UI общается через состояние (state/message/progress),
чтобы не подвешивать окно.
"""

import ctypes
import hashlib
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile

import paths

USER_AGENT = "EVE-LangBridge/0.2"

# Сборка llama.cpp, на которой всё проверялось. Обновлять осознанно:
# имя ассета в релизе зависит от тега.
LLAMA_RELEASE = "b12242"

RUNTIME_VARIANTS = {
    "vulkan": {
        "label": "Vulkan (GPU + CPU)",
        "url": ("https://github.com/ggml-org/llama.cpp/releases/download/"
                f"{LLAMA_RELEASE}/llama-{LLAMA_RELEASE}-bin-win-vulkan-x64.zip"),
        "approx_size": 38 * 1024 * 1024,
    },
    "cpu": {
        "label": "CPU",
        "url": ("https://github.com/ggml-org/llama.cpp/releases/download/"
                f"{LLAMA_RELEASE}/llama-{LLAMA_RELEASE}-bin-win-cpu-x64.zip"),
        "approx_size": 25 * 1024 * 1024,
    },
}

DEFAULT_RUNTIME_VARIANT = "vulkan"

# Каталог моделей. url собирается из repo/file (HuggingFace resolve).
# Требование: файл должен быть меньше ~2 ГБ, чтобы влезать в слабые GPU.
MODEL_CATALOG = {
    "hy-mt2-1.8b-q4": {
        "name": "Hy-MT2 1.8B · Q4_K_M",
        "repo": "tencent/Hy-MT2-1.8B-GGUF",
        "file": "Hy-MT2-1.8B-Q4_K_M.gguf",
        "size": 1133000000,
        "license": "Apache-2.0",
        "note": "Переводческая модель, рекомендуемая по умолчанию",
        "context": 1024,
        "default": True,
    },
    "qwen3-1.7b-q4": {
        "name": "Qwen3 1.7B · Q4_K_M",
        "repo": "bartowski/Qwen_Qwen3-1.7B-GGUF",
        "file": "Qwen_Qwen3-1.7B-Q4_K_M.gguf",
        "size": 1282000000,
        "license": "Apache-2.0",
        "note": "Универсальная модель, альтернатива переводческой",
        "context": 1024,
        # Qwen3 по умолчанию «думает» — для перевода это лишние токены
        # и время. Отключаем через kwargs шаблона (llama-server --jinja).
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    },
}

DEFAULT_MODEL_ID = next(
    (mid for mid, info in MODEL_CATALOG.items() if info.get("default")),
    next(iter(MODEL_CATALOG)),
)

CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


class DownloadCancelled(Exception):
    """Пользователь отменил загрузку."""


class LocalEngineError(RuntimeError):
    """Движок не смог запуститься."""


def catalog_model_ids():
    return list(MODEL_CATALOG.keys())


def model_info(model_id):
    return MODEL_CATALOG.get(model_id) or MODEL_CATALOG[DEFAULT_MODEL_ID]


def model_url(model_id):
    info = model_info(model_id)
    return f"https://huggingface.co/{info['repo']}/resolve/main/{info['file']}"


def model_path(model_id):
    return os.path.join(paths.models_dir(), model_info(model_id)["file"])


def model_installed(model_id):
    path = model_path(model_id)
    try:
        return os.path.getsize(path) > 1024 * 1024
    except OSError:
        return False


def runtime_exe():
    return os.path.join(paths.runtime_dir(), "llama-server.exe")


def runtime_installed():
    return os.path.exists(runtime_exe())


def default_runtime_variant():
    """Vulkan берём, только если в системе есть Vulkan-рантайм."""
    if os.name != "nt":
        return "cpu"
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    if os.path.exists(os.path.join(system_root, "System32", "vulkan-1.dll")):
        return DEFAULT_RUNTIME_VARIANT
    return "cpu"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _http_ok(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except Exception:
        return False


def _set_below_normal(proc):
    """Понижаем приоритет процесса, чтобы не отбирать кванты у игры."""
    try:
        handle = getattr(proc, "_handle", None)
        if handle:
            ctypes.windll.kernel32.SetPriorityClass(
                int(handle), BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def download_file(url, dest, progress=None, cancel=None, sha256=None):
    """Скачивает файл с докачкой. progress(downloaded, total) — по троттлингу."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0

    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)
    last_report = [0.0]

    def report(downloaded, total, force=False):
        if progress is None:
            return
        now = time.monotonic()
        if force or now - last_report[0] >= 0.15:
            last_report[0] = now
            try:
                progress(downloaded, total)
            except Exception:
                pass

    with urllib.request.urlopen(request, timeout=60) as response:
        status = getattr(response, "status", 200)
        if have and status != 206:
            # Сервер не умеет докачку — начинаем заново.
            have = 0
        length = response.headers.get("Content-Length")
        total = have + int(length) if length else 0
        report(have, total, force=True)
        mode = "ab" if have else "wb"
        with open(part, mode) as out:
            while True:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                chunk = response.read(262144)
                if not chunk:
                    break
                out.write(chunk)
                have += len(chunk)
                report(have, total)

    if total and have < total:
        raise LocalEngineError(
            f"Загрузка не завершена ({have} из {total} байт)")

    if sha256:
        digest = hashlib.sha256()
        with open(part, "rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest().lower() != sha256.lower():
            os.remove(part)
            raise LocalEngineError("Файл повреждён (не совпала контрольная сумма)")

    os.replace(part, dest)
    report(os.path.getsize(dest), os.path.getsize(dest), force=True)
    return dest


def install_runtime(variant=None, progress=None, cancel=None):
    """Скачивает и распаковывает llama-server. Возвращает путь к exe."""
    variant = variant or default_runtime_variant()
    if variant not in RUNTIME_VARIANTS:
        variant = "cpu"
    info = RUNTIME_VARIANTS[variant]
    archive = os.path.join(paths.runtime_dir(), f"llama-{variant}.zip")
    download_file(info["url"], archive, progress=progress, cancel=cancel)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(paths.runtime_dir())
    try:
        os.remove(archive)
    except OSError:
        pass
    if not runtime_installed():
        raise LocalEngineError("В архиве не оказалось llama-server.exe")
    with open(os.path.join(paths.runtime_dir(), ".variant"), "w",
              encoding="utf-8") as f:
        f.write(variant)
    return runtime_exe()


def installed_runtime_variant():
    try:
        with open(os.path.join(paths.runtime_dir(), ".variant"),
                  encoding="utf-8") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def download_model(model_id, progress=None, cancel=None):
    """Скачивает GGUF. Возвращает путь к файлу."""
    info = model_info(model_id)
    return download_file(model_url(model_id), model_path(model_id),
                         progress=progress, cancel=cancel)


def _tail(path, limit=4000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


class LocalEngine:
    """Жизненный цикл llama-server внутри приложения."""

    def __init__(self):
        self.state = "stopped"      # stopped | starting | running | error
        self.message = ""
        self.mode = ""              # gpu | cpu
        self.port = 0
        self.model_id = DEFAULT_MODEL_ID
        self._proc = None
        self._lock = threading.RLock()
        self._thread = None
        self._stop_event = threading.Event()
        self._watchdog = None
        self._restarts = 0
        self._params = (1024, 0, "auto")

    # ---------- состояние ----------
    @property
    def base_url(self):
        if not self.port:
            return ""
        return f"http://127.0.0.1:{self.port}/v1"

    def status(self):
        return {
            "state": self.state,
            "message": self.message,
            "mode": self.mode,
            "port": self.port,
            "model_id": self.model_id,
        }

    def _set(self, state=None, message=None, mode=None):
        with self._lock:
            if state is not None:
                self.state = state
            if message is not None:
                self.message = message
            if mode is not None:
                self.mode = mode

    # ---------- запуск ----------
    def start_async(self, model_id=DEFAULT_MODEL_ID, context=1024,
                    threads=0, gpu_layers="auto", reset_restarts=True):
        with self._lock:
            if self.state in ("starting", "running"):
                return
            self.model_id = model_id if model_id in MODEL_CATALOG else DEFAULT_MODEL_ID
            self._params = (context, threads, gpu_layers)
            self._stop_event.clear()
            if reset_restarts:
                self._restarts = 0
            self._set(state="starting", message="Запускаю движок…", mode="")
            self._thread = threading.Thread(
                target=self._start_worker,
                args=(context, threads, gpu_layers),
                daemon=True,
            )
            self._thread.start()

    def _attempts(self, gpu_layers):
        """Цепочка попыток: GPU -> GPU без KV-кэша -> CPU."""
        if gpu_layers == "auto":
            return [("gpu", ["-ngl", "99"]),
                    ("gpu", ["-ngl", "99", "-nkvo"]),
                    ("cpu", ["-ngl", "0"])]
        try:
            layers = int(gpu_layers)
        except (TypeError, ValueError):
            layers = -1
        if layers == 0:
            return [("cpu", ["-ngl", "0"])]
        if layers > 0:
            return [("gpu", ["-ngl", str(layers)]),
                    ("gpu", ["-ngl", str(layers), "-nkvo"]),
                    ("cpu", ["-ngl", "0"])]
        return [("gpu", ["-ngl", "99"]), ("cpu", ["-ngl", "0"])]

    def _start_worker(self, context, threads, gpu_layers):
        if not runtime_installed():
            self._set(state="error",
                      message="Движок не установлен: нет llama-server.exe")
            return
        if not model_installed(self.model_id):
            info = model_info(self.model_id)
            self._set(state="error",
                      message=f"Модель {info['name']} не скачана")
            return

        last_error = ""
        for mode, extra in self._attempts(gpu_layers):
            if self._stop_event.is_set():
                self._set(state="stopped", message="")
                return
            self._set(state="starting",
                      message=f"Запускаю движок ({'GPU' if mode == 'gpu' else 'CPU'})…")
            if self._try_start(mode, extra, context, threads):
                self._set(state="running", message="", mode=mode)
                self._start_watchdog()
                return
            last_error = self.message or last_error
            if mode == "cpu":
                break
        self._set(state="error", message=last_error or "Движок не запустился")

    def _try_start(self, mode, extra_args, context, threads):
        port = _free_port()
        log_path = os.path.join(paths.logs_dir(), "llama-server.log")
        command = [
            runtime_exe(),
            "--model", model_path(self.model_id),
            "--host", "127.0.0.1",
            "--port", str(port),
            "-c", str(int(context or 1024)),
            "--parallel", "1",
            "--jinja",
        ]
        command += extra_args
        if mode == "cpu":
            # Не отбираем все ядра у игры: половина, но не больше четырёх.
            cores = os.cpu_count() or 4
            worker_threads = int(threads or max(2, min(4, cores // 2)))
            command += ["-t", str(worker_threads)]

        try:
            log = open(log_path, "ab")
        except OSError:
            log = subprocess.DEVNULL
        try:
            if hasattr(log, "write"):
                log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} "
                          f"{mode} {' '.join(extra_args)} ===\n".encode("utf-8"))
                log.flush()
            proc = subprocess.Popen(
                command,
                cwd=paths.runtime_dir(),
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as exc:
            self.message = f"Не удалось запустить llama-server: {exc}"
            return False
        finally:
            if hasattr(log, "close") and log is not subprocess.DEVNULL:
                log.close()

        _set_below_normal(proc)
        deadline = time.time() + 120
        while time.time() < deadline:
            if self._stop_event.is_set():
                self._terminate(proc)
                self.message = ""
                return False
            if proc.poll() is not None:
                self._proc = None
                self.message = self._diagnose(log_path, proc.returncode)
                return False
            if _http_ok(f"http://127.0.0.1:{port}/v1/models"):
                with self._lock:
                    # stop() мог прийти, пока мы ждали ответа сервера —
                    # тогда процесс нужно сразу погасить, иначе он осиротеет.
                    if self._stop_event.is_set():
                        self._terminate(proc)
                        self.message = ""
                        return False
                    self._proc = proc
                    self.port = port
                return True
            time.sleep(0.3)
        self._terminate(proc)
        self.message = "Движок не ответил за 120 секунд"
        return False

    @staticmethod
    def _diagnose(log_path, code):
        tail = _tail(log_path).lower()
        if "out of memory" in tail or "failed to allocate" in tail \
                or "outofdevicememory" in tail:
            return "Не хватило видеопамяти — переключаюсь на CPU"
        if "vulkan" in tail and ("error" in tail or "fail" in tail):
            return "Vulkan не завёлся — переключаюсь на CPU"
        return f"llama-server завершился с кодом {code}"

    def _terminate(self, proc):
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        except Exception:
            pass

    # ---------- наблюдение ----------
    def _start_watchdog(self):
        if self._watchdog is not None and self._watchdog.is_alive():
            return
        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()

    def _watch(self):
        while not self._stop_event.is_set():
            time.sleep(3)
            with self._lock:
                proc = self._proc
            if proc is None or proc.poll() is None:
                continue
            if self._stop_event.is_set():
                return
            with self._lock:
                self._proc = None
                self.port = 0
            # Один автоматический перезапуск: сервер может упасть из-за
            # нехватки памяти уже после загрузки модели.
            if self._restarts < 1 and not self._stop_event.is_set():
                self._restarts += 1
                self._set(state="stopped",
                          message="Движок упал, перезапускаю…")
                self.start_async(self.model_id, *self._params,
                                 reset_restarts=False)
                return
            self._set(state="error", message="Движок неожиданно остановился")
            return

    # ---------- ожидание ----------
    def wait_ready(self, timeout=45.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.state
            if state == "running":
                return True
            if state in ("error", "stopped"):
                return False
            time.sleep(0.2)
        return self.state == "running"

    def stop(self):
        self._stop_event.set()
        with self._lock:
            proc = self._proc
            self._proc = None
        self._terminate(proc)
        self._set(state="stopped", message="", mode="")
        self.port = 0
