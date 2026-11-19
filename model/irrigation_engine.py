"""Rule-based irrigation guidance. NOT a controller: it only tells the farmer what to consider.

threshold = soil moisture (% of field capacity, as read by a sensor or estimated by the farmer) below which irrigation is
usually advisable for the crop; upper = level above which waterlogging is a concern. Values are general guidelines.
"""
PROFILES = {"Rice": (70, 100), "Wheat": (50, 90), "Maize": (50, 90), "Potato": (60, 85), "Tomato": (60, 85), "Cotton": (45, 90),
            "Sugarcane": (55, 95), "Groundnut": (45, 85), "Ragi": (40, 85), "Chickpea": (40, 80)}
SOIL_ADJ = {"Sandy": 5, "Red": 3, "Laterite": 3, "Loamy": 0, "Alluvial": 0, "Black (Regur)": -3, "Clay": -3}
STATUSES = ("required", "not_required", "monitor")
LIMITS = {"soil_moisture": (0, 100), "temperature": (-10, 60), "humidity": (0, 100), "recent_rainfall": (0, 500)}


def validate(form):
    """Returns (values dict, error_key)."""
    vals = {}
    for key, (lo, hi) in LIMITS.items():
        raw = (form.get(key) or "").strip()
        if raw == "":
            return None, "err.number"
        try:
            v = float(raw)
        except ValueError:
            return None, "err.number"
        if not lo <= v <= hi:
            return None, "err.number"
        vals[key] = v
    return vals, None


def evaluate(crop, soil, moisture, temp, humidity, rain_mm, forecast_rain_mm=None):
    base, upper = PROFILES[crop]
    thr = base + SOIL_ADJ.get(soil, 0)
    thr += 5 if temp >= 35 else 3 if temp >= 30 else 0
    thr += 3 if humidity < 40 else -3 if humidity >= 85 else 0
    thr = max(25, min(thr, upper - 10))
    rain_soon = (forecast_rain_mm or 0) >= 10

    if moisture >= upper:
        status, state = "not_required", "waterlogged"
    elif rain_mm >= 25 and moisture >= thr - 20:
        status, state = "not_required", "adequate"
    elif moisture < thr - 5:
        status = "monitor" if (rain_mm >= 10 or rain_soon) else "required"
        state = "dry"
    elif moisture <= thr + 10:
        status, state = "monitor", "adequate" if moisture >= thr else "low"
    else:
        status, state = "not_required", "adequate" if moisture < upper - 10 else "wet"

    if status == "required":
        timing = "early_morning_evening" if temp >= 30 else "morning"
    elif status == "monitor":
        timing = "recheck"
    else:
        timing = "not_now"

    sug = ["irr.sug.mulch", "irr.sug.no_midday"]
    if crop == "Rice":
        sug.append("irr.sug.rice")
    else:
        sug.append("irr.sug.no_waterlog")
    if soil == "Sandy":
        sug.append("irr.sug.sandy")
    elif soil in ("Clay", "Black (Regur)"):
        sug.append("irr.sug.clay")
    if crop in ("Tomato", "Potato", "Cotton", "Sugarcane", "Maize"):
        sug.append("irr.sug.drip")
    if rain_mm >= 10:
        sug.append("irr.sug.recent_rain")
    if rain_soon:
        sug.append("irr.sug.rain_forecast")
    if temp >= 35:
        sug.append("irr.sug.heat")
    return {"status": status, "moisture_state": state, "timing": timing, "threshold": round(thr),
            "upper": upper, "suggestions": sug, "forecast_rain": forecast_rain_mm}
