"""Compiles tools/tr_*.py (DATA = {key: (english, kannada, hindi)}) into i18n/en.json, kn.json, hi.json.
Run: python tools/build_translations.py     (Kannada and Hindi were written for this project and should be
reviewed by a native speaker before a public release.)"""
import glob, importlib.util, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = {"en": {}, "kn": {}, "hi": {}}
for path in sorted(glob.glob(os.path.join(ROOT, "tools", "tr_*.py"))):
    spec = importlib.util.spec_from_file_location("trmod", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    for key, (en, kn, hi) in mod.DATA.items():
        for lang, text in (("en", en), ("kn", kn), ("hi", hi)):
            if key in out[lang]:
                raise SystemExit(f"duplicate key {key} in {path}")
            out[lang][key] = text
os.makedirs(os.path.join(ROOT, "i18n"), exist_ok=True)
for lang, data in out.items():
    with open(os.path.join(ROOT, "i18n", f"{lang}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
print({k: len(v) for k, v in out.items()}, "keys")
