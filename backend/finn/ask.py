"""Ask a question about one filing or one research report, framed by what the investor is working on.

The model sees only the chosen context. Every point it makes must cite a piece of that context, and the
citations are checked in code. If the context does not answer the question, the reply says so and points
to the person in the network most likely to know.
"""
import re

from . import llm
from .config import PORTFOLIO
from .network import graph
from .pull import research
from .push import classify
from .sources import docs, nse

_SYSTEM = """You answer an investor's question about an Indian listed company.

Ground rules, no exceptions:
- Use ONLY the context in this message. Nothing from memory about the company, no news, no broker views.
- Each point needs "cites": a list of evidence ids exactly as they appear in square brackets in the context.
- If the context answers only part of the question, answer that part with "answered": true and name the
  rest in "missing". Set "answered" to false only when the context answers none of it. Never guess.
- Never estimate or calculate a number that is not printed in the context.
- Plain, short sentences that read well on a phone. No advice, no buy or sell.
- The investor may say what they are working on. Where the context allows, bring out what matters for that.
  Do not stretch: if the context has nothing relevant to their focus, say so in one clause.

Reply with JSON only:
{"answered": true|false,
 "points": [{"text": "...", "cites": ["..."]}],
 "missing": "one sentence on what these sources do not cover, or null",
 "follow_ups": ["two short follow-up questions these same sources could answer"]}
At most four points, the most useful first."""

_STOP = {"what", "which", "when", "where", "does", "did", "have", "has", "this", "that", "with", "about", "from",
         "they", "their", "them", "there", "will", "would", "could", "should", "were", "been", "being", "into",
         "over", "than", "then", "also", "much", "many", "more", "most", "some", "your", "tell", "said", "says",
         "company", "management", "quarter", "year"}


def _keywords(text: str) -> set[str]:
    return {graph._stem(w) for w in re.findall(r"[a-z][a-z0-9&-]{2,}", text.lower()) if w not in _STOP and len(w) > 3}


def _relevant_pages(pages: dict[str, str], question: str, keep: int) -> list[str]:
    """Pick the pages that share the most distinct words with the question. Plain word overlap, no model."""
    wanted = _keywords(question)
    if not wanted:
        return list(pages)[:keep]
    scored = []
    for page_id, text in pages.items():
        found = _keywords(text) & wanted
        if found:
            scored.append((len(found), text.lower().count(next(iter(found))), page_id))
    scored.sort(reverse=True)
    return [page_id for _, _, page_id in scored[:keep]]


def _filing_context(symbol: str, item_id: str, question: str) -> tuple[str, dict, str]:
    rows = nse.announcements(symbol, 120)
    item = next((dict(r) for r in rows if r["id"] == item_id), None)
    if not item:
        raise LookupError("Filing not found")
    item = classify.classify([item])[0]
    company = PORTFOLIO.get(symbol, item["company"])
    evidence = {"S": {"label": "Exchange summary", "text": item["text"] or item["subject"]}}
    parts = [f"Filing by {company} on {item['time']}, type: {item['label']}.",
             f"[S] Exchange summary: {item['text'] or item['subject']}"]
    if item.get("url", "").lower().endswith(".pdf"):
        try:
            texts = docs.pages(item["url"], max_pages=24)
        except Exception:
            texts = []
        pages = {f"P{n}": text for n, text in enumerate(texts, start=1) if len(text.strip()) > 40}
        chosen = list(pages) if len(pages) <= 8 else sorted(
            set(list(pages)[:3]) | set(_relevant_pages(pages, question, 6)), key=lambda p: int(p[1:]))
        for page_id in chosen:
            evidence[page_id] = {"label": f"Filing, page {page_id[1:]}", "url": item["url"], "page": int(page_id[1:])}
            parts.append(f"[{page_id}]\n{pages[page_id][:6000]}")
    return "\n\n".join(parts), evidence, f"{company}: {item['label']} filing"


