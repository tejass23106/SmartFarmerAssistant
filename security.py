"""Security hardening: secret key, cookies, headers, login throttling,
session guard (deactivated users), password policy and password change page."""
import os
import secrets
import sqlite3
import threading
import time
from datetime import timedelta

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from utils.database import get_db
from utils.helpers import login_required

# ------------------------------------------------------------------ .env file
def load_dotenv(path):
    """Read KEY=VALUE lines from a .env file into os.environ (existing variables win). No extra dependency."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# ---------------------------------------------------------------- secret key
def load_secret_key(base_dir):
    """SECRET_KEY env var if set, otherwise a random key created once and stored in database/.secret_key."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(base_dir, "database", ".secret_key")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


# ------------------------------------------------------------ password policy
COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwerty123",
    "qwertyuiop", "iloveyou1", "admin123", "admin1234", "welcome1", "welcome123", "abc12345",
    "letmein123", "farmer123", "11111111", "00000000",
}


def password_error(pw):
    """Return an error message, or None if the password is acceptable."""
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 128:
        return "Password is too long (maximum 128 characters)."
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return "Password must contain at least one letter and one number."
    if pw.lower() in COMMON_PASSWORDS:
        return "That password is too common. Please choose a less predictable one."
    return None


# ------------------------------------------------------------ login throttling
MAX_FAILS = 5          # per email+IP (or per user for password changes)
MAX_FAILS_IP = 20      # per IP address
WINDOW = 15 * 60       # failures older than this are forgotten
LOCK_TIME = 15 * 60

_lock = threading.Lock()
_fails = {}            # key -> [timestamps]
_locked = {}           # key -> locked-until timestamp


def locked_seconds(*keys):
    """Seconds remaining on the longest active lock among the keys (0 = not locked)."""
    now = time.time()
    remaining = 0.0
    with _lock:
        for k in keys:
            until = _locked.get(k)
            if until is None:
                continue
            if until > now:
                remaining = max(remaining, until - now)
            else:
                del _locked[k]
    return int(remaining) + 1 if remaining else 0


def record_failure(key, limit=MAX_FAILS):
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(key, []) if now - t < WINDOW]
        recent.append(now)
        if len(recent) >= limit:
            _locked[key] = now + LOCK_TIME
            recent = []
        _fails[key] = recent


def clear_failures(key):
    with _lock:
        _fails.pop(key, None)
        _locked.pop(key, None)


# ------------------------------------------------------------ headers / policy
CSP = "; ".join([
    "default-src 'self'",
    # inline scripts are used by the chart/preview snippets in the templates
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "font-src 'self' https://cdn.jsdelivr.net data:",
    "img-src 'self' data: blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def register(app):
    app.config.update(
        SESSION_COOKIE_NAME="sfa_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("HTTPS_ONLY") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        TEMPLATES_AUTO_RELOAD=True,
    )

    @app.before_request
    def verify_session_user():
        """Log out users who were deleted/deactivated; keep name and role in sync with the database."""
        if request.endpoint in (None, "static") or "user_id" not in session:
            return None
        conn = get_db()
        try:
            row = conn.execute("SELECT full_name, role, is_active FROM users WHERE id=?",
                               (session["user_id"],)).fetchone()
        except sqlite3.Error:
            return None   # do not lock everyone out because of a temporary database problem
        finally:
            conn.close()
        if not row or not row["is_active"]:
            session.clear()
            flash("Your session has ended. Please log in again.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != row["role"]:
            session["role"] = row["role"]
        if session.get("name") != row["full_name"]:
            session["name"] = row["full_name"]
        return None

    @app.after_request
    def add_security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if "user_id" in session and request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"   # no cached private pages after logout
        return resp

    # ------------------------------------------------------- change password
    @app.route("/account/password", methods=["GET", "POST"])
    @login_required
    def change_password():
        uid = session["user_id"]
        key = f"pw:{uid}"
        if request.method == "POST":
            wait = locked_seconds(key)
            if wait:
                flash(f"Too many incorrect attempts. Please try again in {-(-wait // 60)} minute(s).", "danger")
                return render_template("change_password.html"), 429

            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            conn = get_db()
            try:
                user = conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
                strength = password_error(new)
                error = None
                if not user or not check_password_hash(user["password_hash"], current):
                    record_failure(key)
                    error = "Current password is incorrect."
                elif strength:
                    error = strength
                elif new != confirm:
                    error = "New passwords do not match."
                elif new == current:
                    error = "The new password must be different from the current one."

                if error:
                    flash(error, "danger")
                else:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (generate_password_hash(new), uid))
                    conn.commit()
                    clear_failures(key)
                    session.pop("default_pw", None)
                    flash("Password changed successfully.", "success")
                    return redirect(url_for("home"))
            except sqlite3.Error:
                flash("Database error. Please try again.", "danger")
            finally:
                conn.close()
        return render_template("change_password.html")
