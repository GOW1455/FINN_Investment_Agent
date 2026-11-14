"""Warm the caches and save fallbacks, so the demo never depends on a scraper or a model being up.

  uv run python scripts/precompute.py              # snapshot data + research every demo company
  uv run python scripts/precompute.py --no-research
  uv run python scripts/precompute.py INFY CAMS     # research only these symbols
"""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn import llm
from finn.config import CACHE, PORTFOLIO, RESEARCH_DEMO, SNAPSHOT
from finn.pull import research
from finn.push import digest
from finn.sources import screener

args = [a for a in sys.argv[1:] if not a.startswith("--")]
symbols = [a.upper() for a in args] or [*RESEARCH_DEMO, *PORTFOLIO]

print("Fetching filings and prices for the portfolio ...")
feed = digest.digest(hours=24 * 30)
print(f"  {feed['counts']['total']} filings in 30 days, {len(feed['alerts'])} alerts, failed: {feed['failed_symbols']}")
for symbol in {*PORTFOLIO, *RESEARCH_DEMO}:
    try:
        screener.company(symbol)
    except Exception as error:
        print(f"  screener failed for {symbol}: {error}")
copied = 0
for path in CACHE.glob("*.json"):
    if path.name.startswith(("nse_", "prices_", "screener_")):
        shutil.copy2(path, SNAPSHOT / path.name)
        copied += 1
print(f"  saved {copied} fallback files to {SNAPSHOT}")

if "--no-research" in sys.argv:
    sys.exit(0)
if not llm.available("fast"):
    sys.exit("No model key found. Add one to backend/.env (see .env.example), then run this again.")

for symbol in symbols:
    started = time.time()
    try:
        result = research.run(symbol, refresh="--refresh" in sys.argv)
        audit = result.get("audit", {})
        print(f"  {symbol}: {result['status']}, {audit.get('claims', 0) - audit.get('dropped', 0)} claims kept, "
              f"{audit.get('dropped', 0)} dropped, {time.time() - started:.0f}s")
    except Exception as error:
        print(f"  {symbol}: failed ({error})")
    time.sleep(4)   # stay inside free-tier rate limits
print("Model usage:", llm.usage)