def _research_context(symbol: str, question: str) -> tuple[str, dict, str]:
    report = research.cached(symbol)
    if not report or report.get("status") != "complete":
        raise LookupError("Research this company first, then ask about it")
    evidence = {}
    parts = [f"Research on {report['name']} ({symbol}), generated {report['generated_at']}."]

    parts.append("REPORTED NUMBERS")
    for fact in report["facts"]:
        evidence[fact["id"]] = {"label": "Reported number", "text": fact["text"]}
        parts.append(f"[{fact['id']}] {fact['text']}")

    urls = {call["tag"]: call["url"] for call in report.get("calls", [])}
    if report.get("guidance"):
        parts.append("WHAT MANAGEMENT PROMISED (exact quotes from earnings calls)")
        for promise in report["guidance"]:
            tag, _, page = promise["cite"].partition(":")
            evidence[promise["id"]] = {"label": f"Management, {promise['said_in']} call", "text": f"“{promise['quote']}”",
                                       "url": urls.get(tag), "page": int(page) if page.isdigit() else None}
            parts.append(f"[{promise['id']}] {promise['said_in']} call, horizon {promise.get('horizon') or 'unstated'}: "
                         f"{promise['statement']} — \"{promise['quote']}\"")
    if report.get("scorecard"):
        parts.append("PROMISED VS DELIVERED (already checked against the numbers)")
        for row in report["scorecard"]:
            parts.append(f"- [{row['guidance']}] {row['verdict']}: {row['delivered']} {row['cites']}")

    # Add the transcript pages closest to the question, so answers can go beyond the saved summary.
    pages = {}
    for call in report.get("calls", []):
        try:
            texts = docs.pages(call["url"], max_pages=45)
        except Exception:
            continue
        for number, text in enumerate(texts, start=1):
            if len(text.strip()) > 80:
                pages[f"{call['tag']}:{number}"] = text
    dates = {call["tag"]: call["date"] for call in report.get("calls", [])}
    chosen = _relevant_pages(pages, question, 6)
    if chosen:
        parts.append("EARNINGS-CALL PAGES CLOSEST TO THE QUESTION")
        for page_id in chosen:
            tag, _, page = page_id.partition(":")
            evidence[page_id] = {"label": f"Earnings call, {dates.get(tag, '')}, page {page}", "url": urls.get(tag),
                                 "page": int(page)}
            parts.append(f"[{page_id}]\n{pages[page_id][:5000]}")
    return "\n\n".join(parts), evidence, f"{report['name']}: research report"


def answer(kind: str, symbol: str, question: str, item_id: str = "", focus: str = "", history: list | None = None,
           model: str | None = None) -> dict:
    """Answer one question from one chosen context. Raises LookupError if the context does not exist."""
    question = " ".join(question.split())[:500]
    focus = " ".join((focus or "").split())[:500]
    if kind == "filing":
        context, evidence, about = _filing_context(symbol, item_id, question)
    else:
        context, evidence, about = _research_context(symbol, question)

    earlier = ""
    for turn in (history or [])[-3:]:
        if isinstance(turn, dict) and turn.get("q"):
            earlier += f"Earlier question: {str(turn['q'])[:300]}\nEarlier answer: {str(turn.get('a', ''))[:900]}\n"
    user = (
        (f"The investor is working on: {focus}\n\n" if focus else "")
        + (f"{earlier}\n" if earlier else "")
        + f"QUESTION: {question}\n\nCONTEXT\n{context}"
    )
    used = {}
    out = llm.ask(_SYSTEM, user, tier="fast", max_tokens=1200, model=model, used=used)

    points = []
    for point in out.get("points") or []:
        if not isinstance(point, dict) or not point.get("text"):
            continue
        cites = [c for c in (str(c).strip().strip("[]") for c in point.get("cites") or []) if c in evidence]
        if cites:                                   # a point with no traceable citation is not shown
            points.append({"text": point["text"], "cites": list(dict.fromkeys(cites))})
    answered = bool(out.get("answered")) and bool(points)
    cited = {c for p in points for c in p["cites"]}
    return {
        "about": about, "question": question, "answered": answered,
        "points": points if answered else [],
        "missing": out.get("missing") if isinstance(out.get("missing"), str) else None,
        "follow_ups": [q for q in out.get("follow_ups") or [] if isinstance(q, str)][:2],
        "evidence": {key: evidence[key] for key in cited},
        # When the documents cannot answer, a person might.
        "who": [] if answered else graph.who_to_call(symbol, limit=2),
        "model": " + ".join(sorted(used.get("fast", []))) or "saved answer",
    }
