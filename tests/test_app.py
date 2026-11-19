"""Automated tests for Smart Farmer Assistant.

Run from the project root:
    python -m unittest tests.test_app -v

A temporary database is used, so your real database is never touched.
"""
import io
import itertools
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["SECRET_KEY"] = "unit-test-secret"
_TMP = tempfile.mkdtemp(prefix="sfa_test_")

import utils.database as dbmod                      # noqa: E402
dbmod.DB_PATH = os.path.join(_TMP, "test.db")       # must be set before the app is imported

import app as appmod                                # noqa: E402
import security                                     # noqa: E402
from PIL import Image                               # noqa: E402

APP = appmod.app
APP.config["TESTING"] = True
UPLOADS = APP.config["UPLOAD_FOLDER"]
_UPLOADS_BEFORE = set(os.listdir(UPLOADS))

GOOD_PW = "Tractor2024"
_counter = itertools.count(1)


def tearDownModule():
    for f in set(os.listdir(UPLOADS)) - _UPLOADS_BEFORE:      # remove files created by the tests
        try:
            os.remove(os.path.join(UPLOADS, f))
        except OSError:
            pass
    shutil.rmtree(_TMP, ignore_errors=True)


# ------------------------------------------------------------------ helpers
def next_email():
    return f"user{next(_counter)}@example.com"


def text(resp):
    return resp.get_data(as_text=True)


def db_one(sql, params=()):
    conn = dbmod.get_db()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def db_all(sql, params=()):
    conn = dbmod.get_db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def png():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (40, 160, 60)).save(buf, "PNG")
    buf.seek(0)
    return buf


class Browser:
    """A test client that automatically sends the CSRF token with every POST."""

    def __init__(self):
        self.c = APP.test_client()

    def token(self):
        with self.c.session_transaction() as s:
            if "_csrf" not in s:
                s["_csrf"] = "test-token"
            return s["_csrf"]

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        data["_csrf"] = self.token()
        return self.c.post(url, data=data, **kw)

    def register(self, email, name="Test Farmer", pw=GOOD_PW, confirm=None, **extra):
        data = {"full_name": name, "email": email, "password": pw,
                "confirm_password": pw if confirm is None else confirm,
                "phone": "9876543210", "location": "Mysuru"}
        data.update(extra)
        return self.post("/register", data)

    def login(self, email, pw=GOOD_PW, **kw):
        return self.post("/login", {"email": email, "password": pw}, **kw)

    def logout(self):
        return self.post("/logout")


def new_farmer(name="Test Farmer"):
    b, em = Browser(), next_email()
    b.register(em, name=name)
    b.login(em)
    return b, em


def admin_browser():
    b = Browser()
    b.login(dbmod.DEFAULT_ADMIN_EMAIL, dbmod.DEFAULT_ADMIN_PASSWORD)
    return b


def make_report(b, crop="Tomato", disease="Early Blight", location="Mysuru", on=None,
                with_image=True, **extra):
    data = {"crop_name": crop, "disease_name": disease, "location": location,
            "description": "Spots on lower leaves",
            "report_date": (on or date.today()).isoformat()}
    if with_image:
        data["image"] = (png(), "leaf.png")
    data.update(extra)
    return b.post("/reports/new", data, content_type="multipart/form-data")


def latest_report_id(email):
    row = db_one("SELECT r.id FROM disease_reports r JOIN users u ON u.id=r.user_id "
                 "WHERE u.email=? ORDER BY r.id DESC", (email,))
    return row["id"] if row else None


FAKE_PREDICTION = {
    "label": "Tomato___Early_blight", "crop": "Tomato", "disease": "Early blight",
    "confidence": 94.2, "low_confidence": False,
    "top": [{"label": "Tomato___Early_blight", "confidence": 94.2},
            {"label": "Tomato___Late_blight", "confidence": 4.1},
            {"label": "Tomato___Healthy", "confidence": 1.7}],
}


class Base(unittest.TestCase):
    def setUp(self):
        security._fails.clear()      # reset login throttling between tests
        security._locked.clear()


