"""Pull: primary-source research on any NSE company, argued out by four agents.

The four agents take real turns in a structured debate. The output is research, not a BUY/SELL signal:

  Numbers Analyst   reads the financial fact sheet            (cheap model)
  Guidance Analyst  reads the last four concall transcripts   (cheap model, one call per transcript)
  Skeptic           checks what was promised against what was delivered, then challenges both (strong model)
  Moderator         hears the rebuttals and writes the bull and bear case                     (strong model)

Rules that hold for every agent: only the supplied evidence, every point cited, no outside knowledge.
A validator then checks each citation in code and drops anything it cannot trace.
"""
import re
import time
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from rapidfuzz import fuzz

from .. import llm, rag, store
from ..config import PORTFOLIO, PULL, READ_ANNUAL_REPORT
from ..network import graph
from ..sources import docs, screener
from . import facts as fact_sheet

VERSION = 5
_RULES = """Ground rules, no exceptions:
- Use ONLY the evidence in this message. Nothing from memory about this company, no news, no broker views.
- Every point needs "cites": a list of evidence ids exactly as given (for example "N7" or "C2:14").
- If the evidence does not cover something, leave it out. Never estimate a number.
- Plain, short sentences an investor can read on a phone. No advice, no buy or sell.
- Reply with JSON only."""

_NUMBERS = f"""You are the Numbers Analyst on an investment research desk. You see a numbered fact sheet
computed from the company's reported financials. Say what the numbers show, not what management says.
{_RULES}
Reply as: {{"snapshot": [point], "trajectory": [point], "balance_sheet": [point], "cash_quality": [point]}}
where point = {{"text": "...", "cites": ["N.."]}}. Two to three points per section, each one a finding
(a direction, a turn, a risk), not a restatement of a single number."""

_GUIDANCE = f"""You are the Guidance Analyst. You read one earnings-call transcript. Pages are marked [C#:page].
Find what management explicitly guided or promised on headline numbers: growth, margins, capex, debt,
capacity, timelines. Only forward-looking statements count (expect, will, target, aim, guide). A report of
what already happened (order wins this quarter, current cash balance) is not a promise. Ignore vague optimism.
Prefer statements with a number or a date.
{_RULES}
Reply as: {{"quarter": "the quarter this call discusses, e.g. Q2 FY27",
 "guidance": [{{"metric": "growth|margin|capex|debt|capacity|other", "statement": "the promise in one sentence",
   "quote": "management's exact words, at most 30 words, copied verbatim", "cite": "C#:page",
   "horizon": "by when, e.g. FY27, next two quarters", "kind": "numeric|directional"}}],
 "tone": "one sentence on how management sounded and why",
 "pressure": [{{"text": "what analysts pushed on", "cites": ["C#:page"]}}]}}
At most 6 guidance items, the most important first. At most 3 pressure points."""

_BUSINESS = f"""You describe what a company does from excerpts of its annual report. Excerpts are marked [A:page].
{_RULES}
Reply as: {{"what": {{"text": "what the company does, two sentences", "cites": ["A:.."]}},
 "segments": [{{"name": "...", "text": "what it is and its share of revenue if stated", "cites": ["A:.."]}}]}}
At most 5 segments."""

_SKEPTIC = f"""You are the Skeptic. Management made the promises listed as G1, G2, ... on past earnings calls.
The fact sheet (N ids) shows what was actually reported. Your job is to analyse management, not summarise them.
For each promise that the reported numbers can test, give a verdict.
Chronology is strict: judge a promise ONLY against the quarters listed as "reported since" that call.
A quarter from before the call is never evidence of delivery. Compare like with like (quarter with quarter,
year with year). Do not score a promise marked "cannot be tested yet".
{_RULES}
Reply as: {{"scorecard": [{{"guidance": "G#", "delivered": "what the numbers show since, one sentence",
   "verdict": "delivered|partly|missed|too_early", "cites": ["N.."]}}],
 "divergences": [{{"text": "where the story and the numbers disagree", "cites": ["G#" or "N.." ...]}}],
 "challenge_numbers": "one pointed question for the Numbers Analyst about something the fact sheet glosses over",
 "challenge_guidance": "one pointed question for the Guidance Analyst about management's credibility"}}
Use "too_early" when the horizon lies beyond the latest reported quarter. Skip promises the fact sheet cannot test.
Prefer promises with a number or a date over vague ones.
"missed" needs a reported number that contradicts the promise. If the fact sheet has no number that can
test a promise (a segment, an order book, R&D spend), leave that promise out entirely: absence of data is
not a miss and not a divergence.
At most 6 scorecard rows and 3 divergences."""

