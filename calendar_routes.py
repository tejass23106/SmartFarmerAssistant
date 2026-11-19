"""Farming calendar: crop plans with estimated stages and reminders, plus personal activities.

All dates produced from a sowing date are ESTIMATES (flagged is_estimate=1). They are rough, general timings;
the real schedule depends on variety, weather and local advice. Fertilizer reminders name no quantities."""
import calendar as cal_mod
import sqlite3
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, session, url_for

from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required

# crop: (total days estimate, [(stage, start_day, end_day)], irrigation interval days, [(day, fertilizer reminder)])
PLANS = {
 "Rice": (120, [("Nursery sowing", 0, 25), ("Transplanting", 25, 30), ("Tillering", 30, 55), ("Panicle initiation", 55, 75),
                ("Flowering and grain filling", 75, 105), ("Maturity and harvest", 105, 120)], 4,
          [(15, "nitrogen top-dressing as advised by your soil test"), (40, "second nitrogen top-dressing (split dose)")]),
 "Wheat": (120, [("Sowing", 0, 5), ("Crown root initiation", 20, 25), ("Tillering", 25, 45), ("Jointing", 45, 65),
                 ("Flowering", 65, 85), ("Grain filling", 85, 105), ("Maturity and harvest", 105, 120)], 15,
          [(0, "basal dose of phosphorus and potassium at sowing"), (25, "first nitrogen top-dressing")]),
 "Maize": (100, [("Sowing", 0, 5), ("Vegetative growth", 5, 40), ("Tasseling and silking", 40, 60), ("Grain filling", 60, 85),
                 ("Maturity and harvest", 85, 100)], 10,
          [(0, "basal dose at sowing as advised by your soil test"), (25, "first nitrogen top-dressing")]),
 "Potato": (100, [("Planting", 0, 10), ("Sprouting and emergence", 10, 25), ("Vegetative growth", 25, 50), ("Tuber initiation", 50, 65),
                  ("Tuber bulking", 65, 90), ("Maturity and harvest", 90, 100)], 7,
          [(0, "basal dose at planting"), (30, "earthing up with nitrogen top-dressing")]),
 "Tomato": (120, [("Nursery", 0, 25), ("Transplanting", 25, 30), ("Vegetative growth", 30, 50), ("Flowering and fruit set", 50, 75),
                  ("Fruiting and harvest", 75, 120)], 3,
          [(20, "basal dose at transplanting as advised by your soil test"), (45, "top-dressing after first flowering")]),
 "Cotton": (180, [("Sowing", 0, 10), ("Seedling", 10, 40), ("Squaring", 40, 70), ("Flowering and boll formation", 70, 120),
                  ("Boll opening", 120, 160), ("Picking", 160, 180)], 12,
          [(0, "basal dose at sowing"), (45, "first top-dressing")]),
 "Sugarcane": (330, [("Planting (setts)", 0, 30), ("Germination and tillering", 30, 120), ("Grand growth", 120, 240),
                     ("Maturity and ripening", 240, 300), ("Harvest", 300, 330)], 10,
          [(45, "first top-dressing"), (120, "second top-dressing")]),
 "Groundnut": (110, [("Sowing", 0, 10), ("Vegetative growth", 10, 35), ("Flowering and pegging", 35, 60),
                     ("Pod development", 60, 90), ("Maturity and harvest", 90, 110)], 12,
          [(0, "basal dose of phosphorus and gypsum as advised by your soil test")]),
 "Ragi": (120, [("Nursery or sowing", 0, 20), ("Transplanting or thinning", 20, 30), ("Tillering", 30, 55),
                ("Ear head emergence", 55, 80), ("Grain filling", 80, 105), ("Maturity and harvest", 105, 120)], 15,
          [(0, "basal dose at sowing as advised by your soil test")]),
 "Chickpea": (110, [("Sowing", 0, 7), ("Vegetative growth", 7, 40), ("Flowering", 40, 65), ("Pod development", 65, 95),
                    ("Maturity and harvest", 95, 110)], 15,
          [(0, "basal phosphorus at sowing as advised by your soil test")]),
}
KINDS = ("custom", "irrigation", "fertilizer", "growth_stage", "harvest")
MAX_PLANS = 20


