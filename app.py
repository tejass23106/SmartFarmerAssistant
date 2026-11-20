import json
import os
import math
import sqlite3
import secrets
import importlib
from urllib.parse import urlparse

from jinja2 import pass_context
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

from utils.database import get_db, init_db, DEFAULT_ADMIN_PASSWORD
from utils import analytics, dashboard as dashboard_data, i18n, weather
from utils.activity import log_activity
from utils.helpers import (login_required, role_required, valid_email, save_image, safe_next, crop_slug)
from security import (register as register_security, load_secret_key, load_dotenv, password_error,
                      locked_seconds, record_failure, clear_failures, MAX_FAILS, MAX_FAILS_IP)
from model.crop_recommend import recommend, validate_inputs, LIMITS, FEATURES, using_ml
from model.advisory_engine import (SOILS, SEASONS, WATER_LEVELS, SEASON_HINTS, advise,
                                   validate as validate_advisory, related_crop_info)
from model.plant_health_api import (
    analyze_plant_image,
    PlantHealthAPIError,
)
app = Flask(__name__)
load_dotenv(os.path.join(app.root_path, ".env"))   # optional local settings (API keys, SECRET_KEY, ...)
app.config["SECRET_KEY"] = load_secret_key(app.root_path)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

init_db()
register_security(app)   # cookies, headers, session guard, change-password page


# ---------- CSRF protection ----------
CSRF_EXEMPT = {"sensor_ingest"}   # JSON endpoint for ESP32/Arduino devices, authenticated by a device key


@app.before_request
def csrf_protect():
    if request.method == "POST" and request.endpoint not in CSRF_EXEMPT:
        token = session.get("_csrf") or ""
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
        if not token or not secrets.compare_digest(token.encode(), sent.encode()):
            abort(400)


@app.context_processor
def inject_globals():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)

    def safe_url(endpoint, **values):
        """url_for that returns '#' for pages not built yet."""
        return url_for(endpoint, **values) if endpoint in app.view_functions else "#"

    def crop_img(name):
        """URL of the illustration for a crop (falls back to a generic plant image)."""
        slug = crop_slug(name)
        rel = f"img/crops/{slug}.svg"
        if not slug or not os.path.exists(os.path.join(app.static_folder, rel)):
            rel = "img/crops/default.svg"
        return url_for("static", filename=rel)

    lang = i18n.valid_lang(session.get("lang")) or i18n.valid_lang(request.cookies.get("lang")) or "en"
    unread = 0
    if session.get("role") == "farmer":
        conn = get_db()
        try:
            unread = conn.execute("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0",
                                  (session["user_id"],)).fetchone()["c"]
        except sqlite3.Error:
            unread = 0
        finally:
            conn.close()
    return {"csrf_token": session["_csrf"], "safe_url": safe_url, "crop_img": crop_img, "lang": lang,
            "LANGS": i18n.LANGS, "speech_lang": i18n.SPEECH_LANG.get(lang, "en-IN"), "unread_count": unread,
            "t": lambda key, **kw: i18n.translate(lang, key, **kw),
            "tn": lambda kind, name: i18n.translate_name(lang, kind, name)}


def back_or(endpoint):
    """Redirect target: the referring page if it is on this site, otherwise a safe default."""
    ref = request.referrer
    if ref and urlparse(ref).netloc == request.host:
        return ref
    return url_for(endpoint)


@app.template_filter("status_label")
@pass_context
def status_label(ctx, status):
    """Report status shown to the user: 'Reviewed' is displayed as 'Under Review' (translated)."""
    return ctx["t"]("status." + str(status))


# ---------- Error pages ----------
@app.errorhandler(400)
def bad_request(e):
    flash("Your session expired or the request was invalid. Please try again.", "danger")
    return redirect(back_or("login"))


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(413)
def too_large(e):
    flash("File too large. Maximum allowed size is 5 MB.", "danger")
    return redirect(back_or("home"))


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Something went wrong on our side."), 500


