import os
import re
import uuid
from functools import wraps

from flask import session, redirect, url_for, flash, request
from PIL import Image, ImageOps

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
ALLOWED_FORMATS = {"JPEG", "PNG"}
MAX_PIXELS = 40_000_000   # reject "decompression bomb" images
MAX_SIDE = 2048           # larger images are scaled down
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def safe_next(target):
    """Return `target` only if it is a local path (prevents open redirects after login)."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target


def crop_slug(name):
    """'Black Gram' -> 'black-gram' (used to find static/img/crops/<slug>.svg)."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _login_redirect():
    flash("Please log in to continue.", "warning")
    if request.method == "GET":
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    return redirect(url_for("login"))


def valid_email(email):
    return bool(EMAIL_RE.match(email or "")) and len(email) <= 120


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return _login_redirect()
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return _login_redirect()
            if session.get("role") != role:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def save_image(file_storage, upload_folder):
    """Validate, sanitise and save an uploaded image. Returns (filename, error).

    The image is decoded and re-encoded as a fresh JPEG with a random name, so
    any hidden data in the original file (scripts, metadata) is discarded.
    """
    if not file_storage or not file_storage.filename:
        return None, "Please choose an image file."
    name = file_storage.filename
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        return None, "Invalid file type. Only JPG, JPEG and PNG images are allowed."

    stream = file_storage.stream
    try:
        img = Image.open(stream)
        if img.format not in ALLOWED_FORMATS:
            return None, "The file content is not a valid JPG or PNG image."
        if img.width * img.height > MAX_PIXELS:
            return None, "The image dimensions are too large. Please upload a smaller photo."
        img.verify()
        stream.seek(0)
        img = Image.open(stream)
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        return None, "The uploaded file is not a valid image."

    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))

    filename = f"{uuid.uuid4().hex}.jpg"
    os.makedirs(upload_folder, exist_ok=True)
    try:
        img.save(os.path.join(upload_folder, filename), "JPEG", quality=90)
    except OSError:
        return None, "Could not save the image. Please try again."
    return filename, None
