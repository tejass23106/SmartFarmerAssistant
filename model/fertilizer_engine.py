"""Fertilizer guidance from soil-test values. Gives fertilizer TYPES, nutrient contents, application guidance and
precautions. It deliberately gives NO quantities: the dose must come from the farmer's Soil Health Card / state agriculture
department. Nutrient ratings follow the Soil Health Card standard (available N, P, K in kg/ha); pH classes are approximate."""

# (low if value < first, medium if <= second, otherwise high)
RATINGS = {"N": (280, 560), "P": (10, 25), "K": (120, 280)}
LIMITS = {"N": (0, 2000), "P": (0, 500), "K": (0, 3000), "ph": (0, 14)}
CROPS = ("Rice", "Wheat", "Maize", "Potato", "Tomato", "Cotton", "Sugarcane", "Groundnut", "Ragi", "Chickpea")
LEGUMES = ("Groundnut", "Chickpea")

# nutrient -> list of (fertilizer key, nutrient content text)
FERTILIZERS = {
    "N": [("urea", "46% N"), ("ammonium_sulphate", "21% N (+ sulphur)"), ("organic", "FYM / compost / vermicompost / green manure")],
    "P": [("ssp", "16% P2O5 (+ sulphur)"), ("dap", "18% N, 46% P2O5"), ("organic", "FYM / compost")],
    "K": [("mop", "60% K2O"), ("sop", "50% K2O (+ sulphur)")],
}
CHLORIDE_SENSITIVE = ("Potato",)


def classify(nutrient, value):
    lo, hi = RATINGS[nutrient]
    return "low" if value < lo else "medium" if value <= hi else "high"


def ph_class(ph):
    return "acidic" if ph < 6.5 else "neutral" if ph <= 7.5 else "alkaline"


def validate(form):
    vals = {}
    for key, (lo, hi) in LIMITS.items():
        raw = (form.get(key) or "").strip()
        try:
            v = float(raw)
        except ValueError:
            return None, "err.number"
        if not lo <= v <= hi:
            return None, "err.number"
        vals[key] = v
    return vals, None


def advise(crop, n, p, k, ph, soil=None):
    ratings = {"N": classify("N", n), "P": classify("P", p), "K": classify("K", k)}
    deficient = [x for x, r in ratings.items() if r == "low"]
    moderate = [x for x, r in ratings.items() if r == "medium"]
    fert = []
    for nutrient in deficient:
        for name, content in FERTILIZERS[nutrient]:
            if crop in LEGUMES and nutrient == "N" and name != "organic":
                continue              # legumes fix their own nitrogen
            if nutrient == "K" and name == "sop" and crop not in CHLORIDE_SENSITIVE:
                continue              # sulphate of potash is mainly for chloride-sensitive crops
            if nutrient == "K" and name == "mop" and crop in CHLORIDE_SENSITIVE:
                continue
            fert.append({"nutrient": nutrient, "name": name, "content": content})
    notes = ["fert.note.follow_card"]
    if crop in LEGUMES:
        notes.append("fert.note.legume")
    if crop == "Rice":
        notes.append("fert.note.rice")
    if crop in CHLORIDE_SENSITIVE:
        notes.append("fert.note.potato")
    pc = ph_class(ph)
    if pc == "acidic":
        notes.append("fert.note.acidic")
    elif pc == "alkaline":
        notes.append("fert.note.alkaline")
    if not deficient:
        notes.append("fert.note.no_deficiency")
    return {"ratings": ratings, "deficient": deficient, "moderate": moderate, "ph_class": pc,
            "fertilizers": fert, "notes": notes, "legume": crop in LEGUMES}
