"""Проверка обновлений через GitHub Releases.

Работает без токена: репозиторий должен быть публичным, иначе GitHub
вернёт 404. Ошибки сети не считаются критичными — приложение просто
молчит или показывает «не удалось проверить» при ручной проверке.
"""

import json
import re
import urllib.request

REPO = "psych3del1c/EVE-LangBridge"
RELEASES_URL = f"https://github.com/{REPO}/releases"
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
USER_AGENT = "EVE-LangBridge"

_VERSION_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([a-z]+)\.?(\d*))?$", re.IGNORECASE)
# Порядок предварительных версий: alpha < beta < rc < стабильная.
_PRE_RANK = {"alpha": 0, "beta": 1, "rc": 2}
_STABLE_RANK = 9


def parse_version(text):
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    major, minor, patch = (int(match.group(1)), int(match.group(2)),
                           int(match.group(3)))
    pre_name = (match.group(4) or "").lower()
    pre_num = int(match.group(5) or 0)
    if pre_name in _PRE_RANK:
        return (major, minor, patch, _PRE_RANK[pre_name], pre_num)
    if pre_name:
        return None
    return (major, minor, patch, _STABLE_RANK, 0)


def is_prerelease(text):
    return "-" in (text or "")


def fetch_releases(timeout=6.0):
    """Список вышедших релизов. Исключения — наверх."""
    request = urllib.request.Request(API_URL, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    releases = []
    for item in data or []:
        if item.get("draft"):
            continue
        tag = item.get("tag_name") or ""
        key = parse_version(tag)
        if key is None:
            continue
        releases.append({
            "version": tag.lstrip("vV"),
            "key": key,
            "url": item.get("html_url") or RELEASES_URL,
            "prerelease": bool(item.get("prerelease")) or is_prerelease(tag),
        })
    return releases


def check(current, timeout=6.0):
    """Самая новая подходящая версия или None.

    Пользователю на стабильной версии беты не предлагаем, тестерам
    на бете — предлагаем и беты, и стабильные.
    """
    releases = fetch_releases(timeout)
    current_key = parse_version(current) or (0, 0, 0, 0, 0)
    current_is_pre = is_prerelease(current)
    best = None
    for release in releases:
        if release["key"] <= current_key:
            continue
        if release["prerelease"] and not current_is_pre:
            continue
        if best is None or release["key"] > best["key"]:
            best = release
    return best
