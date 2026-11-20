import os
import sqlite3
import turso_serverless
from werkzeug.security import generate_password_hash

from utils.migrations import LATEST_VERSION, backup_database, current_version, run_migrations

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "smart_farmer.db")

# Default admin (change the password after first login!)
DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@smartfarmer.com")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'farmer' CHECK (role IN ('farmer','admin')),
    phone TEXT,
    location TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    suitable_conditions TEXT,
    cultivation_advice TEXT
);

CREATE TABLE IF NOT EXISTS diseases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop_id INTEGER REFERENCES crops(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    class_label TEXT NOT NULL UNIQUE,
    description TEXT,
    symptoms TEXT,
    prevention TEXT,
    management TEXT
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    crop_name TEXT,
    disease_name TEXT,
    confidence REAL,
    image_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS disease_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prediction_id INTEGER REFERENCES predictions(id) ON DELETE SET NULL,
    crop_name TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    image_path TEXT,
    location TEXT,
    description TEXT,
    report_date TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending','Reviewed','Resolved'))
);

CREATE TABLE IF NOT EXISTS crop_advisories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CROPS = [
    ("Potato", "Cool-season tuber crop.", "Temp 15-20 C, well-drained loamy soil, pH 5.0-6.5.",
     "Plant certified seed tubers, earth up regularly, avoid waterlogging."),
    ("Tomato", "Warm-season fruiting vegetable.", "Temp 20-27 C, fertile well-drained soil, pH 6.0-6.8.",
     "Stake plants, water evenly, rotate crops each season."),
    ("Rice", "Staple cereal grown in warm, wet conditions.", "Temp 22-30 C, high rainfall or irrigation, pH 5.5-7.0.",
     "Maintain standing water during growth, transplant healthy seedlings."),
    ("Wheat", "Cool-season staple cereal.", "Temp 12-25 C, moderate rainfall, pH 6.0-7.5.",
     "Sow at the right time, ensure timely irrigation at critical stages."),
    ("Maize", "Versatile cereal and fodder crop.", "Temp 21-30 C, well-drained fertile soil, pH 5.8-7.0.",
     "Provide adequate spacing and balanced nutrition."),
]

DISEASES = [
    ("Potato", "Healthy", "Potato___Healthy", "The leaf shows no visible signs of disease.",
     "Uniform green colour, no spots or lesions.", "Continue good field hygiene and balanced nutrition.",
     "Keep monitoring the crop regularly."),
    ("Potato", "Late Blight", "Potato___Late_blight",
     "A fungus-like disease that spreads quickly in cool, wet weather.",
     "Dark water-soaked patches on leaves, white mould underneath in humid weather.",
     "Use healthy seed tubers, avoid overhead irrigation, improve air flow, rotate crops.",
     "Remove badly affected plants and consult a local agricultural officer for treatment advice."),
    ("Tomato", "Healthy", "Tomato___Healthy", "The leaf shows no visible signs of disease.",
     "Uniform green colour, no spots or lesions.", "Maintain good spacing, watering and hygiene.",
     "Keep monitoring the crop regularly."),
    ("Tomato", "Early Blight", "Tomato___Early_blight",
     "A fungal disease that commonly affects older leaves first.",
     "Brown spots with concentric rings, yellowing around spots.",
     "Rotate crops, remove plant debris, avoid wetting leaves, mulch the soil.",
     "Remove affected lower leaves and consult a local agricultural expert for treatment options."),
    ("Tomato", "Late Blight", "Tomato___Late_blight",
     "A fast-spreading disease favoured by cool, humid weather.",
     "Large greasy grey-green patches on leaves, spots on stems and fruit.",
     "Use resistant varieties, avoid overcrowding, keep foliage dry.",
     "Isolate or remove severely infected plants and seek local expert advice quickly."),
         ("Potato", "Black Scurf", "Potato_Tuber___Black_Scurf",
     "A fungal disease caused by Rhizoctonia solani, producing dark, hard sclerotia on potato tubers.",
     "Black or dark-brown crust-like structures attached to the tuber skin.",
     "Use certified disease-free seed tubers, rotate crops and remove infected plant debris.",
     "Sort out severely affected tubers and use healthy seed material for the next planting."),

    ("Potato", "Blackleg", "Potato_Tuber___Blackleg",
     "A bacterial disease that affects potato stems and tubers.",
     "Blackened stems, wilting plants and dark, decayed areas around tuber eyes.",
     "Use certified seed potatoes, avoid planting damaged tubers and maintain field drainage.",
     "Remove infected plants and tubers. Avoid using infected potatoes as seed."),

    ("Potato", "Blackspot Bruising", "Potato_Tuber___Blackspot_Bruising",
     "A physiological condition caused by mechanical impact during harvesting, handling or storage.",
     "Dark internal spots beneath the tuber skin, often visible after cutting.",
     "Handle potatoes carefully, avoid dropping them and maintain suitable storage conditions.",
     "Separate damaged tubers and reduce mechanical damage during transport and storage."),

    ("Potato", "Brown Rot", "Potato_Tuber___Brown_Rot",
     "A bacterial disease caused by Ralstonia solanacearum that affects potato vascular tissue.",
     "Brown vascular discoloration, wilting plants and possible bacterial ooze from cut tubers.",
     "Use certified disease-free seed, clean equipment and avoid contaminated irrigation water.",
     "Remove infected plants and tubers. Follow local agricultural guidance before replanting."),

    ("Potato", "Common Scab", "Potato_Tuber___Common_Scab",
     "A soil-borne disease caused by Streptomyces bacteria that affects potato tuber surfaces.",
     "Rough, corky, raised or sunken lesions on the tuber skin.",
     "Maintain consistent soil moisture during tuber formation and use healthy seed potatoes.",
     "Sort affected tubers and use suitable varieties and soil management practices."),

    ("Potato", "Dry Rot", "Potato_Tuber___Dry_Rot",
     "A fungal storage disease commonly associated with Fusarium species.",
     "Dry, sunken, wrinkled lesions and internal brown, dry decay.",
     "Avoid tuber injuries, cure harvested potatoes properly and maintain suitable storage conditions.",
     "Remove rotting tubers and prevent damaged potatoes from entering storage."),

    ("Potato", "Healthy", "Potato_Tuber___Healthy_Potatoes",
     "The potato tuber shows no visible signs of the diseases represented in this model.",
     "Firm tuber surface without obvious rot, major lesions or abnormal discoloration.",
     "Store in a cool, dark, well-ventilated place and handle tubers carefully.",
     "Continue proper storage and inspect potatoes regularly."),

    ("Potato", "Miscellaneous", "Potato_Tuber___Miscellaneous",
     "The image has been classified into a miscellaneous category. A specific condition cannot be established from this classification.",
     "Appearance may vary and does not identify one specific disease.",
     "Inspect the tuber carefully and compare symptoms with established disease descriptions.",
     "Seek advice from an agricultural expert if abnormal symptoms are present."),

    ("Potato", "Pink Rot", "Potato_Tuber___Pink_Rot",
     "A tuber disease caused by Phytophthora erythroseptica, often associated with wet soil conditions.",
     "Water-soaked areas that may develop a pinkish discoloration after cutting and exposure to air.",
     "Improve soil drainage, avoid excessive irrigation and use healthy seed tubers.",
     "Remove affected tubers and avoid storing them with healthy potatoes."),

    ("Potato", "Soft Rot", "Potato_Tuber___Soft_Rot",
     "A bacterial disease that causes watery breakdown of potato tuber tissue.",
     "Soft, wet, mushy tissue with possible unpleasant smell.",
     "Avoid harvesting damaged tubers, reduce injuries and maintain dry, ventilated storage.",
     "Remove rotting tubers immediately and clean storage containers.")
]

