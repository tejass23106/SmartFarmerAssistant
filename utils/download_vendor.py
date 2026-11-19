"""Download Bootstrap, Bootstrap Icons and Chart.js into static/vendor/ and point the templates at them.
Run once while connected to the internet:  python utils/download_vendor.py
"""
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "static", "vendor")
TEMPLATES = os.path.join(ROOT, "templates")
CDN = "https://cdn.jsdelivr.net/npm/"

# (url, local path inside static/vendor)
FILES = [
    (CDN + "bootstrap@5.3.3/dist/css/bootstrap.min.css", "bootstrap.min.css"),
    (CDN + "bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js", "bootstrap.bundle.min.js"),
    (CDN + "bootstrap-icons@1.11.3/font/bootstrap-icons.css", "bootstrap-icons.css"),
    (CDN + "bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2", "fonts/bootstrap-icons.woff2"),
    (CDN + "bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff", "fonts/bootstrap-icons.woff"),
    (CDN + "chart.js@4.4.3/dist/chart.umd.min.js", "chart.umd.min.js"),
]

# CDN URLs used in the templates -> local file
REPLACE = {url: local for url, local in FILES if not local.startswith("fonts/")}


def download():
    for url, local in FILES:
        dest = os.path.join(VENDOR, local)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        print("Downloading", url)
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            sys.exit(f"Download failed: {exc}\nCheck your internet connection and try again.")


def rewrite_templates():
    changed = 0
    for folder, _, names in os.walk(TEMPLATES):
        for name in names:
            if not name.endswith(".html"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            new = content
            for url, local in REPLACE.items():
                new = new.replace(url, "{{ url_for('static', filename='vendor/%s') }}" % local)
            if new != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
                changed += 1
                print("Updated", os.path.relpath(path, ROOT))
    return changed


if __name__ == "__main__":
    download()
    n = rewrite_templates()
    print(f"Done. {n} template(s) now use local files. Restart the app and hard-refresh (Ctrl+F5).")
