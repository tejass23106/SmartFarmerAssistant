"""Rule-based crop advisory from soil type, season and water availability.

This is NOT a trained model: each crop is scored with simple, general agronomic guidelines
(illustrative; not a substitute for a soil test or advice from an agricultural officer).
Soil-test values (N, P, K, temperature, humidity, pH, rainfall) are handled by model/crop_recommend.py.
"""
SOILS = ("Alluvial", "Black (Regur)", "Red", "Laterite", "Sandy", "Loamy", "Clay")
SEASONS = ("Kharif", "Rabi", "Zaid")
SEASON_HINTS = {"Kharif": "June-October", "Rabi": "October-March", "Zaid": "March-June"}
WATER_LEVELS = ("Low", "Medium", "High")
_LEVEL = {"Low": 1, "Medium": 2, "High": 3}

PROFILES = {  # soils: 1 = well suited, .6 = workable; seasons: 0..1; need: usual water requirement
    "Rice": dict(soils={"Alluvial": 1, "Clay": 1, "Loamy": .6, "Black (Regur)": .6}, seasons={"Kharif": 1, "Rabi": .5, "Zaid": .3}, need="High"),
    "Wheat": dict(soils={"Alluvial": 1, "Loamy": 1, "Black (Regur)": .6, "Clay": .6}, seasons={"Rabi": 1, "Kharif": .1, "Zaid": .2}, need="Medium"),
    "Maize": dict(soils={"Loamy": 1, "Red": 1, "Alluvial": 1, "Sandy": .6}, seasons={"Kharif": 1, "Rabi": .7, "Zaid": .6}, need="Medium"),
    "Potato": dict(soils={"Loamy": 1, "Sandy": .6, "Alluvial": 1}, seasons={"Rabi": 1, "Kharif": .3, "Zaid": .2}, need="Medium"),
    "Tomato": dict(soils={"Loamy": 1, "Red": 1, "Sandy": .6, "Alluvial": .6}, seasons={"Rabi": 1, "Kharif": .7, "Zaid": .6}, need="Medium"),
    "Cotton": dict(soils={"Black (Regur)": 1, "Alluvial": .6, "Red": .6}, seasons={"Kharif": 1, "Rabi": .2, "Zaid": .3}, need="Medium"),
    "Sugarcane": dict(soils={"Alluvial": 1, "Black (Regur)": 1, "Loamy": 1, "Clay": .6}, seasons={"Kharif": .8, "Zaid": .8, "Rabi": .6}, need="High"),
    "Groundnut": dict(soils={"Sandy": 1, "Red": 1, "Loamy": 1, "Laterite": .6}, seasons={"Kharif": 1, "Rabi": .6, "Zaid": .6}, need="Low"),
    "Ragi": dict(soils={"Red": 1, "Loamy": 1, "Laterite": 1, "Sandy": .6}, seasons={"Kharif": 1, "Rabi": .4, "Zaid": .3}, need="Low"),
    "Chickpea": dict(soils={"Black (Regur)": 1, "Loamy": 1, "Alluvial": .6, "Clay": .6}, seasons={"Rabi": 1, "Kharif": .1, "Zaid": .1}, need="Low"),
}
W_SEASON, W_SOIL, W_WATER = 0.40, 0.35, 0.25


def validate(soil, season, water):
    if soil not in SOILS:
        return "err.choose_soil"
    if season not in SEASONS:
        return "err.choose_season"
    if water not in WATER_LEVELS:
        return "err.choose_water"
    return None


def _water_fit(available, need):
    a, n = _LEVEL[available], _LEVEL[need]
    if a >= n:
        return 1.0 if a - n < 2 else 0.9
    return 0.5 if n - a == 1 else 0.15


def _reasons(p, soil, season, water):
    """Reasons as (translation key, params)."""
    s, q, fit = p["seasons"].get(season, 0), p["soils"].get(soil, 0), _water_fit(water, p["need"])
    return [("why.season_good" if s >= .9 else "why.season_ok" if s >= .4 else "why.season_bad", {"season": season}),
            ("why.soil_good" if q >= .9 else "why.soil_ok" if q > 0 else "why.soil_bad", {"soil": soil}),
            ("why.water_good" if fit >= .9 else "why.water_low" if fit >= .5 else "why.water_bad", {"need": p["need"]})]


def advise(soil, season, water, top=3):
    err = validate(soil, season, water)
    if err:
        raise ValueError(err)
    ranked = []
    for crop, p in PROFILES.items():
        score = 100 * (W_SEASON * p["seasons"].get(season, 0) + W_SOIL * p["soils"].get(soil, 0.2) +
                       W_WATER * _water_fit(water, p["need"]))
        ranked.append({"crop": crop, "score": round(score, 1), "reasons": _reasons(p, soil, season, water),
                       "water_need": p["need"]})
    ranked.sort(key=lambda r: (-r["score"], r["crop"]))
    return ranked[:top]


def related_crop_info(conn, payload):
    """Rows of the crops table for every crop named in a result payload (admin edits show up immediately)."""
    names = {t["crop"] for t in payload.get("top", [])}
    if payload.get("soil_test"):
        names.add(payload["soil_test"]["crop"])
    info = {}
    for n in names:
        row = conn.execute("SELECT * FROM crops WHERE LOWER(name)=LOWER(?)", (n,)).fetchone()
        info[n] = dict(row) if row else None
    return info