def _date(text):
    try:
        d = date.fromisoformat((text or "").strip())
    except ValueError:
        return None
    return d if date(2000, 1, 1) <= d <= date(2100, 12, 31) else None


def create_plan(conn, uid, crop, sow, farm_id, notes):
    total, stages, irr, fert = PLANS[crop]
    cur = conn.execute("INSERT INTO crop_plans (user_id, farm_id, crop, sowing_date, notes) VALUES (?,?,?,?,?)",
                       (uid, farm_id, crop, sow.isoformat(), notes))
    pid = cur.lastrowid
    rows = []
    for name, a, b in stages:
        rows.append((uid, pid, "growth_stage", f"{crop}: {name}", "Estimated stage (general timing).",
                     (sow + timedelta(days=a)).isoformat(), (sow + timedelta(days=b)).isoformat(), 1, 1))
    step = max(irr, total // 25)
    for day in range(0, total, step):
        rows.append((uid, pid, "irrigation", f"{crop}: check soil moisture and irrigate if needed",
                     "Reminder. Check before watering; see Smart Irrigation.", (sow + timedelta(days=day)).isoformat(), None, 1, 1))
    for day, text in fert:
        rows.append((uid, pid, "fertilizer", f"{crop}: fertilizer reminder", text.capitalize() + ". No quantities here; follow your soil test.",
                     (sow + timedelta(days=day)).isoformat(), None, 1, 1))
    rows.append((uid, pid, "harvest", f"{crop}: expected harvest period", "Estimated window; depends on variety and weather.",
                 (sow + timedelta(days=total - 10)).isoformat(), (sow + timedelta(days=total)).isoformat(), 1, 1))
    conn.executemany("INSERT INTO calendar_activities (user_id, plan_id, kind, title, description, start_date, end_date, "
                     "is_estimate, auto) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return pid, len(rows)


def register(app):

    @app.route("/calendar")
    @role_required("farmer")
    def calendar_page():
        uid = session["user_id"]
        today = date.today()
        try:
            y, m = int(request.args.get("y", today.year)), int(request.args.get("m", today.month))
            if not (2000 <= y <= 2100 and 1 <= m <= 12):
                raise ValueError
        except ValueError:
            y, m = today.year, today.month
        first = date(y, m, 1)
        last = date(y, m, cal_mod.monthrange(y, m)[1])
        prev_m = (first - timedelta(days=1))
        next_m = (last + timedelta(days=1))
        conn = get_db()
        try:
            acts = conn.execute("SELECT * FROM calendar_activities WHERE user_id=? AND start_date BETWEEN ? AND ? ORDER BY start_date, id",
                                (uid, first.isoformat(), last.isoformat())).fetchall()
            upcoming = conn.execute("SELECT * FROM calendar_activities WHERE user_id=? AND completed=0 AND start_date >= ? "
                                    "ORDER BY start_date, id LIMIT 25", (uid, today.isoformat())).fetchall()
            plans = conn.execute("SELECT p.*, f.name farm_name FROM crop_plans p LEFT JOIN farms f ON f.id=p.farm_id "
                                 "WHERE p.user_id=? ORDER BY p.id DESC", (uid,)).fetchall()
            farms = conn.execute("SELECT id, name FROM farms WHERE user_id=? ORDER BY name COLLATE NOCASE", (uid,)).fetchall()
        finally:
            conn.close()
        by_day = {}
        for a in acts:
            by_day.setdefault(a["start_date"], []).append(a)
        weeks = cal_mod.Calendar(firstweekday=0).monthdatescalendar(y, m)
        return render_template("calendar.html", weeks=weeks, y=y, m=m, by_day=by_day, today=today.isoformat(),
                               upcoming=upcoming, plans=plans, farms=farms, crops=list(PLANS), kinds=KINDS,
                               prev=(prev_m.year, prev_m.month), next=(next_m.year, next_m.month), month=first.month)

    @app.route("/calendar/plan", methods=["POST"])
    @role_required("farmer")
    def calendar_plan_create():
        uid = session["user_id"]
        crop, sow = request.form.get("crop", "").strip(), _date(request.form.get("sowing_date"))
        farm_id = request.form.get("farm_id", type=int)
        notes = request.form.get("notes", "").strip()[:300] or None
        today = date.today()
        if crop not in PLANS:
            flash("cal.err_crop", "danger")
        elif not sow or abs((sow - today).days) > 365:
            flash("cal.err_date", "danger")
        else:
            conn = get_db()
            try:
                if conn.execute("SELECT COUNT(*) c FROM crop_plans WHERE user_id=?", (uid,)).fetchone()["c"] >= MAX_PLANS:
                    flash("cal.plan_limit", "warning")
                elif farm_id and not conn.execute("SELECT 1 FROM farms WHERE id=? AND user_id=?", (farm_id, uid)).fetchone():
                    flash("farm.not_found", "danger")
                else:
                    _, n = create_plan(conn, uid, crop, sow, farm_id or None, notes)
                    log_activity(conn, uid, "farmer", "calendar_plan", crop)
                    conn.commit()
                    flash("cal.plan_created", "success")
            except sqlite3.Error:
                conn.rollback()
                flash("err.database", "danger")
            finally:
                conn.close()
        return redirect(url_for("calendar_page"))

    @app.route("/calendar/plan/<int:plan_id>/delete", methods=["POST"])
    @role_required("farmer")
    def calendar_plan_delete(plan_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM crop_plans WHERE id=? AND user_id=?", (plan_id, session["user_id"]))
            conn.commit()
            flash("cal.plan_deleted" if cur.rowcount else "cal.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("calendar_page"))

    @app.route("/calendar/activity", methods=["POST"])
    @role_required("farmer")
    def calendar_activity_create():
        uid = session["user_id"]
        title = request.form.get("title", "").strip()
        when = _date(request.form.get("start_date"))
        desc = request.form.get("description", "").strip()[:300] or None
        kind = request.form.get("kind", "custom")
        kind = kind if kind in KINDS else "custom"
        if not title or len(title) > 120:
            flash("cal.err_title", "danger")
        elif not when:
            flash("cal.err_date", "danger")
        else:
            conn = get_db()
            try:
                conn.execute("INSERT INTO calendar_activities (user_id, kind, title, description, start_date, is_estimate, auto) "
                             "VALUES (?,?,?,?,?,0,0)", (uid, kind, title, desc, when.isoformat()))
                conn.commit()
                flash("cal.added", "success")
            except sqlite3.Error:
                conn.rollback()
                flash("err.database", "danger")
            finally:
                conn.close()
        return redirect(url_for("calendar_page", y=when.year if when else None, m=when.month if when else None))

    @app.route("/calendar/activity/<int:act_id>/edit", methods=["POST"])
    @role_required("farmer")
    def calendar_activity_edit(act_id):
        title = request.form.get("title", "").strip()
        when = _date(request.form.get("start_date"))
        desc = request.form.get("description", "").strip()[:300] or None
        if not title or len(title) > 120:
            flash("cal.err_title", "danger")
        elif not when:
            flash("cal.err_date", "danger")
        else:
            conn = get_db()
            try:
                cur = conn.execute("UPDATE calendar_activities SET title=?, start_date=?, description=? WHERE id=? AND user_id=?",
                                   (title, when.isoformat(), desc, act_id, session["user_id"]))
                conn.commit()
                flash("cal.updated" if cur.rowcount else "cal.not_found", "success" if cur.rowcount else "danger")
            except sqlite3.Error:
                conn.rollback()
                flash("err.database", "danger")
            finally:
                conn.close()
        return redirect(url_for("calendar_page"))

    @app.route("/calendar/activity/<int:act_id>/toggle", methods=["POST"])
    @role_required("farmer")
    def calendar_activity_toggle(act_id):
        conn = get_db()
        try:
            cur = conn.execute("UPDATE calendar_activities SET completed = 1 - completed WHERE id=? AND user_id=?",
                               (act_id, session["user_id"]))
            conn.commit()
            if not cur.rowcount:
                flash("cal.not_found", "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(request.referrer if request.referrer and request.host in request.referrer else url_for("calendar_page"))

    @app.route("/calendar/activity/<int:act_id>/delete", methods=["POST"])
    @role_required("farmer")
    def calendar_activity_delete(act_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM calendar_activities WHERE id=? AND user_id=?", (act_id, session["user_id"]))
            conn.commit()
            flash("cal.deleted" if cur.rowcount else "cal.not_found", "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")
        finally:
            conn.close()
        return redirect(url_for("calendar_page"))
