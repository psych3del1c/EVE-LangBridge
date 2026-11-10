"""
Сборка словаря EVE-терминов из официального SDE (jsonl).

Результат — eve_terms.json:
  {
    "meta":  {...},
    "map":    {"裂谷级": "Rifter", "Рифтер": "Rifter", ...},
    "keep_en": ["Jita", ...],
    "keep_ci": ["Rifter", "Small Shield Extender II", ...]
  }

map      — локализованное название -> английское (для замены в тексте).
keep_en  — английские названия, которые нельзя переводить, только с заглавной
           буквы (регионы, системы, одиночные названия предметов).
keep_ci  — корабли и многословные названия: защищаются в любом регистре,
           потому что игроки пишут "any astero fit", "wts rifter".

Запуск:  python build_terms.py
"""

import json
import os
import re
import sys
import collections

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_sde_dir():
    """Ищет папку SDE (eve-online-static-data-*) рядом со скриптом."""
    candidates = []
    try:
        for name in os.listdir(BASE_DIR):
            path = os.path.join(BASE_DIR, name)
            if name.startswith("eve-online-static-data") and os.path.isdir(path):
                candidates.append(path)
    except OSError:
        pass
    return sorted(candidates)[-1] if candidates else os.path.join(
        BASE_DIR, "eve-online-static-data-3670638-jsonl")


SDE_DIR = find_sde_dir()
OUT_FILE = os.path.join(BASE_DIR, "eve_terms.json")

# Языки клиента, названия из которых переводим обратно в английский.
# de/es/fr можно добавить, но там много коротких слов, совпадающих
# с обычными словами ("sol", "eau", "lien"), поэтому по умолчанию их нет.
LOCALES = ["zh", "ru", "ja", "ko"]

# Языки, на которые умеем показывать названия в переводе (настройка
# «Названия EVE»). Английский — это исходные имена, для него карта не нужна.
DISPLAY_LOCALES = ["ru", "zh"]

# Категории типов, которые имеют смысл в чате (корабли, модули, предметы...).
# 2 (Celestial) и 3 (Station) исключены: там слишком общие слова
# ("Планета", "Луна", "Офис"), которые нельзя слепо заменять.
TYPE_CATEGORIES = {
    4, 5, 6, 7, 8, 9, 10, 16, 17, 18, 20, 22, 23, 24, 25,
    30, 32, 34, 35, 39, 40, 41, 42, 43, 46, 49, 65, 66, 87, 91,
    2100, 2107, 2118, 2143,
}

# Категории, где одиночные английские слова — имена собственные
# (минералы, руда, товары и т.п.), а не обычные слова вроде "Shield".
KEEP_SINGLE_WORD_CATEGORIES = {4, 10, 17, 24, 25, 35, 42, 43}

# Скрипты без пробелов: для них нельзя использовать границы слов.
CJK_RANGES = (
    (0x3040, 0x30FF),   # хирагана, катакана
    (0x3400, 0x4DBF),   # CJK ext A
    (0x4E00, 0x9FFF),   # CJK
    (0xF900, 0xFAFF),   # CJK compatibility
)


