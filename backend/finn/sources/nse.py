"""Corporate announcements from the NSE corporate-filings API."""
import threading
import time
from datetime import datetime, timedelta

import httpx

from .. import store
from ..config import UA

_API = "https://www.nseindia.com/api/corporate-announcements"
_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}

_cookies: dict = {}
_cookies_lock = threading.Lock()
_cookies_at: float = 0.0
_COOKIE_TTL = 90 * 60  # NSE session cookies last ~2h; refresh well before they expire


def _refresh_cookies() -> None:
    """Fetch the NSE homepage once to get session cookies shared across all symbol fetches."""
    global _cookies, _cookies_at
    try:
        r = httpx.get("https://www.nseindia.com/", headers=_HEADERS, timeout=10, follow_redirects=True)
        _cookies = dict(r.cookies)
        _cookies_at = time.time()
    except Exception:
        pass


def _get_cookies() -> dict:
    with _cookies_lock:
        if time.time() - _cookies_at > _COOKIE_TTL:
            _refresh_cookies()
    return _cookies


def _fetch(symbol: str, days: int) -> list[dict]:
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    params = {
        "index": "equities",
        "symbol": symbol,
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
    }
    with httpx.Client(headers=_HEADERS, cookies=_get_cookies(), timeout=25, follow_redirects=True) as client:
        response = client.get(_API, params=params)
        if response.status_code in (401, 403):
            # Cookie may have expired mid-flight; force a refresh and retry once
            with _cookies_lock:
                _refresh_cookies()
            with httpx.Client(headers=_HEADERS, cookies=_cookies, timeout=25, follow_redirects=True) as retry:
                response = retry.get(_API, params=params)
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError(f"unexpected NSE response for {symbol}")
    out = []
    for row in rows:
        if row.get("symbol") != symbol:
            continue
        out.append({
            "id": str(row.get("seq_id") or row.get("dt")),
            "symbol": symbol,
            "company": row.get("sm_name") or symbol,
            "industry": row.get("smIndustry") or "",
            "time": row.get("sort_date") or "",          # 'YYYY-MM-DD HH:MM:SS', exchange time (IST)
            "subject": (row.get("desc") or "").strip(),
            "text": (row.get("attchmntText") or "").strip(),
            "url": row.get("attchmntFile") or "",
        })
    out.sort(key=lambda a: a["time"], reverse=True)
    return out


def announcements(symbol: str, days: int = 120) -> list[dict]:
    """Announcements for one symbol over the last `days`, newest first. Cached for 2 hours.

    120 days of historical filings are mostly immutable — only the last hour or two can have new entries,
    so a 30-minute TTL was wasteful. 2 hours avoids redundant full re-fetches during market hours."""
    rows, _ = store.cached(f"nse_{symbol}_{days}", 2 * 3600, lambda: _fetch(symbol, days))
    return rows