_REBUT = f"""You are the {{role}} in a research debate. The Skeptic has challenged your work. Answer directly
from the evidence. If the Skeptic is right, concede.
{_RULES}
Reply as: {{{{"answer": "two or three sentences", "cites": ["..."], "concede": true|false}}}}"""

_MODERATOR = f"""You are the Moderator closing a research debate. You have the Numbers Analyst's findings,
the Guidance Analyst's record of promises, the Skeptic's scorecard, and the rebuttals.
Weigh them and write the two cases. Where an analyst conceded, reflect it.
{_RULES}
Reply as: {{"headline": "one sentence: the single most important thing about this company right now",
 "narrative_vs_numbers": {{"text": "two sentences: does management's story match the reported numbers", "cites": [..]}},
 "bull": [point], "bear": [point],
 "ask_management": ["three questions worth asking the management, each tied to a finding"]}}
Exactly three bull and three bear points, each {{"text": "...", "cites": [...]}}, strongest first."""


def _clean_cite(raw) -> str:
    text = str(raw).strip().strip("[]").replace(" ", "")
    text = re.sub(r"p\.?", ":", text) if re.match(r"^[CA]\d*p", text) else text
    return text.replace("::", ":")


class _Evidence:
    """Everything an agent may cite, so claims can be checked in code."""

    def __init__(self):
        self.ids = set()
        self.pages = {}      # "C1:7" -> page text
        self.guidance = {}   # "G3" -> guidance item

    def check(self, points, counter) -> list:
        """Keep points with at least one traceable citation; count what was dropped."""
        kept = []
        for point in points or []:
            if not isinstance(point, dict) or not point.get("text"):
                continue
            cites = [c for c in (_clean_cite(c) for c in point.get("cites") or []) if c in self.ids]
            counter["claims"] += 1
            if cites:
                point["cites"] = list(dict.fromkeys(cites))
                kept.append(point)
            else:
                counter["dropped"] += 1
        return kept

    def locate_quote(self, quote: str, cite: str, prefix: str) -> str | None:
        """Confirm a verbatim quote really sits on the cited page; if the page is off, find the right one."""
        needle = " ".join(quote.lower().split())
        if len(needle) < 12:
            return None

        def on(page_id):
            hay = " ".join(self.pages.get(page_id, "").lower().split())
            return bool(hay) and fuzz.partial_ratio(needle, hay) >= 86

        if on(cite):
            return cite
        for page_id in self.pages:
            if page_id.startswith(prefix + ":") and on(page_id):
                return page_id
        return None


def _transcript_block(evidence: _Evidence, tag: str, pages: list[str], budget: int = 110_000) -> str:
    parts, used = [], 0
    for number, text in enumerate(pages, start=1):
        page_id = f"{tag}:{number}"
        evidence.ids.add(page_id)
        evidence.pages[page_id] = text
        if used < budget:
            parts.append(f"[{page_id}]\n{text.strip()}")
            used += len(text)
    return "\n\n".join(parts)


def _business(company: dict, evidence: _Evidence, counter: dict, sources: list, ask) -> dict | None:
    reports = sorted(company["documents"]["annual_reports"], key=lambda r: -r["year"])
    if not reports:
        return None
    report = reports[0]
    pages = docs.pages(report["url"], max_pages=140)   # the business overview sits in the front half
    index = rag.build(report["url"], pages)
    found = {}
    for query in ("business segments and their share of revenue", "principal products, services and markets",
                  "overview of the company's operations and strategy"):
        for chunk in rag.search(index, query, k=4):
            found.setdefault((chunk["page"], chunk["text"][:60]), chunk)
    chunks = sorted(found.values(), key=lambda c: c["page"])[:10]
    if not chunks:
        return None
    for chunk in chunks:
        page_id = f"A:{chunk['page']}"
        evidence.ids.add(page_id)
        evidence.pages[page_id] = pages[chunk["page"] - 1]
    body = "\n\n".join(f"[A:{c['page']}]\n{c['text']}" for c in chunks)
    out = ask(_BUSINESS, body, tier="fast", max_tokens=1200)
    what = evidence.check([out.get("what")], counter)
    segments = evidence.check(out.get("segments"), counter)
    sources.append({"id": "A", "kind": "annual_report", "label": f"Annual Report {report['year']}",
                    "url": report["url"]})
    if not what and not segments:
        return None
    return {"what": what[0] if what else None, "segments": segments}


