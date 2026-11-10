"""Словарь сленга: раскрытие сокращений до перевода.

Встроенный slang.json + пользовательский data/slang.user.json.
Пользовательские записи перекрывают встроенные, а `disabled`
отключает встроенную запись (в файле: "en:gj", "keep:o7").
"""

import json
import os
import re

import paths

LANGS = ("en", "ru", "zh")


def bundled_path():
    return paths.resource_path("slang.json")


def user_path():
    return os.path.join(paths.data_dir(), "slang.user.json")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_expand(bundled, user, disabled):
    expand = {lang: {} for lang in LANGS}
    for lang in LANGS:
        source = (bundled.get("expand") or {}).get(lang) or {}
        for key, value in source.items():
            if key and value:
                expand[lang][key] = value
    for token in disabled:
        lang, _, phrase = str(token).partition(":")
        phrase = phrase.strip().lower()
        if lang in expand and phrase:
            for key in [k for k in expand[lang] if k.lower() == phrase]:
                expand[lang].pop(key, None)
    for lang in LANGS:
        source = (user.get("expand") or {}).get(lang) or {}
        for key, value in source.items():
            if key and value:
                expand[lang][key] = value
    return expand


def _merge_keep(bundled, user, disabled):
    keep = []
    seen = set()
    for item in list(bundled.get("keep") or []) + list(user.get("keep") or []):
        text = str(item).strip()
        if not text or text.lower() in seen:
            continue
        if "keep:" + text.lower() in disabled:
            continue
        seen.add(text.lower())
        keep.append(text)
    return keep


def load_slang():
    bundled = _read(bundled_path())
    user = _read(user_path())
    disabled = {str(x).strip().lower() for x in (user.get("disabled") or [])}
    return SlangDictionary(_merge_expand(bundled, user, disabled),
                           _merge_keep(bundled, user, disabled))


def user_data():
    """Содержимое пользовательского файла (для редактора)."""
    data = _read(user_path())
    data.setdefault("expand", {lang: {} for lang in LANGS})
    data.setdefault("keep", [])
    data.setdefault("disabled", [])
    for lang in LANGS:
        data["expand"].setdefault(lang, {})
    return data


def save_user_data(data):
    path = user_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)


def ensure_user_file():
    """Создаёт пустой пользовательский файл, чтобы его можно было открыть."""
    if not os.path.exists(user_path()):
        save_user_data({"expand": {lang: {} for lang in LANGS},
                        "keep": [], "disabled": []})
    return user_path()


class SlangDictionary:
    """Раскрытие сокращений и список слов, которые не переводим."""

    def __init__(self, expand=None, keep=None):
        self.expand = {lang: dict((expand or {}).get(lang) or {})
                       for lang in LANGS}
        self.keep = [str(item) for item in (keep or []) if str(item).strip()]
        self._tables = {}
        self._patterns = {}
        for lang in LANGS:
            table = {key.lower(): value
                     for key, value in self.expand[lang].items()
                     if key and value}
            self._tables[lang] = table
            self._patterns[lang] = self._compile(table)

    @staticmethod
    def _compile(table):
        if not table:
            return None
        keys = sorted(table, key=len, reverse=True)
        alternatives = []
        for key in keys:
            words = [re.escape(part) for part in key.split()]
            alternatives.append(r"\s+".join(words))
        return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b",
                          re.IGNORECASE)

    def expand_text(self, text, lang="en"):
        """Раскрывает сокращения: сначала язык строки, затем английские."""
        if not text:
            return text
        order = ["en"]
        if lang in LANGS and lang != "en":
            order.insert(0, lang)
        for code in order:
            pattern = self._patterns.get(code)
            if pattern is None:
                continue
            table = self._tables[code]

            def replace(match, table=table):
                key = " ".join(match.group(0).lower().split())
                return table.get(key, match.group(0))

            text = pattern.sub(replace, text)
        return text

    def keep_terms(self):
        return list(self.keep)

    def entries(self):
        """[(язык, фраза, значение)] для таблицы в настройках."""
        rows = []
        for lang in LANGS:
            for phrase, value in sorted(self.expand[lang].items()):
                rows.append((lang, phrase, value))
        return rows
