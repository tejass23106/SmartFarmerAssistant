"""Farm profiles: farmers save their farms (location, area, soil, water source, main crop)."""
import sqlite3

from flask import flash, redirect, render_template, request, session, url_for

from model.advisory_engine import SOILS
from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required

WATER_SOURCES = ("Rainfed", "Canal", "Borewell / Well", "Drip / Sprinkler", "River / Tank")
MAX_FARMS = 20


def _validate(form):
    name, location = form.get("name", "").strip(), form.get("location", "").strip()
    area_raw, soil = form.get("area_acres", "").strip(), form.get("soil_type", "").strip()
    water, crop, notes = form.get("water_source", "").strip(), form.get("main_crop", "").strip(), form.get("notes", "").strip()
    if not name:
        return None, "farm.err_name"
    if len(name) > 80:
        return None, "farm.err_name_long"
    if not location:
        return None, "farm.err_location"
    if len(location) > 120:
        return None, "farm.err_location_long"
    area = None
    if area_raw:
        try:
            area = float(area_raw)
        except ValueError:
            return None, "farm.err_area"
        if not (0 < area <= 100000):
            return None, "farm.err_area"
    if soil and soil not in SOILS:
        return None, "err.choose_soil"
    if water and water not in WATER_SOURCES:
        return None, "farm.err_water"
    if len(crop) > 60 or len(notes) > 500:
        return None, "farm.err_long"
    return dict(name=name, location=location, area=area, soil=soil or None, water=water or None,
                crop=crop or None, notes=notes or None), None


def register(app):

    def _page(form):
        conn = get_db()
        try:
            farms = conn.execute("SELECT * FROM farms WHERE user_id=? ORDER BY name COLLATE NOCASE", (session["user_id"],)).fetchall()
        finally:
            conn.close()
        return render_template("farms.html", farms=farms, form=form, soils=SOILS, water_sources=WATER_SOURCES)

    @app.route("/farms")
    @role_required("farmer")
    def farms():
        form, edit = {}, request.args.get("edit", type=int)
        if edit:
            conn = get_db()
            try:
                row = conn.execute("SELECT * FROM farms WHERE id=? AND user_id=?", (edit, session["user_id"])).fetchone()
            finally:
                conn.close()
            if row:
                form = dict(row)
            else:
                flash("farm.not_found", "danger")
        return _page(form)

    @app.route("/farms/save", methods=["POST"])
    @role_required("farmer")
    def farm_save():
        uid, fid = session["user_id"], request.form.get("id", type=int)
        data, error = _validate(request.form)
        if error:
            flash(error, "danger")
            return _page(request.form)
        conn, ok = get_db(), True
        try:
            if fid:
                cur = conn.execute("UPDATE farms SET name=?, location=?, area_acres=?, soil_type=?, water_source=?, "
                                   "main_crop=?, notes=? WHERE id=? AND user_id=?",
                                   (data["name"], data["location"], data["area"], data["soil"], data["water"],
                                    data["crop"], data["notes"], fid, uid))
                if cur.rowcount == 0:
                    flash("farm.not_found", "danger")
                    ok = False
                else:
                    flash("farm.updated", "success")
            elif conn.execute("SELECT COUNT(*) c FROM farms WHERE user_id=?", (uid,)).fetchone()["c"] >= MAX_FARMS:
                flash("farm.limit", "warning")
                ok = False
            else:
                conn.execute("INSERT INTO farms (user_id, name, location, area_acres, soil_type, water_source, main_crop, notes) "
                             "VALUES (?,?,?,?,?,?,?,?)", (uid, data["name"], data["location"], data["area"], data["soil"],
                                                          data["water"], data["crop"], data["notes"]))
                log_activity(conn, uid, "farmer", "farm_added", data["name"])
                flash("farm.added", "success")
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("farm.duplicate", "danger")
            ok = False
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
            ok = False
        finally:
            conn.close()
        return redirect(url_for("farms")) if ok else _page(request.form)

    @app.route("/farms/<int:farm_id>/delete", methods=["POST"])
    @role_required("farmer")
    def farm_delete(farm_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM farms WHERE id=? AND user_id=?", (farm_id, session["user_id"]))
            conn.commit()
            flash("farm.deleted" if cur.rowcount else "farm.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("farms"))
