"""Disease reporting: farmer report submission/history and admin report management."""
import os
import sqlite3
from datetime import date, datetime

from flask import render_template, request, redirect, url_for, session, flash, abort

from utils.activity import log_activity, notify
from utils.database import get_db
from utils.helpers import role_required, save_image

STATUSES = ("Pending", "Reviewed", "Resolved")


def _valid_date(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _disease_info(conn, crop, disease):
    return conn.execute(
        "SELECT d.* FROM diseases d JOIN crops c ON c.id = d.crop_id "
        "WHERE LOWER(c.name)=LOWER(?) AND LOWER(d.name)=LOWER(?)", (crop, disease)).fetchone()


def _remove_if_unused(conn, filename, folder):
    """Delete an uploaded image only when no prediction or report still uses it."""
    if not filename:
        return
    used = conn.execute(
        "SELECT 1 FROM predictions WHERE image_path=? UNION ALL "
        "SELECT 1 FROM disease_reports WHERE image_path=? LIMIT 1", (filename, filename)).fetchone()
    if not used:
        try:
            os.remove(os.path.join(folder, filename))
        except OSError:
            pass


def register(app):
    folder = app.config["UPLOAD_FOLDER"]

    # ------------------------------------------------------------------ farmer
    @app.route("/reports/new", methods=["GET", "POST"])
    @role_required("farmer")
    def report_new():
        uid = session["user_id"]
        pid = request.values.get("prediction_id", type=int)
        conn = get_db()
        try:
            pred = None
            if pid:
                pred = conn.execute("SELECT * FROM predictions WHERE id=? AND user_id=?", (pid, uid)).fetchone()
                if not pred:
                    abort(404)
                dup = conn.execute("SELECT id FROM disease_reports WHERE prediction_id=? AND user_id=?",
                                   (pid, uid)).fetchone()
                if dup:
                    flash("You have already reported this prediction.", "info")
                    return redirect(url_for("report_detail", report_id=dup["id"]))

            if request.method == "POST":
                form = request.form
                crop = form.get("crop_name", "").strip()
                disease = form.get("disease_name", "").strip()
                location = form.get("location", "").strip()
                description = form.get("description", "").strip()
                rdate = _valid_date(form.get("report_date", "").strip())

                error = None
                if not crop or not disease:
                    error = "Crop name and disease name are required."
                elif len(crop) > 60 or len(disease) > 80:
                    error = "Crop or disease name is too long."
                elif not location:
                    error = "Please enter your location or general area."
                elif len(location) > 120:
                    error = "Location is too long (maximum 120 characters)."
                elif len(description) > 1000:
                    error = "Description is too long (maximum 1000 characters)."
                elif rdate is None:
                    error = "Please enter a valid date."
                elif rdate > date.today():
                    error = "The report date cannot be in the future."

                filename, new_file = None, None
                if not error:
                    if pred:
                        filename = pred["image_path"]
                    else:
                        filename, error = save_image(request.files.get("image"), folder)
                        new_file = filename

                if not error:
                    try:
                        conn.execute(
                            "INSERT INTO disease_reports (user_id, prediction_id, crop_name, disease_name, "
                            "image_path, location, description, report_date, confidence) VALUES (?,?,?,?,?,?,?,?,?)",
                            (uid, pred["id"] if pred else None, crop, disease, filename, location,
                             description, rdate.isoformat(), pred["confidence"] if pred else None))
                        log_activity(conn, uid, "farmer", "report", f"{crop} - {disease}")
                        conn.commit()
                        flash("Your disease report has been submitted successfully.", "success")
                        return redirect(url_for("reports"))
                    except sqlite3.Error:
                        error = "Database error while saving the report. Please try again."
                        _remove_if_unused(conn, new_file, folder)
                flash(error, "danger")
            else:
                user = conn.execute("SELECT location FROM users WHERE id=?", (uid,)).fetchone()
                form = {
                    "crop_name": pred["crop_name"] if pred else "",
                    "disease_name": pred["disease_name"] if pred else "",
                    "location": (user["location"] or "") if user else "",
                    "description": "",
                    "report_date": date.today().isoformat(),
                }

            crops = conn.execute("SELECT name FROM crops ORDER BY name").fetchall()
            diseases = conn.execute("SELECT DISTINCT name FROM diseases ORDER BY name").fetchall()
            return render_template("report_form.html", form=form, pred=pred, crops=crops,
                                   diseases=diseases, today=date.today().isoformat())
        finally:
            conn.close()

    @app.route("/reports")
    @role_required("farmer")
    def reports():
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        start = request.args.get("start", "").strip()
        end = request.args.get("end", "").strip()

        sql, params = "SELECT * FROM disease_reports WHERE user_id=?", [session["user_id"]]
        if q:
            sql += " AND (crop_name LIKE ? OR disease_name LIKE ? OR location LIKE ? OR description LIKE ?)"
            params += [f"%{q}%"] * 4
        if status in STATUSES:
            sql += " AND status=?"
            params.append(status)
        if _valid_date(start):
            sql += " AND report_date >= ?"
            params.append(start)
        if _valid_date(end):
            sql += " AND report_date <= ?"
            params.append(end)
        sql += " ORDER BY report_date DESC, id DESC"

        conn = get_db()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return render_template("reports.html", reports=rows, q=q, status=status, start=start,
                               end=end, statuses=STATUSES)

    @app.route("/reports/<int:report_id>")
    @role_required("farmer")
    def report_detail(report_id):
        conn = get_db()
        r = conn.execute("SELECT * FROM disease_reports WHERE id=? AND user_id=?",
                         (report_id, session["user_id"])).fetchone()
        if not r:
            conn.close()
            abort(404)
        info = _disease_info(conn, r["crop_name"], r["disease_name"])
        conn.close()
        return render_template("report_detail.html", r=r, info=info, reporter=None,
                               is_admin=False, statuses=STATUSES)

    @app.route("/reports/<int:report_id>/delete", methods=["POST"])
    @role_required("farmer")
    def report_delete(report_id):
        conn = get_db()
        try:
            r = conn.execute("SELECT * FROM disease_reports WHERE id=? AND user_id=?",
                             (report_id, session["user_id"])).fetchone()
            if not r:
                abort(404)
            if r["status"] != "Pending":
                flash("Only pending reports can be deleted.", "warning")
                return redirect(url_for("report_detail", report_id=report_id))
            conn.execute("DELETE FROM disease_reports WHERE id=?", (report_id,))
            conn.commit()
            _remove_if_unused(conn, r["image_path"], folder)
            flash("Report deleted.", "success")
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
        finally:
            conn.close()
        return redirect(url_for("reports"))

    # ------------------------------------------------------------------- admin
    @app.route("/admin/reports")
    @role_required("admin")
    def admin_reports():
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()

        sql = ("SELECT r.*, u.full_name, u.email FROM disease_reports r "
               "JOIN users u ON u.id = r.user_id WHERE 1=1")
        params = []
        if q:
            sql += (" AND (r.crop_name LIKE ? OR r.disease_name LIKE ? OR r.location LIKE ? "
                    "OR u.full_name LIKE ?)")
            params += [f"%{q}%"] * 4
        if status in STATUSES:
            sql += " AND r.status=?"
            params.append(status)
        sql += " ORDER BY r.id DESC"

        conn = get_db()
        rows = conn.execute(sql, params).fetchall()
        raw = {x["status"]: x["c"] for x in conn.execute(
            "SELECT status, COUNT(*) c FROM disease_reports GROUP BY status")}
        conn.close()
        counts = {s: raw.get(s, 0) for s in STATUSES}
        return render_template("admin/reports.html", reports=rows, q=q, status=status,
                               statuses=STATUSES, counts=counts)

    @app.route("/admin/reports/<int:report_id>")
    @role_required("admin")
    def admin_report_detail(report_id):
        conn = get_db()
        r = conn.execute("SELECT * FROM disease_reports WHERE id=?", (report_id,)).fetchone()
        if not r:
            conn.close()
            abort(404)
        reporter = conn.execute("SELECT full_name, email, phone FROM users WHERE id=?",
                                (r["user_id"],)).fetchone()
        info = _disease_info(conn, r["crop_name"], r["disease_name"])
        conn.close()
        return render_template("report_detail.html", r=r, info=info, reporter=reporter,
                               is_admin=True, statuses=STATUSES)

    @app.route("/admin/reports/<int:report_id>/status", methods=["POST"])
    @role_required("admin")
    def admin_report_status(report_id):
        status = request.form.get("status", "")
        if status not in STATUSES:
            flash("Invalid status selected.", "danger")
        else:
            conn = get_db()
            try:
                cur = conn.execute("UPDATE disease_reports SET status=? WHERE id=?", (status, report_id))
                row = conn.execute("SELECT user_id, crop_name, disease_name FROM disease_reports WHERE id=?", (report_id,)).fetchone()
                if cur.rowcount and row:
                    label = {"Reviewed": "Under Review"}.get(status, status)
                    notify(conn, row["user_id"], f"Report #{report_id} is now: {label}",
                           f"{row['crop_name']} - {row['disease_name']}", f"/reports/{report_id}", "report")
                    log_activity(conn, session["user_id"], "admin", "report_status", f"#{report_id} -> {status}")
                conn.commit()
                flash(f"Report #{report_id} marked as {status}." if cur.rowcount
                      else "Report not found.", "success" if cur.rowcount else "danger")
            except sqlite3.Error:
                flash("Database error. Please try again.", "danger")
            finally:
                conn.close()
        if request.form.get("back") == "detail":
            return redirect(url_for("admin_report_detail", report_id=report_id))
        return redirect(url_for("admin_reports"))

    @app.route("/admin/reports/<int:report_id>/delete", methods=["POST"])
    @role_required("admin")
    def admin_report_delete(report_id):
        conn = get_db()
        try:
            r = conn.execute("SELECT image_path FROM disease_reports WHERE id=?", (report_id,)).fetchone()
            if not r:
                flash("Report not found.", "danger")
            else:
                conn.execute("DELETE FROM disease_reports WHERE id=?", (report_id,))
                conn.commit()
                _remove_if_unused(conn, r["image_path"], folder)
                flash(f"Report #{report_id} deleted.", "success")
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_reports"))
