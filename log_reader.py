"""Чтение логов чата EVE Online с нескольких клиентов.

EVE пишет отдельный файл на канал для каждого запущенного клиента.
Здесь мы:

  * читаем только то, что дописалось (по смещению и mtime);
  * один раз на файл разбираем шапку (имя канала) и кодировку;
  * склеиваем недописанные строки между опросами;
  * группируем файлы по имени канала — сообщения из нескольких окон
    попадают в один канал.
"""

import codecs
import os
import time

HEADER_BYTES = 4096
STALE_SECONDS = 7 * 24 * 3600


class _FileState:
    __slots__ = ("offset", "size", "mtime", "encoding", "decoder",
                 "tail", "channel", "seen")

    def __init__(self):
        self.offset = 0
        self.size = 0
        self.mtime = 0.0
        self.encoding = None
        self.decoder = None
        self.tail = ""
        self.channel = ""
        self.seen = time.time()


def _detect_encoding(raw):
    """Кодировка лога: BOM, затем UTF-16 по нулям, затем эвристики."""
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw and raw.count(b"\x00") > len(raw) // 4:
        return "utf-16-le"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        found = chardet.detect(raw).get("encoding")
        if found:
            return found
    except Exception:
        pass
    return "cp1251"


def _parse_header(text):
    """Channel Name и Listener из шапки файла."""
    channel = ""
    listener = ""
    for line in text.splitlines()[:20]:
        line = line.replace("\ufeff", "").strip()
        if line.startswith("Channel Name:"):
            channel = line.split(":", 1)[1].strip()
        elif line.startswith("Listener:"):
            listener = line.split(":", 1)[1].strip()
    return channel, listener


def _channel_from_filename(name):
    """Запасной вариант, если шапки нет: Local_2026... -> Local."""
    return name.split("_")[0]


class LogTailer:
    """Хвост логов: отдаёт только новые полные строки по каналам."""

    def __init__(self, directory):
        self.directory = directory
        self.files = {}
        self._primed = False

    def prime(self):
        """Запоминает существующие файлы на конце: старая история не нужна."""
        now = time.time()
        try:
            with os.scandir(self.directory) as entries:
                for entry in entries:
                    if not entry.name.lower().endswith(".txt"):
                        continue
                    try:
                        # os.stat, а не entry.stat(): у scandir размер может
                        # отставать на одну запись (кэш каталога Windows).
                        stat = os.stat(entry.path)
                    except OSError:
                        continue
                    state = _FileState()
                    state.offset = stat.st_size
                    state.size = stat.st_size
                    state.mtime = stat.st_mtime
                    state.seen = now
                    self.files[entry.path] = state
        except OSError:
            pass
        self._primed = True

    def poll(self):
        """Список (канал, строка) из всех файлов, где появились новые данные."""
        result = []
        now = time.time()
        try:
            with os.scandir(self.directory) as entries:
                for entry in entries:
                    if not entry.name.lower().endswith(".txt"):
                        continue
                    try:
                        # Свежий размер: entry.stat() у scandir кэшируется
                        # и отстаёт, из-за чего новые строки не замечались.
                        stat = os.stat(entry.path)
                    except OSError:
                        continue
                    path = entry.path
                    state = self.files.get(path)
                    if state is None:
                        # Новый файл (клиент только что запустился) — читаем весь.
                        state = _FileState()
                        state.size = stat.st_size
                        state.mtime = stat.st_mtime
                        state.seen = now
                        self.files[path] = state
                        result.extend(self._read(path, state))
                        continue
                    if stat.st_size == state.size and stat.st_mtime == state.mtime:
                        continue
                    state.seen = now
                    if stat.st_size < state.offset:
                        # Файл перезаписали (новая сессия с тем же именем).
                        state.offset = 0
                        state.decoder = None
                        state.tail = ""
                    state.size = stat.st_size
                    state.mtime = stat.st_mtime
                    result.extend(self._read(path, state))
        except OSError:
            pass
        self._prune(now)
        return result

    # ---------- внутреннее ----------
    def _load_meta(self, path, state):
        state.encoding = "utf-8"
        state.channel = _channel_from_filename(os.path.basename(path))
        try:
            with open(path, "rb") as handle:
                raw = handle.read(HEADER_BYTES)
        except OSError:
            raw = b""
        if raw:
            state.encoding = _detect_encoding(raw)
            channel, _listener = _parse_header(
                raw.decode(state.encoding, "replace"))
            if channel:
                state.channel = channel
        state.decoder = codecs.getincrementaldecoder(state.encoding)("replace")

    def _read(self, path, state):
        if state.encoding is None:
            self._load_meta(path, state)
        length = state.size - state.offset
        if length <= 0:
            return []
        try:
            with open(path, "rb") as handle:
                handle.seek(state.offset)
                data = handle.read(length)
                state.offset = handle.tell()
        except OSError:
            return []
        if not data:
            return []

        # Инкрементальный декодер не рвёт многобайтные символы на границе куска.
        text = state.tail + state.decoder.decode(data)
        text = text.replace("\ufeff", "").replace("\x00", "")
        state.tail = ""
        parts = text.splitlines(keepends=True)
        if parts and not parts[-1].endswith(("\n", "\r")):
            state.tail = parts.pop()

        channel = state.channel
        return [(channel, part.rstrip("\r\n")) for part in parts]

    def _prune(self, now):
        """Забывает давно не менявшиеся и полностью прочитанные файлы."""
        stale = [path for path, state in self.files.items()
                 if now - state.seen > STALE_SECONDS and state.offset >= state.size]
        for path in stale:
            del self.files[path]

    # ---------- история для показа при запуске ----------
    def _channel_of(self, path):
        state = self.files.get(path)
        if state is not None and state.channel:
            return state.channel
        return self._read_header(path)[0]

    def _read_header(self, path):
        try:
            with open(path, "rb") as handle:
                raw = handle.read(HEADER_BYTES)
        except OSError:
            return "", ""
        if not raw:
            return "", ""
        encoding = _detect_encoding(raw)
        return _parse_header(raw.decode(encoding, "replace"))

    def _tail_lines(self, path, limit):
        """Последние limit строк файла (для истории при запуске)."""
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as handle:
                offset = max(0, size - 65536)
                handle.seek(offset)
                raw = handle.read()
        except OSError:
            return []
        if not raw:
            return []
        channel, _listener = self._read_header(path)
        encoding = _detect_encoding(raw)
        text = raw.decode(encoding, "replace").replace("\ufeff", "")
        lines = [line.rstrip("\r") for line in text.splitlines() if line.strip()]
        if offset > 0 and lines:
            lines = lines[1:]  # первая строка могла обрезаться
        return lines[-limit:]

    def recent_lines(self, channels, limit=5, max_age_hours=12):
        """Последние сообщения по указанным каналам (для показа при запуске)."""
        channels = set(channels or [])
        if not channels:
            return []
        cutoff = time.time() - max_age_hours * 3600
        newest = {}
        try:
            with os.scandir(self.directory) as entries:
                for entry in entries:
                    if not entry.name.lower().endswith(".txt"):
                        continue
                    try:
                        stat = os.stat(entry.path)
                    except OSError:
                        continue
                    if stat.st_mtime < cutoff:
                        continue
                    channel = self._channel_of(entry.path)
                    if channel not in channels:
                        continue
                    best = newest.get(channel)
                    if best is None or stat.st_mtime > best[0]:
                        newest[channel] = (stat.st_mtime, entry.path)
        except OSError:
            pass

        result = []
        for channel, (_mtime, path) in newest.items():
            result.extend((channel, line)
                          for line in self._tail_lines(path, limit))
        return result
