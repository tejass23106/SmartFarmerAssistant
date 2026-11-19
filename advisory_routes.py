"""Crop advisory: farmer reading page and admin add/edit/delete."""
import sqlite3

from flask import render_template, request, redirect, url_for, flash

from utils.database import get_db
from utils.helpers import login_required, role_required

CATEGORIES = (
    "Crop Selection", "Soil Preparation", "Irrigation", "Fertilizer Basics",
    "Pest and Disease Prevention", "Weather Precautions", "Harvesting Basics",
)


def register(app):

    # ------------------------------------------------------------------ farmer
    @app.route("/advisory")
    @login_required
    def advisory():
        q = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()

        sql, params = "SELECT * FROM crop_advisories WHERE 1=1", []
        if q:
            sql += " AND (title LIKE ? OR content LIKE ?)"
            params += [f"%{q}%"] * 2
        if category in CATEGORIES:
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY id"

        conn = get_db()
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        grouped = {}
        for r in rows:
            grouped.setdefault(r["category"], []).append(r)
        order = [c for c in CATEGORIES if c in grouped] + [c for c in grouped if c not in CATEGORIES]
        groups = [(c, grouped[c]) for c in order]
        return render_template("advisory.html", groups=groups, q=q, category=category,
                               categories=CATEGORIES)

    # ------------------------------------------------------------------- admin
    def _page(form):
        q = request.args.get("q", "").strip()
        sql, params = "SELECT * FROM crop_advisories WHERE 1=1", []
        if q:
            sql += " AND (title LIKE ? OR content LIKE ? OR category LIKE ?)"
            params += [f"%{q}%"] * 3
        conn = get_db()
        rows = conn.execute(sql + " ORDER BY category, id", params).fetchall()
        conn.close()
        return render_template("admin/advisories.html", rows=rows, form=form, q=q,
                               categories=CATEGORIES)

    @app.route("/admin/advisories")
    @role_required("admin")
    def admin_advisories():
        form = {}
        edit = request.args.get("edit", type=int)
        if edit:
            conn = get_db()
            row = conn.execute("SELECT * FROM crop_advisories WHERE id=?", (edit,)).fetchone()
            conn.close()
            if row:
                form = dict(row)
            else:
                flash("Advisory not found.", "danger")
        return _page(form)

    @app.route("/admin/advisories/save", methods=["POST"])
    @role_required("admin")
    def admin_advisory_save():
        aid = request.form.get("id", type=int)
        category = request.form.get("category", "").strip()
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

        error = None
        if category not in CATEGORIES:
            error = "Please choose a valid category."
        elif not title:
            error = "Title is required."
        elif len(title) > 150:
            error = "Title is too long (maximum 150 characters)."
        elif not content:
            error = "Content is required."
        elif len(content) > 3000:
            error = "Content is too long (maximum 3000 characters)."
        if error:
            flash(error, "danger")
            return _page(request.form)

        conn = get_db()
        ok = True
        try:
            if aid:
                cur = conn.execute("UPDATE crop_advisories SET category=?, title=?, content=? WHERE id=?",
                                   (category, title, content, aid))
                if cur.rowcount == 0:
                    flash("Advisory not found.", "danger")
                    ok = False
                else:
                    flash("Advisory updated.", "success")
            else:
                conn.execute("INSERT INTO crop_advisories (category, title, content) VALUES (?,?,?)",
                             (category, title, content))
                flash("Advisory added.", "success")
            conn.commit()
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
            ok = False
        finally:
            conn.close()
        if not ok:
            return _page(request.form)
        return redirect(url_for("admin_advisories"))

    @app.route("/admin/advisories/<int:advisory_id>/delete", methods=["POST"])
    @role_required("admin")
    def admin_advisory_delete(advisory_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM crop_advisories WHERE id=?", (advisory_id,))
            conn.commit()
            flash("Advisory deleted." if cur.rowcount else "Advisory not found.",
                  "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_advisories"))