ADVISORIES = [
    ("Crop Selection", "Choose crops that suit your climate", "Match the crop to your region's temperature, rainfall and soil type. Use the Crop Recommendation tool and consult local extension officers."),
    ("Soil Preparation", "Prepare soil before sowing", "Plough to a fine tilth, add organic matter such as compost, and test soil pH and nutrients every season."),
    ("Irrigation", "Water efficiently", "Irrigate at critical growth stages and avoid waterlogging. Early morning watering reduces evaporation and disease."),
    ("Fertilizer Basics", "Balanced nutrition", "Base fertilizer use on soil tests. Combine organic and chemical sources sensibly and avoid over-application."),
    ("Pest and Disease Prevention", "Prevent problems early", "Use healthy seed, rotate crops, remove infected plant parts, and inspect fields regularly. Report unusual symptoms early."),
    ("Weather Precautions", "Prepare for weather changes", "Watch forecasts. Ensure drainage before heavy rain and protect young plants from frost or heat waves."),
    ("Harvesting Basics", "Harvest at the right time", "Harvest at maturity, in dry weather where possible, and handle produce gently to reduce losses."),
]


def get_db():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    if url and token:
        conn = turso_serverless.connect(url, auth_token=token)
        conn.row_factory = turso_serverless.Row
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db():
    """Create tables, seed default data and apply pending migrations. Safe to run many times.

    If the database file already exists and has pending migrations, a backup copy is saved in
    database/backups/ first. Existing tables and records are never dropped.
    """
    remote = bool(
        os.environ.get("TURSO_DATABASE_URL")
        and os.environ.get("TURSO_AUTH_TOKEN")
    )

    if not remote:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    existed = (
        not remote
        and os.path.exists(DB_PATH)
        and os.path.getsize(DB_PATH) > 0
    )

    conn = get_db()
    try:
        if existed and current_version(conn) < LATEST_VERSION:
            backup_database(conn, DB_PATH)
        conn.executescript(SCHEMA)
        if not conn.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone():
            conn.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (?,?,?,'admin')",
                         ("System Admin", DEFAULT_ADMIN_EMAIL, generate_password_hash(DEFAULT_ADMIN_PASSWORD)))
        if not conn.execute("SELECT 1 FROM crops LIMIT 1").fetchone():
            conn.executemany("INSERT INTO crops (name, description, suitable_conditions, cultivation_advice) VALUES (?,?,?,?)", CROPS)
            for crop, name, label, desc, sym, prev, man in DISEASES:
                crop_id = conn.execute("SELECT id FROM crops WHERE name=?", (crop,)).fetchone()["id"]
                conn.execute("INSERT INTO diseases (crop_id, name, class_label, description, symptoms, prevention, management) "
                             "VALUES (?,?,?,?,?,?,?)", (crop_id, name, label, desc, sym, prev, man))
        if not conn.execute("SELECT 1 FROM crop_advisories LIMIT 1").fetchone():
            conn.executemany("INSERT INTO crop_advisories (category, title, content) VALUES (?,?,?)", ADVISORIES)
        conn.commit()
        run_migrations(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialised at", DB_PATH)
