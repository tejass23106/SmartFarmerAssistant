"""Fertilizer recommendation module (types and guidance only - no quantities)."""
import json
import sqlite3

from flask import flash, render_template, request, session

from model.advisory_engine import SOILS
from model.fertilizer_engine import CROPS, FERTILIZERS, LIMITS, RATINGS, advise, validate
from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required


def register(app):

    @app.route("/fertilizer", methods=["GET", "POST"])
    @role_required("farmer")
    def fertilizer_page():
        uid = session["user_id"]
        conn = get_db()
        try:
            farms = conn.execute("SELECT * FROM farms WHERE user_id=? ORDER BY name COLLATE NOCASE", (uid,)).fetchall()
            form, result = {}, None
            if request.method == "POST":
                form = request.form
                crop, soil, farm_id = form.get("crop", ""), form.get("soil_type", ""), form.get("farm_id", type=int)
                vals, error = validate(form)
                if crop not in CROPS:
                    error = "err.choose_crop"
                elif soil and soil not in SOILS:
                    error = "err.choose_soil"
                elif farm_id and not any(f["id"] == farm_id for f in farms):
                    error = "farm.not_found"
                if error:
                    flash(error, "danger")
                else:
                    result = dict(advise(crop, vals["N"], vals["P"], vals["K"], vals["ph"], soil or None),
                                  crop=crop, soil=soil, inputs=vals)
                    try:
                        conn.execute("INSERT INTO soil_records (user_id, farm_id, crop, soil_type, nitrogen, phosphorus, potassium, ph, "
                                     "summary_json) VALUES (?,?,?,?,?,?,?,?,?)",
                                     (uid, farm_id, crop, soil or None, vals["N"], vals["P"], vals["K"], vals["ph"],
                                      json.dumps({k: result[k] for k in ("ratings", "deficient", "ph_class")} |
                                                 {"fertilizers": [f["name"] for f in result["fertilizers"]]})))
                        log_activity(conn, uid, "farmer", "soil_check", crop)
                        conn.commit()
                    except sqlite3.Error:
                        conn.rollback()
                        flash("err.database", "danger")
        finally:
            conn.close()
        return render_template("fertilizer.html", farms=farms, crops=CROPS, soils=SOILS, form=form, result=result,
                               limits=LIMITS, ratings=RATINGS, fertilizers=FERTILIZERS)
