import json
from functools import lru_cache
from pathlib import Path

SUPPORTED_LOCALES = {"es-ES", "en-US"}
DEFAULT_LOCALE = "es-ES"

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


@lru_cache(maxsize=None)
def load_catalog(locale: str) -> dict:
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE
    path = LOCALES_DIR / locale / "messages.json"
    if not path.exists():
        return {} if locale == DEFAULT_LOCALE else load_catalog(DEFAULT_LOCALE)
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def translate(key: str, locale: str, **kwargs) -> str:
    cat = load_catalog(locale)
    text = cat.get(key)
    if text is None:
        # Fallback: default → clave literal
        if locale != DEFAULT_LOCALE:
            text = load_catalog(DEFAULT_LOCALE).get(key, key)
        else:
            text = key
    try:
        return text.format(**kwargs)
    except Exception:
        return text
