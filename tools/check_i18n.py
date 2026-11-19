"""Lists translation keys used in templates/Python that are missing from i18n/en.json.

Only literal keys are checked. Keys built at run time (for example 'act.' + action or 'adv.f_' ~ key) are
checked by prefix: each prefix must have at least one real key. Run: python tools/check_i18n.py"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
en = json.load(open(os.path.join(ROOT, "i18n", "en.json"), encoding="utf-8"))

# t('key' ...) where the key is a literal (not followed by ~ which would mean a runtime prefix)
PAT_T = re.compile(r"""\bt\(\s*['"]([a-zA-Z0-9_.]+)['"](?!\s*~)""")
PAT_TN = re.compile(r"""\btn\(\s*['"](\w+)['"]\s*,\s*['"]([^'"]+)['"]""")
PREFIXES = ["adv.f_", "adv.mode_", "adv.water_", "chat.s", "fert.pre", "irr.src_", "landing.step"]

used = set()
files = (glob.glob(os.path.join(ROOT, "templates", "**", "*.html"), recursive=True)
         + glob.glob(os.path.join(ROOT, "*.py")) + glob.glob(os.path.join(ROOT, "utils", "*.py")))
for f in files:
    src = open(f, encoding="utf-8").read()
    used.update(PAT_T.findall(src))
    used.update(f"n.{kind}.{name}" for kind, name in PAT_TN.findall(src))

missing = sorted(k for k in used if not k.endswith(".") and k not in en and not k.startswith("n.") and "." in k)
# tn() names must exist in en.json too (crop/soil/season/water/disease/wsrc names)
missing += sorted(k for k in used if k.startswith("n.") and k not in en)
bad_prefixes = [p for p in PREFIXES if not any(k.startswith(p) for k in en)]
print(f"{len(used)} keys used; missing literal keys: {len(missing)}; prefixes without keys: {bad_prefixes or 'none'}")
for k in missing:
    print("  MISSING", k)
sys.exit(1 if (missing or bad_prefixes) else 0)
