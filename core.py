import os
import time
import threading
import re
import json
import queue
from collections import OrderedDict

from log_reader import LogTailer
from slang import load_slang
import app_log

# Признаки того, что модель пересказала инструкцию про метки вместо
# перевода сообщения. Модель может перевести саму подсказку, поэтому
# проверяем на всех трёх языках интерфейса.
LEAK_STRONG = (
    # английский
    "do not translate", "do not remove", "do not omit", "keep tokens",
    "must remain in the", "placeholder",
    # русский
    "не нужно переводить", "не переводить", "не переводи ", "не удаляй",
    "исходном тексте", "исходный текст", "метки вида",
    # китайский
    "不要翻译", "不要删除", "不要省略", "必须保留",
)
LEAK_WEAK = (
    "токен", "маркер", "метк", "опускать", "marker", "omit them",
    "must remain", "all markers", "标记", "保留", "原文中",
)

import paths

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TERMS_FILE = paths.resource_path("eve_terms.json")


# ==================== Определение письменности ====================
def _char_script(ch):
    """Грубая классификация символа по письменности (для границ слов)."""
    cp = ord(ch)
    if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x3040 <= cp <= 0x30FF or 0xF900 <= cp <= 0xFAFF):
        return "cjk"
    low = ch.lower()
    if "a" <= low <= "z":
        return "latin"
    if "а" <= low <= "я" or low == "ё":
        return "cyr"
    if 0xAC00 <= cp <= 0xD7A3 or 0x1100 <= cp <= 0x11FF:
        return "hangul"
    if ch.isdigit():
        return "digit"
    return "other"


def _is_cjk(ch):
    return _char_script(ch) == "cjk"


def _is_word_char_for(ch, term_ch):
    """Является ли ch частью того же слова, что и term_ch."""
    term_script = _char_script(term_ch)
    if term_script in ("cjk", "hangul"):
        # В китайском/японском нет пробелов, а в корейском к слову
        # приклеиваются частицы ("지타에서") — границы не нужны.
        return False
    if term_script == "digit":
        term_script = "latin"
    ch_script = _char_script(ch)
    if ch_script in ("cjk", "other"):
        return False
    if ch_script == "digit":
        return True
    return ch_script == term_script


