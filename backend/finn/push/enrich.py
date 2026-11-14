"""Turn a bare filing into something worth reading: headline numbers, or who the new person is.

The model only reads and transcribes. Every percentage change is computed in code.
"""
import re

from .. import llm
from ..sources import docs, screener


def pct(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old) * 100, 1)


def _row(table: dict, *names):
    for name in names:
        if name in table["rows"]:
            return table["rows"][name]
    return None


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def quarter_reported(filed: str) -> str:
    """The quarter a results filing is about: the last quarter-end before the filing date ('Sep 2026')."""
    year, month = int(filed[:4]), int(filed[5:7])
    end = ((month - 1) // 3) * 3          # 0, 3, 6 or 9: the last completed quarter-end month
    if end == 0:
        return f"Dec {year - 1}"
    return f"{_MONTHS[end - 1]} {year}"


def results_from_screener(symbol: str, filed: str | None = None) -> dict | None:
    """Revenue, EBITDA, PBT, PAT for the latest quarter with QoQ and YoY, from standardised quarterly tables.

    With `filed` (the filing time), return None unless the table already holds the quarter that filing
    reports. A results card showing last quarter's numbers would be worse than no card.
    """
    data = screener.company(symbol)
    table = data["tables"].get("quarters")
    if not table or len(table["periods"]) < 2:
        return None
    periods = table["periods"]
    if filed and periods[-1] != quarter_reported(filed):
        return None
    lines = {
        "Revenue": _row(table, "Sales", "Revenue"),
        "EBITDA": _row(table, "Operating Profit", "Financing Profit"),
        "PBT": _row(table, "Profit before tax"),
        "PAT": _row(table, "Net Profit"),
    }
    metrics = []
    for name, values in lines.items():
        if not values:
            continue
        now = values[-1]
        prev = values[-2] if len(values) >= 2 else None
        year_ago = values[-5] if len(values) >= 5 else None
        metrics.append({"name": name, "value": now, "prev": prev, "year_ago": year_ago,
                        "qoq": pct(now, prev), "yoy": pct(now, year_ago)})
    if not metrics:
        return None
    return {
        "period": periods[-1], "prev_period": periods[-2],
        "year_ago_period": periods[-5] if len(periods) >= 5 else None,
        "unit": "₹ crore", "basis": data.get("basis", ""), "metrics": metrics,
        "source": "Standardised quarterly table (screener.in)", "source_url": data.get("url", ""),
        "note": ("EBITDA shown is operating profit before other income."
                 if "Operating Profit" in table["rows"] else
                 "For lenders, the EBITDA line shows financing profit."),
    }


_RESULTS_SYSTEM = """You transcribe numbers from an Indian company's quarterly results filing.
Use the CONSOLIDATED statement if present, else standalone. Take three columns: the current quarter,
the immediately preceding quarter, and the same quarter of the previous year.
Copy figures exactly as printed; do not calculate or estimate. Use null when a line is not printed.
Reply as JSON:
{"basis": "consolidated|standalone", "unit": "e.g. Rs crore / Rs lakh / Rs million",
 "quarter_label": "...", "prev_label": "...", "year_ago_label": "...",
 "lines": {"revenue_from_operations": [cur, prev, year_ago], "other_income": [...],
           "finance_costs": [...], "depreciation": [...],
           "profit_before_tax": [...], "profit_after_tax": [...]},
 "page": <page number where the table is>}
If the document has no results table, reply {"lines": null}."""


def results_from_filing(url: str) -> dict | None:
    """Read the actual results PDF. Returns None when no model is configured or the table cannot be read."""
    if not url.lower().endswith(".pdf") or not llm.available("fast"):
        return None
    try:
        pages = docs.pages(url, max_pages=14)
    except Exception:
        return None
    keep = [(i + 1, t) for i, t in enumerate(pages)
            if re.search(r"revenue from operations|total income|profit before tax|interest earned", t, re.I)][:5]
    if not keep:
        return None
    body = "\n\n".join(f"[page {n}]\n{t[:7000]}" for n, t in keep)
    try:
        out = llm.ask(_RESULTS_SYSTEM, body, tier="fast", max_tokens=1200)
    except Exception:
        return None
    lines = out.get("lines")
    if not lines:
        return None

    def triple(key):
        values = lines.get(key) or [None, None, None]
        values = [v if isinstance(v, (int, float)) else None for v in values][:3]
        return values + [None] * (3 - len(values))

    revenue, pbt, pat = triple("revenue_from_operations"), triple("profit_before_tax"), triple("profit_after_tax")
    other, finance, depreciation = triple("other_income"), triple("finance_costs"), triple("depreciation")
    ebitda = [None, None, None]
    for i in range(3):
        if None not in (pbt[i], finance[i], depreciation[i]):
            ebitda[i] = round(pbt[i] + finance[i] + depreciation[i] - (other[i] or 0), 2)
    metrics = []
    for name, values in (("Revenue", revenue), ("EBITDA", ebitda), ("PBT", pbt), ("PAT", pat)):
        if values[0] is None:
            continue
        metrics.append({"name": name, "value": values[0], "prev": values[1], "year_ago": values[2],
                        "qoq": pct(values[0], values[1]), "yoy": pct(values[0], values[2])})
    if len(metrics) < 2:
        return None
    return {
        "period": out.get("quarter_label") or "Latest quarter", "prev_period": out.get("prev_label"),
        "year_ago_period": out.get("year_ago_label"), "unit": out.get("unit") or "",
        "basis": out.get("basis") or "", "metrics": metrics,
        "source": f"Results filing, page {out.get('page') or keep[0][0]}", "source_url": url,
        "note": "EBITDA = PBT + finance costs + depreciation − other income, computed from the filing's lines.",
    }


_PERSON_SYSTEM = """You read an Indian stock-exchange filing about a change in directors or senior management.
Extract only what the filing itself says. Do not add anything from your own knowledge of the person.
Reply as JSON:
{"people": [{"name": "...", "change": "appointment|resignation|retirement|cessation|re-appointment",
  "role": "role at this company", "effective": "date as written or null",
  "reason": "stated reason for leaving, or null",
  "bio": "two plain sentences on background, from the filing's brief profile; null if no profile is given",
  "career": [{"company": "...", "title": "...", "from": year or null, "to": year or null}],
  "education": [{"school": "...", "degree": "...", "year": year or null}]}]}
List at most 3 people, the most senior first."""

_NAME = re.compile(r"(?:appointment|resignation|cessation|retirement|re-?appointment)\s+of\s+"
                   r"((?:Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+[A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,3})\s+as\s+"
                   r"(?:an?\s+|the\s+)?([^.,;]{3,80}?)(?:\s+of the company|\s+w\.e\.f|[.,;]|$)", re.I)


def people_from_filing(item: dict) -> list[dict]:
    """Who joined or left, with background taken from the filing's own brief profile."""
    people = []
    if llm.available("fast") and item.get("url", "").lower().endswith(".pdf"):
        try:
            pages = docs.pages(item["url"], max_pages=8)
            body = "\n\n".join(f"[page {i + 1}]\n{t[:6000]}" for i, t in enumerate(pages))
            if body.strip():
                out = llm.ask(_PERSON_SYSTEM, f"Exchange summary: {item['text']}\n\n{body}", tier="fast",
                              max_tokens=1500)
                people = [p for p in out.get("people", []) if p.get("name")][:3]
        except Exception:
            people = []
    if not people:  # no model, or a scanned PDF: fall back to the exchange's one-line description
        match = _NAME.search(item.get("text", ""))
        if match:
            change = re.match(r"\w+-?\w*", match.group(0)).group(0).lower()
            people = [{"name": match.group(1).strip(), "change": change, "role": match.group(2).strip(),
                       "effective": None, "reason": None, "bio": None, "career": [], "education": []}]
    for person in people:
        person.setdefault("career", [])
        person.setdefault("education", [])
        person["career"] = [r for r in (person["career"] or []) if isinstance(r, dict) and r.get("company")]
        person["education"] = [e for e in (person["education"] or []) if isinstance(e, dict) and e.get("school")]
    return people