# ---------- Chart/statistics helpers ----------
def status_counts(conn, user_id=None):
    sql, params = "SELECT status, COUNT(*) c FROM disease_reports", ()
    if user_id:
        sql, params = sql + " WHERE user_id=?", (user_id,)
    data = {r["status"]: r["c"] for r in conn.execute(sql + " GROUP BY status", params)}
    return [data.get(s, 0) for s in ("Pending", "Reviewed", "Resolved")]


def disease_counts(conn, user_id=None):
    sql, params = "SELECT disease_name, COUNT(*) c FROM predictions", ()
    if user_id:
        sql, params = sql + " WHERE user_id=?", (user_id,)
    rows = conn.execute(sql + " GROUP BY disease_name ORDER BY c DESC LIMIT 6", params).fetchall()
    return [r["disease_name"] for r in rows], [r["c"] for r in rows]


def find_disease_info(conn, crop_name, disease_name):
    return conn.execute(
        "SELECT d.* FROM diseases d JOIN crops c ON c.id = d.crop_id "
        "WHERE LOWER(c.name)=LOWER(?) AND LOWER(d.name)=LOWER(?)", (crop_name, disease_name)).fetchone()


def remove_upload(filename):
    try:
        os.remove(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    except OSError:
        pass


# ---------- Auth ----------
@app.route("/")
def home():
    """Public landing page for visitors; signed-in users go straight to their dashboard."""
    if "user_id" in session:
        return redirect(url_for("admin_dashboard" if session.get("role") == "admin" else "dashboard"))
    return render_template("landing.html", contact_email=os.environ.get("CONTACT_EMAIL", "").strip() or None)


@app.route("/about")
def about():
    return redirect(url_for("home") + "#about")


@app.route("/services")
def services():
    return redirect(url_for("home") + "#services")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        error = None
        if not name or not email or not password:
            error = "Name, email and password are required."
        elif len(name) > 80:
            error = "Name is too long."
        elif not valid_email(email):
            error = "Please enter a valid email address."
        elif password_error(password):
            error = password_error(password)
        elif password != confirm:
            error = "Passwords do not match."
        elif phone and not phone.replace("+", "").replace(" ", "").isdigit():
            error = "Phone number may contain only digits, spaces and +."
        elif len(phone) > 20 or len(location) > 120:
            error = "Phone number or location is too long."

        if error:
            flash(error, "danger")
            return render_template("register.html", form=request.form)

        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (full_name, email, password_hash, phone, location) VALUES (?,?,?,?,?)",
                (name, email, generate_password_hash(password), phone, location),
            )
            log_activity(conn, cur.lastrowid, "farmer", "registered")
            conn.commit()
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "danger")
            return render_template("register.html", form=request.form)
        except sqlite3.Error:
            flash("Database error. Please try again later.", "danger")
            return render_template("register.html", form=request.form)
        finally:
            conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_next(request.values.get("next"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ip = request.remote_addr or "unknown"
        k_user, k_ip = f"login:{email}:{ip}", f"ip:{ip}"

        wait = locked_seconds(k_user, k_ip)
        if wait:
            flash(f"Too many failed attempts. Please try again in {math.ceil(wait / 60)} minute(s).", "danger")
            return render_template("login.html", next_url=next_url), 429

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html", next_url=next_url)
        conn = get_db()
        try:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        except sqlite3.Error:
            flash("Database error. Please try again later.", "danger")
            return render_template("login.html", next_url=next_url)
        finally:
            conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            record_failure(k_user, MAX_FAILS)
            record_failure(k_ip, MAX_FAILS_IP)
            flash("Invalid email or password.", "danger")
            return render_template("login.html", next_url=next_url)
        if not user["is_active"]:
            flash("Your account has been deactivated. Contact the administrator.", "danger")
            return render_template("login.html", next_url=next_url)

        clear_failures(k_user)
        prev_lang = i18n.valid_lang(session.get("lang")) or i18n.valid_lang(request.cookies.get("lang"))
        session.clear()                       # prevents session fixation
        session.permanent = True              # applies the 2-hour idle timeout
        session["_csrf"] = secrets.token_hex(16)
        session["user_id"] = user["id"]
        session["name"] = user["full_name"]
        session["role"] = user["role"]
        if user["role"] == "admin" and secrets.compare_digest(password.encode(), DEFAULT_ADMIN_PASSWORD.encode()):
            session["default_pw"] = True      # shows the "change your password" banner
        conn = get_db()
        try:
            pref = conn.execute("SELECT language FROM user_preferences WHERE user_id=?", (user["id"],)).fetchone()
            if pref:
                session["lang"] = pref["language"]
            elif prev_lang:
                session["lang"] = prev_lang
                conn.execute("INSERT OR IGNORE INTO user_preferences (user_id, language) VALUES (?,?)", (user["id"], prev_lang))
            conn.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
            log_activity(conn, user["id"], user["role"], "login")
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
        finally:
            conn.close()
        flash(f"Welcome back, {user['full_name']}!", "success")
        return redirect(next_url or url_for("home"))
    return render_template("login.html", next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------- Farmer ----------
@app.route("/dashboard")
@role_required("farmer")
def dashboard():
    uid = session["user_id"]
    conn = get_db()
    try:
        data = dashboard_data.build(conn, uid)
        wx = weather.summary_for_user(conn, uid)
    finally:
        conn.close()
    return render_template("dashboard.html", wx=wx, **data)


@app.route("/profile", methods=["GET", "POST"])
@role_required("farmer")
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")

        error = None
        if not name or len(name) > 80:
            error = "Please enter a valid name (up to 80 characters)."
        elif phone and not phone.replace("+", "").replace(" ", "").isdigit():
            error = "Phone number may contain only digits, spaces and +."
        elif len(phone) > 20 or len(location) > 120:
            error = "Phone number or location is too long."
        elif new:
            if not check_password_hash(user["password_hash"], current):
                error = "Current password is incorrect."
            elif password_error(new):
                error = password_error(new)

        if error:
            flash(error, "danger")
        else:
            try:
                conn.execute("UPDATE users SET full_name=?, phone=?, location=? WHERE id=?",
                             (name, phone, location, user["id"]))
                if new:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (generate_password_hash(new), user["id"]))
                conn.commit()
                session["name"] = name
                flash("Profile updated successfully.", "success")
                return redirect(url_for("profile"))
            except sqlite3.Error:
                flash("Database error. Please try again.", "danger")
            finally:
                conn.close()
            conn = get_db()   # re-open so the page below can still read the user row
            user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("profile.html", user=user)


@app.route("/crop-recommendation", methods=["GET", "POST"])
@role_required("farmer")
def crop_recommendation():
    """Two modes: 'soil_test' (N, P, K, temperature, humidity, pH, rainfall -> trained model, or the rule-based
    fallback when no model is trained) and 'quick' (soil type, season, water availability -> rule-based advisory)."""
    uid = session["user_id"]
    conn = get_db()
    try:
        farms = conn.execute("SELECT * FROM farms WHERE user_id=? ORDER BY name COLLATE NOCASE", (uid,)).fetchall()
        result, info, form = None, {}, {}
        mode = request.values.get("mode", "soil_test")
        mode = mode if mode in ("soil_test", "quick") else "soil_test"

        if request.method == "POST":
            form = request.form
            location = form.get("location", "").strip()
            farm_id = form.get("farm_id", type=int)
            soil = form.get("soil_type", "").strip()
            season = form.get("season", "").strip()
            water = form.get("water_availability", "").strip()
            error, values = None, None

            if len(location) > 120:
                error = "farm.err_location_long"
            elif farm_id and not any(f["id"] == farm_id for f in farms):
                error = "farm.not_found"
            elif mode == "quick":
                error = validate_advisory(soil, season, water)
            else:
                values, error = validate_inputs(form)          # specific message, e.g. "Soil pH must be between 0 and 14."

            if error:
                flash(error, "danger")
            else:
                try:
                    if mode == "quick":
                        top = advise(soil, season, water)
                        method = "Rule-based advisory (soil type, season, water availability)"
                    else:
                        r = recommend(values)
                        top = [{"crop": r["crop"], "score": r["confidence"], "reasons": [], "water_need": None}] + \
                              [{"crop": c, "score": sc, "reasons": [], "water_need": None} for c, sc in r["alternatives"]]
                        method = r["method"]
                except Exception:
                    top = None
                    flash("Could not generate a recommendation. Please check your inputs and try again.", "danger")
                if top:
                    result = {"mode": mode, "method": method, "top": top, "soil_test": None,
                              "inputs": {"soil_type": soil, "season": season, "water": water, "location": location,
                                         **({k: v for k, v in zip(FEATURES, values)} if values else {})}}
                    nums = values or [None] * 7
                    try:
                        cur = conn.execute(
                            "INSERT INTO recommendations (user_id, farm_id, mode, soil_type, season, water_availability, location, "
                            "nitrogen, phosphorus, potassium, temperature, humidity, ph, rainfall, top_crop, top_score, method, "
                            "result_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (uid, farm_id, mode, soil or None, season or None, water or None, location or None, *nums,
                             top[0]["crop"], top[0]["score"], method, json.dumps(result)))
                        log_activity(conn, uid, "farmer", "recommendation", top[0]["crop"])
                        conn.commit()
                        result["id"] = cur.lastrowid
                    except sqlite3.Error:
                        conn.rollback()
                        flash("The recommendation was generated but could not be saved to your history.", "warning")
                    info = related_crop_info(conn, result)
    finally:
        conn.close()
    return render_template("crop_recommendation.html", result=result, info=info, form=form, farms=farms, mode=mode,
                           limits=LIMITS, soils=SOILS, seasons=SEASONS, season_hints=SEASON_HINTS,
                           water_levels=WATER_LEVELS, ml_ready=using_ml())


@app.route("/disease-detection", methods=["GET", "POST"])
@role_required("farmer")
def disease_detection():
    uid = session["user_id"]

    if request.method == "POST":
        filename, error = save_image(
            request.files.get("leaf_image"),
            app.config["UPLOAD_FOLDER"]
        )

        if error:
            flash(error, "danger")
            return redirect(url_for("disease_detection"))

        path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        # Call Plant.id API
        try:
            api_result = analyze_plant_image(path)

            classification = [
                {
                    "name": str(item.get("name", "Unknown")),
                    "probability": float(item.get("probability") or 0)
                }
                for item in api_result["classification"]
            ]

            diseases = [
                {
                    "name": str(item.get("name", "Unknown")),
                    "probability": float(item.get("probability") or 0)
                }
                for item in api_result["diseases"]
            ]

            healthy_probability = api_result.get(
                "healthy_probability"
            )

            if healthy_probability is not None:
                healthy_probability = float(healthy_probability)

        except PlantHealthAPIError as exc:
            remove_upload(filename)
            flash(f"Plant.id API error: {exc}", "danger")
            return redirect(url_for("disease_detection"))

        except Exception:
            remove_upload(filename)
            app.logger.exception("Plant.id analysis failed")
            flash(
                "Image analysis failed. Please try again.",
                "danger"
            )
            return redirect(url_for("disease_detection"))

        # Save API suggestions in the existing predictions table.
        plant_name = (
            classification[0]["name"]
            if classification
            else "Unknown plant"
        )

        disease_name = (
            diseases[0]["name"]
            if diseases
            else "No disease suggestion"
        )

        disease_confidence = (
            diseases[0]["probability"] * 100
            if diseases
            else 0.0
        )

        conn = get_db()

        try:
            cur = conn.execute(
                "INSERT INTO predictions "
                "(user_id, crop_name, disease_name, confidence, image_path) "
                "VALUES (?,?,?,?,?)",
                (
                    uid,
                    plant_name,
                    disease_name,
                    disease_confidence,
                    filename
                )
            )

            prediction_id = cur.lastrowid

            log_activity(
                conn,
                uid,
                "farmer",
                "prediction",
                f"Plant.id analysis: {plant_name} - {disease_name}"
            )

            conn.commit()

        except sqlite3.Error:
            conn.rollback()
            remove_upload(filename)
            flash(
                "Database error while saving the result.",
                "danger"
            )
            return redirect(url_for("disease_detection"))

        finally:
            conn.close()

        # Keep the API response for the result page.
        session["last_prediction"] = {
            "id": prediction_id,
            "api_used": True,
            "classification": classification,
            "diseases": diseases,
            "healthy_probability": healthy_probability
        }

        return redirect(
            url_for(
                "disease_result",
                prediction_id=prediction_id
            )
        )

    # GET request: show upload page and recent predictions.
    conn = get_db()

    recent = conn.execute(
        "SELECT * FROM predictions WHERE user_id=? "
        "ORDER BY id DESC LIMIT 5",
        (uid,)
    ).fetchall()

    conn.close()

    return render_template(
        "disease_detection.html",
        recent=recent,
        api_configured=bool(os.getenv("PLANT_HEALTH_API_KEY"))
    )


@app.route("/disease-result/<int:prediction_id>")
@role_required("farmer")
def disease_result(prediction_id):
    last = session.get("last_prediction")

    api_used = bool(
        last
        and last.get("id") == prediction_id
        and last.get("api_used")
    )

    conn = get_db()
    p = conn.execute(
        "SELECT * FROM predictions WHERE id=? AND user_id=?",
        (prediction_id, session["user_id"])
    ).fetchone()

    if not p:
        conn.close()
        abort(404)

    info = None if api_used else find_disease_info(
        conn, p["crop_name"], p["disease_name"]
    )
    conn.close()

    classification = last.get("classification", []) if api_used else []
    diseases = last.get("diseases", []) if api_used else []
    healthy_probability = last.get("healthy_probability") if api_used else None

    confidence = float(p["confidence"] or 0)

    return render_template(
        "disease_result.html",
        p=p,
        info=info,
        top=[],
        supported=[],
        is_tuber=False,
        low=confidence < 60,
        threshold=60,
        healthy=(p["disease_name"] or "").lower() == "healthy",
        api_used=api_used,
        classification=classification,
        diseases=diseases,
        healthy_probability=healthy_probability
    )

# ---------- Admin ----------
@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    """Admin overview: every figure and chart is computed from the database (utils/analytics.py)."""
    conn = get_db()
    try:
        data = analytics.build(conn)
    finally:
        conn.close()
    return render_template("admin/dashboard.html", **data)


@app.route("/admin/users")
@role_required("admin")
def admin_users():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    conn = get_db()
    users = conn.execute(
        "SELECT u.*, (SELECT COUNT(*) FROM disease_reports r WHERE r.user_id=u.id) AS report_count "
        "FROM users u WHERE u.role='farmer' AND (u.full_name LIKE ? OR u.email LIKE ?) "
        "ORDER BY u.id DESC", (like, like)).fetchall()
    conn.close()
    return render_template("admin/users.html", users=users, q=q)


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_user(user_id):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET is_active = 1 - is_active WHERE id=? AND role='farmer'", (user_id,))
        conn.commit()
        flash("User status updated.", "success")
    except sqlite3.Error:
        flash("Database error. Please try again.", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_user(user_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM users WHERE id=? AND role='farmer'", (user_id,))
        conn.commit()
        flash("User and related records deleted.", "success")
    except sqlite3.Error:
        flash("Database error. Please try again.", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_users"))


# ---------- Feature modules ----------
# Each module defines register(app). Missing modules are skipped so the app still starts.
for _name in ("public_routes", "farm_routes", "history_routes", "notification_routes", "weather_routes",
              "irrigation_routes", "fertilizer_routes", "chat_routes", "market_routes", "calendar_routes",
              "scheme_routes", "export_routes", "report_routes", "advisory_routes", "admin_routes"):
    try:
        importlib.import_module(_name).register(app)
    except ModuleNotFoundError as exc:
        if exc.name != _name:   # a real missing dependency inside the module should still raise
            raise


if __name__ == "__main__":
    # Debug mode exposes an interactive debugger, so it is OFF unless you opt in:
    #   Windows:   set FLASK_DEBUG=1        Linux/Mac:  export FLASK_DEBUG=1
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
