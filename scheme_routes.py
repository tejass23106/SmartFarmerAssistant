"""Government schemes (farmer information page + admin management), and contact messages (admin)."""
import sqlite3
from datetime import date

from flask import abort, flash, redirect, render_template, request, session, url_for

from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required

FIELDS = ("name", "category", "description", "eligibility", "benefits", "documents", "process",
          "official_url", "source_name", "source_url", "last_verified")
LIMITS = {"name": 120, "category": 60, "description": 800, "eligibility": 800, "benefits": 800, "documents": 800,
          "process": 1200, "official_url": 200, "source_name": 160, "source_url": 200}


def _valid_url(u):
    return u.startswith("https://") and " " not in u and len(u) > 12


def register(app):

    @app.route("/schemes")
    @role_required("farmer")
    def schemes_page():
        cat = request.args.get("category", "").strip()
        conn = get_db()
        try:
            cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM schemes WHERE is_active=1 AND category IS NOT NULL ORDER BY category")]
            if cat and cat in cats:
                rows = conn.execute("SELECT * FROM schemes WHERE is_active=1 AND category=? ORDER BY name", (cat,)).fetchall()
            else:
                cat = ""
                rows = conn.execute("SELECT * FROM schemes WHERE is_active=1 ORDER BY name").fetchall()
        finally:
            conn.close()
        return render_template("schemes.html", schemes=rows, categories=cats, category=cat)

    # ------------------------------------------------------------------ admin
    def _form_values(form):
        data = {f: form.get(f, "").strip() for f in FIELDS}
        return data

    def _validate(data):
        for f, lim in LIMITS.items():
            if len(data[f]) > lim:
                return "scheme.err_long"
        if not data["name"] or not data["description"]:
            return "scheme.err_required"
        if data["official_url"] and not _valid_url(data["official_url"]):
            return "scheme.err_url"
        if data["source_url"] and not _valid_url(data["source_url"]):
            return "scheme.err_url"
        if data["last_verified"]:
            try:
                date.fromisoformat(data["last_verified"])
            except ValueError:
                return "scheme.err_date"
        return None

    def _page(form=None, edit_row=None):
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM schemes ORDER BY name").fetchall()
        finally:
            conn.close()
        return render_template("admin/schemes.html", rows=rows, form=form or {}, edit=edit_row)

    @app.route("/admin/schemes")
    @role_required("admin")
    def admin_schemes():
        edit_id = request.args.get("edit", type=int)
        edit_row = None
        if edit_id:
            conn = get_db()
            try:
                edit_row = conn.execute("SELECT * FROM schemes WHERE id=?", (edit_id,)).fetchone()
            finally:
                conn.close()
            if not edit_row:
                flash("scheme.not_found", "danger")
        return _page(dict(edit_row) if edit_row else {}, edit_row)

    @app.route("/admin/schemes/save", methods=["POST"])
    @role_required("admin")
    def admin_scheme_save():
        sid = request.form.get("id", type=int)
        data = _form_values(request.form)
        error = _validate(data)
        if error:
            flash(error, "danger")
            return _page(data)
        conn = get_db()
        try:
            if sid:
                cur = conn.execute("UPDATE schemes SET name=?, category=?, description=?, eligibility=?, benefits=?, documents=?, "
                                   "process=?, official_url=?, source_name=?, source_url=?, last_verified=? WHERE id=?",
                                   tuple(data[f] or None for f in FIELDS) + (sid,))
                if not cur.rowcount:
                    flash("scheme.not_found", "danger")
                    conn.rollback()
                    return _page(data)
                flash("scheme.updated", "success")
            else:
                conn.execute("INSERT INTO schemes (name, category, description, eligibility, benefits, documents, process, "
                             "official_url, source_name, source_url, last_verified) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             tuple(data[f] or None for f in FIELDS))
                flash("scheme.added", "success")
            log_activity(conn, session["user_id"], "admin", "scheme_saved", data["name"])
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("scheme.duplicate", "danger")
            return _page(data)
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
            return _page(data)
        finally:
            conn.close()
        return redirect(url_for("admin_schemes"))

    @app.route("/admin/schemes/<int:sid>/toggle", methods=["POST"])
    @role_required("admin")
    def admin_scheme_toggle(sid):
        conn = get_db()
        try:
            cur = conn.execute("UPDATE schemes SET is_active = 1 - is_active WHERE id=?", (sid,))
            conn.commit()
            flash("scheme.toggled" if cur.rowcount else "scheme.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_schemes"))

    @app.route("/admin/schemes/<int:sid>/delete", methods=["POST"])
    @role_required("admin")
    def admin_scheme_delete(sid):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM schemes WHERE id=?", (sid,))
            conn.commit()
            flash("scheme.deleted" if cur.rowcount else "scheme.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_schemes"))

    @app.route("/admin/messages")
    @role_required("admin")
    def admin_messages():
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM contact_messages ORDER BY id DESC LIMIT 200").fetchall()
        finally:
            conn.close()
        return render_template("admin/messages.html", rows=rows)

    @app.route("/admin/messages/<int:mid>/toggle", methods=["POST"])
    @role_required("admin")
    def admin_message_toggle(mid):
        conn = get_db()
        try:
            cur = conn.execute("UPDATE contact_messages SET is_read = 1 - is_read WHERE id=?", (mid,))
            conn.commit()
            if not cur.rowcount:
                flash("scheme.not_found", "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_messages"))

    @app.route("/admin/messages/<int:mid>/delete", methods=["POST"])
    @role_required("admin")
    def admin_message_delete(mid):
        conn = get_db()
        try:
            conn.execute("DELETE FROM contact_messages WHERE id=?", (mid,))
            conn.commit()
            flash("msg.deleted", "success")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_messages"))
