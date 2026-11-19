# Smart Farmer Assistant

An AI-powered agriculture and decision-support web application for Indian farmers, built with **Flask, SQLite,
TensorFlow/Keras and Bootstrap**. Engineering mini project.

## What it does

| Farmer | Administrator |
|---|---|
| Crop advisory: soil type, season and water (quick), or soil-test values N, P, K, temperature, humidity, pH, rainfall | Dashboard with totals, monthly registrations, detections and recommendations, reports by crop, location and status (interactive charts) |
| Leaf disease diagnosis from a photo, or from the camera, with confidence, symptoms, causes, prevention and general treatment | Manage farmers (activate, deactivate, delete) |
| Disease reports with status (Pending, Under Review, Resolved) and notifications when the status changes | Review, update and delete disease reports |
| Smart irrigation: Irrigation Required / Not Required / Monitor Soil Moisture, with timing and water-management tips | Manage crops, diseases and advisories |
| Fertilizer advice: nutrient status (Soil Health Card bands), suitable fertilizer types, application guidance and precautions | Manage government schemes and read contact messages |
| Weather: search any town, current conditions, 7-day forecast, farming advisory | Export a PDF summary and an Excel workbook |
| Market prices from data.gov.in (state, crop, district), with comparison and trend charts | |
| Farming calendar: crop plan with estimated stages, irrigation and fertilizer reminders, custom activities | |
| Government schemes with eligibility, benefits, documents, process, official link and verification date | |
| AI chatbot in English, Kannada and Hindi, with saved conversations; voice input and read-aloud where the browser supports it | |
| Farm details, history of everything, notifications, activity feed, sensor devices (ESP32 / Arduino) | |

## Technology

| Layer | Used |
|---|---|
| Frontend | HTML5, CSS3, Bootstrap 5, JavaScript, Chart.js, Web Speech API |
| Backend | Python 3.9–3.12, Flask |
| Database | SQLite with versioned, additive migrations (`utils/migrations.py`) |
| AI / ML | TensorFlow/Keras (MobileNetV2 transfer learning), OpenCV, NumPy, Pandas, scikit-learn |
| External data | Open-Meteo (weather, no key), data.gov.in (market prices, key), Anthropic API (chatbot, key) |

## Project layout

```
app.py                      Main Flask app: landing, auth, dashboards, advisory, detection, admin users
security.py                 Secret key, .env loader, cookies, security headers, login throttling
public_routes.py            Language switch, contact form
farm_routes.py              Farm details            history_routes.py   History and recommendation details
weather_routes.py           Weather                 irrigation_routes.py  Irrigation + sensor devices API
fertilizer_routes.py        Fertilizer advice      market_routes.py    Market prices (data.gov.in)
calendar_routes.py          Farming calendar       chat_routes.py      AI chatbot
scheme_routes.py            Schemes, messages      export_routes.py    PDF and Excel exports
report_routes.py            Disease reports        advisory_routes.py  Advisory articles
admin_routes.py             Crops and diseases     notification_routes.py  Notifications
model/                      advisory_engine, crop_recommend (+ training), disease_predict (+ training),
                            irrigation_engine, fertilizer_engine
utils/                      database, migrations, i18n, weather, http, chatbot, analytics, dashboard, activity
i18n/                       en.json, kn.json, hi.json (generated from tools/tr_*.py)
templates/                  Jinja2 pages (+ admin/)     static/css, static/js (script.js, chat.js, voice.js)
static/img/                 Generated hero and crop illustrations (tools/make_images.py)
tests/                      test_app.py (core, 29 tests), test_v2.py (new features, 37 tests)
tools/                      build_translations.py, check_i18n.py, make_images.py, tr_*.py
docs/esp32_soil_sensor.ino  Example sensor sketch (not hardware-tested by the project)
```

## Setup

Requires Python **3.9 to 3.12** (TensorFlow does not support newer versions yet).

