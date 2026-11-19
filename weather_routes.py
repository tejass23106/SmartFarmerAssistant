"""Weather page: city search, farm locations, current conditions, 7-day forecast and advisory (Open-Meteo, no API key)."""
import sqlite3

from flask import flash, redirect, render_template, request, session, url_for

from utils import weather
from utils.database import get_db
from utils.helpers import role_required


def _float(value, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def register(app):

    @app.route("/weather")
    @role_required("farmer")
    def weather_page():
        uid = session["user_id"]
        conn = get_db()
        try:
            farms = conn.execute("SELECT name, location FROM farms WHERE user_id=? ORDER BY name COLLATE NOCASE", (uid,)).fetchall()
            saved = weather.saved_place(conn, uid)
        finally:
            conn.close()

        q = (request.args.get("q") or "").strip()
        lat, lon = _float(request.args.get("lat"), -90, 90), _float(request.args.get("lon"), -180, 180)
        name = (request.args.get("name") or "").strip()[:120]
        places, place, data, error = [], None, None, None
        try:
            if q:
                places = weather.search_places(q)
                if not places:
                    error = "wx.not_found"
                else:
                    p = places[0]
                    place = {"name": weather.place_label(p), "lat": p["lat"], "lon": p["lon"]}
            elif lat is not None and lon is not None:
                place = {"name": name or f"{lat:.2f}, {lon:.2f}", "lat": lat, "lon": lon}
            elif saved:
                place = saved
            if place and not error:
                data = weather.get_forecast(place["lat"], place["lon"])
        except weather.WeatherError as exc:
            error = str(exc)
        return render_template("weather.html", q=q, farms=farms, places=places, place=place, data=data, error=error,
                               saved=saved)

    @app.route("/weather/save", methods=["POST"])
    @role_required("farmer")
    def weather_save():
        lat, lon = _float(request.form.get("lat"), -90, 90), _float(request.form.get("lon"), -180, 180)
        name = (request.form.get("name") or "").strip()[:120]
        if lat is None or lon is None or not name:
            flash("wx.save_invalid", "danger")
            return redirect(url_for("weather_page"))
        conn = get_db()
        try:
            conn.execute("INSERT INTO user_preferences (user_id, weather_place, weather_lat, weather_lon) VALUES (?,?,?,?) "
                         "ON CONFLICT(user_id) DO UPDATE SET weather_place=excluded.weather_place, "
                         "weather_lat=excluded.weather_lat, weather_lon=excluded.weather_lon",
                         (session["user_id"], name, lat, lon))
            conn.commit()
            flash("wx.saved", "success")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("weather_page"))
