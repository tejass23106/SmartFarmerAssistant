"""Translation structure: one JSON file per language in i18n/ (en, kn, hi), keyed by dotted names.

Templates call t('nav.dashboard'); crop/disease/soil names use tn('crop', 'Rice'). A missing key falls back
to English, then to the key itself, so a missing translation never breaks a page.
"""
import json
import os
import re

I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n")
LANGS = {"en": "English", "kn": "ಕನ್ನಡ", "hi": "हिन्दी"}
SPEECH_LANG = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN"}
LANG_NAME_FOR_AI = {"en": "English", "kn": "Kannada", "hi": "Hindi"}
_cache = {}


def load(lang):
    if lang not in LANGS:
        lang = "en"
    if lang not in _cache:
        path = os.path.join(I18N_DIR, f"{lang}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _cache[lang] = json.load(f)
        except (OSError, ValueError):
            _cache[lang] = {}
    return _cache[lang]


def clear_cache():
    _cache.clear()


def translate(lang, key, **params):
    text = load(lang).get(key) or load("en").get(key) or key
    if params:
        try:
            text = text.format(**params)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def translate_name(lang, kind, name):
    """Translate a data value such as a crop name; unknown names are returned unchanged."""
    if not name:
        return name
    key = f"n.{kind}.{name}"
    return load(lang).get(key) or load("en").get(key) or name


def valid_lang(code):
    return code if code in LANGS else None


KEY_RE = re.compile(r"""\bt\(\s*['"]([a-zA-Z0-9_.]+)['"]""")
