"""Tests for the v2 modules: weather, irrigation (incl. sensor API), fertilizer, market, calendar, chatbot,
schemes, messages, analytics and exports. External services are replaced by fakes; no network is used.

Run from the project root:  python -m unittest tests.test_v2 -v
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, timedelta
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SECRET_KEY"] = "unit-test-secret-v2"
for _k in (
    "MARKET_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENWEATHER_API_KEY",
):
    os.environ.pop(_k, None)
_TMP = tempfile.mkdtemp(prefix="sfa_v2_")

import utils.database as dbmod                      # noqa: E402
dbmod.DB_PATH = os.path.join(_TMP, "v2.db")
dbmod.init_db()                                  # create this temporary database schema (safe if run after other tests)

import app as appmod                                # noqa: E402
import security                                     # noqa: E402
import chat_routes, irrigation_routes, market_routes, utils.weather as W   # noqa: E402
from utils import chatbot                           # noqa: E402
from model.irrigation_engine import evaluate        # noqa: E402
from model.fertilizer_engine import advise          # noqa: E402

APP = appmod.app
APP.config["TESTING"] = True
GOOD = "Tractor2024"
_n = [0]


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


def db_one(sql, p=()):
    c = dbmod.get_db()
    try:
        return c.execute(sql, p).fetchone()
    finally:
        c.close()


class Resp:
    """Stand-in for the object returned by urllib.request.urlopen."""
    def __init__(self, obj):
        self._b = json.dumps(obj).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Client:
    def __init__(self, email=None, role_admin=False):
        self.c = APP.test_client()
        self.token = None
        if role_admin:
            self._login(dbmod.DEFAULT_ADMIN_EMAIL, dbmod.DEFAULT_ADMIN_PASSWORD)
        elif email:
            self.register(email)
            self._login(email, GOOD)

    def _tok(self):
        with self.c.session_transaction() as s:
            s.setdefault("_csrf", "tok-" + str(_n[0]))
            return s["_csrf"]

    def register(self, email):
        self._tok()
        self.c.post("/register", data={"_csrf": self._tok(), "full_name": "Test Farmer", "email": email,
                                       "password": GOOD, "confirm_password": GOOD, "location": "Mysuru"})

    def _login(self, email, pw):
        self.c.post("/login", data={"_csrf": self._tok(), "email": email, "password": pw})

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, **kw):
        if "json" in kw:                                   # JSON APIs: token in header, like static/js/chat.js
            return self.c.post(url, json=kw.pop("json"), headers={"X-CSRF-Token": self._tok()}, **kw)
        d = dict(data or {})
        d["_csrf"] = self._tok()
        return self.c.post(url, data=d, **kw)

    def text(self, url, **kw):
        return self.c.get(url, **kw).get_data(as_text=True)


def next_email():
    _n[0] += 1
    return f"v2user{_n[0]}@example.com"


class Base(unittest.TestCase):
    def setUp(self):
        security._fails.clear()
        security._locked.clear()
        W.clear_cache()
        market_routes._cache.clear()
        irrigation_routes._last_seen.clear()
        chat_routes._hits.clear()


class TestPermissionsPolicy(Base):
    def test_camera_and_microphone_are_allowed_for_same_origin(self):
        response = APP.test_client().get("/")
        policy = response.headers.get("Permissions-Policy", "")
        self.assertIn("camera=(self)", policy)
        self.assertIn("microphone=(self)", policy)
        self.assertIn("geolocation=()", policy)


# --------------------------------------------------------------- engines (pure logic)
class TestEngines(Base):
    def test_irrigation_states(self):
        self.assertEqual(evaluate("Tomato", "Loamy", 35, 34, 50, 0)["status"], "required")
        self.assertEqual(evaluate("Tomato", "Loamy", 35, 34, 50, 15)["status"], "monitor")   # rain already fell
        self.assertEqual(evaluate("Rice", "Clay", 98, 28, 80, 0)["status"], "not_required")  # waterlogged
        self.assertIn("irr.sug.rice", evaluate("Rice", "Clay", 60, 28, 60, 0)["suggestions"])

    def test_irrigation_never_claims_control(self):
        r = evaluate("Wheat", "Loamy", 40, 25, 60, 0)
        self.assertNotIn("pump", json.dumps(r).lower())

    def test_fertilizer_no_quantities_and_legume_rule(self):
        r = advise("Groundnut", 200, 8, 300, 5.8)
        self.assertEqual(r["ratings"], {"N": "low", "P": "low", "K": "high"})
        self.assertTrue(all(f["name"] != "urea" for f in r["fertilizers"]))      # legumes fix their own N
        blob = json.dumps(r)
        self.assertNotIn("kg/acre", blob)
        self.assertNotRegex(blob, r"\d+\s*(kg|g|ml|litre|liter)\b")               # no dose figures

    def test_fertilizer_ratings_match_soil_health_card_bands(self):
        self.assertEqual(advise("Maize", 279, 9, 119, 7)["ratings"], {"N": "low", "P": "low", "K": "low"})
        self.assertEqual(advise("Maize", 561, 26, 281, 7)["ratings"], {"N": "high", "P": "high", "K": "high"})

    def test_weather_codes_and_tips(self):
        self.assertEqual(W.describe(61)[0], "Rain")
        self.assertEqual(W.describe(9999)[0], "Unknown")
        tips = W.farming_tips({"temp": 36, "humidity": 90, "wind": 5, "rain": 0},
                              [{"rain": 8, "rain_prob": 80, "max": 36}])
        keys = [t[0] for t in tips]
        self.assertIn("tip.rain_soon", keys)
        self.assertIn("tip.heat", keys)
        self.assertIn("tip.humid", keys)

    def test_place_validation(self):
        self.assertTrue(W.valid_place("Mysuru, Karnataka"))
        self.assertFalse(W.valid_place("<script>"))

    def test_translations_fall_back_to_english(self):
        from utils import i18n
        self.assertEqual(i18n.translate("hi", "does.not.exist"), "does.not.exist")
        self.assertEqual(i18n.translate_name("kn", "crop", "Rice"), "ಭತ್ತ")
        self.assertEqual(i18n.translate_name("en", "crop", "Unknown crop"), "Unknown crop")


# ----------------------------------------------------------------- weather (mocked)
class TestWeather(Base):
    def test_search_and_forecast_with_fake_service(self):
        geo = {"results": [{"name": "Mysuru", "latitude": 12.3, "longitude": 76.6, "admin1": "Karnataka", "country": "India"}]}
        days = [f"2026-11-{4 + i:02d}" for i in range(7)]
        fc = {"current": {"time": "t", "temperature_2m": 29.5, "relative_humidity_2m": 88, "apparent_temperature": 32,
                          "precipitation": 0, "weather_code": 3, "wind_speed_10m": 12},
              "daily": {"time": days, "weather_code": [61] * 7, "temperature_2m_max": [31] * 7, "temperature_2m_min": [21] * 7,
                        "precipitation_sum": [12, 2, 0, 0, 0, 1, 9], "precipitation_probability_max": [85] * 7,
                        "wind_speed_10m_max": [18] * 7}}
        def fake(req, timeout=None):
            return Resp(geo if "geocoding" in req.full_url else fc)
        with patch("urllib.request.urlopen", fake):
            places = W.search_places("Mysuru")
            data = W.get_forecast(places[0]["lat"], places[0]["lon"])
        self.assertEqual(len(data["daily"]), 7)
        self.assertEqual(data["current"]["temp"], 29.5)
        self.assertTrue(any(t[0] == "tip.rain_soon" for t in data["tips"]))

    def test_service_down_gives_friendly_error_not_crash(self):
        def down(req, timeout=None):
            raise urllib.error.URLError("offline")
        with patch("urllib.request.urlopen", down):
            with self.assertRaises(W.WeatherError):
                W.get_forecast(12.3, 76.6)
        c = Client(next_email())
        with patch("urllib.request.urlopen", down):
            self.assertEqual(c.get("/weather?q=Mysuru").status_code, 200)

    def test_weather_page_needs_login(self):
        self.assertEqual(APP.test_client().get("/weather").status_code, 302)


# --------------------------------------------------------------- irrigation + sensors
class TestIrrigation(Base):
    def test_manual_check_saves_history(self):
        c = Client(next_email())
        r = c.post("/irrigation", {"crop": "Tomato", "soil_type": "Loamy", "soil_moisture": "35", "temperature": "34",
                                   "humidity": "50", "recent_rainfall": "0"})
        self.assertTrue("Irrigation Required" in r.get_data(as_text=True) or "Monitor Soil Moisture" in r.get_data(as_text=True))
        self.assertIsNotNone(db_one("SELECT 1 FROM irrigation_records WHERE crop='Tomato' ORDER BY id DESC LIMIT 1"))

    def test_invalid_input_rejected(self):
        c = Client(next_email())
        r = c.post("/irrigation", {"crop": "Tomato", "soil_type": "Loamy", "soil_moisture": "170", "temperature": "34",
                                   "humidity": "50", "recent_rainfall": "0"})
        self.assertIn("valid numbers", r.get_data(as_text=True))

    def test_device_key_is_hashed_and_readings_stored(self):
        c = Client(next_email())
        html = c.post("/devices", {"name": "North field"}).get_data(as_text=True)
        key = html.split('id="newToken">')[1].split("<")[0]
        self.assertIsNone(db_one("SELECT 1 FROM devices WHERE token_hash=?", (key,)))      # never stored in clear
        def ingest(body, k=key):
            return APP.test_client().post("/api/sensor-readings", json=body, headers={"X-Device-Key": k} if k else {})
        self.assertEqual(ingest({"soil_moisture": 40}, None).status_code, 401)
        self.assertEqual(ingest({"soil_moisture": 40}, "wrong").status_code, 401)
        self.assertEqual(ingest({"soil_moisture": 140}).status_code, 400)
        self.assertEqual(ingest({"temperature": 20}).status_code, 400)
        self.assertEqual(ingest({"soil_moisture": 41.5, "temperature": 29}).status_code, 200)
        self.assertEqual(ingest({"soil_moisture": 42}).status_code, 429)                   # rate limited
        self.assertEqual(db_one("SELECT soil_moisture FROM sensor_readings ORDER BY id DESC LIMIT 1")[0], 41.5)

    def test_sensor_value_used_when_selected(self):
        c = Client(next_email())
        irrigation_routes._last_seen.clear()
        html = c.post("/devices", {"name": "S1"}).get_data(as_text=True)
        key = html.split('id="newToken">')[1].split("<")[0]
        APP.test_client().post("/api/sensor-readings", json={"soil_moisture": 99}, headers={"X-Device-Key": key})
        c.post("/irrigation", {"use_sensor": "1", "crop": "Maize", "soil_type": "Red", "soil_moisture": "1", "temperature": "28",
                               "humidity": "60", "recent_rainfall": "0"})
        row = db_one("SELECT soil_moisture, source FROM irrigation_records ORDER BY id DESC LIMIT 1")
        self.assertEqual((row[0], row[1]), (99.0, "sensor"))

    def test_device_isolation_between_farmers(self):
        a = Client(next_email())
        html = a.post("/devices", {"name": "A"}).get_data(as_text=True)
        did = db_one("SELECT id FROM devices ORDER BY id DESC LIMIT 1")[0]
        b = Client(next_email())
        self.assertIn("not found", b.post(f"/devices/{did}/delete", {}, follow_redirects=True).get_data(as_text=True).lower())
        self.assertIsNotNone(db_one("SELECT 1 FROM devices WHERE id=?", (did,)))


# ------------------------------------------------------------------- fertilizer page
class TestFertilizer(Base):
    def test_page_flow_and_validation(self):
        c = Client(next_email())
        t = c.post("/fertilizer", {"crop": "Potato", "soil_type": "", "N": "300", "P": "30", "K": "100", "ph": "7.9"}).get_data(as_text=True)
        self.assertIn("Sulphate of potash", t)
        self.assertIn("No quantities are given", t)
        self.assertIn("valid numbers", c.post("/fertilizer", {"crop": "Rice", "N": "-5", "P": "8", "K": "3", "ph": "6"}).get_data(as_text=True))
        self.assertIsNotNone(db_one("SELECT 1 FROM soil_records ORDER BY id DESC LIMIT 1"))


# ----------------------------------------------------------------------- market (mocked)
class TestMarket(Base):
    REC = {"records": [{"state": "Karnataka", "district": "Mysuru", "market": "Mysuru APMC", "commodity": "Tomato", "variety": "Local",
                        "grade": "FAQ", "arrival_date": "04/11/2026", "min_price": "1200", "max_price": "2000", "modal_price": "1600"}]}

    def test_without_key_nothing_is_invented(self):
        c = Client(next_email())
        t = c.text("/market?state=Karnataka&commodity=Tomato")
        self.assertIn("Live prices are off", t)
        self.assertNotIn("Live from data.gov.in", t)          # never presented as live without a key
        if "Saved data" in t:                                 # only prices earlier real responses stored
            self.assertIn("Showing prices saved earlier", t)

    def test_live_then_stored_fallback(self):
        c = Client(next_email())
        os.environ["MARKET_API_KEY"] = "k-test"
        try:
            with patch("urllib.request.urlopen", lambda req, timeout=None: Resp(self.REC)):
                t = c.text("/market?state=Karnataka&commodity=Tomato")
            self.assertIn("Mysuru APMC", t)
            self.assertIn("Live from data.gov.in", t)
            market_routes._cache.clear()
            def down(req, timeout=None):
                raise urllib.error.URLError("x")
            with patch("urllib.request.urlopen", down):
                t = c.text("/market?state=Karnataka&commodity=Tomato")
            self.assertIn("Showing prices saved earlier", t)
            self.assertIn("Mysuru APMC", t)
        finally:
            os.environ.pop("MARKET_API_KEY", None)

    def test_key_rejected_message(self):
        c = Client(next_email())
        os.environ["MARKET_API_KEY"] = "bad"
        try:
            market_routes._cache.clear()
            def bad(req, timeout=None):
                raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
            with patch("urllib.request.urlopen", bad):
                self.assertIn("rejected", c.text("/market?state=Karnataka&commodity=Tomato"))
        finally:
            os.environ.pop("MARKET_API_KEY", None)

    def test_inputs_validated(self):
        c = Client(next_email())
        self.assertIn("Please choose a state", c.text("/market?state=Mars&commodity=Tomato"))
        self.assertIn("valid crop", c.text("/market?state=Karnataka&commodity=%3Cb%3E"))


# -------------------------------------------------------------------------- calendar
class TestCalendar(Base):
    def test_plan_creates_estimated_items_and_no_quantities(self):
        c = Client(next_email())
        c.post("/calendar/plan", {"crop": "Tomato", "sowing_date": date.today().isoformat()})
        pid = db_one("SELECT id FROM crop_plans ORDER BY id DESC LIMIT 1")[0]
        rows = dmod_rows(pid)
        kinds = {r[0] for r in rows}
        self.assertTrue({"growth_stage", "irrigation", "fertilizer", "harvest"} <= kinds)
        self.assertTrue(all(r[1] == 1 for r in rows))                       # every item flagged as estimate
        self.assertTrue(all(not any(ch.isdigit() for ch in (r[2] or "")) for r in rows if r[0] == "fertilizer"))

    def test_validation_and_ownership(self):
        a = Client(next_email())
        self.assertIn("choose a crop", a.post("/calendar/plan", {"crop": "Mango", "sowing_date": date.today().isoformat()},
                                              follow_redirects=True).get_data(as_text=True))
        self.assertIn("valid date", a.post("/calendar/plan", {"crop": "Rice", "sowing_date": "1900-01-01"},
                                           follow_redirects=True).get_data(as_text=True))
        a.post("/calendar/plan", {"crop": "Rice", "sowing_date": date.today().isoformat()})
        pid = db_one("SELECT id FROM crop_plans ORDER BY id DESC LIMIT 1")[0]
        b = Client(next_email())
        self.assertIn("not found", b.post(f"/calendar/plan/{pid}/delete", {}, follow_redirects=True).get_data(as_text=True).lower())
        self.assertIsNotNone(db_one("SELECT 1 FROM crop_plans WHERE id=?", (pid,)))

    def test_custom_activity_crud(self):
        c = Client(next_email())
        c.post("/calendar/activity", {"title": "Buy seeds", "start_date": "2026-12-01", "kind": "custom"})
        aid = db_one("SELECT id FROM calendar_activities WHERE title='Buy seeds'")[0]
        c.post(f"/calendar/activity/{aid}/toggle", {})
        self.assertEqual(db_one("SELECT completed FROM calendar_activities WHERE id=?", (aid,))[0], 1)
        c.post(f"/calendar/activity/{aid}/edit", {"title": "Buy seeds (2)", "start_date": "2026-12-02"})
        self.assertIn("Buy seeds (2)", c.text("/calendar?y=2026&m=12"))
        c.post(f"/calendar/activity/{aid}/delete", {})
        self.assertIsNone(db_one("SELECT 1 FROM calendar_activities WHERE id=?", (aid,)))


def dmod_rows(pid):
    c = dbmod.get_db()
    try:
        return [tuple(r) for r in c.execute("SELECT kind, is_estimate, description FROM calendar_activities WHERE plan_id=?", (pid,))]
    finally:
        c.close()


# -------------------------------------------------------------------------- chatbot
class TestChatbot(Base):

    def setUp(self):
        super().setUp()
        os.environ.pop("GEMINI_API_KEY", None)

    def fake_gemini(self, text="Prepare loose, well-drained soil.", error=None):
        seen = {}

        class FakeModels:
            def generate_content(self, **kwargs):
                seen.update(kwargs)

                if error:
                    raise error

                class Response:
                    pass

                response = Response()
                response.text = text
                return response

        class FakeClient:
            def __init__(self, **kwargs):
                seen["client"] = kwargs

                self.models = FakeModels()

        return FakeClient, seen

    def test_not_configured_is_graceful_and_stores_nothing(self):
        c = Client(next_email())

        r = c.post("/api/chat", json={
            "message": "How to grow tomato?"
        })

        self.assertEqual(r.status_code, 503)
        self.assertIn("not set up", r.get_json()["error"])

        self.assertEqual(
            db_one("SELECT COUNT(*) FROM chat_messages")[0], 0
        )

    def test_reply_stored_and_key_sent_only_server_side(self):
        c = Client(next_email())

        os.environ["GEMINI_API_KEY"] = "test-gemini-secret"

        FakeClient, seen = self.fake_gemini()

        try:
            with patch("utils.chatbot.genai.Client", FakeClient):
                r = c.post("/api/chat", json={
                    "message": "Soil for tomato?",
                    "language": "kn"
                })

            result = r.get_json()

            self.assertTrue(result["ok"])

            self.assertEqual(
                seen["client"]["api_key"], "test-gemini-secret"
            )

            self.assertEqual(
                seen["model"], chatbot.model_name()
            )

            self.assertIn(
                "Kannada",
                seen["config"].system_instruction
            )

            self.assertNotIn(
                "test-gemini-secret", c.text("/chat")
            )

            self.assertEqual(
                db_one(
                    "SELECT COUNT(*) FROM chat_messages WHERE conversation_id=?",
                    (result["conversation_id"],)
                )[0],
                2
            )

        finally:
            os.environ.pop("GEMINI_API_KEY", None)
    def test_streaming_success_saves_complete_reply(self):
        c = Client(next_email())
        os.environ["GEMINI_API_KEY"] = "test-stream-key"

        class FakeModels:
            def generate_content_stream(self, **kwargs):
                for text in ("Prepare loose ", "soil for ", "tomatoes."):
                    yield type("Chunk", (), {"text": text})()

        class FakeClient:
            def __init__(self, **kwargs):
                self.models = FakeModels()

        try:
            with patch("utils.chatbot.genai.Client", FakeClient):
                r = c.post("/api/chat", json={
                    "message": "How to prepare soil?",
                    "stream": True
                })

            body = r.get_data(as_text=True)

            self.assertEqual(r.status_code, 200)
            self.assertIn("event: token", body)
            self.assertIn("event: done", body)
            self.assertIn("Prepare loose ", body)
            self.assertIn("tomatoes.", body)

            done_frame = next(
                frame for frame in body.split("\n\n")
                if frame.startswith("event: done")
            )
            done_data = next(
                line[5:].strip() for line in done_frame.splitlines()
                if line.startswith("data:")
            )
            conversation_id = json.loads(done_data)["conversation_id"]

            messages = db_one(
                "SELECT COUNT(*) FROM chat_messages WHERE conversation_id=?",
                (conversation_id,)
            )[0]
            self.assertEqual(messages, 2)

            assistant = db_one(
                "SELECT content FROM chat_messages "
                "WHERE conversation_id=? AND role='assistant'",
                (conversation_id,)
            )[0]
            self.assertEqual(
                assistant,
                "Prepare loose soil for tomatoes."
            )

        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_streaming_failure_does_not_save_partial_reply(self):
        c = Client(next_email())
        os.environ["GEMINI_API_KEY"] = "test-stream-key"
        before_messages = db_one(
            "SELECT COUNT(*) FROM chat_messages"
        )[0]

        before_conversations = db_one(
            "SELECT COUNT(*) FROM chat_conversations"
        )[0]

        class FakeModels:
            def generate_content_stream(self, **kwargs):
                yield type("Chunk", (), {"text": "Partial answer"})()
                raise RuntimeError("Simulated provider failure")

        class FakeClient:
            def __init__(self, **kwargs):
                self.models = FakeModels()

        try:
            with patch("utils.chatbot.genai.Client", FakeClient):
                r = c.post("/api/chat", json={
                    "message": "How to grow tomatoes?",
                    "stream": True
                })

            body = r.get_data(as_text=True)

            self.assertEqual(r.status_code, 200)
            self.assertIn("event: token", body)
            self.assertIn("Partial answer", body)
            self.assertIn("event: error", body)
            self.assertNotIn("event: done", body)

            self.assertEqual(
                db_one("SELECT COUNT(*) FROM chat_messages")[0],
                before_messages,
                "Failed streaming must not save partial messages."
            )

            self.assertEqual(
                db_one("SELECT COUNT(*) FROM chat_conversations")[0],
                before_conversations,
                "Failed streaming must not create a conversation."
            )

        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_failures_map_to_messages(self):
        c = Client(next_email())

        os.environ["GEMINI_API_KEY"] = "test-key"

        class FakeError(Exception):
            code = 401

        FakeClient, seen = self.fake_gemini(error=FakeError("Unauthorized"))

        try:
            with patch("utils.chatbot.genai.Client", FakeClient):
                r = c.post("/api/chat", json={"message": "hello"})

            self.assertEqual(r.status_code, 502)
            self.assertIn("rejected", r.get_json()["error"])

        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_other_users_cannot_read_or_post_to_a_chat(self):
        a = Client(next_email())

        os.environ["GEMINI_API_KEY"] = "test-key"

        FakeClient, seen = self.fake_gemini(text="ok")

        try:
            with patch("utils.chatbot.genai.Client", FakeClient):
                cid = a.post(
                    "/api/chat",
                    json={"message": "hi"}
                ).get_json()["conversation_id"]

            b = Client(next_email())

            self.assertEqual(
                b.get(f"/chat?c={cid}").status_code, 404
            )

            with patch("utils.chatbot.genai.Client", FakeClient):
                r = b.post(
                    "/api/chat",
                    json={"message": "x", "conversation_id": cid}
                )

            self.assertEqual(r.status_code, 404)

        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_rate_limit(self):
        c = Client(next_email())

        os.environ["GEMINI_API_KEY"] = "test-key"

        FakeClient, seen = self.fake_gemini(text="ok")

        try:
            with patch("utils.chatbot.genai.Client", FakeClient):
                codes = [
                    c.post(
                        "/api/chat",
                        json={"message": f"q{i}"}
                    ).status_code
                    for i in range(chat_routes.RATE_LIMIT + 2)
                ]

            self.assertEqual(codes[-1], 429)

        finally:
            os.environ.pop("GEMINI_API_KEY", None)


# --------------------------------------------------------------- schemes, messages, admin
class TestSchemesAndAdmin(Base):
    def test_seeded_schemes_visible_with_official_sources(self):
        c = Client(next_email())
        t = c.text("/schemes")
        for name in ("PM-KISAN", "PMFBY", "Kisan Credit Card", "Soil Health Card"):
            self.assertIn(name, t)
        self.assertIn("https://pmkisan.gov.in", t)
        self.assertNotIn("Rs 5 lakh", t)                 # unverified claim must not be shown

    def test_scheme_admin_crud_and_validation(self):
        admin = Client(role_admin=True)
        self.assertIn("https://", admin.post("/admin/schemes/save", {"name": "Test scheme", "description": "d",
                                                                  "official_url": "http://insecure.example"}, follow_redirects=True).get_data(as_text=True))
        admin.post("/admin/schemes/save", {"name": "Test scheme", "description": "d", "official_url": "https://example.gov.in"})
        sid = db_one("SELECT id FROM schemes WHERE name='Test scheme'")[0]
        c = Client(next_email())
        admin.post(f"/admin/schemes/{sid}/toggle", {})
        self.assertNotIn("Test scheme", c.text("/schemes"))
        admin.post(f"/admin/schemes/{sid}/delete", {})
        self.assertIsNone(db_one("SELECT 1 FROM schemes WHERE id=?", (sid,)))

    def test_contact_form_to_admin_inbox(self):
        c = Client(next_email())
        c.post("/contact", {"name": "Ravi", "email": "r@example.com", "message": "Please add more crops in Kannada."})
        admin = Client(role_admin=True)
        self.assertIn("Please add more crops", admin.text("/admin/messages"))

    def test_admin_pages_forbidden_to_farmers(self):
        c = Client(next_email())
        for url in ("/admin/schemes", "/admin/messages", "/admin/export/pdf", "/admin/export/excel"):
            self.assertEqual(c.get(url).status_code, 302, url)

    def test_admin_dashboard_numbers_come_from_database(self):
        admin = Client(role_admin=True)
        t = admin.text("/admin")
        self.assertIn("Admin dashboard", t)
        farmers = db_one("SELECT COUNT(*) FROM users WHERE role='farmer'")[0]
        self.assertIn(f"<h2>{farmers}</h2>", t)

    def test_exports_are_valid_files(self):
        admin = Client(role_admin=True)
        pdf = admin.get("/admin/export/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.data[:4], b"%PDF")
        xl = admin.get("/admin/export/excel")
        self.assertEqual(xl.status_code, 200)
        self.assertEqual(xl.data[:2], b"PK")
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(xl.data))
        self.assertEqual(wb.sheetnames, ["Summary", "Reports", "Farmers", "Predictions", "Recommendations"])


# ------------------------------------------------------- language and activity
class TestLanguageAndActivity(Base):
    def test_language_persists_for_user(self):
        email = next_email()
        c = Client(email)
        c.get("/language/kn")
        self.assertIn("ಹವಾಮಾನ", c.text("/weather"))
        c2 = Client()
        c2.post("/login", {"email": email, "password": GOOD})
        self.assertIn('lang="kn"', c2.text("/dashboard"))

    def test_unknown_language_rejected(self):
        self.assertEqual(APP.test_client().get("/language/fr").status_code, 404)

    def test_activity_is_logged_for_admin_views(self):
        c = Client(next_email())
        c.post("/farms/save", {"name": "Logged farm", "location": "Hassan"})
        self.assertIsNotNone(db_one("SELECT 1 FROM activity_log WHERE action='farm_added'"))


if __name__ == "__main__":
    unittest.main()
