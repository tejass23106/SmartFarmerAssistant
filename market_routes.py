"""Crop market prices from data.gov.in (Government of India Open Data Platform).

Needs a free API key: set MARKET_API_KEY (get one at data.gov.in). Without it the page shows only prices already stored
from earlier successful requests, and says so. No prices are ever generated locally.
Prices on this dataset are per quintal (100 kg)."""
import os
import re
import sqlite3
import threading
import time

from flask import render_template, request, session, flash

from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required
from utils.http import ApiError, request_json

API_URL = "https://api.data.gov.in/resource/{rid}"
DEFAULT_RID = "9ef84268-d588-465a-a308-a864a43d0070"   # verify on data.gov.in; override with MARKET_RESOURCE_ID
CACHE_TTL = 1800
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .()/\-]{1,39}$")
STATES = ("Andhra Pradesh", "Bihar", "Gujarat", "Haryana", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
          "Odisha", "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal")
COMMODITIES = ("Tomato", "Potato", "Onion", "Rice", "Wheat", "Maize", "Cotton", "Groundnut", "Ragi", "Chickpea",
               "Bajra", "Jowar", "Sugarcane", "Turmeric", "Banana", "Green Chilli", "Brinjal", "Cabbage")
_cache, _lock = {}, threading.Lock()


class MarketError(Exception):
    def __init__(self, key):
        super().__init__(key)
        self.key = key


def api_key():
    return os.environ.get("MARKET_API_KEY", "").strip()


def fetch_prices(state, commodity, district=None):
    """Live records from data.gov.in as dicts. Raises MarketError with a translation key on any problem."""
    key = api_key()
    if not key:
        raise MarketError("mkt.not_configured")
    ck = (state, commodity, district or "")
    with _lock:
        hit = _cache.get(ck)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    rid = os.environ.get("MARKET_RESOURCE_ID", "").strip() or DEFAULT_RID
    params = {"api-key": key, "format": "json", "limit": 100,
              "filters[state.keyword]": state, "filters[commodity]": commodity}
    if district:
        params["filters[district]"] = district
    try:
        data = request_json(API_URL.format(rid=rid), params, timeout=15)
    except ApiError as exc:
        raise MarketError("mkt.key_rejected" if exc.status in (401, 403) else "mkt.unavailable")
    rows = []
    for r in data.get("records") or []:
        try:
            rows.append({"state": r["state"], "district": r["district"], "market": r["market"],
                         "commodity": r["commodity"], "variety": r.get("variety") or "", "grade": r.get("grade"),
                         "arrival_date": r["arrival_date"], "min": float(r["min_price"]),
                         "max": float(r["max_price"]), "modal": float(r["modal_price"])})
        except (KeyError, TypeError, ValueError):
            continue
    with _lock:
        _cache[ck] = (time.time(), rows)
    return rows


def store(conn, rows):
    for r in rows:
        conn.execute("INSERT OR IGNORE INTO market_prices (state, district, market, commodity, variety, grade, arrival_date, "
                     "min_price, max_price, modal_price) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (r["state"], r["district"], r["market"], r["commodity"], r["variety"], r["grade"], r["arrival_date"],
                      r["min"], r["max"], r["modal"]))


def _view(row):
    return {"state": row["state"], "district": row["district"], "market": row["market"], "commodity": row["commodity"],
            "variety": row["variety"], "arrival_date": row["arrival_date"], "min": row["min_price"],
            "max": row["max_price"], "modal": row["modal_price"]}


def register(app):

    @app.route("/market")
    @role_required("farmer")
    def market_page():
        state = request.args.get("state", "").strip()
        commodity = request.args.get("commodity", "").strip()
        district = request.args.get("district", "").strip()[:40]
        error_key = None
        if state and state not in STATES:
            state, error_key = "", "mkt.err_state"
        if commodity and not NAME_RE.match(commodity):
            commodity, error_key = "", "mkt.err_commodity"
        if district and not NAME_RE.match(district):
            district, error_key = "", "mkt.err_commodity"

        rows, source, updated, trend = [], None, None, []
        conn = get_db()
        try:
            if state and commodity:
                try:
                    live = fetch_prices(state, commodity, district or None)
                    store(conn, live)
                    conn.commit()
                    rows = [dict(m, arrival_date=m["arrival_date"]) for m in live]
                    source = "live"
                    updated = max((r["arrival_date"] for r in live), default=None)
                except MarketError as exc:
                    error_key = exc.key
                    stored = conn.execute(
                        "SELECT * FROM market_prices WHERE state=? AND commodity=? AND (? = '' OR district=?) "
                        "ORDER BY arrival_date DESC, id DESC LIMIT 200", (state, commodity, district, district)).fetchall()
                    rows = [_view(r) for r in stored]
                    if rows:
                        source = "stored"
                        updated = stored[0]["fetched_at"][:16]
                trend = conn.execute(
                    "SELECT arrival_date d, AVG(modal_price) p FROM market_prices WHERE state=? AND commodity=? "
                    "GROUP BY arrival_date ORDER BY arrival_date DESC LIMIT 60", (state, commodity)).fetchall()
            log_activity(conn, session["user_id"], "farmer", "market_search", f"{commodity} {state}") if state and commodity else None
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            error_key = error_key or "err.database"
        finally:
            conn.close()
        comp = {}
        for r in rows:
            comp[r["market"]] = max(comp.get(r["market"], 0), r["modal"] or 0)
        return render_template("market.html", states=STATES, commodities=COMMODITIES, state=state, commodity=commodity,
                               district=district, rows=rows, source=source, updated=updated, error=error_key,
                               trend=list(reversed([dict(t) for t in trend])), comp=sorted(comp.items())[:12],
                               configured=bool(api_key()), searched=bool(state and commodity))
