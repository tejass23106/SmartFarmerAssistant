"""History: recommendations, disease diagnoses, irrigation and soil/fertilizer records in one place."""
import json
import sqlite3

from flask import abort, flash, redirect, render_template, request, session, url_for

from model.advisory_engine import related_crop_info
from utils.database import get_db
from utils.helpers import role_required

TABS = {"recommendations": "SELECT * FROM recommendations WHERE user_id=? ORDER BY id DESC LIMIT 100",
        "diagnoses": "SELECT * FROM predictions WHERE user_id=? ORDER BY id DESC LIMIT 100",
        "irrigation": "SELECT * FROM irrigation_records WHERE user_id=? ORDER BY id DESC LIMIT 100",
        "soil": "SELECT * FROM soil_records WHERE user_id=? ORDER BY id DESC LIMIT 100",
        "reports": "SELECT * FROM disease_reports WHERE user_id=? ORDER BY id DESC LIMIT 100"}
COUNT_SQL = {"recommendations": "recommendations", "diagnoses": "predictions", "irrigation": "irrigation_records",
             "soil": "soil_records", "reports": "disease_reports"}


def register(app):

    @app.route("/history")
    @role_required("farmer")
    def history():
        tab = request.args.get("tab", "recommendations")
        tab = tab if tab in TABS else "recommendations"
        uid, conn = session["user_id"], get_db()
        try:
            counts = {k: conn.execute(f"SELECT COUNT(*) c FROM {t} WHERE user_id=?", (uid,)).fetchone()["c"]
                      for k, t in COUNT_SQL.items()}
            rows = conn.execute(TABS[tab], (uid,)).fetchall()
        finally:
            conn.close()
        return render_template("history.html", tab=tab, rows=rows, counts=counts)

    @app.route("/recommendations/<int:rec_id>")
    @role_required("farmer")
    def recommendation_detail(rec_id):
        conn = get_db()
        try:
            rec = conn.execute("SELECT * FROM recommendations WHERE id=? AND user_id=?", (rec_id, session["user_id"])).fetchone()
            if not rec:
                abort(404)
            try:
                result = json.loads(rec["result_json"])
            except ValueError:
                result = {"inputs": {}, "top": [], "soil_test": None}
            info = related_crop_info(conn, result)
        finally:
            conn.close()
        return render_template("recommendation_detail.html", rec=rec, result=result, info=info)

    @app.route("/recommendations/<int:rec_id>/delete", methods=["POST"])
    @role_required("farmer")
    def recommendation_delete(rec_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM recommendations WHERE id=? AND user_id=?", (rec_id, session["user_id"]))
            conn.commit()
            flash("history.removed" if cur.rowcount else "history.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("history", tab="recommendations"))