# ==================== Защита EVE-терминов ====================
class TermGuard:
    """
    Находит в тексте названия кораблей/предметов/систем и подменяет их
    на плейсхолдеры [[N]] перед отправкой в нейросеть. После перевода
    возвращает на их место английские названия.

    eve_terms.json генерируется скриптом build_terms.py из официального SDE.
    """

    PLACEHOLDER_RE = re.compile(
        r"[\[［]\s*[\[［]\s*(\d+)\s*[\]］]\s*[\]］]"
    )
    PLACEHOLDER_SINGLE_RE = re.compile(r"[\[［]\s*(\d+)\s*[\]］]")

    def __init__(self, terms_file=TERMS_FILE, extra_keep=None,
                 display_lang="en"):
        self.terms = {}       # lower(name) -> (English name, case_sensitive)
        self.highlight_terms = set()  # ключи только из keep_en + keep_ci
        self._index = None    # first char -> (lengths desc, {length: {term: en}})
        self._index_lock = threading.Lock()
        self._loaded = False
        self._terms_file = terms_file
        # На каком языке показывать названия в переводе (en/ru/zh).
        self._display_lang = display_lang if display_lang in ("en", "ru", "zh") else "en"
        self._en_to = {}
        self._display_cache = {}
        # Слова из словаря сленга с пометкой «не переводить»: защищаем их
        # так же, как термины, но не подсвечиваем в чате.
        self._extra_keep = [str(item).strip() for item in (extra_keep or [])
                            if str(item).strip()]
        self._load_terms(terms_file)

    def set_extra_keep(self, terms):
        """Меняет список «не переводить» и пересобирает словарь терминов."""
        self._extra_keep = [str(item).strip() for item in (terms or [])
                            if str(item).strip()]
        self.terms = {}
        self.highlight_terms = set()
        self._load_terms(self._terms_file)
        self._loaded = True
        with self._index_lock:
            self._index = None

    def set_display_lang(self, lang):
        """Меняет язык названий в переводе (en/ru/zh)."""
        lang = lang if lang in ("en", "ru", "zh") else "en"
        self._display_lang = lang

    def _display_map(self, lang):
        """Карта «английское имя -> форма» для языка (с кэшем)."""
        if lang == "en":
            return {}
        cached = self._display_cache.get(lang)
        if cached is None:
            cached = {}
            for en, forms in self._en_to.items():
                name = (forms or {}).get(lang)
                if name:
                    cached[str(en).lower()] = name
            self._display_cache[lang] = cached
        return cached

    def display_name(self, english_name, lang=None):
        """Английское название -> форма для языка (по умолчанию — общий)."""
        lang = lang or self._display_lang
        if lang == "en" or not english_name:
            return english_name
        return self._display_map(lang).get(str(english_name).lower(),
                                          english_name)

    # ---------- загрузка ----------
    def _load_terms(self, path):
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mapping = data.get("map", {})
            if isinstance(mapping, dict):
                for key, en in mapping.items():
                    key = key.strip().lower()
                    if key and en:
                        self.terms[key] = (en, False)
            # Английские имена собственные защищаем с учётом регистра:
            # так "Cache" (регион) не трогает обычное слово "cache".
            for en in data.get("keep_en", []):
                en = str(en).strip()
                if en and len(en) >= 2:
                    self.terms.setdefault(en.lower(), (en, True))
                    self.highlight_terms.add(en.lower())
            # Корабли и многословные названия защищаем в любом регистре:
            # игроки пишут "any astero fit", "wts rifter".
            for en in data.get("keep_ci", []):
                en = str(en).strip()
                if en and len(en) >= 2:
                    self.terms.setdefault(en.lower(), (en, False))
                    self.highlight_terms.add(en.lower())
            # Слова из словаря сленга: защищаем, но не подсвечиваем.
            for item in self._extra_keep:
                if item:
                    self.terms.setdefault(item.lower(), (item, False))
            # Обратная карта: английское имя -> формы на разных языках.
            self._en_to = data.get("en_to") or {}
            self._display_cache = {}
            self._loaded = True
        except Exception:
            pass

    def _build_index(self):
        index = {}
        for term, value in self.terms.items():
            first = term[0]
            tables = index.setdefault(first, {})
            tables.setdefault(len(term), {})[term] = value
        for first, tables in index.items():
            index[first] = (sorted(tables.keys(), reverse=True), tables)
        self._index = index

    def ensure_ready(self):
        """Строит индекс при первом обращении (не тормозит запуск окна)."""
        if self._index is not None:
            return
        with self._index_lock:
            if self._index is None:
                self._build_index()

    @property
    def ready(self):
        return bool(self.terms)

    # ---------- поиск ----------
    def _match_at(self, original, lowered, i, n):
        entry = self._index.get(lowered[i])
        if not entry:
            return None
        lengths, tables = entry
        for length in lengths:
            end = i + length
            if end > n:
                continue
            term = lowered[i:end]
            found = tables[length].get(term)
            if found is None:
                continue
            value, case_sensitive = found
            if case_sensitive:
                chunk = original[i:end]
                if chunk.lower() != value.lower():
                    continue
                # Имена собственные защищаем только с заглавной буквы:
                # "Cache" (регион) — да, обычное слово "cache" — нет.
                if chunk.islower():
                    continue
            if i > 0 and _is_word_char_for(lowered[i - 1], term[0]):
                continue
            if end < n and _is_word_char_for(lowered[end], term[-1]):
                continue
            return length, value
        return None

    def _scan(self, text, mask, display_lang=None):
        """Один проход. mask=True -> (текст с [[N]], [названия на языке показа])."""
        if not text:
            return text, []
        self.ensure_ready()
        low = text.lower()
        if len(low) != len(text):
            low = text
        n = len(text)
        out = []
        replaced = []
        i = 0
        while i < n:
            match = self._match_at(text, low, i, n)
            if match is None:
                out.append(text[i])
                i += 1
                continue
            length, value = match
            shown = self.display_name(value, display_lang)
            if mask:
                out.append("[[%d]]" % len(replaced))
            else:
                out.append(shown)
            replaced.append(shown)
            i += length
        return "".join(out), replaced

    def find_spans(self, text):
        """Диапазоны (start, end) терминов из keep_en + keep_ci.
        Используется только для подсветки в UI; map (локализованные
        названия) намеренно не подсвечивается."""
        if not text:
            return []
        self.ensure_ready()
        low = text.lower()
        if len(low) != len(text):
            low = text
        n = len(text)
        spans = []
        i = 0
        while i < n:
            match = self._match_at(text, low, i, n)
            if match is None:
                i += 1
                continue
            length, _value = match
            if low[i:i + length] in self.highlight_terms:
                spans.append((i, i + length))
                i += length
            else:
                # Термин из map не подсвечиваем, но внутри него может
                # начинаться название корабля/системы — идём дальше по символу.
                i += 1
        return spans

    # ---------- публичный API ----------
    def protect(self, text, display_lang=None):
        """Текст -> (текст с плейсхолдерами, список названий)."""
        return self._scan(text, mask=True, display_lang=display_lang)

    def restore(self, text, replacements):
        """Возвращает английские названия на место плейсхолдеров."""
        if not replacements:
            return text, []
        used = [False] * len(replacements)

        def repl(match):
            try:
                idx = int(match.group(1))
            except ValueError:
                return match.group(0)
            if 0 <= idx < len(replacements):
                used[idx] = True
                return replacements[idx]
            return match.group(0)

        def repl_unused(match):
            try:
                idx = int(match.group(1))
            except ValueError:
                return match.group(0)
            if 0 <= idx < len(replacements) and not used[idx]:
                used[idx] = True
                return replacements[idx]
            return match.group(0)

        # Сначала строгий вариант [[0]], затем — если модель потеряла
        # одну скобку — одиночный [0].
        text = self.PLACEHOLDER_RE.sub(repl, text)
        text = self.PLACEHOLDER_SINGLE_RE.sub(repl_unused, text)
        missing = [name for i, name in enumerate(replacements) if not used[i]]
        return text, missing

    def localize(self, text, display_lang=None):
        """Приводит названия в тексте к выбранному языку показа."""
        if not text:
            return text, []
        return self._scan(text, mask=False, display_lang=display_lang)

    # Старое имя оставлено, чтобы не сломать внешние вызовы.
    englishize = localize


