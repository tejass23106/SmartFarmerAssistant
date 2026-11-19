"""Tiny JSON-over-HTTP helper shared by the weather, market-price and chatbot modules.

Uses only the standard library. Every failure is converted into ApiError so callers can show a
friendly message instead of a traceback. Tests patch `utils.http.urllib.request.urlopen`.
"""
import json
import urllib.error
import urllib.parse
import urllib.request


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def request_json(url, params=None, headers=None, body=None, timeout=8, method=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "SmartFarmerAssistant/2.0"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(f"HTTP {exc.code}", exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiError("The service could not be reached.", None)
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiError("The service sent an unreadable response.", None)