def is_cjk(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


def is_cjk_string(text):
    return any(is_cjk(ch) for ch in text)


def load_jsonl(name):
    path = os.path.join(SDE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_groups():
    groups = {}
    for d in load_jsonl("groups.jsonl"):
        groups[d["_key"]] = d.get("categoryID")
    return groups


def _is_latin_only(text):
    """True, если в строке нет CJK, хангыля и кириллицы."""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
                0x3040 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7A3):
            return False
        low = ch.lower()
        if "а" <= low <= "я" or low == "ё":
            return False
    return True


def add_term(mapping, conflicts, key, en, priority, min_cjk_len=2):
    """Добавляет соответствие localized -> en с учётом приоритета."""
    key = key.strip()
    if not key or not en:
        return
    if key.lower() == en.lower():
        return
    # Латинские варианты названий из SDE — почти всегда дубликаты/мусор.
    # Английские имена собственные защищаются отдельно через keep_en.
    if _is_latin_only(key):
        return
    # Односимвольные CJK-названия ("水", "碳", "氧", ...) слишком часто
    # встречаются внутри обычных слов — пропускаем.
    if is_cjk_string(key) and len(key) < min_cjk_len:
        return
    folded = key.lower()
    old = mapping.get(folded)
    if old is None:
        mapping[folded] = en
    elif old != en:
        conflicts[(folded, en)] += 1


def add_variants(mapping, conflicts, loc, loc_name, en, category, priority,
                 min_cjk_len=2):
    """Дополнительные формы, которыми игроки обычно пишут названия."""
    # Китайские/японские корабли: "小鹰级" -> "小鹰".
    if category == 6 and loc in ("zh", "ja"):
        for suffix in ("级", "級"):
            if loc_name.endswith(suffix) and len(loc_name) > len(suffix) + 1:
                add_term(mapping, conflicts, loc_name[:-len(suffix)], en,
                         priority, min_cjk_len=min_cjk_len)
    # Названия с римской цифрой через пробел:
    #   "护盾扩展装置 II" -> "护盾扩展装置II" (без пробела)
    #   "护盾扩展装置 II" -> "护盾扩展装置" -> "Shield Extender" (без тира)
    m = re.match(r"^(.*\S)\s+(i{1,3}|iv|v|vi{0,3}|ix|x)$", loc_name, re.IGNORECASE)
    if m:
        add_term(mapping, conflicts, m.group(1) + m.group(2), en,
                 priority, min_cjk_len=min_cjk_len)
        # Обобщённое имя без тира имеет смысл только для модулей,
        # боеприпасов, дронов и истребителей.
        if category in (7, 8, 18, 87):
            en_base = re.sub(r"\s+(i{1,3}|iv|v|vi{0,3}|ix|x)$", "", en,
                             flags=re.IGNORECASE)
            if en_base != en:
                add_term(mapping, conflicts, m.group(1), en_base,
                         priority, min_cjk_len=min_cjk_len)


def add_display(en_to, en, names):
    """Обратная карта: английское имя -> локализованные формы для перевода."""
    en = (en or "").strip()
    if not en:
        return
    for loc in DISPLAY_LOCALES:
        loc_name = (names.get(loc) or "").strip()
        if loc_name and loc_name != en:
            en_to.setdefault(en, {})[loc] = loc_name


def add_keep(keep, name):
    name = (name or "").strip()
    if name and len(name) >= 2:
        keep.add(name)
def add_keep_ci(keep_ci, name):
    """Имена, которые защищаем в любом регистре (корабли и т.п.)."""
    name = (name or "").strip()
    if name and len(name) >= 2:
        keep_ci.add(name)


def main():
    if not os.path.isdir(SDE_DIR):
        print("SDE folder not found:", SDE_DIR)
        sys.exit(1)

    mapping = {}
    en_to = {}
    conflicts = collections.Counter()
    keep = set()
    keep_ci = set()
    stats = collections.Counter()

    # ---------- Системы, созвездия, регионы ----------
    for fn, kind, prio in (
        ("mapSolarSystems.jsonl", "system", 100),
        ("mapConstellations.jsonl", "constellation", 95),
        ("mapRegions.jsonl", "region", 90),
    ):
        for d in load_jsonl(fn):
            names = d.get("name", {})
            en = (names.get("en") or "").strip()
            if not en:
                continue
            add_keep(keep, en)
            add_display(en_to, en, names)
            for loc in LOCALES:
                loc_name = names.get(loc)
                if loc_name:
                    add_term(mapping, conflicts, loc_name, en, prio)
                    stats[kind] += 1

    # ---------- Фракции, корпорации, расы ----------
    for fn, kind, prio in (
        ("factions.jsonl", "faction", 85),
        ("npcCorporations.jsonl", "corporation", 80),
        ("races.jsonl", "race", 75),
        ("ancestries.jsonl", "ancestry", 70),
        ("bloodlines.jsonl", "bloodline", 65),
        ("landmarks.jsonl", "landmark", 60),
    ):
        for d in load_jsonl(fn):
            names = d.get("name", {})
            en = (names.get("en") or "").strip()
            if not en or en.startswith("#"):
                continue
            add_keep(keep, en)
            add_display(en_to, en, names)
            for loc in LOCALES:
                loc_name = names.get(loc)
                if loc_name:
                    add_term(mapping, conflicts, loc_name, en, prio)
                    stats[kind] += 1

    # ---------- Типы предметов ----------
    groups = build_groups()
    total_types = 0
    for d in load_jsonl("types.jsonl"):
        if not d.get("published"):
            continue
        names = d.get("name", {})
        en = (names.get("en") or "").strip()
        if not en or en.startswith("#"):
            continue
        cat = groups.get(d.get("groupID"))
        if cat not in TYPE_CATEGORIES:
            continue
        total_types += 1

        if cat == 6:  # корабли — игроки часто пишут их со строчной буквы: "any astero fit"
            add_keep_ci(keep_ci, en)
        elif " " in en:
            add_keep_ci(keep_ci, en)    # многословные названия предметов
        elif cat in KEEP_SINGLE_WORD_CATEGORIES:
            add_keep(keep, en)          # минералы, руда, товары

        add_display(en_to, en, names)

        # У товаров/планетарки много коротких общих слов ("报告", "垃圾"):
        # их требуем длиной от 3 символов, иначе страдает обычный текст.
        min_cjk = 3 if cat in (17, 42, 43) else 2

        for loc in LOCALES:
            loc_name = names.get(loc)
            if loc_name:
                add_term(mapping, conflicts, loc_name, en, 50,
                         min_cjk_len=min_cjk)
                add_variants(mapping, conflicts, loc, loc_name, en, cat, 50,
                             min_cjk_len=min_cjk)
                stats["type"] += 1

    sde_info = {}
    try:
        with open(os.path.join(SDE_DIR, "_sde.jsonl"), "r", encoding="utf-8") as f:
            sde_info = json.loads(f.readline())
    except Exception:
        pass

    meta = {
        "sde_dir": os.path.basename(SDE_DIR),
        "sde_build": sde_info.get("buildNumber"),
        "sde_date": sde_info.get("releaseDate"),
        "locales": LOCALES,
        "published_types": total_types,
        "map_entries": len(mapping),
        "en_to_entries": len(en_to),
        "keep_en_entries": len(keep),
        "keep_ci_entries": len(keep_ci),
        "conflicts": len(conflicts),
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "map": mapping, "en_to": en_to,
                   "keep_en": sorted(keep), "keep_ci": sorted(keep_ci)},
                  f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(OUT_FILE) / 1024 / 1024
    print("Saved:", OUT_FILE)
    print("Size: %.1f MB" % size_mb)
    for k, v in meta.items():
        print("  %-18s %s" % (k, v))
    print("  terms by kind:")
    for k, v in stats.most_common():
        print("    %-14s %d" % (k, v))
    if conflicts:
        print("Top conflicts (kept first):")
        for (key, en), n in conflicts.most_common(10):
            print("   ", repr(key), "->", repr(en), n)


if __name__ == "__main__":
    main()