class TranslatorEngine:
    def __init__(
        self,
        ui_callback,
        backend,
        log_dir=None,
        poll_interval=1.0,
        target_lang="ru",
        system_prompt="",
        terms_lang="en"
    ):
        self.ui_callback = ui_callback
        self.backend = backend
        self.log_dir = log_dir or paths.resolve_input_path(
            r"~\Documents\EVE\logs\Chatlogs")
        self.poll_interval = poll_interval
        self.target_lang = target_lang

        self.system_prompt = system_prompt or (
            f"You are a translator. Translate the text to {{target_lang}}. "
            f"Output ONLY the translation, without any comments."
        )

        self.running = True

        # Чтение логов всех клиентов: свои файлы на каждый канал.
        self.tailer = LogTailer(self.log_dir)

        # Дедупликация одинаковых сообщений из разных окон игры.
        self._dedupe = OrderedDict()
        self._dedupe_ttl = 15.0
        self._dedupe_max = 2000

        # Очередь перевода: один воркер последовательно ходит в модель.
        # Так локальный сервер не захлёбывается и строки идут по порядку.
        self._jobs = queue.Queue(maxsize=1000)
        self._worker = None
        self._job_sentinel = object()

        # Кэш готовых переводов (LRU): реклама в чате повторяется часто,
        # и такие повторы не должны занимать GPU/CPU.
        self._cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_max = 256

        # --- Словарь сленга и защита EVE-терминов ---
        self.slang = load_slang()
        self.terms_lang = terms_lang if terms_lang in ("en", "ru", "zh") else "en"
        self.guard = TermGuard(TERMS_FILE, extra_keep=self.slang.keep_terms(),
                               display_lang=self.terms_lang)
        app_log.log(f"engine: log_dir={self.log_dir} terms={len(self.guard.terms)} "
                    f"display={self.terms_lang}")

        self.log_pattern = re.compile(
            r"\[\s*(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s*\]\s*(.*?)\s*>\s*(.*)"
        )
        # EVE пишет команду /emote в лог как есть, хотя в игре сообщение
        # выглядит как «* Ник * текст». Команду убираем перед переводом,
        # иначе она уходит в модель и попадает в перевод.
        self.emote_pattern = re.compile(r"^/\s*(?:emote|me)\b\s*", re.IGNORECASE)
        self.chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        self.russian_pattern = re.compile(r'[а-яА-ЯёЁ]')
        self.english_pattern = re.compile(r'[a-zA-Z]')

    def list_models(self, timeout=3.0):
        """Список моделей активного бэкенда."""
        return self.backend.list_models(timeout=timeout)

    def start(self):
        self._worker = threading.Thread(target=self._work_loop, daemon=True)
        self._worker.start()
        thread = threading.Thread(target=self._watch_logs, daemon=True)
        thread.start()

    # ---------- очередь перевода ----------
    def _enqueue(self, channel_name, time_str, sender, message, is_emote):
        try:
            self._jobs.put_nowait(
                (channel_name, time_str, sender, message, is_emote))
        except queue.Full:
            # Очередь переполнена (шквал сообщений) — показываем оригинал,
            # чтобы не терять строки и не копить минуты задержки.
            self.ui_callback(channel_name, {
                "header": self._chat_header(time_str, sender, is_emote),
                "original": message,
                "translation": "",
            }, [], "original")

    def _work_loop(self):
        while True:
            try:
                job = self._jobs.get(timeout=0.5)
            except queue.Empty:
                if not self.running:
                    return
                continue
            if job is self._job_sentinel:
                return
            try:
                self._translate_and_send(*job)
            except Exception as exc:
                # Не теряем сообщение, если перевод упал по любой причине.
                app_log.log(f"worker: ошибка перевода {exc!r}")
                try:
                    channel, time_str, sender, message, is_emote = job
                    self.ui_callback(channel, {
                        "header": self._chat_header(time_str, sender, is_emote),
                        "original": message,
                        "translation": "",
                    }, [], "original")
                except Exception:
                    pass
            finally:
                self._jobs.task_done()

    def queue_size(self):
        return self._jobs.qsize()

    # ---------- дедупликация сообщений из нескольких окон ----------
    def _is_duplicate(self, channel, time_str, sender, message):
        """True, если это же сообщение уже пришло из другого клиента.

        Ключ включает время сообщения: настоящее повторение того же
        текста всегда имеет другую секунду."""
        key = (channel, time_str, sender, message)
        now = time.monotonic()
        while self._dedupe:
            first_key = next(iter(self._dedupe))
            if now - self._dedupe[first_key] > self._dedupe_ttl:
                self._dedupe.popitem(last=False)
            else:
                break
        if key in self._dedupe:
            return True
        self._dedupe[key] = now
        if len(self._dedupe) > self._dedupe_max:
            self._dedupe.popitem(last=False)
        return False

    # ---------- кэш переводов ----------
    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()

    def _cache_get(self, message):
        with self._cache_lock:
            item = self._cache.get(message)
            if item is None:
                return None
            self._cache.move_to_end(message)
            return item

    def _cache_put(self, message, text, kept_words):
        with self._cache_lock:
            self._cache[message] = (text, list(kept_words))
            self._cache.move_to_end(message)
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)

    def _watch_logs(self):
        # Индекс терминов строим в фоне, чтобы не подвешивать окно.
        app_log.log(f"watcher: start, log_dir={self.log_dir}")
        self.guard.ensure_ready()
        if not os.path.exists(self.log_dir):
            app_log.log("watcher: папка логов не найдена, выход")
            return
        # Существующую историю не перечитываем — только новое.
        self.tailer.prime()
        app_log.log(f"watcher: файлов под наблюдением {len(self.tailer.files)}")
        total_lines = 0
        last_beat = time.time()
        while self.running:
            try:
                lines = self.tailer.poll()
                if lines:
                    total_lines += len(lines)
                    app_log.log(f"watcher: новых строк {len(lines)} "
                                f"(всего {total_lines})")
                for channel_name, line in lines:
                    self._parse_and_translate(line.strip(), channel_name)
            except Exception as exc:
                app_log.log(f"watcher: ошибка {exc!r}")
            # Раз в полминуты пишем, что живы и какое самое свежее изменение
            # в файлах — чтобы по логу было видно, пишет ли игра.
            if time.time() - last_beat > 30:
                last_beat = time.time()
                newest = max((state.mtime for state in self.tailer.files.values()),
                             default=0)
                stamp = time.strftime("%H:%M:%S", time.localtime(newest)) if newest else "-"
                app_log.log(f"watcher: жив, файлов {len(self.tailer.files)}, "
                            f"последнее изменение {stamp}")
            time.sleep(self.poll_interval)

    def _parse_and_translate(self, line, channel_name):
        if not line:
            return
        match = self.log_pattern.search(line)
        if not match:
            return

        time_str, sender, message = match.groups()
        time_only = time_str[-8:]
        sender = re.sub(r'<[^>]+>', '', sender).strip()

        is_emote = bool(self.emote_pattern.match(message))
        if is_emote:
            message = self.emote_pattern.sub("", message, count=1).strip()
        if not message:
            return

        # Одно и то же сообщение приходит в лог каждого запущенного клиента.
        # Время сообщения у всех одинаковое, поэтому точного ключа достаточно.
        if self._is_duplicate(channel_name, time_only, sender, message):
            return

        has_cn = bool(self.chinese_pattern.search(message))
        has_ru = bool(self.russian_pattern.search(message))
        has_en = bool(self.english_pattern.search(message))

        msg_data = {
            "header": self._chat_header(time_only, sender, is_emote),
            "original": message,
            "translation": ""
        }

        if not (has_cn or has_ru or has_en):
            self.ui_callback(channel_name, msg_data, [], "original")
            return

        if self.target_lang == "ru" and has_ru and not has_en and not has_cn:
            self.ui_callback(channel_name, msg_data, [], "original")
            return
        if self.target_lang == "en" and has_en and not has_ru and not has_cn:
            self.ui_callback(channel_name, msg_data, [], "original")
            return
        if self.target_lang == "zh" and has_cn and not has_ru and not has_en:
            self.ui_callback(channel_name, msg_data, [], "original")
            return

        self._enqueue(channel_name, time_only, sender, message, is_emote)

    @staticmethod
    def _chat_header(time_str, sender, is_emote):
        """Заголовок сообщения. Для emote — как в игре: «* Ник *»."""
        if is_emote:
            return f"[{time_str}] * {sender} *"
        return f"[{time_str}] {sender}:"

    def _translate_and_send(self, channel_name, time_str, sender, message,
                            is_emote=False):
        cached = self._cache_get(message)
        if cached is not None:
            text, kept = cached
            self.ui_callback(channel_name, {
                "header": self._chat_header(time_str, sender, is_emote),
                "original": message,
                "translation": text,
            }, list(kept), "translated")
            return

        # 1. Раскрываем сленг: gj -> good job. Делаем до защиты терминов,
        #    чтобы сокращение не ушло в модель как есть.
        expanded = self.slang.expand_text(message, self._source_lang(message))

        # 2. Прячем EVE-термины и «не переводимые» слова под [[N]].
        masked, replacements = self.guard.protect(expanded)

        # 3. Переводим. Если модель вместо текста пересказала инструкцию
        #    про метки — пробуем иначе, вплоть до оригинала.
        result = self._translate_safely(expanded, masked, replacements)

        if not self.running:
            return

        if result is None:
            # Совсем не вышло: показываем оригинал, лучше чем мусор.
            app_log.log("translate: все попытки плохие, показан оригинал")
            final_text, kept_words = message, []
            cacheable = False
        else:
            final_text, kept_words = result
            cacheable = True

        msg_data = {
            "header": self._chat_header(time_str, sender, is_emote),
            "original": message,
            "translation": final_text
        }
        if cacheable:
            self._cache_put(message, final_text, kept_words)
        self.ui_callback(channel_name, msg_data, kept_words, "translated")

    def _translate_safely(self, original, masked, replacements):
        """Перевод с защитой от «перевода инструкции» и потери меток.

        Возвращает (текст, сохранённые_слова) или None, если все
        попытки дали мусор."""
        attempts = ((False, None), (True, 0.0)) if replacements else ((False, None),)
        best = None

        for strict, temperature in attempts:
            answer = self._translate(
                masked if replacements else original,
                bool(replacements), strict=strict, temperature=temperature)
            if not answer or self._looks_like_instruction(answer):
                continue
            if replacements:
                text, missing = self.guard.restore(answer, replacements)
            else:
                text, missing = answer, []
            if self._looks_like_instruction(text):
                continue
            if not missing:
                return self._finish(text, replacements)
            if best is None or len(missing) < len(best[1]):
                best = (text, missing)

        if best is not None and len(best[1]) <= 1:
            # Потерялось одно название — дописываем его, как раньше.
            text = best[0].rstrip() + " [" + ", ".join(best[1]) + "]"
            return self._finish(text, replacements)

        # Метки не удержались: переводим без масок, но явно просим модель
        # не переводить названия — иначе она сделает «Феникс» из «Phoenix».
        plain = self._translate(original, False, keep_names=replacements)
        if plain and not self._looks_like_instruction(plain):
            return self._finish(plain, [])
        return None

    def _finish(self, text, replacements):
        text, extra = self.guard.localize(text)
        kept = []
        for name in list(replacements) + list(extra):
            if name and name not in kept:
                kept.append(name)
        return text, kept

    @staticmethod
    def _looks_like_instruction(text):
        """Модель иногда переводит подсказку про метки вместо сообщения."""
        if not text:
            return False
        low = text.lower()
        if any(marker in low for marker in LEAK_STRONG):
            return True
        # Слабые признаки поодиночке бывают и в обычном тексте
        # («метки», «токен»), поэтому требуем хотя бы два.
        return sum(1 for marker in LEAK_WEAK if marker in low) >= 2

    def _source_lang(self, text):
        if self.chinese_pattern.search(text):
            return "zh"
        if self.russian_pattern.search(text):
            return "ru"
        return "en"

    def reload_slang(self):
        """Перечитывает словарь (после правок в настройках)."""
        self.slang = load_slang()
        self.guard.set_extra_keep(self.slang.keep_terms())
        self.clear_cache()

    def set_terms_lang(self, lang):
        """Язык, на котором показывать названия EVE (en/ru/zh)."""
        lang = lang if lang in ("en", "ru", "zh") else "en"
        if lang == getattr(self, "terms_lang", None):
            return
        self.terms_lang = lang
        self.guard.set_display_lang(lang)
        self.clear_cache()

    def replay_history(self, channels, limit=5):
        """Показывает последние сообщения из указанных каналов."""
        try:
            lines = self.tailer.recent_lines(channels, limit=limit)
        except Exception as exc:
            app_log.log(f"history: ошибка {exc!r}")
            return 0
        count = 0
        for channel_name, line in lines:
            self._parse_and_translate(line.strip(), channel_name)
            count += 1
        app_log.log(f"history: показано строк {count} "
                    f"из каналов {list(channels)[:5]}")
        return count

    def translate_outgoing(self, text, target_lang="en"):
        """Перевод исходящего сообщения — напрямую, без словаря.

        Панель перевода не подставляет названия из EVE-словаря: модель
        переводит текст как есть, чтобы игрок сам решал, как писать ники
        и названия кораблей.
        """
        text = (text or "").strip()
        if not text:
            return ""
        lang_name = {"ru": "Russian", "en": "English",
                     "zh": "Chinese"}.get(target_lang, "English")
        prompt = self.system_prompt.replace("{target_lang}", lang_name)
        try:
            answer = self.backend.chat(
                [{"role": "system", "content": prompt},
                 {"role": "user", "content": text}],
                temperature=0.2, timeout=60)
        except Exception as exc:
            app_log.log(f"outgoing: ошибка перевода {exc!r}")
            return text
        if not answer or self._looks_like_instruction(answer):
            return text
        return answer.strip() or text

    def _placeholder_hint(self, strict=False):
        """Короткая английская инструкция: её меньше шансов перевести."""
        hint = ("\nKeep tokens like [[0]] and [[1]] exactly as they are: "
                "do not translate, replace or omit them.")
        if strict:
            hint += " Every token must be present in the output."
        return hint

    def _translate(self, text, has_placeholders=False,
                   strict=False, temperature=None, keep_names=None):
        if not text.strip():
            return ""

        lang_map = {"ru": "Russian", "en": "English", "zh": "Chinese"}
        target_name = lang_map.get(self.target_lang, "Russian")

        prompt = self.system_prompt.replace("{target_lang}", target_name)
        if has_placeholders:
            prompt += self._placeholder_hint(strict)
        if keep_names:
            names = []
            for name in keep_names:
                name = str(name).strip()
                if name and name not in names:
                    names.append(name)
            if names:
                prompt += ("\nKeep these names exactly as written, do not "
                           "translate or change them: " + ", ".join(names))

        try:
            return self.backend.chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                temperature=temperature,
            )
        except Exception:
            # Модель недоступна — показываем оригинал без перевода,
            # но не теряем сообщение.
            return text

    def stop(self):
        self.running = False
        try:
            self._jobs.put_nowait(self._job_sentinel)
        except queue.Full:
            pass
