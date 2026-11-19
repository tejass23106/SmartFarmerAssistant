"""Weather via Open-Meteo (https://open-meteo.com): no API key needed, real data, 7-day forecast, city search.

All network failures become WeatherError with a message that is safe to show to the user.
Results are cached in memory (forecast 10 min, place search 24 h) to be polite to the free service.
"""
import re
import threading
import time

from utils.http import ApiError, request_json

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_TTL, PLACE_TTL = 600, 86400
PLACE_RE = re.compile(r"^[^\W_][\w\s,.'()\-]{1,79}$", re.UNICODE)

# WMO weather interpretation codes -> (description, bootstrap icon, wet?)
_CODES = {0: ("Clear sky", "sun", False), 1: ("Mainly clear", "sun", False), 2: ("Partly cloudy", "cloud-sun", False),
          3: ("Overcast", "clouds", False), 45: ("Fog", "cloud-fog", False), 48: ("Fog", "cloud-fog", False)}
for _c in (51, 53, 55, 56, 57):
    _CODES[_c] = ("Drizzle", "cloud-drizzle", True)
for _c in (61, 63, 65, 66, 67):
    _CODES[_c] = ("Rain", "cloud-rain", True)
for _c in (71, 73, 75, 77, 85, 86):
    _CODES[_c] = ("Snow", "snow", False)
for _c in (80, 81, 82):
    _CODES[_c] = ("Rain showers", "cloud-rain-heavy", True)
for _c in (95, 96, 99):
    _CODES[_c] = ("Thunderstorm", "cloud-lightning-rain", True)

_cache, _lock = {}, threading.Lock()


class WeatherError(Exception):
    """User-safe explanation of why weather could not be loaded."""


def describe(code):
    return _CODES.get(code, ("Unknown", "cloud", False))


def valid_place(text):
    return bool(text) and bool(PLACE_RE.match(text.strip()))


def _cached(key, ttl):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    return None


def _store(key, value):
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def clear_cache():
    with _lock:
        _cache.clear()


def search_places(query, count=5):
    """City/village search. Prefers India, falls back to a worldwide search. Returns a list of dicts."""
    q = (query or "").strip()
    if not valid_place(q):
        raise WeatherError("Please enter a valid place name.")
    key = ("place", q.lower())
    hit = _cached(key, PLACE_TTL)
    if hit is not None:
        return hit
    results = []
    try:
        for extra in ({"countryCode": "IN"}, {}):
            data = request_json(GEOCODE_URL, dict({"name": q, "count": count, "language": "en", "format": "json"}, **extra))
            results = data.get("results") or []
            if results:
                break
    except ApiError:
        raise WeatherError("Could not reach the weather service. Please check the internet connection and try again.")
    places = [{"name": r.get("name", q), "state": r.get("admin1", ""), "country": r.get("country", ""),
               "lat": r["latitude"], "lon": r["longitude"]} for r in results if "latitude" in r and "longitude" in r]
    return _store(key, places)


def place_label(p):
    return ", ".join(x for x in (p.get("name"), p.get("state"), p.get("country")) if x)


def get_forecast(lat, lon):
    """Current conditions + 7-day daily forecast for coordinates."""
    key = ("fc", round(float(lat), 2), round(float(lon), 2))
    hit = _cached(key, FORECAST_TTL)
    if hit is not None:
        return hit
    try:
        d = request_json(FORECAST_URL, {
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max"})
    except ApiError:
        raise WeatherError("The weather service is not available right now. Please try again later.")
    try:
        cur = d["current"]
        desc, icon, wet = describe(cur.get("weather_code"))
        current = {"temp": cur["temperature_2m"], "feels_like": cur.get("apparent_temperature", cur["temperature_2m"]),
                   "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m", 0),
                   "rain": cur.get("precipitation", 0) or 0, "description": desc, "icon": icon, "wet": wet,
                   "time": cur.get("time", "")}
        daily, dd = [], d["daily"]
        for i, day in enumerate(dd["time"]):
            ddesc, dicon, dwet = describe(dd["weather_code"][i])
            daily.append({"date": day, "max": dd["temperature_2m_max"][i], "min": dd["temperature_2m_min"][i],
                          "rain": dd["precipitation_sum"][i] or 0,
                          "rain_prob": (dd.get("precipitation_probability_max") or [None] * (i + 1))[i],
                          "wind": (dd.get("wind_speed_10m_max") or [0] * (i + 1))[i],
                          "description": ddesc, "icon": dicon, "wet": dwet})
    except (KeyError, IndexError, TypeError):
        raise WeatherError("The weather service sent incomplete data. Please try again later.")
    return _store(key, {"current": current, "daily": daily, "tips": farming_tips(current, daily)})


def farming_tips(current, daily):
    """General advisory as (translation key, params). Based on the numbers; never a guaranteed prediction."""
    tips = []
    rain_next = sum((x["rain"] or 0) for x in daily[:2])
    prob = max([x["rain_prob"] or 0 for x in daily[:2]] or [0])
    if rain_next >= 5 or prob >= 70:
        tips.append(("tip.rain_soon", {"mm": round(rain_next, 1), "prob": int(prob)}))
    if (current["temp"] or 0) >= 35 or (daily and (daily[0]["max"] or 0) >= 38):
        tips.append(("tip.heat", {"temp": round(max(current["temp"], daily[0]["max"] if daily else 0))}))
    if (current["humidity"] or 0) >= 85:
        tips.append(("tip.humid", {"rh": current["humidity"]}))
    if (current["wind"] or 0) >= 30:
        tips.append(("tip.wind", {"kmh": round(current["wind"])}))
    if (current["temp"] or 99) <= 8:
        tips.append(("tip.cold", {"temp": round(current["temp"])}))
    if not tips:
        tips.append(("tip.ok", {}))
    return tips


def rain_expected_mm(forecast, days=2):
    return round(sum((x["rain"] or 0) for x in forecast["daily"][:days]), 1)


def saved_place(conn, user_id):
    """The farmer's saved weather place as dict(name, lat, lon), or None."""
    row = conn.execute("SELECT weather_place, weather_lat, weather_lon FROM user_preferences WHERE user_id=?",
                       (user_id,)).fetchone()
    if row and row["weather_lat"] is not None and row["weather_lon"] is not None:
        return {"name": row["weather_place"] or "", "lat": row["weather_lat"], "lon": row["weather_lon"]}
    return None


def summary_for_user(conn, user_id):
    """Dict for dashboard/irrigation: {place, forecast} | {needs_location} | {error}. Never raises."""
    place = saved_place(conn, user_id)
    try:
        if not place:
            farm = conn.execute("SELECT location FROM farms WHERE user_id=? ORDER BY id LIMIT 1", (user_id,)).fetchone()
            loc = (farm["location"] if farm else None) or (conn.execute(
                "SELECT location FROM users WHERE id=?", (user_id,)).fetchone() or {"location": None})["location"]
            if not loc or not valid_place(loc):
                return {"needs_location": True}
            found = search_places(loc, 1)
            if not found:
                return {"needs_location": True}
            place = {"name": place_label(found[0]), "lat": found[0]["lat"], "lon": found[0]["lon"]}
        return {"place": place["name"], "forecast": get_forecast(place["lat"], place["lon"])}
    except WeatherError as exc:
        return {"error": str(exc)}
