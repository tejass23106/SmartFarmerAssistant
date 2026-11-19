"""Admin analytics. Every number and chart series comes from database rows."""
from datetime import date


def _months(n):
    """Last n months as 'YYYY-MM' strings, oldest first."""
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


def build(conn):
    def one(sql, *p):
        return conn.execute(sql, p).fetchone()[0]

    def rows(sql, *p):
        return [tuple(r) for r in conn.execute(sql, p).fetchall()]

    totals = {
        "farmers": one("SELECT COUNT(*) FROM users WHERE role='farmer'"),
        "active": one("SELECT COUNT(*) FROM users WHERE role='farmer' AND is_active=1 AND last_login >= datetime('now','-30 days')"),
        "deactivated": one("SELECT COUNT(*) FROM users WHERE role='farmer' AND is_active=0"),
        "farms": one("SELECT COUNT(*) FROM farms"),
        "predictions": one("SELECT COUNT(*) FROM predictions"),
        "recommendations": one("SELECT COUNT(*) FROM recommendations"),
        "reports": one("SELECT COUNT(*) FROM disease_reports"),
        "pending": one("SELECT COUNT(*) FROM disease_reports WHERE status='Pending'"),
        "messages": one("SELECT COUNT(*) FROM contact_messages WHERE is_read=0"),
    }
    months = _months(12)
    reg = dict(rows("SELECT strftime('%Y-%m', created_at) m, COUNT(*) FROM users WHERE role='farmer' "
                    "AND created_at >= date('now','start of month','-11 months') GROUP BY m"))
    months6 = _months(6)
    det = dict(rows("SELECT strftime('%Y-%m', created_at) m, COUNT(*) FROM predictions "
                    "WHERE created_at >= date('now','start of month','-5 months') GROUP BY m"))
    low = one("SELECT COUNT(*) FROM predictions WHERE confidence < 60")
    total_pred = totals["predictions"] or 0
    charts = {
        "reg_labels": months, "reg_values": [reg.get(m, 0) for m in months],
        "det_labels": months6, "det_values": [det.get(m, 0) for m in months6],
        "diseases": rows("SELECT disease_name, COUNT(*) c FROM predictions GROUP BY disease_name ORDER BY c DESC LIMIT 8"),
        "rec_crops": rows("SELECT top_crop, COUNT(*) c FROM recommendations WHERE top_crop IS NOT NULL GROUP BY top_crop ORDER BY c DESC LIMIT 8"),
        "rep_crop": rows("SELECT crop_name, COUNT(*) c FROM disease_reports GROUP BY crop_name ORDER BY c DESC LIMIT 8"),
        "rep_loc": rows("SELECT MIN(TRIM(location)), COUNT(*) c FROM disease_reports WHERE location IS NOT NULL AND TRIM(location)<>'' "
                        "GROUP BY LOWER(TRIM(location)) ORDER BY c DESC LIMIT 8"),
        "rep_status": rows("SELECT status, COUNT(*) FROM disease_reports GROUP BY status"),
    }
    charts["rep_status"] = [dict(charts["rep_status"]).get(s, 0) for s in ("Pending", "Reviewed", "Resolved")]
    return {
        "totals": totals,
        "charts": charts,
        "low_conf": low,
        "low_conf_pct": round(100.0 * low / total_pred, 1) if total_pred else 0,
        "recent_reports": conn.execute("SELECT r.*, u.full_name FROM disease_reports r JOIN users u ON u.id=r.user_id "
                                       "ORDER BY r.id DESC LIMIT 6").fetchall(),
        "recent_users": conn.execute("SELECT * FROM users WHERE role='farmer' ORDER BY id DESC LIMIT 6").fetchall(),
        "activity": conn.execute("SELECT a.*, u.full_name FROM activity_log a LEFT JOIN users u ON u.id=a.user_id "
                                 "ORDER BY a.id DESC LIMIT 15").fetchall(),
    }
