"""Build the numbered fact sheet the analysts argue from.

All arithmetic (growth rates, margins, leverage, cash conversion) happens here, in code.
The agents receive finished facts with ids like N7 and may only cite them, never recompute them.
"""
import re


def _label(period: str) -> str:
    match = re.match(r"Mar (\d{4})$", period)
    return f"FY{match.group(1)[2:]}" if match else period


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:,.1f}".rstrip("0").rstrip(".")


def _row(table, *names):
    if not table:
        return None
    for name in names:
        if name in table["rows"]:
            return table["rows"][name]
    return None


def _series(table, values, last: int, skip_ttm: bool = True) -> list[tuple[str, float]]:
    pairs = [(p, v) for p, v in zip(table["periods"], values) if not (skip_ttm and p == "TTM")]
    return [(_label(p), v) for p, v in pairs[-last:]]


def _cagr(first, last, years):
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return round(((last / first) ** (1 / years) - 1) * 100, 1)


def _growth(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old) * 100, 1)


def build(company: dict) -> list[dict]:
    """Return facts as [{id, topic, text}] from the standardised screener tables."""
    tables = company.get("tables", {})
    pl, bs, cf = tables.get("profit-loss"), tables.get("balance-sheet"), tables.get("cash-flow")
    ratios, quarters = tables.get("ratios"), tables.get("quarters")
    facts = []

    def add(topic, text):
        facts.append({"id": f"N{len(facts) + 1}", "topic": topic, "text": text})

    def add_series(topic, name, table, values, last=6, unit="₹ cr"):
        if values:
            points = _series(table, values, last)
            if any(v is not None for _, v in points):
                add(topic, f"{name} ({unit}): " + " | ".join(f"{p} {_fmt(v)}" for p, v in points))

    for key, value in list(company.get("top_ratios", {}).items())[:9]:
        if key not in ("Current Price", "High / Low", "Face Value"):   # share price is not business performance
            add("snapshot", f"{key}: {value}")

    sales = _row(pl, "Sales", "Revenue")
    profit = _row(pl, "Net Profit")
    if pl:
        add_series("trajectory", "Annual revenue", pl, sales)
        add_series("trajectory", "Operating margin", pl, _row(pl, "OPM %", "Financing Margin %"), unit="%")
        add_series("trajectory", "Annual net profit", pl, profit)
        add_series("trajectory", "EPS", pl, _row(pl, "EPS in Rs"), unit="₹")
        for name, values in (("Revenue", sales), ("Net profit", profit)):
            if not values:
                continue
            points = _series(pl, values, 6)
            for years in (3, 5):
                if len(points) > years:
                    rate = _cagr(points[-1 - years][1], points[-1][1], years)
                    if rate is not None:
                        add("trajectory", f"{name} {years}-year CAGR to {points[-1][0]}: {rate}%")
        if "TTM" in pl["periods"] and sales:
            add("snapshot", f"Trailing-twelve-month revenue ₹{_fmt(sales[-1])} cr"
                            + (f", net profit ₹{_fmt(profit[-1])} cr" if profit else ""))

    if bs:
        borrowings = _row(bs, "Borrowings", "Borrowing")
        equity_capital, reserves = _row(bs, "Equity Capital"), _row(bs, "Reserves")
        add_series("balance_sheet", "Borrowings", bs, borrowings)
        add_series("balance_sheet", "Deposits", bs, _row(bs, "Deposits"))
        if equity_capital and reserves:
            equity = [(a or 0) + (b or 0) for a, b in zip(equity_capital, reserves)]
            add_series("balance_sheet", "Shareholders' equity", bs, equity)
            if borrowings:
                ratio = [round(d / e, 2) if d is not None and e else None for d, e in zip(borrowings, equity)]
                add_series("balance_sheet", "Debt-to-equity", bs, ratio, unit="x")
        add_series("balance_sheet", "Capital work in progress", bs, _row(bs, "CWIP"))
        add_series("balance_sheet", "Fixed assets", bs, _row(bs, "Fixed Assets"))
    if pl:
        operating, interest = _row(pl, "Operating Profit"), _row(pl, "Interest")
        other = _row(pl, "Other Income")
        if operating and interest:
            cover = [round(((o or 0) + ((x or 0) if other else 0)) / i, 1) if i else None
                     for o, i, x in zip(operating, interest, other or [0] * len(operating))]
            add_series("balance_sheet", "Interest cover (operating profit + other income) / interest",
                       pl, cover, unit="x")

    if cf:
        cfo = _row(cf, "Cash from Operating Activity")
        add_series("cash_quality", "Cash from operations", cf, cfo)
        add_series("cash_quality", "Cash from investing", cf, _row(cf, "Cash from Investing Activity"))
        add_series("cash_quality", "Free cash flow", cf, _row(cf, "Free Cash Flow"))
        if cfo and profit and pl:
            by_year = dict(zip(pl["periods"], profit))
            pairs = [(p, c, by_year.get(p)) for p, c in zip(cf["periods"], cfo)
                     if p != "TTM" and c is not None and by_year.get(p) is not None][-5:]
            total_profit = sum(p for _, _, p in pairs)
            if pairs and total_profit > 0:
                conversion = round(sum(c for _, c, _ in pairs) / total_profit * 100)
                add("cash_quality",
                    f"Cash conversion over {_label(pairs[0][0])}–{_label(pairs[-1][0])}: cumulative cash from "
                    f"operations is {conversion}% of cumulative net profit")
    if ratios:
        for name in ("Debtor Days", "Inventory Days", "Days Payable", "Cash Conversion Cycle",
                     "Working Capital Days"):
            add_series("cash_quality", name, ratios, _row(ratios, name), unit="days")
        add_series("trajectory", "ROCE", ratios, _row(ratios, "ROCE %"), unit="%")
        add_series("trajectory", "ROE", ratios, _row(ratios, "ROE %"), unit="%")

    if quarters:
        q_sales = _row(quarters, "Sales", "Revenue")
        q_profit = _row(quarters, "Net Profit")
        q_margin = _row(quarters, "OPM %", "Financing Margin %")
        add_series("quarterly", "Quarterly revenue", quarters, q_sales, last=8)
        add_series("quarterly", "Quarterly operating margin", quarters, q_margin, last=8, unit="%")
        add_series("quarterly", "Quarterly net profit", quarters, q_profit, last=8)
        periods = quarters["periods"]
        for name, values in (("revenue", q_sales), ("net profit", q_profit)):
            if values and len(values) >= 5:
                growth = [(periods[i], _growth(values[i], values[i - 4])) for i in range(max(4, len(values) - 5), len(values))]
                add("quarterly", f"Quarterly {name} growth, year on year (%): "
                    + " | ".join(f"{p} {_fmt(g)}" for p, g in growth))
        if q_margin and len(q_margin) >= 5 and None not in (q_margin[-1], q_margin[-5]):
            add("quarterly", f"Operating margin moved {q_margin[-1] - q_margin[-5]:+.1f} percentage points, "
                             f"{periods[-5]} to {periods[-1]}")
    return facts
