"""Minimal message catalog. Add e.g. ``de.json`` with the same keys to support German."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DEFAULT_LANG = "en"


@lru_cache
def _catalog(lang: str) -> dict[str, str]:
    path = Path(__file__).with_name(f"{lang}.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def t(key: str, lang: str = DEFAULT_LANG, **params: object) -> str:
    text = _catalog(lang).get(key) or _catalog(DEFAULT_LANG).get(key) or key
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text
