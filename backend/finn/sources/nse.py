"""Corporate announcements from the NSE corporate-filings API."""
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


def _fetch(symbol: str, days: int) -> list[dict]:
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    params = {
        "index": "equities",
        "symbol": symbol,
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
    }
    with httpx.Client(headers=_HEADERS, timeout=25, follow_redirects=True) as client:
        try:  # the site sets cookies on the landing page; the API sometimes needs them
            client.get("https://www.nseindia.com/")
        except httpx.HTTPError:
            pass
        response = client.get(_API, params=params)
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
    """Announcements for one symbol over the last `days`, newest first. Cached for 30 minutes."""
    rows, _ = store.cached(f"nse_{symbol}_{days}", 30 * 60, lambda: _fetch(symbol, days))
    return rows
