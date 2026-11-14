"""End-of-day price and volume from Yahoo Finance, plus the unusual-move check."""
from datetime import date

import yfinance as yf

from .. import store


def history(symbol: str, days: int = 90) -> list[dict]:
    """Daily bars, oldest first: [{date, close, volume}]."""

    def fetch():
        frame = yf.Ticker(f"{symbol}.NS").history(period=f"{days}d", interval="1d", auto_adjust=False)
        if frame.empty:
            raise RuntimeError(f"no price data for {symbol}")
        return [
            {"date": idx.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2), "volume": int(row["Volume"])}
            for idx, row in frame.iterrows()
            if row["Close"] == row["Close"]  # drop NaN rows
        ]

    bars, _ = store.cached(f"prices_{symbol}", 6 * 3600, fetch)
    return bars


def move_on(bars: list[dict], index: int, lookback_days: int) -> dict | None:
    """One day's move: change from the previous close, and volume against the average of the days before."""
    if index < 1 or index >= len(bars):
        return None
    day, prev = bars[index], bars[index - 1]
    window = bars[max(0, index - lookback_days):index]
    avg_volume = sum(b["volume"] for b in window) / len(window) if window else 0
    return {
        "date": day["date"], "close": day["close"], "volume": day["volume"],
        "change_pct": round((day["close"] / prev["close"] - 1) * 100, 2) if prev["close"] else 0.0,
        "volume_x": round(day["volume"] / avg_volume, 2) if avg_volume else 0.0,
    }


def unusual_move(bars: list[dict], volume_multiple: float, price_move_pct: float, lookback_days: int) -> dict | None:
    """Compare the latest bar with the investor's own thresholds. Pure function, no I/O."""
    if len(bars) < 3:
        return None
    move = move_on(bars, len(bars) - 1, lookback_days)
    reasons = []
    if abs(move["change_pct"]) >= price_move_pct:
        reasons.append("price")
    if move["volume_x"] >= volume_multiple:
        reasons.append("volume")
    return {**move, "triggered": reasons}


def reaction_to(bars: list[dict], filed: str, volume_multiple: float, price_move_pct: float,
                lookback_days: int) -> dict | None:
    """Did the stock move unusually when a filing came out? `filed` is 'YYYY-MM-DD HH:MM:SS' exchange time.

    The market can only react on the first session that could see the filing: the same day if it was filed
    before the 15:30 close, otherwise the next trading day. Returns None if that session has not happened,
    is not in the price history, or was an ordinary day by the investor's own thresholds."""
    day, clock = filed[:10], filed[11:16]
    for index, bar in enumerate(bars):
        if bar["date"] > day or (bar["date"] == day and clock <= "15:30"):
            first_seen = index
            break
    else:
        return None
    gap = (date.fromisoformat(bars[first_seen]["date"]) - date.fromisoformat(day)).days
    if gap > 5:              # more than a long weekend apart: the price history starts after this filing
        return None
    move = move_on(bars, first_seen, lookback_days)
    if not move or (abs(move["change_pct"]) < price_move_pct and move["volume_x"] < volume_multiple):
        return None
    return {"date": move["date"], "change_pct": move["change_pct"], "volume_x": move["volume_x"]}
