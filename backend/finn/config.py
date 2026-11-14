"""Central configuration: paths, demo portfolio, model routing."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
CACHE = DATA / "cache"          # refreshable caches (prices, filings, screener pages)
DOCS = DATA / "docs"            # downloaded PDFs and extracted page text
PULL = DATA / "pull"            # finished research results, one JSON per ticker
SNAPSHOT = DATA / "snapshot"    # committed fallbacks so the demo never depends on a scraper
CONTACTS = DATA / "network" / "contacts.json"    # contacts the investor adds in the app; never committed
for _p in (CACHE, DOCS, PULL, SNAPSHOT, CONTACTS.parent):
    _p.mkdir(parents=True, exist_ok=True)

# Demo portfolio: NSE symbol -> display name. Sector, peers and registered name are fetched, not written here.
# The engine itself takes any NSE symbol.
PORTFOLIO = {
    "RELIANCE": "Reliance Industries",
    "HDFCBANK": "HDFC Bank",
    "BAJFINANCE": "Bajaj Finance",
    "INFY": "Infosys",
    "TCS": "Tata Consultancy Services",
    "BHARTIARTL": "Bharti Airtel",
    "LT": "Larsen & Toubro",
    "ITC": "ITC",
    "SUNPHARMA": "Sun Pharma",
    "ASIANPAINT": "Asian Paints",
    "PIDILITIND": "Pidilite Industries",
    "DEEPAKNTR": "Deepak Nitrite",
    "TITAN": "Titan Company",
    "TRENT": "Trent",
    "DIXON": "Dixon Technologies",
    "POLYCAB": "Polycab India",
    "CDSL": "CDSL",
    "IRCTC": "IRCTC",
}
RESEARCH_DEMO = ["KPITTECH", "LAURUSLABS", "CAMS", "ASTRAL"]

# Models. By default every step runs on FINN_FAST_MODEL. Setting FINN_STRONG_MODEL sends only the two
# reasoning steps (Skeptic, Moderator) to a stronger model. Any LiteLLM model string works; set in backend/.env.
FAST_MODEL = os.getenv("FINN_FAST_MODEL", "gemini/gemini-3.5-flash-lite")
STRONG_MODEL = os.getenv("FINN_STRONG_MODEL", FAST_MODEL)
# Models the investor may pick in the app for new research. Only those with a key configured are offered.
MODEL_CHOICES = [m.strip() for m in os.getenv(
    "FINN_MODEL_CHOICES",
    f"{FAST_MODEL},gemini/gemini-3.1-flash-lite,gemini/gemini-3-flash-preview",
).split(",") if m.strip()]
# Used when a tier's model is overloaded, timing out or retired, so one provider's bad day does not stop the app.
FALLBACK_MODEL = os.getenv("FINN_FALLBACK_MODEL", "")

# Reading the annual report needs a local embedding model (about 130 MB). Turn it off on very small hosts;
# the business section is then skipped and everything else still runs.
READ_ANNUAL_REPORT = os.getenv("FINN_READ_ANNUAL_REPORT", "1") != "0"

# Demo mode: serve filings, prices and fundamentals from the saved snapshot instead of calling the sources.
# The clock is frozen at the snapshot's newest filing, so "last 24 hours" keeps meaning the same thing.
# A company that is not in the snapshot is still fetched live.
OFFLINE = os.getenv("FINN_OFFLINE", "0") == "1"

DEFAULT_ALERTS = {"volume_multiple": 2.0, "price_move_pct": 4.0, "lookback_days": 20}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
