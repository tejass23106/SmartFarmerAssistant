"""In-app notifications for farmers."""
import sqlite3

from flask import flash, redirect, render_template, session, url_for

from utils.database import get_db
from utils.helpers import role_required


def register(app):

    @app.route("/notifications")
    @role_required("farmer")
    def notifications():
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100",
                                (session["user_id"],)).fetchall()
        finally:
            conn.close()
        return render_template("notifications.html", rows=rows)

    @app.route("/notifications/read-all", methods=["POST"])
    @role_required("farmer")
    def notifications_read_all():
        conn = get_db()
        try:
            conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session["user_id"],))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("notifications"))
