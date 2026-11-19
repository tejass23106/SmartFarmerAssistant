"""Small helpers for the activity log and in-app notifications. They never raise."""
import sqlite3


def log_activity(conn, user_id, role, action, detail=None):
    try:
        conn.execute("INSERT INTO activity_log (user_id, role, action, detail) VALUES (?,?,?,?)",
                     (user_id, role, action, (detail or "")[:300] or None))
    except sqlite3.Error:
        pass


def notify(conn, user_id, title, body=None, link=None, kind="info", dedupe_key=None):
    """Create a notification. A repeated dedupe_key for the same user is ignored."""
    try:
        conn.execute("INSERT OR IGNORE INTO notifications (user_id, kind, title, body, link, dedupe_key) VALUES (?,?,?,?,?,?)",
                     (user_id, kind, title[:150], (body or "")[:400] or None, link, dedupe_key))
    except sqlite3.Error:
        pass
