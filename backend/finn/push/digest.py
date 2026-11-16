"""Push: the windowed digest, the alert check, and the detail card for one filing."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import llm
from ..config import DEFAULT_ALERTS, OFFLINE, PORTFOLIO, WEIGHTS
from ..network import graph
from ..sources import docs, nse, prices
from . import classify, enrich

_IST = ZoneInfo("Asia/Kolkata")
_NETWORK_CATEGORIES = {"results", "M&A", "capex", "litigation", "fund_raise", "management_change",
                       "credit_rating", "pledging"}
_HISTORY_DAYS = 120


def _now_ist() -> datetime:
    return datetime.now(_IST).replace(tzinfo=None)


def _fetch_all(symbols) -> tuple[list[dict], list[str]]:
    def one(symbol):
        try:
            return nse.announcements(symbol, _HISTORY_DAYS), None
        except Exception:
            return [], symbol

    workers = min(len(symbols), 18)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, symbols))
    rows = [row for batch, _ in results for row in batch]
    failed = [symbol for _, symbol in results if symbol]
    return rows, failed


def _fold_related(items: list[dict]) -> list[dict]:
    """A company files the same event several times (board outcome, results, press release).
    Keep the most informative one and tuck the rest under it."""
    groups = {}
    for item in items:
        groups.setdefault((item["symbol"], item["category"], item["time"][:10]), []).append(item)
    leads = []
    for group in groups.values():
        group.sort(key=lambda a: (-a["priority"], -len(a["text"])))
        lead = group[0]
        lead["related"] = [{"id": a["id"], "subject": a["subject"], "url": a["url"], "time": a["time"]}
                           for a in group[1:]]
        leads.append(lead)
    return leads


def _price_history(symbols) -> dict:
    """Daily bars per symbol, fetched side by side. A symbol with no data is simply absent."""
    def one(symbol):
        try:
            return symbol, prices.history(symbol)
        except Exception:
            return symbol, None

    workers = min(len(symbols), 18)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {symbol: bars for symbol, bars in pool.map(one, symbols) if bars}


def _alerts(bars_by_symbol: dict, thresholds: dict) -> list[dict]:
    moves = []
    for symbol, bars in bars_by_symbol.items():
        move = prices.unusual_move(bars, thresholds["volume_multiple"], thresholds["price_move_pct"],
                                   int(thresholds["lookback_days"]))
        if move:
            moves.append({"symbol": symbol, "company": PORTFOLIO.get(symbol, symbol), **move})
    return moves


def _process_digest(rows: list, bars_by_symbol: dict, hours: int, weights: dict | None,
                    thresholds: dict, symbols: list, failed: list, now: datetime) -> dict:
    """Build the full ranked digest from already-fetched rows and price bars."""
    since = (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    in_window = [dict(row) for row in rows if row["time"] >= since]
    reactions = {}
    for row in in_window:
        bars = bars_by_symbol.get(row["symbol"])
        move = bars and prices.reaction_to(bars, row["time"], thresholds["volume_multiple"],
                                           thresholds["price_move_pct"], int(thresholds["lookback_days"]))
        if move:
            reactions[row["id"]] = move
    items = _fold_related(classify.classify(in_window, weights, reactions))

    # Boost/penalise priority based on portfolio weight. A company with twice the average weight
    # gets up to +10 points; one with half gets up to -10 points. Re-apply tiers after adjustment.
    if WEIGHTS:
        avg_w = sum(WEIGHTS.values()) / len(WEIGHTS)
        tiers = classify.SETTINGS["tiers"]
        for item in items:
            w = WEIGHTS.get(item["symbol"], avg_w)
            bonus = round((w - avg_w) / max(avg_w, 0.01) * 10)
            if bonus:
                item["priority"] = max(0, min(100, item["priority"] + bonus))
                item.setdefault("why", []).append(
                    f"{'+'if bonus > 0 else ''}{bonus} for {w}% portfolio weight")
                item["tier"] = ("material" if item["priority"] >= tiers["material"]
                                else "notable" if item["priority"] >= tiers["notable"]
                                else "routine")

    needs_network = {a["symbol"] for a in items if a["tier"] != "routine" and a["category"] in _NETWORK_CATEGORIES}
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda s: graph.competitors(s), needs_network))
    for item in items:
        item["company"] = PORTFOLIO.get(item["symbol"], item["company"])
        if item["tier"] != "routine" and item["category"] in _NETWORK_CATEGORIES:
            item["network"] = graph.who_to_call(item["symbol"], limit=1)
        if item["tier"] == "material" and item["category"] == "results":
            try:
                item["results"] = enrich.results_from_screener(item["symbol"], filed=item["time"])
            except Exception:
                item["results"] = None
    items.sort(key=lambda a: (-a["priority"], a["time"]), reverse=False)
    surfaced = [a for a in items if a["tier"] != "routine"]
    routine = [a for a in items if a["tier"] == "routine"]
    routine_groups: dict = {}
    for item in routine:
        # Routine items are only shown as "Company — subject" links; strip everything else
        routine_groups.setdefault(item["label"], []).append(
            {"id": item["id"], "url": item["url"], "company": item["company"], "subject": item["subject"]}
        )
    moves = _alerts(bars_by_symbol, thresholds)
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"), "snapshot": OFFLINE, "window_hours": hours, "thresholds": thresholds,
        "counts": {"total": len(in_window), "material": sum(a["tier"] == "material" for a in items),
                   "notable": sum(a["tier"] == "notable" for a in items), "routine": len(routine),
                   "folded": len(in_window) - len(items)},
        "alerts": sorted([m for m in moves if m["triggered"]], key=lambda m: -abs(m["change_pct"])),
        "tape": sorted(moves, key=lambda m: -abs(m["change_pct"])),
        "items": surfaced,
        "routine": [{"label": label, "count": len(group), "items": group}
                    for label, group in sorted(routine_groups.items(), key=lambda kv: -len(kv[1]))],
        "nudges": graph.keep_warm(items),
        "failed_symbols": failed,
    }


def digest(hours: int = 24, weights: dict | None = None, thresholds: dict | None = None,
           symbols: list[str] | None = None) -> dict:
    symbols = symbols or list(PORTFOLIO)
    thresholds = {**DEFAULT_ALERTS, **(thresholds or {})}
    rows, failed = _fetch_all(symbols)
    bars_by_symbol = _price_history(symbols)
    now = _now_ist()
    if OFFLINE and rows:
        now = datetime.strptime(max(row["time"] for row in rows), "%Y-%m-%d %H:%M:%S")
    return _process_digest(rows, bars_by_symbol, hours, weights, thresholds, symbols, failed, now)


_CHUNK = 15  # items per batch — keeps each SSE event under ~20 KB


def _emit_chunked(result: dict, emit) -> None:
    """Send the digest result as several small events instead of one large blob.

    Sequence:
      result_meta   – counts, alerts, nudges, thresholds and other scalar fields
      result_items  – surfaced items (material + notable) in batches of _CHUNK
      result_routine – routine groups
      result_done   – signals the stream is complete
    """
    meta = {k: v for k, v in result.items() if k not in ("items", "routine")}
    emit({"type": "result_meta", "data": meta})
    items = result.get("items", [])
    for i in range(0, max(len(items), 1), _CHUNK):
        emit({"type": "result_items", "items": items[i: i + _CHUNK]})
    routine = result.get("routine", [])
    for i in range(0, max(len(routine), 1), _CHUNK):
        emit({"type": "result_routine", "groups": routine[i: i + _CHUNK]})
    emit({"type": "result_done"})


def digest_stream(hours: int = 24, weights: dict | None = None, thresholds: dict | None = None,
                  symbols: list[str] | None = None, emit=lambda e: None) -> None:
    """Fetch all symbols in parallel; emit per-symbol progress events, then the final ranked result.

    Events:
      {"type": "start", "total": N}
      {"type": "symbol", "symbol": "...", "done": N, "total": N, "items": [...material+notable...]}
      {"type": "result", "data": {...}}   ← final ranked, folded, fully enriched digest
    """
    symbols = symbols or list(PORTFOLIO)
    thresholds = {**DEFAULT_ALERTS, **(thresholds or {})}

    if OFFLINE:
        emit({"type": "result", "data": digest(hours, weights, thresholds, symbols)})
        return

    now = _now_ist()
    since = (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    total = len(symbols)
    emit({"type": "start", "total": total})

    all_rows: dict[str, list] = {}
    bars_by_symbol: dict[str, list] = {}
    failed: list[str] = []
    nse_done = 0

    with ThreadPoolExecutor(max_workers=18) as pool:
        nse_futs = {pool.submit(nse.announcements, s, _HISTORY_DAYS): s for s in symbols}
        price_futs = {pool.submit(prices.history, s): s for s in symbols}

        for fut in as_completed({**nse_futs, **price_futs}):
            is_nse = fut in nse_futs
            symbol = nse_futs[fut] if is_nse else price_futs[fut]

            if is_nse:
                try:
                    all_rows[symbol] = fut.result()
                except Exception:
                    all_rows[symbol] = []
                    failed.append(symbol)
                nse_done += 1
                in_window = [dict(r) for r in all_rows[symbol] if r["time"] >= since]
                preview = [i for i in classify.classify(in_window, weights) if i["tier"] != "routine"]
                for item in preview:
                    item["company"] = PORTFOLIO.get(item["symbol"], item["company"])
                emit({"type": "symbol", "symbol": symbol, "done": nse_done, "total": total, "items": preview})
            else:  # price future
                try:
                    bars_by_symbol[symbol] = fut.result()
                except Exception:
                    pass

    rows = [r for s in symbols for r in all_rows.get(s, [])]
    result = _process_digest(rows, bars_by_symbol, hours, weights, thresholds, symbols, failed, now)
    _emit_chunked(result, emit)


_BRIEF_SYSTEM = """You brief a busy investor on one stock-exchange filing. Use only the filing text given.
Reply as JSON: {"what": "one sentence: what happened", "facts": ["up to 3 hard facts: amounts, dates,
counterparties, stakes"], "watch": "one sentence: the question this raises for a shareholder, or null"}.
No adjectives, no advice. If the text says nothing concrete, return {"what": null}."""


def _brief(item: dict) -> dict | None:
    if not llm.available("fast") or not item.get("url", "").lower().endswith(".pdf"):
        return None
    try:
        pages = docs.pages(item["url"], max_pages=6)
        body = "\n\n".join(t[:5000] for t in pages)
        if len(body.strip()) < 200:
            return None
        out = llm.ask(_BRIEF_SYSTEM, f"Exchange summary: {item['text']}\n\n{body}", tier="fast", max_tokens=600)
        return out if out.get("what") else None
    except Exception:
        return None


def detail(symbol: str, item_id: str) -> dict | None:
    """The full card for one filing: numbers for results, the person for management changes,
    and for everything material, who in the network can explain it."""
    rows = nse.announcements(symbol, _HISTORY_DAYS)
    match = next((dict(row) for row in rows if row["id"] == item_id), None)
    if not match:
        return None
    item = classify.classify([match])[0]
    item["company"] = PORTFOLIO.get(symbol, item["company"])
    category = item["category"]

    if category == "results":
        item["results"] = enrich.results_from_filing(item["url"])
        if item["results"] is None:
            try:
                item["results"] = enrich.results_from_screener(symbol, filed=item["time"])
            except Exception:
                item["results"] = None
        if item["results"] is None:
            item["results_pending"] = True
    elif category == "management_change":
        people = enrich.people_from_filing(item)
        for person in people:
            paths = graph.paths_to(person)
            for path in paths:
                path["link"] = graph.link_strength(path["score"])
            person["network"] = paths
        item["people"] = people
    elif item["tier"] != "routine":
        item["brief"] = _brief(item)

    if category in _NETWORK_CATEGORIES or item["tier"] == "material":
        item["who_to_call"] = graph.who_to_call(symbol, limit=3)
    return item
