"""Smart irrigation guidance + sensor devices (ESP32/Arduino can POST soil-moisture readings to /api/sensor-readings).

The module only gives advice. It does not control any pump or valve; no hardware control is implemented."""
import hashlib
import json
import secrets
import sqlite3
import time

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from model.advisory_engine import SOILS
from model.irrigation_engine import LIMITS, PROFILES, evaluate, validate
from utils import weather
from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required

MIN_SECONDS_BETWEEN_READINGS = 5
_last_seen = {}      # device_id -> timestamp (in memory)


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register(app):

    def _latest_sensor(conn, uid):
        return conn.execute("SELECT r.*, d.name device_name FROM sensor_readings r JOIN devices d ON d.id=r.device_id "
                            "WHERE r.user_id=? ORDER BY r.id DESC LIMIT 1", (uid,)).fetchone()

    @app.route("/irrigation", methods=["GET", "POST"])
    @role_required("farmer")
    def irrigation_page():
        uid = session["user_id"]
        conn = get_db()
        try:
            farms = conn.execute("SELECT * FROM farms WHERE user_id=? ORDER BY name COLLATE NOCASE", (uid,)).fetchall()
            sensor = _latest_sensor(conn, uid)
            form, result = {}, None
            if request.method == "POST":
                form = request.form
                crop, soil = form.get("crop", ""), form.get("soil_type", "")
                farm_id = form.get("farm_id", type=int)
                use_sensor = form.get("use_sensor") == "1" and sensor is not None
                vals, error = validate(form if not use_sensor else dict(form, soil_moisture=str(sensor["soil_moisture"]),
                                       temperature=str(sensor["temperature"] if sensor["temperature"] is not None else form.get("temperature", "")),
                                       humidity=str(sensor["humidity"] if sensor["humidity"] is not None else form.get("humidity", ""))))
                if crop not in PROFILES:
                    error = "err.choose_crop"
                elif soil not in SOILS:
                    error = "err.choose_soil"
                elif farm_id and not any(f["id"] == farm_id for f in farms):
                    error = "farm.not_found"
                if error:
                    flash(error, "danger")
                else:
                    forecast_rain, wx_note = None, None
                    wx = weather.summary_for_user(conn, uid)
                    if wx and wx.get("forecast"):
                        forecast_rain = weather.rain_expected_mm(wx["forecast"])
                    r = evaluate(crop, soil, vals["soil_moisture"], vals["temperature"], vals["humidity"],
                                 vals["recent_rainfall"], forecast_rain)
                    result = dict(r, crop=crop, soil=soil, inputs=vals, source="sensor" if use_sensor else "manual",
                                  sensor_time=sensor["recorded_at"] if use_sensor else None)
                    try:
                        conn.execute("INSERT INTO irrigation_records (user_id, farm_id, crop, soil_type, soil_moisture, temperature, "
                                     "humidity, recent_rainfall, status, source, summary_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                     (uid, farm_id, crop, soil, vals["soil_moisture"], vals["temperature"], vals["humidity"],
                                      vals["recent_rainfall"], r["status"], result["source"], json.dumps(r)))
                        log_activity(conn, uid, "farmer", "irrigation", f"{crop}: {r['status']}")
                        conn.commit()
                    except sqlite3.Error:
                        conn.rollback()
                        flash("err.database", "danger")
            recent = conn.execute("SELECT * FROM irrigation_records WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        finally:
            conn.close()
        return render_template("irrigation.html", farms=farms, crops=list(PROFILES), soils=SOILS, form=form, result=result,
                               sensor=sensor, recent=recent, limits=LIMITS)

    # ------------------------------------------------------------------ devices (farmer)
    @app.route("/devices", methods=["GET", "POST"])
    @role_required("farmer")
    def devices_page():
        uid, new_token = session["user_id"], None
        conn = get_db()
        try:
            if request.method == "POST":
                name = request.form.get("name", "").strip()
                if not name or len(name) > 60:
                    flash("dev.err_name", "danger")
                elif conn.execute("SELECT COUNT(*) c FROM devices WHERE user_id=?", (uid,)).fetchone()["c"] >= 10:
                    flash("dev.err_limit", "warning")
                else:
                    new_token = secrets.token_urlsafe(24)
                    conn.execute("INSERT INTO devices (user_id, name, token_hash) VALUES (?,?,?)", (uid, name, _hash(new_token)))
                    log_activity(conn, uid, "farmer", "device_added", name)
                    conn.commit()
                    flash("dev.added", "success")
            devices = conn.execute(
                "SELECT d.*, (SELECT soil_moisture FROM sensor_readings r WHERE r.device_id=d.id ORDER BY r.id DESC LIMIT 1) last_moisture "
                "FROM devices d WHERE d.user_id=? ORDER BY d.id DESC", (uid,)).fetchall()
            readings = conn.execute("SELECT r.*, d.name device_name FROM sensor_readings r JOIN devices d ON d.id=r.device_id "
                                    "WHERE r.user_id=? ORDER BY r.id DESC LIMIT 10", (uid,)).fetchall()
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
            devices, readings = [], []
        finally:
            conn.close()
        return render_template("devices.html", devices=devices, readings=readings, new_token=new_token,
                               endpoint=request.host_url.rstrip("/") + url_for("sensor_ingest"))

    @app.route("/devices/<int:device_id>/delete", methods=["POST"])
    @role_required("farmer")
    def device_delete(device_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM devices WHERE id=? AND user_id=?", (device_id, session["user_id"]))
            conn.commit()
            flash("dev.deleted" if cur.rowcount else "dev.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("devices_page"))

    # ------------------------------------------------------------------ device API (no session, no CSRF: key-authenticated)
    @app.route("/api/sensor-readings", methods=["POST"])
    def sensor_ingest():
        key = request.headers.get("X-Device-Key", "").strip()
        if not key:
            return jsonify(ok=False, error="missing X-Device-Key header"), 401
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(ok=False, error="send a JSON object"), 400
        try:
            moisture = float(body["soil_moisture"])
            temp = float(body["temperature"]) if body.get("temperature") is not None else None
            hum = float(body["humidity"]) if body.get("humidity") is not None else None
        except (KeyError, TypeError, ValueError):
            return jsonify(ok=False, error="soil_moisture (0-100) is required; temperature and humidity must be numbers"), 400
        if not 0 <= moisture <= 100 or (temp is not None and not -40 <= temp <= 80) or (hum is not None and not 0 <= hum <= 100):
            return jsonify(ok=False, error="value out of range"), 400
        conn = get_db()
        try:
            dev = conn.execute("SELECT id, user_id FROM devices WHERE token_hash=?", (_hash(key),)).fetchone()
            if not dev:
                return jsonify(ok=False, error="unknown device key"), 401
            now = time.time()
            if now - _last_seen.get(dev["id"], 0) < MIN_SECONDS_BETWEEN_READINGS:
                return jsonify(ok=False, error="too many readings; wait a few seconds"), 429
            _last_seen[dev["id"]] = now
            conn.execute("INSERT INTO sensor_readings (device_id, user_id, soil_moisture, temperature, humidity) VALUES (?,?,?,?,?)",
                         (dev["id"], dev["user_id"], moisture, temp, hum))
            conn.execute("UPDATE devices SET last_seen=CURRENT_TIMESTAMP WHERE id=?", (dev["id"],))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            return jsonify(ok=False, error="database error"), 500
        finally:
            conn.close()
        return jsonify(ok=True)
