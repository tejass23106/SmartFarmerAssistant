"""Data for the farmer dashboard: every value comes from database rows (or the weather service, fetched by the caller)."""
import json
from datetime import date, timedelta

from utils.activity import notify


def _json(text):
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def build(conn, uid):
    def count(sql, *p):
        return conn.execute(sql, (uid,) + p).fetchone()["c"]

    stats = {"farms": count("SELECT COUNT(*) c FROM farms WHERE user_id=?"),
             "recommendations": count("SELECT COUNT(*) c FROM recommendations WHERE user_id=?"),
             "predictions": count("SELECT COUNT(*) c FROM predictions WHERE user_id=?"),
             "reports": count("SELECT COUNT(*) c FROM disease_reports WHERE user_id=?"),
             "pending": count("SELECT COUNT(*) c FROM disease_reports WHERE user_id=? AND status='Pending'")}
    d = {"stats": stats}
    d["recent_reports"] = conn.execute("SELECT * FROM disease_reports WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
    d["recent_recs"] = conn.execute("SELECT * FROM recommendations WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
    d["recent_preds"] = conn.execute("SELECT * FROM predictions WHERE user_id=? ORDER BY id DESC LIMIT 4", (uid,)).fetchall()
    d["latest_rec"] = d["recent_recs"][0] if d["recent_recs"] else None

    soil = conn.execute("SELECT * FROM soil_records WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    d["soil"] = dict(soil, summary=_json(soil["summary_json"])) if soil else None
    irr = conn.execute("SELECT * FROM irrigation_records WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    d["irrigation"] = dict(irr, summary=_json(irr["summary_json"])) if irr else None

    # market: latest stored prices for the farmer's most relevant crop
    crop = (d["latest_rec"]["top_crop"] if d["latest_rec"] else None)
    if not crop:
        farm = conn.execute("SELECT main_crop FROM farms WHERE user_id=? AND main_crop IS NOT NULL AND main_crop<>'' "
                            "ORDER BY id LIMIT 1", (uid,)).fetchone()
        crop = farm["main_crop"] if farm else None
    d["market_crop"] = crop
    d["market"] = []
    if crop:
        rows = conn.execute("SELECT * FROM market_prices WHERE commodity LIKE ? ORDER BY arrival_date DESC, id DESC LIMIT 3",
                            (crop + "%",)).fetchall()
        d["market"] = rows

    today = date.today()
    soon = (today + timedelta(days=14)).isoformat()
    d["calendar"] = conn.execute(
        "SELECT * FROM calendar_activities WHERE user_id=? AND completed=0 AND start_date BETWEEN ? AND ? "
        "ORDER BY start_date LIMIT 5", (uid, today.isoformat(), soon)).fetchall()
    d["overdue"] = count("SELECT COUNT(*) c FROM calendar_activities WHERE user_id=? AND completed=0 AND start_date < ?",
                         today.isoformat())
    # reminders -> notifications (one per activity, only for things due within two days)
    for a in conn.execute("SELECT id, title, start_date FROM calendar_activities WHERE user_id=? AND completed=0 "
                          "AND start_date BETWEEN ? AND ?", (uid, today.isoformat(), (today + timedelta(days=2)).isoformat())):
        notify(conn, uid, a["title"], f"Due {a['start_date']}", "/calendar", "reminder", f"cal:{a['id']}")
    conn.commit()
    d["notifications"] = conn.execute("SELECT * FROM notifications WHERE user_id=? AND is_read=0 ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
    d["activity"] = conn.execute("SELECT * FROM activity_log WHERE user_id=? ORDER BY id DESC LIMIT 6", (uid,)).fetchall()

    sr = {r["status"]: r["c"] for r in conn.execute(
        "SELECT status, COUNT(*) c FROM disease_reports WHERE user_id=? GROUP BY status", (uid,))}
    d["status_data"] = [sr.get(s, 0) for s in ("Pending", "Reviewed", "Resolved")]
    rows = conn.execute("SELECT disease_name, COUNT(*) c FROM predictions WHERE user_id=? GROUP BY disease_name "
                        "ORDER BY c DESC LIMIT 6", (uid,)).fetchall()
    d["d_labels"], d["d_values"] = [r["disease_name"] for r in rows], [r["c"] for r in rows]
    rows = conn.execute("SELECT top_crop, COUNT(*) c FROM recommendations WHERE user_id=? AND top_crop IS NOT NULL "
                        "GROUP BY top_crop ORDER BY c DESC LIMIT 6", (uid,)).fetchall()
    d["r_labels"], d["r_values"] = [r["top_crop"] for r in rows], [r["c"] for r in rows]
    return d
