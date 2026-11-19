"""Versioned, additive database migrations (SQLite PRAGMA user_version).

Rules: existing tables/records are never dropped or rewritten; every migration is idempotent and
runs in a transaction. Before the first pending migration on an existing database file,
init_db() saves an automatic backup in database/backups/.
"""
import os
import sqlite3
from datetime import datetime

KEEP_BACKUPS = 5
VERIFIED_ON = "2026-11-04"

EXTRA_CROPS = [
    ("Cotton", "Fibre crop grown mainly in the warm season.",
     "Temp 21-32 C, deep well-drained soil (black soil is ideal), pH 6.0-8.0.",
     "Use quality seed, keep fields weed-free and scout regularly for pests.",
     "Irrigate at flowering and boll formation; avoid waterlogging."),
    ("Sugarcane", "Long-duration sugar and jaggery crop.",
     "Temp 20-35 C, deep fertile soil, assured water supply, pH 6.5-7.5.",
     "Plant healthy setts, earth up and trash-mulch to conserve moisture.",
     "Needs frequent irrigation, especially during germination and tillering."),
    ("Groundnut", "Oilseed legume that suits light soils.",
     "Temp 25-30 C, well-drained sandy loam or red soil, pH 6.0-7.0.",
     "Keep soil loose around pegging and harvest when pods mature.",
     "Light irrigation at flowering and pod filling; avoid standing water."),
    ("Ragi", "Hardy finger-millet crop for dry regions.",
     "Temp 20-30 C, red or light soils, low to moderate rainfall, pH 5.0-8.2.",
     "Transplant seedlings or sow in lines and keep the field weed-free early on.",
     "Mostly rainfed; one or two protective irrigations in dry spells."),
    ("Chickpea", "Winter pulse crop (Bengal gram) that fixes nitrogen.",
     "Temp 15-25 C, well-drained black or loamy soil, pH 6.0-8.0.",
     "Sow on residual moisture and avoid excess nitrogen fertilizer.",
     "Needs very little water; irrigate lightly at flowering if the season is dry."),
]
BASE_IRRIGATION = {
    "Potato": "Light, frequent irrigation; keep soil evenly moist but never waterlogged.",
    "Tomato": "Water regularly and evenly; drip irrigation reduces leaf wetness and disease.",
    "Rice": "Keep fields flooded to a shallow depth during most growth stages; drain before harvest.",
    "Wheat": "Irrigate at crown root initiation, tillering, flowering and grain filling.",
    "Maize": "Avoid water stress at tasseling and silking; ensure good drainage.",
}
DISEASE_TEXT = {  # class_label -> (causes, treatment). General guidance only: no chemical names or doses.
    "Potato___Healthy": ("No disease detected on this leaf.",
        "No treatment is needed. Keep monitoring, use balanced nutrition and good field hygiene."),
    "Potato___Late_blight": (
        "Caused by the oomycete Phytophthora infestans. It spreads quickly in cool, wet, humid weather through spores "
        "carried by wind and water, and from infected tubers and crop debris.",
        "Remove and destroy badly infected plants and leaves (do not compost them), improve air flow and avoid overhead "
        "watering. Ask your local agriculture officer which approved fungicide, dose and timing suit your crop and region."),
    "Tomato___Healthy": ("No disease detected on this leaf.",
        "No treatment is needed. Keep monitoring, water at the base of the plant and keep spacing open."),
    "Tomato___Early_blight": (
        "Caused by the fungus Alternaria solani. It survives on crop debris and in the soil and spreads in warm, humid "
        "weather, mainly on older, stressed plants.",
        "Remove affected lower leaves, mulch the soil, avoid wetting the foliage and rotate crops. Ask your local "
        "agriculture officer which approved fungicide, dose and timing suit your crop and region."),
    "Tomato___Late_blight": (
        "Caused by Phytophthora infestans. It is favoured by cool, wet, humid weather and spreads rapidly between plants.",
        "Isolate or remove severely infected plants quickly, keep foliage dry and improve air flow. Contact your local "
        "agriculture officer promptly for approved treatment advice."),
}
SCHEMES_SEED = [
    ("PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)", "Income support",
     "Income support scheme of the Government of India for landholding farmer families.",
     "Landholding farmer families, subject to the exclusion criteria published on the official portal. e-KYC is mandatory.",
     "Rs 6,000 per year, paid in three equal instalments of Rs 2,000 every four months directly into the bank account "
     "(Direct Benefit Transfer).",
     "Aadhaar number (linked to the bank account), bank account details, land-holding records and a mobile number.",
     "Register on the PM-KISAN portal (Farmers Corner > New Farmer Registration), at a Common Service Centre, or through "
     "your local revenue or agriculture office. Complete e-KYC (Aadhaar OTP on the portal or biometric at a CSC) so that "
     "instalments are not held up.",
     "https://pmkisan.gov.in", "PM-KISAN portal / Department of Agriculture & Farmers Welfare", "https://pmkisan.gov.in"),
    ("PMFBY (Pradhan Mantri Fasal Bima Yojana)", "Crop insurance",
     "Crop insurance scheme that protects farmers against yield loss from natural calamities, pests and diseases.",
     "Farmers, including sharecroppers and tenant farmers who have the required documents, growing notified crops in "
     "notified areas, subject to scheme conditions.",
     "Insurance cover for crop loss from notified risks. The farmer pays a capped premium: up to 2% of the sum insured for "
     "Kharif food and oilseed crops, 1.5% for Rabi food and oilseed crops and 5% for annual commercial and horticultural "
     "crops. The rest of the premium is subsidised by the Central and State Governments.",
     "Typically: identity proof, bank account details, land record or tenancy proof, sowing details and a passport-size "
     "photograph. The exact list varies by state, so confirm it on the portal.",
     "Enrol before the notified cut-off date of the season through your bank, a Common Service Centre, an authorised "
     "insurance company or agent, or the PMFBY portal. Report crop loss within 72 hours through the channels shown on the portal.",
     "https://pmfby.gov.in", "PMFBY portal (Government of India)", "https://pmfby.gov.in"),
    ("Kisan Credit Card (KCC)", "Credit",
     "A credit facility that gives farmers timely, low-cost short-term credit for crop cultivation and related needs.",
     "Owner cultivators (individual or joint), tenant farmers, oral lessees and sharecroppers. Farmers in animal "
     "husbandry and fisheries can also be covered. The bank decides final eligibility.",
     "Revolving short-term credit for crop cultivation. Eligible crop loans can get an interest subvention, and prompt repayment "
     "can earn a further incentive; the scheme's commonly quoted effective rate for timely repayment is about 4% a year. "
     "The limit and rates are revised from time to time, so confirm the current figures with your bank.",
     "Typically: identity and address proof, land records or tenancy details, passport-size photographs and the bank's "
     "application form. Requirements vary by bank.",
     "Apply at a bank branch (commercial, regional rural or cooperative bank), or through the bank's online KCC "
     "application where available. The bank verifies eligibility and sanctions the limit.",
     "https://agriwelfare.gov.in", "Department of Agriculture & Farmers Welfare; RBI/NABARD guidelines", "https://agriwelfare.gov.in"),
    ("Soil Health Card Scheme", "Soil health",
     "Scheme that tests the soil of a farmer's land and issues a card with the soil's nutrient status and crop-wise "
     "fertiliser recommendations.",
     "All farmers. Soil sampling and the card are free; samples are collected through the state agriculture department.",
     "A free soil health card (paper and online) showing the nutrient status with colour-coded ratings, along with "
     "crop-wise recommendations on fertiliser use and soil amendments.",
     "Basic farmer details (name, village, district) and land details such as the survey number. Aadhaar or a mobile "
     "number helps in retrieving the card online.",
     "Ask your local agriculture office or Krishi Vigyan Kendra to collect a soil sample for testing at a soil testing "
     "laboratory. View or download the card on the Soil Health Card portal (Farmer's Corner).",
     "https://soilhealth.dac.gov.in", "Soil Health Card portal (Department of Agriculture & Farmers Welfare)",
     "https://soilhealth.dac.gov.in"),
]


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def _m1_farms_recommendations(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL, location TEXT NOT NULL, area_acres REAL, soil_type TEXT, water_source TEXT,
        main_crop TEXT, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        farm_id INTEGER REFERENCES farms(id) ON DELETE SET NULL,
        mode TEXT NOT NULL DEFAULT 'soil_test',
        soil_type TEXT, season TEXT, water_availability TEXT, location TEXT,
        nitrogen REAL, phosphorus REAL, potassium REAL, temperature REAL, humidity REAL, ph REAL, rainfall REAL,
        top_crop TEXT, top_score REAL, method TEXT, result_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def _m2_crop_knowledge(conn):
    if not _has_column(conn, "crops", "irrigation_advice"):
        conn.execute("ALTER TABLE crops ADD COLUMN irrigation_advice TEXT")
    for name, text in BASE_IRRIGATION.items():
        conn.execute("UPDATE crops SET irrigation_advice=? WHERE name=? AND (irrigation_advice IS NULL OR irrigation_advice='')",
                     (text, name))
    for row in EXTRA_CROPS:
        conn.execute("INSERT OR IGNORE INTO crops (name, description, suitable_conditions, cultivation_advice, "
                     "irrigation_advice) VALUES (?,?,?,?,?)", row)


def _m3_disease_details(conn):
    for col in ("causes", "treatment"):
        if not _has_column(conn, "diseases", col):
            conn.execute(f"ALTER TABLE diseases ADD COLUMN {col} TEXT")
    for label, (causes, treatment) in DISEASE_TEXT.items():
        conn.execute("UPDATE diseases SET causes=? WHERE class_label=? AND (causes IS NULL OR causes='')", (causes, label))
        conn.execute("UPDATE diseases SET treatment=? WHERE class_label=? AND (treatment IS NULL OR treatment='')",
                     (treatment, label))


def _m4_users_prefs_notifications(conn):
    if not _has_column(conn, "users", "last_login"):
        conn.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        language TEXT NOT NULL DEFAULT 'en',
        weather_place TEXT, weather_lat REAL, weather_lon REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL DEFAULT 'info', title TEXT NOT NULL, body TEXT, link TEXT,
        is_read INTEGER NOT NULL DEFAULT 0, dedupe_key TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, dedupe_key))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        role TEXT, action TEXT NOT NULL, detail TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS contact_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT NOT NULL, message TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def _m5_soil_irrigation_sensors(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS soil_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        farm_id INTEGER REFERENCES farms(id) ON DELETE SET NULL,
        crop TEXT, soil_type TEXT, nitrogen REAL, phosphorus REAL, potassium REAL, ph REAL,
        summary_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS irrigation_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        farm_id INTEGER REFERENCES farms(id) ON DELETE SET NULL,
        crop TEXT NOT NULL, soil_type TEXT, soil_moisture REAL, temperature REAL, humidity REAL, recent_rainfall REAL,
        status TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manual', summary_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, last_seen TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        soil_moisture REAL NOT NULL, temperature REAL, humidity REAL,
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def _m6_chat(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'en',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user','assistant')), content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def _m7_calendar(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS crop_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        farm_id INTEGER REFERENCES farms(id) ON DELETE SET NULL,
        crop TEXT NOT NULL, sowing_date TEXT NOT NULL, notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS calendar_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        plan_id INTEGER REFERENCES crop_plans(id) ON DELETE CASCADE,
        kind TEXT NOT NULL DEFAULT 'custom', title TEXT NOT NULL, description TEXT,
        start_date TEXT NOT NULL, end_date TEXT,
        is_estimate INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0, auto INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def _m8_schemes_market(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS schemes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, category TEXT, description TEXT, eligibility TEXT, benefits TEXT,
        documents TEXT, process TEXT, official_url TEXT, source_name TEXT, source_url TEXT, last_verified TEXT,
        is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for row in SCHEMES_SEED:
        conn.execute("INSERT OR IGNORE INTO schemes (name, category, description, eligibility, benefits, documents, "
                     "process, official_url, source_name, source_url, last_verified) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     row + (VERIFIED_ON,))
    conn.execute("""CREATE TABLE IF NOT EXISTS market_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT NOT NULL, district TEXT NOT NULL, market TEXT NOT NULL, commodity TEXT NOT NULL,
        variety TEXT NOT NULL DEFAULT '', grade TEXT, arrival_date TEXT NOT NULL,
        min_price REAL, max_price REAL, modal_price REAL,
        fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (state, district, market, commodity, variety, arrival_date))""")


def _m9_indexes(conn):
    for s in (
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_farms_user_name ON farms(user_id, name COLLATE NOCASE)",
        "CREATE INDEX IF NOT EXISTS idx_recs_user ON recommendations(user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_reports_user ON disease_reports(user_id, report_date)",
        "CREATE INDEX IF NOT EXISTS idx_reports_status ON disease_reports(status)",
        "CREATE INDEX IF NOT EXISTS idx_reports_crop ON disease_reports(crop_name)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_diseases_crop ON diseases(crop_id)",
        "CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read)",
        "CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_irrig_user ON irrigation_records(user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_sensor_user ON sensor_readings(user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_chatmsg_conv ON chat_messages(conversation_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_cal_user ON calendar_activities(user_id, start_date)",
        "CREATE INDEX IF NOT EXISTS idx_market_lookup ON market_prices(commodity, state, arrival_date)",
    ):
        conn.execute(s)


MIGRATIONS = [(1, _m1_farms_recommendations), (2, _m2_crop_knowledge), (3, _m3_disease_details),
              (4, _m4_users_prefs_notifications), (5, _m5_soil_irrigation_sensors), (6, _m6_chat),
              (7, _m7_calendar), (8, _m8_schemes_market), (9, _m9_indexes)]
LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def backup_database(conn, db_path):
    """Copy the live database to database/backups/ with SQLite's online backup API."""
    folder = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(db_path))[0]
    path = os.path.join(folder, f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_v{current_version(conn)}.db")
    dst = sqlite3.connect(path)
    try:
        conn.backup(dst)
    finally:
        dst.close()
    old = sorted(f for f in os.listdir(folder) if f.startswith(stem + "_") and f.endswith(".db"))
    for f in old[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(folder, f))
        except OSError:
            pass
    return path


def run_migrations(conn):
    """Apply pending migrations; returns the list of versions applied."""
    applied, current = [], current_version(conn)
    for version, fn in MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.execute("BEGIN")
            fn(conn)
            conn.execute(f"PRAGMA user_version = {int(version)}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append(version)
    return applied
