"""Public pages and shared endpoints: language switch, contact form, about/services anchors."""
import sqlite3
import time
from urllib.parse import urlparse

from flask import abort, flash, redirect, render_template, request, session, url_for

from utils.database import get_db
from utils.helpers import safe_next, valid_email
from utils.i18n import LANGS

_contact_hits = {}   # ip -> [timestamps]; in memory, resets on restart


def register(app):

    @app.route("/language/<code>")
    def set_language(code):
        if code not in LANGS:
            abort(404)
        session["lang"] = code
        if "user_id" in session:
            conn = get_db()
            try:
                conn.execute("INSERT INTO user_preferences (user_id, language) VALUES (?, ?) "
                             "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language", (session["user_id"], code))
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
            finally:
                conn.close()
        ref = request.referrer
        target = safe_next(request.args.get("next")) or (ref if ref and urlparse(ref).netloc == request.host else None) \
            or url_for("home")
        resp = redirect(target)
        resp.set_cookie("lang", code, max_age=365 * 24 * 3600, samesite="Lax", httponly=True)
        return resp

    @app.route("/contact", methods=["POST"])
    def contact():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        message = request.form.get("message", "").strip()
        ip, now = request.remote_addr or "?", time.time()
        hits = [t for t in _contact_hits.get(ip, []) if now - t < 600]
        error = None
        if len(hits) >= 3:
            error = "contact.err_rate"
        elif not name or len(name) > 80:
            error = "contact.err_name"
        elif not valid_email(email):
            error = "contact.err_email"
        elif not (10 <= len(message) <= 1000):
            error = "contact.err_message"
        if error:
            flash(error, "danger")
        else:
            conn = get_db()
            try:
                conn.execute("INSERT INTO contact_messages (name, email, message) VALUES (?,?,?)", (name, email, message))
                conn.commit()
                hits.append(now)
                flash("contact.thanks", "success")
            except sqlite3.Error:
                conn.rollback()
                flash("err.database", "danger")
            finally:
                conn.close()
        _contact_hits[ip] = hits
        return redirect(url_for("home") + "#contact")