_NO_DATA = re.compile(r"\bno (specific |clear |direct )?(data|evidence|figures?|information)\b|"
                      r"not (available|provided|disclosed|reported)|cannot be (verified|tested)", re.I)
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_key(label: str) -> int | None:
    """'Sep 2026' -> 2026*12 + 8, so periods and call dates can be ordered."""
    match = re.match(r"([A-Z][a-z]{2})\w* (\d{4})$", label.strip())
    if not match or match.group(1) not in _MONTHS:
        return None
    return int(match.group(2)) * 12 + _MONTHS.index(match.group(1))


def _reported_since(call_date: str, periods: list[str]) -> list[str]:
    """Quarters whose results came out after an earnings call. A call held in Nov discusses the Sep quarter,
    so only quarters ending after the call month can test what was promised on it."""
    held = _month_key(call_date)
    if held is None:
        return []
    return [p for p in periods if (_month_key(p) or 0) >= held]


def _cached(symbol: str) -> dict | None:
    result = store.read(PULL / f"{symbol}.json")
    if not result or result.get("version") != VERSION:
        return None
    try:   # the network may have changed since this report was saved
        result["who_to_call"] = graph.who_to_call(symbol, company_name=result.get("name", ""), limit=3)
    except Exception:
        pass
    return result


def cached(symbol: str) -> dict | None:
    return _cached(symbol.upper())