```bash
python -m venv venv
venv\Scripts\activate              # Windows
source venv/bin/activate           # Linux / macOS
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. The database and sample data are created on first run.

**Default administrator:** `admin@smartfarmer.com` / `Admin@123`. A warning banner stays until you change the password.
Farmers register from the home page.

### API keys and settings

Copy `.env.example` to `.env` next to `app.py` and fill in what you need. Nothing is hard-coded and keys are never sent to the browser.

| Feature | Needs | Without it |
|---|---|---|
| Weather, forecast, weather advisory | nothing (Open-Meteo) | works |
| Market prices | `MARKET_API_KEY` from data.gov.in | page shows previously saved prices with a notice, or says prices are off |
| AI chatbot | `ANTHROPIC_API_KEY` | chat page explains it is not set up; no fake replies |
| Voice input / read-aloud | a browser with Web Speech support (Chrome or Edge works best) | text input still works |
| Disease detection | trained model (see below) | message asking to train the model |
| Crop advisory, soil-test mode | optional trained `crop_model.pkl` | built-in rule-based fallback (5 crops), labelled as such |

## Training the disease model (once)

Put the PlantVillage class folders (Potato and Tomato, see `dataset/README.txt`) in `dataset/`, then:

```bash
python model/train_disease_model.py
python model/train_disease_model.py --epochs 3 --fine-tune 0    # quick test run
```

This writes `model/disease_model.keras`, `class_names.json`, `metrics.json`, `training_history.png` and
`confusion_matrix.png`. The app loads the saved model only; it never retrains at start-up.
The crop model is optional: `python model/train_crop_model.py` with `dataset/Crop_recommendation.csv`.

## Tests

```bash
python -m unittest tests.test_app -v      # original features: 29 tests
python -m unittest tests.test_v2 -v       # new features: 37 tests (external services are faked)
python tools/check_i18n.py                # every translation key used in the pages exists
```

The v2 tests replace the weather, market and AI services with fakes, so they check our code and error handling,
not the live services. Run the live checks yourself (see "Checking the live services" below).

## Checking the live services

1. **Weather:** open *Weather*, search a town, and confirm the forecast and tips appear.
2. **Market:** add `MARKET_API_KEY`, restart, search a state and crop. If nothing appears for a valid crop, try another district or leave it empty, and check the dataset page on data.gov.in.
3. **Chatbot:** add `ANTHROPIC_API_KEY`, restart, ask a question in each language.
4. **Voice:** in Chrome, allow the microphone, press the mic button, check that the text appears before you press Send.

## Languages

English, Kannada and Hindi. The choice is remembered per user and per browser. Text lives in `i18n/*.json`, built
from `tools/tr_*.py`. Run `python tools/build_translations.py` after editing. Kannada and Hindi were written for this
project and should be reviewed by a native speaker before wider use.

## Sensors (ESP32 / Arduino)

Create a device under *Smart Irrigation → Sensors*, copy the key shown once, and POST JSON:

```
POST /api/sensor-readings
X-Device-Key: <key>
{"soil_moisture": 41.5, "temperature": 29.0, "humidity": 62}
```

The app stores the reading and can use it in the irrigation check. It does not switch pumps or valves. Automatic
control would need your own hardware, wiring and safety design. See `docs/esp32_soil_sensor.ino` (an example that
has not been run on hardware).

## Security

Hashed passwords; role checks on every protected route; CSRF tokens on forms and API calls; parameterised SQL;
template escaping; login throttling; upload validation and re-encoding; security headers; HttpOnly and SameSite
cookies; two-hour sessions; deactivated users are logged out on their next request; per-user data isolation (tested);
device keys stored only as hashes; AI and market keys only on the server.

## Limitations (say these in the viva)

- Only Potato and Tomato disease classes (five classes). The model always returns its closest class, so a photo of
  something that is not a leaf is still labelled; a low-confidence warning helps but does not remove this.
- The disease model is trained on lab-style images; accuracy on field photos will be lower than the validation figure.
- The crop advisory and irrigation logic are general rule-based guidelines, not calibrated field models.
- Calendar dates are estimates from typical crop durations, flagged on every item.
- Market prices depend on the data.gov.in dataset and API key; coverage varies by market and day.
- Scheme details were collected from public sources and should be re-checked on the official websites before relying
  on them. Each scheme shows its verification date.
- Kannada and Hindi translations need native-speaker review.
- Voice input depends on the browser and the device; read-aloud needs a voice for the language installed.
- Login lockout and chat/contact rate limits are kept in memory and reset when the app restarts.
- Flask's development server is for demonstrations. For real use, run behind Gunicorn or Waitress over HTTPS.

## Licence and disclaimer

Educational project. The application gives AI-based guidance only. It does not replace advice from a qualified
agricultural officer, and it does not recommend specific chemicals or doses.