# ------------------------------------------------------------ authentication
class TestAuth(Base):
    def test_anonymous_home_shows_landing_and_dashboard_needs_login(self):
        r = Browser().get("/")
        self.assertEqual(r.status_code, 200)                  # public landing page
        self.assertIn("Get Started", text(r))
        r = Browser().get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_register_hashes_password_and_rejects_duplicate(self):
        b, em = Browser(), next_email()
        r = b.register(em)
        self.assertEqual(r.status_code, 302)
        row = db_one("SELECT password_hash, role FROM users WHERE email=?", (em,))
        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "farmer")
        self.assertNotEqual(row["password_hash"], GOOD_PW)
        self.assertNotIn(GOOD_PW, row["password_hash"])
        r = b.register(em)                                    # duplicate email
        self.assertEqual(r.status_code, 200)
        self.assertIn("already exists", text(r))

    def test_register_validation(self):
        cases = [
            (dict(pw="Ab1"), "at least 8 characters"),
            (dict(pw="abcdefghij"), "one letter and one number"),
            (dict(pw="Password123"), "too common"),
            (dict(pw=GOOD_PW, confirm="Different123"), "do not match"),
            (dict(pw=GOOD_PW, email="not-an-email"), "valid email"),
            (dict(pw=GOOD_PW, phone="abc"), "only digits"),
        ]
        for kw, expected in cases:
            with self.subTest(expected=expected):
                kw = dict(kw)
                em = kw.pop("email", next_email())
                r = Browser().register(em, **kw)
                self.assertEqual(r.status_code, 200)
                self.assertIn(expected, text(r))
                self.assertIsNone(db_one("SELECT 1 FROM users WHERE email=?", (em,)))

    def test_login_logout_flow(self):
        b, em = Browser(), next_email()
        b.register(em)
        r = b.login(em, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Welcome back", text(r))
        self.assertEqual(b.get("/dashboard").status_code, 200)
        b.logout()
        r = b.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_login_failures(self):
        b, em = Browser(), next_email()
        b.register(em)
        for email, pw in [(em, "WrongPass123"), ("nobody@example.com", GOOD_PW),
                          ("' OR '1'='1", "x' OR '1'='1")]:
            with self.subTest(email=email):
                r = b.login(email, pw)
                self.assertEqual(r.status_code, 200)
                self.assertIn("Invalid email or password", text(r))

    def test_login_throttling(self):
        b, em = Browser(), next_email()
        b.register(em)
        for _ in range(5):
            b.login(em, "WrongPass123")
        r = b.login(em, GOOD_PW)                              # correct password, but locked out
        self.assertEqual(r.status_code, 429)
        self.assertIn("Too many failed attempts", text(r))

    def test_csrf_blocks_forged_post(self):
        b, em = new_farmer()
        r = b.c.post("/logout")                               # no CSRF token
        self.assertEqual(r.status_code, 302)
        self.assertEqual(b.get("/dashboard").status_code, 200)   # still logged in
        r = Browser().c.post("/register", data={"full_name": "X", "email": next_email(),
                                                 "password": GOOD_PW, "confirm_password": GOOD_PW})
        self.assertEqual(r.status_code, 302)                  # rejected and redirected

    def test_deactivated_user_is_blocked_and_logged_out(self):
        farmer, em = new_farmer()
        uid = db_one("SELECT id FROM users WHERE email=?", (em,))["id"]
        admin = admin_browser()
        admin.post(f"/admin/users/{uid}/toggle")              # deactivate
        r = farmer.get("/dashboard")                          # existing session is ended
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        r = Browser().login(em)                               # and a new login is refused
        self.assertIn("deactivated", text(r))
        admin.post(f"/admin/users/{uid}/toggle")              # reactivate
        r = Browser().login(em)
        self.assertEqual(r.status_code, 302)


# ------------------------------------------------------------- access control
class TestAccessControl(Base):
    FARMER_PAGES = ["/dashboard", "/profile", "/crop-recommendation", "/disease-detection",
                    "/reports", "/reports/new"]
    ADMIN_PAGES = ["/admin", "/admin/users", "/admin/reports", "/admin/crops",
                   "/admin/diseases", "/admin/advisories"]

    def test_anonymous_redirected_everywhere(self):
        b = Browser()
        for url in self.FARMER_PAGES + self.ADMIN_PAGES + ["/advisory", "/account/password"]:
            with self.subTest(url=url):
                r = b.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertIn("/login", r.headers["Location"])

    def test_farmer_blocked_from_admin(self):
        b, _ = new_farmer()
        for url in self.ADMIN_PAGES:
            with self.subTest(url=url):
                r = b.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertNotIn("/admin", r.headers["Location"])

    def test_admin_blocked_from_farmer_pages(self):
        b = admin_browser()
        for url in self.FARMER_PAGES:
            with self.subTest(url=url):
                r = b.get(url)
                self.assertEqual(r.status_code, 302)
        self.assertEqual(b.get("/admin").status_code, 200)
        self.assertEqual(b.get("/advisory").status_code, 200)
        self.assertEqual(b.get("/account/password").status_code, 200)

    def test_anonymous_post_to_admin_action(self):
        _, em = new_farmer()
        uid = db_one("SELECT id FROM users WHERE email=?", (em,))["id"]
        r = Browser().post(f"/admin/users/{uid}/delete")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertIsNotNone(db_one("SELECT 1 FROM users WHERE id=?", (uid,)))


# ----------------------------------------------------------- farmer features
class TestFarmer(Base):
    def test_profile_update(self):
        b, _ = new_farmer()
        r = b.post("/profile", {"full_name": "Ravi Kumar", "phone": "9999999999",
                                "location": "Hassan"}, follow_redirects=True)
        self.assertIn("Profile updated", text(r))
        self.assertIn("Ravi Kumar", text(r))
        r = b.post("/profile", {"full_name": "Ravi Kumar", "phone": "abc", "location": "x"})
        self.assertIn("only digits", text(r))

    def test_change_password(self):
        b, em = new_farmer()
        new_pw = "Harvest2025a"
        self.assertIn("incorrect", text(b.post("/account/password", {
            "current_password": "Wrong12345", "new_password": new_pw, "confirm_password": new_pw})))
        self.assertIn("at least 8 characters", text(b.post("/account/password", {
            "current_password": GOOD_PW, "new_password": "short", "confirm_password": "short"})))
        self.assertIn("do not match", text(b.post("/account/password", {
            "current_password": GOOD_PW, "new_password": new_pw, "confirm_password": "Other12345"})))
        r = b.post("/account/password", {"current_password": GOOD_PW, "new_password": new_pw,
                                         "confirm_password": new_pw})
        self.assertEqual(r.status_code, 302)
        b.logout()
        self.assertIn("Invalid email or password", text(b.login(em, GOOD_PW)))
        self.assertEqual(b.login(em, new_pw).status_code, 302)

    def test_crop_recommendation(self):
        b, _ = new_farmer()
        r = b.post("/crop-recommendation", {"N": "90", "P": "50", "K": "100", "temperature": "24",
                                            "humidity": "70", "ph": "6.4", "rainfall": "100"})
        self.assertEqual(r.status_code, 200)
        page = text(r)
        self.assertTrue("Rule-based" in page or "Machine learning" in page)
        self.assertIn("Suitability score", page)

    def test_crop_recommendation_validation(self):
        b, _ = new_farmer()
        good = {"N": "90", "P": "50", "K": "100", "temperature": "24",
                "humidity": "70", "ph": "6.4", "rainfall": "100"}
        for change, expected in [({"ph": "20"}, "must be between"), ({"N": ""}, "is required"),
                                 ({"humidity": "abc"}, "must be a number")]:
            with self.subTest(change=change):
                r = b.post("/crop-recommendation", {**good, **change})
                self.assertEqual(r.status_code, 200)
                self.assertIn(expected, text(r))

    def test_upload_validation(self):
        b, _ = new_farmer()
        cases = [
            ({"leaf_image": (io.BytesIO(b"not an image"), "fake.jpg")}, "not a valid image"),
            ({"leaf_image": (io.BytesIO(b"GIF89a"), "anim.gif")}, "Invalid file type"),
            ({}, "choose an image"),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected):
                r = b.post("/disease-detection", data, content_type="multipart/form-data",
                           follow_redirects=True)
                self.assertIn(expected, text(r))
        big = {"leaf_image": (io.BytesIO(b"0" * (6 * 1024 * 1024)), "big.jpg")}
        r = b.post("/disease-detection", big, content_type="multipart/form-data")
        self.assertIn(r.status_code, (302, 413))              # over the 5 MB limit

    @unittest.skipIf(appmod.model_available(), "a trained model exists; this test needs it missing")
    def test_detection_without_model(self):
        b, _ = new_farmer()
        r = b.post("/disease-detection", {"leaf_image": (png(), "leaf.png")},
                   content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("not been trained", text(r))

    def test_detection_pipeline_and_report(self):
        """Full flow with the ML model replaced by a stub: upload -> result -> report."""
        b, em = new_farmer()
        with patch.object(
    appmod,
    "predict_image_type",
    lambda path: {
        "category": "tomato_leaf",
        "confidence": 99.0,
        "margin": 98.0
    }
), patch.object(
    appmod,
    "predict_image",
    lambda path, *a, **k: FAKE_PREDICTION
):
            r = b.post("/disease-detection", {"leaf_image": (png(), "leaf.png")},
                       content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/disease-result/", r.headers["Location"])
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])

        page = text(b.get(f"/disease-result/{pid}"))
        self.assertIn("Early Blight", page)
        self.assertIn("94.2", page)
        self.assertIn("concentric rings", page)               # description comes from the diseases table
        self.assertIn("Other possibilities", page)

        form = text(b.get(f"/reports/new?prediction_id={pid}"))
        self.assertIn('value="Early Blight"', form)
        r = b.post("/reports/new", {"prediction_id": pid, "crop_name": "Tomato",
                                    "disease_name": "Early Blight", "location": "Mysuru",
                                    "description": "From detection",
                                    "report_date": date.today().isoformat()})
        self.assertEqual(r.status_code, 302)
        listing = text(b.get("/reports"))
        self.assertIn("Early Blight", listing)
        self.assertIn("94.2%", listing)
        self.assertIn("Pending", listing)
        r = b.get(f"/reports/new?prediction_id={pid}")        # already reported
        self.assertEqual(r.status_code, 302)
        self.assertIn("/reports/", r.headers["Location"])


# ------------------------------------------------------------------- reports
class TestReports(Base):
    def test_manual_report_validation(self):
        b, em = new_farmer()
        for kw, expected in [
            (dict(with_image=False), "choose an image"),
            (dict(on=date.today() + timedelta(days=1)), "cannot be in the future"),
            (dict(location=""), "Please enter your location"),
            (dict(crop=""), "required"),
        ]:
            with self.subTest(expected=expected):
                r = make_report(b, **kw)
                self.assertEqual(r.status_code, 200)
                self.assertIn(expected, text(r))
        self.assertIsNone(latest_report_id(em))               # nothing invalid was saved
        self.assertEqual(make_report(b).status_code, 302)
        self.assertIsNotNone(latest_report_id(em))

    def test_report_search_and_filter(self):
        b, _ = new_farmer()
        make_report(b, "Potato", "Late Blight")
        make_report(b, "Tomato", "Leaf Mold")
        page = text(b.get("/reports?q=Potato"))
        self.assertIn("Late Blight", page)
        self.assertNotIn("Leaf Mold", page)
        self.assertIn("No reports found", text(b.get("/reports?status=Resolved")))
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertIn("No reports found", text(b.get(f"/reports?start={tomorrow}")))

    def test_reports_are_private(self):
        a, a_email = new_farmer()
        make_report(a)
        rid = latest_report_id(a_email)
        other, _ = new_farmer()
        self.assertEqual(other.get(f"/reports/{rid}").status_code, 404)
        self.assertEqual(other.post(f"/reports/{rid}/delete").status_code, 404)
        self.assertEqual(a.get(f"/reports/{rid}").status_code, 200)

    def test_admin_report_management(self):
        farmer, em = new_farmer()
        make_report(farmer)
        rid = latest_report_id(em)
        admin = admin_browser()

        page = text(admin.get(f"/admin/reports/{rid}"))
        self.assertIn(em, page)                               # reporter details are shown to admin

        admin.post(f"/admin/reports/{rid}/status", {"status": "Reviewed"})
        self.assertEqual(db_one("SELECT status FROM disease_reports WHERE id=?", (rid,))["status"], "Reviewed")
        r = admin.post(f"/admin/reports/{rid}/status", {"status": "Hacked"}, follow_redirects=True)
        self.assertIn("Invalid status", text(r))
        self.assertEqual(db_one("SELECT status FROM disease_reports WHERE id=?", (rid,))["status"], "Reviewed")

        r = farmer.post(f"/reports/{rid}/delete", follow_redirects=True)   # not Pending any more
        self.assertIn("Only pending reports", text(r))

        admin.post(f"/admin/reports/{rid}/delete")
        self.assertIsNone(db_one("SELECT 1 FROM disease_reports WHERE id=?", (rid,)))


# --------------------------------------------------------------- admin tools
class TestAdmin(Base):
    def test_admin_dashboard_and_user_search(self):
        _, em = new_farmer()
        admin = admin_browser()
        self.assertIn("Admin dashboard", text(admin.get("/admin")))
        self.assertIn(em, text(admin.get(f"/admin/users?q={em}")))

    def test_advisory_crud(self):
        admin = admin_browser()
        farmer, _ = new_farmer()
        r = admin.post("/admin/advisories/save", {"category": "Hacking", "title": "x", "content": "y"})
        self.assertIn("valid category", text(r))

        r = admin.post("/admin/advisories/save", {"category": "Irrigation", "title": "Drip basics",
                                                  "content": "Use drip irrigation."})
        self.assertEqual(r.status_code, 302)
        self.assertIn("Drip basics", text(farmer.get("/advisory")))

        aid = db_one("SELECT id FROM crop_advisories WHERE title=?", ("Drip basics",))["id"]
        admin.post("/admin/advisories/save", {"id": aid, "category": "Irrigation",
                                              "title": "Drip basics v2", "content": "Updated."})
        page = text(farmer.get("/advisory"))
        self.assertIn("Drip basics v2", page)

        admin.post(f"/admin/advisories/{aid}/delete")
        self.assertNotIn("Drip basics v2", text(farmer.get("/advisory")))

    def test_crop_and_disease_management(self):
        admin = admin_browser()
        self.assertEqual(admin.post("/admin/crops/save", {"name": "Barley", "description": "Cereal crop"}).status_code, 302)
        self.assertIn("already exists", text(admin.post("/admin/crops/save", {"name": "Barley"})))
        cid = db_one("SELECT id FROM crops WHERE name='Barley'")["id"]

        r = admin.post("/admin/diseases/save", {"crop_id": cid, "name": "Leaf spot"})
        self.assertEqual(r.status_code, 302)
        row = db_one("SELECT id, class_label FROM diseases WHERE crop_id=?", (cid,))
        self.assertEqual(row["class_label"], "Barley___Leaf_spot")      # auto-generated label
        self.assertIn("already exists", text(admin.post("/admin/diseases/save",
                                                         {"crop_id": cid, "name": "leaf spot"})))

        r = admin.post(f"/admin/crops/{cid}/delete", follow_redirects=True)     # still has a disease
        self.assertIn("still has", text(r))
        tomato = db_one("SELECT id FROM crops WHERE name='Tomato'")["id"]
        self.assertIn("still has", text(admin.post(f"/admin/crops/{tomato}/delete", follow_redirects=True)))

        admin.post(f"/admin/diseases/{row['id']}/delete")
        admin.post(f"/admin/crops/{cid}/delete")
        self.assertIsNone(db_one("SELECT 1 FROM crops WHERE id=?", (cid,)))


# ----------------------------------------------------- security and seed data
class TestSecurityAndData(Base):
    def test_headers_and_cookie_flags(self):
        r = Browser().get("/login")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'self'", r.headers.get("Content-Security-Policy", ""))

        b, em = Browser(), next_email()
        b.register(em)
        login = b.login(em)
        cookie = " ".join(login.headers.getlist("Set-Cookie"))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertEqual(b.get("/dashboard").headers.get("Cache-Control"), "no-store")
        self.assertEqual(APP.permanent_session_lifetime, timedelta(hours=2))

    def test_output_is_escaped(self):
        name = "<script>alert(1)</script>"
        b, _ = new_farmer(name=name)
        page = text(b.get("/dashboard"))
        self.assertNotIn(name, page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_seed_data(self):
        admin = db_one("SELECT role, password_hash FROM users WHERE email=?", (dbmod.DEFAULT_ADMIN_EMAIL,))
        self.assertEqual(admin["role"], "admin")
        self.assertNotEqual(admin["password_hash"], dbmod.DEFAULT_ADMIN_PASSWORD)
        self.assertGreaterEqual(len(db_all("SELECT 1 FROM crops")), 5)
        self.assertGreaterEqual(len(db_all("SELECT 1 FROM crop_advisories")), 7)
        # the labels must match the dataset folder names used for training
        expected = {"Potato___Healthy", "Potato___Late_blight", "Tomato___Early_blight",
                    "Tomato___Healthy", "Tomato___Late_blight"}
        labels = {r["class_label"] for r in db_all("SELECT class_label FROM diseases")}
        self.assertTrue(expected <= labels)


if __name__ == "__main__":
    unittest.main()