def run(symbol: str, emit=lambda event: None, refresh: bool = False, model: str | None = None) -> dict:
    """Research one company. `emit` receives progress events so the UI can show the debate as it happens.
    `model` runs every step on one chosen model; without it, each step uses its tier's configured model."""
    symbol = symbol.upper().strip()
    if not refresh:
        saved = _cached(symbol)
        if saved:
            for event in saved.get("events", []):
                emit(event)
            emit({"type": "result", "data": saved, "cached": True})
            return saved

    started = time.time()
    events = []

    def say(agent: str, status: str, text: str = "", data=None):
        event = {"type": "agent", "agent": agent, "status": status, "text": text}
        if data is not None:
            event["data"] = data
        events.append(event)
        emit(event)

    counter = {"claims": 0, "dropped": 0}
    evidence = _Evidence()

    say("desk", "working", "Fetching reported financials and documents")
    company = screener.company(symbol)   # raises LookupError for an unknown symbol
    name = PORTFOLIO.get(symbol, company["name"])
    facts = fact_sheet.build(company)
    evidence.ids.update(f["id"] for f in facts)
    sources = [{"id": "N", "kind": "financials", "url": company.get("url", ""),
                "label": f"Reported financials, {company.get('basis', '')} (standardised by screener.in)"}]
    result = {
        "version": VERSION, "symbol": symbol, "name": name, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "top_ratios": company.get("top_ratios", {}), "facts": facts, "sources": sources,
        "who_to_call": graph.who_to_call(symbol, company_name=name, limit=3),
    }
    concalls = company["documents"]["concalls"][:4]
    say("desk", "done", f"{len(facts)} financial facts, {len(concalls)} concall transcripts"
                        f"{', annual report' if company['documents']['annual_reports'] else ''}")

    used = {}                                            # tier -> models that actually answered in this run
    ask = partial(llm.ask, model=model, used=used)
    emit({"type": "model", "model": (model or llm.model_for("fast")).split("/")[-1]})
    if not (llm.available("fast") or (model and llm._has_key(model))):
        result["status"] = "numbers_only"
        result["message"] = "No model key is configured, so only the computed fact sheet is shown."
        emit({"type": "result", "data": result})
        return result

    facts_block = "\n".join(f"[{f['id']}] {f['text']}" for f in facts)
    periods = (company["tables"].get("quarters") or {}).get("periods", [])
    today = datetime.now()
    fy = today.year + 1 if today.month >= 4 else today.year
    context = (
        f"Company: {name}. Today is {today.strftime('%d %B %Y')}. "
        f"The latest reported quarter is {periods[-1] if periods else 'unknown'}; nothing after it has happened yet. "
        f"Indian fiscal years run April to March: FY{fy % 100} is April {fy - 1} to March {fy}, and its quarters "
        f"end in June (Q1), September (Q2), December (Q3) and March (Q4). "
        "Every figure in the fact sheet is a reported, historical number, not a forecast."
    )

    # ---- Round 1: each analyst works alone, in parallel -------------------------------------
    def numbers_job():
        say("numbers", "working", "Reading ten years of reported numbers")
        out = ask(_NUMBERS, f"{context}\n\nFACT SHEET\n{facts_block}", tier="fast", max_tokens=2500)
        sections = {key: evidence.check(out.get(key), counter)
                    for key in ("snapshot", "trajectory", "balance_sheet", "cash_quality")}
        say("numbers", "done", (sections["trajectory"] or sections["snapshot"] or [{"text": ""}])[0]["text"])
        return sections

    def guidance_job(position: int, call: dict):
        tag = f"C{position}"
        pages = docs.pages(call["url"], max_pages=45)
        block = _transcript_block(evidence, tag, pages)
        out = ask(_GUIDANCE, f"{context}\nThis earnings call was held in {call['date']}.\n\n{block}",
                      tier="fast", max_tokens=2500)
        items = []
        for item in out.get("guidance") or []:
            if not isinstance(item, dict) or not item.get("quote") or not item.get("statement"):
                continue
            counter["claims"] += 1
            page_id = evidence.locate_quote(item["quote"], _clean_cite(item.get("cite", "")), tag)
            if not page_id:            # the quote is not in the transcript: discard the promise
                counter["dropped"] += 1
                continue
            items.append({**item, "cite": page_id, "said_in": call["date"], "quarter": out.get("quarter", ""),
                          "tested_by": _reported_since(call["date"], periods)})
        return {"tag": tag, "date": call["date"], "url": call["url"], "quarter": out.get("quarter", ""),
                "tone": out.get("tone", ""), "pressure": evidence.check(out.get("pressure"), counter),
                "guidance": items}

    def business_job():
        if not READ_ANNUAL_REPORT:
            return None
        try:
            return _business(company, evidence, counter, sources, ask)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        numbers_future = pool.submit(numbers_job)
        business_future = pool.submit(business_job)
        say("guidance", "working", f"Reading {len(concalls)} earnings calls for what management promised")
        call_futures = [pool.submit(guidance_job, i + 1, call) for i, call in enumerate(concalls)]
        calls = []
        for future in call_futures:
            try:
                calls.append(future.result())
            except Exception:
                continue
        numbers = numbers_future.result()
        business = business_future.result()

    guidance = []
    for call in calls:
        sources.append({"id": call["tag"], "kind": "concall", "label": f"Earnings call, {call['date']}",
                        "url": call["url"]})
        for item in call["guidance"]:
            item["id"] = f"G{len(guidance) + 1}"
            guidance.append(item)
            evidence.guidance[item["id"]] = item
            evidence.ids.add(item["id"])
    say("guidance", "done",
        f"{len(guidance)} explicit promises across {len(calls)} calls. "
        + (calls[0]["tone"] if calls else "No transcripts were available."))

    result.update(business=business, numbers=numbers, guidance=guidance,
                  calls=[{k: c[k] for k in ("tag", "date", "url", "quarter", "tone", "pressure")} for c in calls])

    # ---- Round 2: the Skeptic tests promises against delivery and challenges both analysts ----
    guidance_block = "\n".join(
        f"[{g['id']}] said on the {g['said_in']} call ({g['quarter']}), horizon {g.get('horizon') or 'unstated'}: "
        f"{g['statement']} — \"{g['quote']}\" "
        + (f"(results reported since: {', '.join(g['tested_by'])})" if g["tested_by"] else "(cannot be tested yet)")
        for g in guidance) or "(no explicit guidance was found)"
    numbers_block = "\n".join(f"- {p['text']} {p['cites']}" for section in numbers.values() for p in section)

    say("skeptic", "working", "Checking what was promised against what was delivered")
    skeptic = ask(_SKEPTIC, f"{context}\n\nPROMISES\n{guidance_block}\n\nFACT SHEET\n{facts_block}\n\n"
                                f"NUMBERS ANALYST'S FINDINGS\n{numbers_block}", tier="strong", max_tokens=3000)
    scorecard = []
    for row in skeptic.get("scorecard") or []:
        item = evidence.guidance.get(_clean_cite(row.get("guidance", "")))
        cites = [c for c in (_clean_cite(c) for c in row.get("cites") or []) if c in evidence.ids]
        counter["claims"] += 1
        if not item or not cites or row.get("verdict") not in ("delivered", "partly", "missed", "too_early"):
            counter["dropped"] += 1
            continue
        if not item["tested_by"]:      # no results exist after this call, whatever the model says
            counter["dropped"] += 1
            continue
        if row["verdict"] != "too_early" and _NO_DATA.search(row.get("delivered", "")):
            counter["dropped"] += 1    # "no data" is not a verdict
            continue
        scorecard.append({"guidance": item["id"], "promise": item["statement"], "quote": item["quote"],
                          "said_in": item["said_in"], "promise_cite": item["cite"], "horizon": item.get("horizon"),
                          "delivered": row.get("delivered", ""), "verdict": row["verdict"], "cites": cites})
    scored = {row["guidance"] for row in scorecard}
    pending = [g for g in guidance if not g["tested_by"] and g["id"] not in scored]
    pending.sort(key=lambda g: g.get("kind") != "numeric")      # promises with a number first
    for item in pending[:3]:           # the newest promises: on record now, to be checked next quarter
        scorecard.append({"guidance": item["id"], "promise": item["statement"], "quote": item["quote"],
                          "said_in": item["said_in"], "promise_cite": item["cite"], "horizon": item.get("horizon"),
                          "delivered": "No results have been reported since this call. Check it next quarter.",
                          "verdict": "too_early", "cites": []})
    divergences = [d for d in evidence.check(skeptic.get("divergences"), counter) if not _NO_DATA.search(d["text"])]
    tally = {v: sum(r["verdict"] == v for r in scorecard) for v in ("delivered", "partly", "missed", "too_early")}
    say("skeptic", "done",
        f"Of {len(scorecard)} testable promises: {tally['delivered']} delivered, {tally['partly']} partly, "
        f"{tally['missed']} missed, {tally['too_early']} too early to say.")

    # ---- Round 3: rebuttals --------------------------------------------------------------------
    def rebut(agent, role, question, context):
        if not question:
            return None
        say("skeptic", "challenge", question, {"to": agent})
        out = ask(_REBUT.format(role=role), f"{context}\n\nThe Skeptic asks: {question}\n\n{context}",
                      tier="fast", max_tokens=700)
        cites = [c for c in (_clean_cite(c) for c in out.get("cites") or []) if c in evidence.ids]
        reply = {"question": question, "answer": out.get("answer", ""), "cites": cites,
                 "concede": bool(out.get("concede"))}
        say(agent, "rebuttal", reply["answer"], {"concede": reply["concede"]})
        return reply

    rebuttals = {}
    try:
        rebuttals["numbers"] = rebut("numbers", "Numbers Analyst", skeptic.get("challenge_numbers"),
                                     f"FACT SHEET\n{facts_block}")
        rebuttals["guidance"] = rebut("guidance", "Guidance Analyst", skeptic.get("challenge_guidance"),
                                      f"PROMISES\n{guidance_block}\n\nFACT SHEET\n{facts_block}")
    except Exception:
        pass   # the debate can close without a rebuttal

    # ---- Close: the Moderator writes both cases -------------------------------------------------
    say("moderator", "working", "Weighing the arguments")
    scorecard_block = "\n".join(f"- [{r['guidance']}] {r['promise']} -> {r['verdict']}: {r['delivered']} {r['cites']}"
                                for r in scorecard) or "(nothing testable)"
    rebuttal_block = "\n".join(
        f"- Skeptic to {who}: {r['question']}\n  Reply ({'concedes' if r['concede'] else 'holds'}): {r['answer']} {r['cites']}"
        for who, r in rebuttals.items() if r) or "(none)"
    moderator = ask(
        _MODERATOR,
        f"{context}\n\nNUMBERS ANALYST\n{numbers_block}\n\nPROMISES (Guidance Analyst)\n{guidance_block}\n\n"
        f"SKEPTIC'S SCORECARD\n{scorecard_block}\n\nDIVERGENCES\n"
        + "\n".join(f"- {d['text']} {d['cites']}" for d in divergences)
        + f"\n\nREBUTTALS\n{rebuttal_block}\n\nFACT SHEET\n{facts_block}", tier="strong", max_tokens=2500)
    verdict = {
        "headline": moderator.get("headline", ""),
        "narrative_vs_numbers": (evidence.check([moderator.get("narrative_vs_numbers")], counter) or [None])[0],
        "bull": evidence.check(moderator.get("bull"), counter),
        "bear": evidence.check(moderator.get("bear"), counter),
        "ask_management": [re.sub(r"\s*[\[(][^\])]*\b[NGCA]\d*[^\])]*[\])]\s*$", "", q).strip()
                           for q in moderator.get("ask_management") or [] if isinstance(q, str)][:3],
    }
    say("moderator", "done", verdict["headline"])

    result.update(
        status="complete", scorecard=scorecard, tally=tally, divergences=divergences, rebuttals=rebuttals,
        verdict=verdict, sources=sources,
        audit={**counter, "seconds": round(time.time() - started, 1),
               "models": {"extraction": " + ".join(sorted(used.get("fast", []))) or "saved answers",
                          "reasoning": " + ".join(sorted(used.get("strong", []))) or "saved answers"}},
        events=events,
    )
    store.write(PULL / f"{symbol}.json", result)
    emit({"type": "result", "data": result})
    return result
