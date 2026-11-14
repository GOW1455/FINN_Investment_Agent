"""Company fundamentals from screener.in: standardised tables plus links to annual reports and concalls."""
import re

import httpx
from bs4 import BeautifulSoup

from .. import store
from ..config import CACHE, SNAPSHOT, UA

_SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]


def _number(text: str):
    cleaned = text.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _table(section) -> dict | None:
    table = section.find("table", class_="data-table") if section else None
    if not table or not table.thead:
        return None
    periods = [th.get_text(strip=True) for th in table.thead.find_all("th")][1:]
    rows = {}
    for tr in table.tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        name = re.sub(r"\s*\+$", "", cells[0].get_text(" ", strip=True)).strip()
        values = [_number(td.get_text(strip=True)) for td in cells[1:]]
        if name and any(v is not None for v in values):
            rows[name] = values
    return {"periods": periods, "rows": rows} if periods and rows else None


def _documents(soup) -> dict:
    docs = {"annual_reports": [], "concalls": []}
    section = soup.find("section", id="documents")
    if not section:
        return docs
    for heading in section.find_all("h3"):
        title = heading.get_text(strip=True).lower()
        box = heading.find_next("ul", class_="list-links")
        if not box:
            continue
        if title.startswith("annual report"):
            for a in box.find_all("a", href=True):
                label = " ".join(a.get_text(" ", strip=True).split())
                year = re.search(r"(20\d\d)", label)
                if year:
                    docs["annual_reports"].append({"year": int(year.group(1)), "url": a["href"]})
        elif title.startswith("concall"):
            for li in box.find_all("li"):
                date = li.find("div")
                link = next((a for a in li.find_all("a", href=True) if a.get_text(strip=True) == "Transcript"), None)
                if date and link:
                    docs["concalls"].append({"date": date.get_text(strip=True), "url": link["href"]})
    return docs


def _peers(client, soup, symbol: str) -> list[dict]:
    """Companies screener.in lists as peers (same industry): the source for 'who are its competitors'."""
    holder = soup.find(attrs={"data-warehouse-id": True})
    if not holder:
        return []
    response = client.get(f"https://www.screener.in/api/company/{holder['data-warehouse-id']}/peers/",
                          headers={"X-Requested-With": "XMLHttpRequest"})
    if response.status_code != 200:
        return []
    peers = []
    for link in BeautifulSoup(response.text, "lxml").select('a[href^="/company/"]'):
        peer = link["href"].split("/")[2]
        name = " ".join(link.get_text(" ", strip=True).split())
        if peer and name and peer != symbol and all(p["symbol"] != peer for p in peers):
            peers.append({"symbol": peer, "name": name})
    return peers[:12]


def _industry(soup) -> list[str]:
    """The classification shown above the peers table, broadest first:
    ['Consumer Discretionary', 'Consumer Durables', 'Paints']."""
    section = soup.find("section", id="peers")
    levels = [a.get_text(" ", strip=True) for a in section.select('a[href^="/market/"]')] if section else []
    return list(dict.fromkeys(level for level in levels if level))


def _parse(html: str, symbol: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    name = soup.find("h1")
    about = soup.select_one(".company-profile .about")
    ratios = {}
    for li in soup.select("#top-ratios li"):
        label, value = li.select_one(".name"), li.select_one(".value")
        if label and value:
            ratios[label.get_text(strip=True)] = " ".join(value.get_text(" ", strip=True).split())
    tables = {}
    for section_id in _SECTIONS:
        parsed = _table(soup.find("section", id=section_id))
        if parsed:
            tables[section_id] = parsed
    return {
        "symbol": symbol,
        "name": name.get_text(strip=True) if name else symbol,
        "about": " ".join(about.get_text(" ", strip=True).split()) if about else "",
        "industry": _industry(soup),
        "top_ratios": ratios,
        "tables": tables,
        "documents": _documents(soup),
    }


def _fetch(symbol: str) -> dict:
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
        best = None
        for suffix, basis in (("consolidated/", "consolidated"), ("", "standalone")):
            response = client.get(f"https://www.screener.in/company/{symbol}/{suffix}")
            if response.status_code == 404:
                continue
            response.raise_for_status()
            parsed = _parse(response.text, symbol)
            parsed["basis"] = basis
            parsed["url"] = str(response.url)
            try:
                parsed["peers"] = _peers(client, BeautifulSoup(response.text, "lxml"), symbol)
            except httpx.HTTPError:
                parsed["peers"] = []
            # Some companies only report standalone numbers; the consolidated page then has empty tables.
            if "quarters" in parsed["tables"]:
                return parsed
            best = best or parsed
    if best is None:
        raise LookupError(f"{symbol} not found on screener.in")
    return best


def company(symbol: str) -> dict:
    """Parsed screener.in page for an NSE symbol. Cached for 12 hours."""
    data, _ = store.cached(f"screener_{symbol}", 12 * 3600, lambda: _fetch(symbol))
    if "peers" not in data or "industry" not in data:   # saved before these were collected: fetch once more
        try:
            data = _fetch(symbol)
            store.write(CACHE / f"screener_{symbol}.json", data)
        except Exception:
            data = {"peers": [], "industry": [], **data}
    return data


def known(symbol: str) -> dict | None:
    """What is already on disk for a symbol, without touching the network. For code that scans many companies."""
    return store.read(CACHE / f"screener_{symbol}.json") or store.read(SNAPSHOT / f"screener_{symbol}.json")
