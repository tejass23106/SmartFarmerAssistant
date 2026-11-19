"""Crop recommendation: Random Forest model if trained, otherwise a rule-based fallback."""
import os

import joblib

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crop_model.pkl")
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]

# (label, min allowed, max allowed)
LIMITS = {
    "N": ("Nitrogen (N)", 0, 300),
    "P": ("Phosphorus (P)", 0, 300),
    "K": ("Potassium (K)", 0, 300),
    "temperature": ("Temperature (°C)", -10, 60),
    "humidity": ("Humidity (%)", 0, 100),
    "ph": ("Soil pH", 0, 14),
    "rainfall": ("Rainfall (mm)", 0, 5000),
}

# Approximate ideal ranges (lo, hi) per feature: N, P, K, temp, humidity, ph, rainfall.
# These are simple illustrative ranges for demonstration, not agronomic prescriptions.
RULES = {
    "Potato": [(80, 120), (40, 80), (80, 120), (15, 22), (60, 85), (5.0, 6.5), (50, 150)],
    "Tomato": [(80, 120), (50, 80), (100, 150), (20, 27), (60, 80), (6.0, 6.8), (60, 120)],
    "Rice":   [(60, 100), (35, 60), (35, 60), (22, 30), (70, 90), (5.5, 7.0), (150, 300)],
    "Wheat":  [(80, 120), (40, 60), (30, 50), (12, 25), (50, 70), (6.0, 7.5), (50, 100)],
    "Maize":  [(60, 100), (35, 60), (20, 60), (21, 30), (55, 75), (5.8, 7.0), (60, 110)],
}

_model = None


def _load_model():
    global _model
    if _model is None:
        if os.path.exists(MODEL_PATH):
            try:
                _model = joblib.load(MODEL_PATH)
            except Exception:
                _model = False
        else:
            _model = False
    return _model or None


def validate_inputs(form):
    """Return (list_of_floats, error_message)."""
    values = []
    for key in FEATURES:
        label, lo, hi = LIMITS[key]
        raw = (form.get(key) or "").strip()
        if raw == "":
            return None, f"{label} is required."
        try:
            val = float(raw)
        except ValueError:
            return None, f"{label} must be a number."
        if not (lo <= val <= hi):
            return None, f"{label} must be between {lo} and {hi}."
        values.append(val)
    return values, None


def _rule_score(values, ranges):
    total = 0.0
    for v, (lo, hi) in zip(values, ranges):
        if lo <= v <= hi:
            total += 1.0
        else:
            dist = (lo - v) if v < lo else (v - hi)
            total += max(0.0, 1.0 - dist / (hi - lo))
    return total / len(ranges)


def recommend(values):
    """Return dict: crop, confidence (0-100), alternatives [(crop, pct)], method."""
    model = _load_model()
    if model is not None:
        try:
            proba = model.predict_proba([values])[0]
            order = proba.argsort()[::-1][:3]
            ranked = [(str(model.classes_[i]).title(), round(float(proba[i]) * 100, 1)) for i in order]
            return {"crop": ranked[0][0], "confidence": ranked[0][1],
                    "alternatives": ranked[1:], "method": "Machine learning (Random Forest)"}
        except Exception:
            pass  # fall through to rules if the model misbehaves

    ranked = sorted(((c, _rule_score(values, r) * 100) for c, r in RULES.items()),
                    key=lambda x: x[1], reverse=True)
    ranked = [(c, round(s, 1)) for c, s in ranked[:3]]
    return {"crop": ranked[0][0], "confidence": ranked[0][1],
            "alternatives": ranked[1:], "method": "Rule-based suitability score"}


def using_ml():
    """True when a trained crop_model.pkl was found and loaded (otherwise the rule-based fallback is used)."""
    return _load_model() is not None
