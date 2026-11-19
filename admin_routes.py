"""Admin management of crops and diseases (the knowledge the AI results are linked to)."""
import sqlite3

from flask import render_template, request, redirect, url_for, flash

from utils.database import get_db
from utils.helpers import role_required

CROP_SPEC = [
    ("name", "Crop name", 60, True),
    ("description", "Description", 500, False),
    ("suitable_conditions", "Suitable conditions", 500, False),
    ("cultivation_advice", "Cultivation advice", 1000, False),
]
DISEASE_SPEC = [
    ("name", "Disease name", 80, True),
    ("class_label", "Class label", 120, False),
    ("description", "Description", 1000, False),
    ("symptoms", "Symptoms", 1000, False),
    ("prevention", "Prevention", 1000, False),
    ("management", "Management suggestions", 1000, False),
]


def _validate(form, spec):
    data = {}
    for key, label, maxlen, required in spec:
        val = form.get(key, "").strip()
        if required and not val:
            return data, f"{label} is required."
        if len(val) > maxlen:
            return data, f"{label} is too long (maximum {maxlen} characters)."
        data[key] = val
    return data, None


def _label(crop_name, disease_name):
    """Default class label in the dataset folder style: Tomato___Early_blight."""
    clean = lambda s: "_".join(s.split())
    return f"{clean(crop_name)}___{clean(disease_name)}"


def register(app):

    # ------------------------------------------------------------------- crops
    def _crops_page(form):
        conn = get_db()
        rows = conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM diseases d WHERE d.crop_id=c.id) AS disease_count "
            "FROM crops c ORDER BY c.name").fetchall()
        conn.close()
        return render_template("admin/crops.html", rows=rows, form=form)

    @app.route("/admin/crops")
    @role_required("admin")
    def admin_crops():
        form = {}
        edit = request.args.get("edit", type=int)
        if edit:
            conn = get_db()
            row = conn.execute("SELECT * FROM crops WHERE id=?", (edit,)).fetchone()
            conn.close()
            if row:
                form = dict(row)
            else:
                flash("Crop not found.", "danger")
        return _crops_page(form)

    @app.route("/admin/crops/save", methods=["POST"])
    @role_required("admin")
    def admin_crop_save():
        cid = request.form.get("id", type=int)
        data, error = _validate(request.form, CROP_SPEC)
        if error:
            flash(error, "danger")
            return _crops_page(request.form)

        values = (data["name"], data["description"], data["suitable_conditions"], data["cultivation_advice"])
        conn = get_db()
        ok = True
        try:
            if cid:
                cur = conn.execute("UPDATE crops SET name=?, description=?, suitable_conditions=?, "
                                   "cultivation_advice=? WHERE id=?", values + (cid,))
                if cur.rowcount == 0:
                    flash("Crop not found.", "danger")
                    ok = False
                else:
                    flash("Crop updated.", "success")
            else:
                conn.execute("INSERT INTO crops (name, description, suitable_conditions, cultivation_advice) "
                             "VALUES (?,?,?,?)", values)
                flash("Crop added.", "success")
            conn.commit()
        except sqlite3.IntegrityError:
            flash("A crop with this name already exists.", "danger")
            ok = False
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
            ok = False
        finally:
            conn.close()
        if not ok:
            return _crops_page(request.form)
        return redirect(url_for("admin_crops"))

    @app.route("/admin/crops/<int:crop_id>/delete", methods=["POST"])
    @role_required("admin")
    def admin_crop_delete(crop_id):
        conn = get_db()
        try:
            n = conn.execute("SELECT COUNT(*) c FROM diseases WHERE crop_id=?", (crop_id,)).fetchone()["c"]
            if n:
                flash(f"This crop still has {n} disease record(s). Delete those first.", "warning")
            else:
                cur = conn.execute("DELETE FROM crops WHERE id=?", (crop_id,))
                conn.commit()
                flash("Crop deleted." if cur.rowcount else "Crop not found.",
                      "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_crops"))

    # ---------------------------------------------------------------- diseases
    def _diseases_page(form):
        crop_filter = request.args.get("crop", type=int)
        sql = ("SELECT d.*, c.name AS crop_name FROM diseases d "
               "LEFT JOIN crops c ON c.id = d.crop_id WHERE 1=1")
        params = []
        if crop_filter:
            sql += " AND d.crop_id=?"
            params.append(crop_filter)
        conn = get_db()
        rows = conn.execute(sql + " ORDER BY c.name, d.name", params).fetchall()
        crops = conn.execute("SELECT id, name FROM crops ORDER BY name").fetchall()
        conn.close()
        return render_template("admin/diseases.html", rows=rows, crops=crops, form=form,
                               crop_filter=crop_filter)

    @app.route("/admin/diseases")
    @role_required("admin")
    def admin_diseases():
        form = {}
        edit = request.args.get("edit", type=int)
        if edit:
            conn = get_db()
            row = conn.execute("SELECT * FROM diseases WHERE id=?", (edit,)).fetchone()
            conn.close()
            if row:
                form = dict(row)
            else:
                flash("Disease not found.", "danger")
        return _diseases_page(form)

    @app.route("/admin/diseases/save", methods=["POST"])
    @role_required("admin")
    def admin_disease_save():
        did = request.form.get("id", type=int)
        crop_id = request.form.get("crop_id", type=int)
        data, error = _validate(request.form, DISEASE_SPEC)

        conn = get_db()
        ok = True
        try:
            crop = conn.execute("SELECT name FROM crops WHERE id=?", (crop_id,)).fetchone() if crop_id else None
            if not error and not crop:
                error = "Please choose a crop."
            if not error:
                dup = conn.execute("SELECT id FROM diseases WHERE crop_id=? AND LOWER(name)=LOWER(?) AND id<>?",
                                   (crop_id, data["name"], did or 0)).fetchone()
                if dup:
                    error = "This disease already exists for the selected crop."
            if error:
                flash(error, "danger")
                ok = False
            else:
                label = data["class_label"] or _label(crop["name"], data["name"])
                values = (crop_id, data["name"], label, data["description"], data["symptoms"],
                          data["prevention"], data["management"])
                if did:
                    cur = conn.execute("UPDATE diseases SET crop_id=?, name=?, class_label=?, description=?, "
                                       "symptoms=?, prevention=?, management=? WHERE id=?", values + (did,))
                    if cur.rowcount == 0:
                        flash("Disease not found.", "danger")
                        ok = False
                    else:
                        flash("Disease updated.", "success")
                else:
                    conn.execute("INSERT INTO diseases (crop_id, name, class_label, description, symptoms, "
                                 "prevention, management) VALUES (?,?,?,?,?,?,?)", values)
                    flash("Disease added.", "success")
                conn.commit()
        except sqlite3.IntegrityError:
            flash("A disease with this class label already exists.", "danger")
            ok = False
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
            ok = False
        finally:
            conn.close()
        if not ok:
            return _diseases_page(request.form)
        return redirect(url_for("admin_diseases"))

    @app.route("/admin/diseases/<int:disease_id>/delete", methods=["POST"])
    @role_required("admin")
    def admin_disease_delete(disease_id):
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM diseases WHERE id=?", (disease_id,))
            conn.commit()
            flash("Disease deleted." if cur.rowcount else "Disease not found.",
                  "success" if cur.rowcount else "danger")
        except sqlite3.Error:
            flash("Database error. Please try again.", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_diseases"))
