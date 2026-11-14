"""HTTP API for FINN. Also serves the built frontend, so the whole app deploys as one service."""
import json
import queue
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from . import ask as asking
from . import llm
from .config import DEFAULT_ALERTS, PORTFOLIO, PULL, RESEARCH_DEMO, ROOT
from .network import graph
from .pull import research
from .push import classify, digest as push

app = FastAPI(title="FINN")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])
_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")


def _symbol(raw: str) -> str:
    symbol = raw.upper().strip().removesuffix(".NS")
    if not _SYMBOL.match(symbol):
        raise HTTPException(400, "Not a valid NSE symbol")
    return symbol


@app.get("/api/health")
def health():
    return {"ok": True, "models": {"fast": llm.model_for("fast"), "strong": llm.model_for("strong"),
                                    "fast_ready": llm.available("fast"), "strong_ready": llm.available("strong")},
            "usage": llm.usage}


@app.get("/api/models")
def models():
    """Models the investor can choose for new research. Saved reports keep the model they were made with."""
    return {"choices": llm.choices(), "default": llm.model_for("fast"),
            "reasoning_default": llm.model_for("strong")}


@app.get("/api/portfolio")
def portfolio():
    done = {p.stem for p in PULL.glob("*.json")}
    return {
        "portfolio": [{"symbol": s, "name": n, "researched": s in done} for s, n in PORTFOLIO.items()],
        "research_demo": [{"symbol": s, "researched": s in done} for s in RESEARCH_DEMO],
        "default_alerts": DEFAULT_ALERTS,
        "investor": graph.investor().get("name", ""),
    }


# ---- Push -------------------------------------------------------------------------------------

@app.get("/api/push/digest")
async def push_digest(hours: int = Query(24, ge=1, le=24 * 90),
                      volume_multiple: float = Query(DEFAULT_ALERTS["volume_multiple"], ge=1, le=20),
                      price_move_pct: float = Query(DEFAULT_ALERTS["price_move_pct"], ge=0.5, le=30),
                      lookback_days: int = Query(DEFAULT_ALERTS["lookback_days"], ge=5, le=60),
                      weights: str = ""):
    """`weights` carries the investor's own starting score per category, as 'results:90,dividend:20'.
    Categories not listed keep the default from the settings file."""
    chosen = {}
    for pair in weights.split(","):
        category, _, value = pair.partition(":")
        if category in classify.LABELS and value.isdigit() and 0 <= int(value) <= 100:
            chosen[category] = int(value)
    thresholds = {"volume_multiple": volume_multiple, "price_move_pct": price_move_pct,
                  "lookback_days": lookback_days}
    return await run_in_threadpool(push.digest, hours, chosen, thresholds)


@app.get("/api/push/settings")
def push_settings():
    """The ranking defaults, so the app can show a slider per category without repeating the numbers."""
    return {
        "categories": [{"id": key, "label": label, "base": classify.SETTINGS["base"][key]}
                       for key, label in classify.LABELS.items()],
        "tiers": classify.SETTINGS["tiers"],
        "market_reaction_points": classify.SETTINGS["market_reaction_points"],
    }


@app.get("/api/push/item/{symbol}/{item_id}")
async def push_item(symbol: str, item_id: str):
    item = await run_in_threadpool(push.detail, _symbol(symbol), item_id)
    if not item:
        raise HTTPException(404, "Filing not found")
    return item


# ---- Pull -------------------------------------------------------------------------------------

@app.get("/api/pull/{symbol}")
def pull_cached(symbol: str):
    result = research.cached(_symbol(symbol))
    if not result:
        raise HTTPException(404, "Not researched yet")
    return result


@app.get("/api/pull/{symbol}/stream")
def pull_stream(symbol: str, refresh: bool = False, model: str = ""):
    """Server-sent events: one per agent step, then the finished result.
    `model` must be one of the models offered by /api/models; it then runs every step of a new debate."""
    symbol = _symbol(symbol)
    if model and model not in {c["id"] for c in llm.choices()}:
        raise HTTPException(400, "That model is not available")
    events: queue.Queue = queue.Queue()

    def work():
        try:
            research.run(symbol, emit=events.put, refresh=refresh, model=model or None)
        except LookupError:
            events.put({"type": "error", "text": f"{symbol} was not found on screener.in. Check the NSE symbol."})
        except Exception as error:
            saved = research.cached(symbol)
            if saved:   # a live run failed (rate limit, scraper): fall back to the last good result
                events.put({"type": "result", "data": saved, "cached": True, "stale": True})
            else:
                events.put({"type": "error", "text": f"Research could not finish: {error}"})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            try:
                event = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- Ask: a question about one filing or one research report ------------------------------------

class Question(BaseModel):
    kind: str = Field(pattern="^(filing|research)$")
    symbol: str
    question: str = Field(min_length=3, max_length=500)
    item_id: str = Field(default="", max_length=40)
    focus: str = Field(default="", max_length=500)       # what the investor is working on
    history: list[dict] = Field(default_factory=list, max_length=6)
    model: str = ""


@app.post("/api/ask")
async def ask_question(body: Question):
    symbol = _symbol(body.symbol)
    if body.model and body.model not in {c["id"] for c in llm.choices()}:
        raise HTTPException(400, "That model is not available")
    if not llm.available("fast"):
        raise HTTPException(503, "No model key is configured")
    try:
        return await run_in_threadpool(asking.answer, body.kind, symbol, body.question, body.item_id,
                                       body.focus, body.history, body.model or None)
    except LookupError as error:
        raise HTTPException(404, str(error))
    except RuntimeError as error:                       # every model in the chain failed
        raise HTTPException(502, f"The model could not answer just now: {error}")


# ---- Network ----------------------------------------------------------------------------------

@app.get("/api/network/people")
def network_people():
    cards = [graph.dossier(p["id"]) for p in graph.people()]
    return {"investor": graph.investor(), "people": cards, "synthetic": True}


class Role(BaseModel):
    company: str = Field(max_length=80)
    title: str = Field(default="", max_length=80)
    from_year: int | None = Field(default=None, ge=1950, le=2100, alias="from")
    to_year: int | None = Field(default=None, ge=1950, le=2100, alias="to")


class School(BaseModel):
    school: str = Field(max_length=80)
    degree: str = Field(default="", max_length=80)
    year: int | None = Field(default=None, ge=1950, le=2100)


class NewContact(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    headline: str = Field(default="", max_length=120)
    relation: str = Field(default="", max_length=120)          # how the investor knows them
    strength: int = Field(default=3, ge=1, le=5)
    last_contact: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    career: list[Role] = Field(default_factory=list, max_length=12)
    education: list[School] = Field(default_factory=list, max_length=6)
    expertise: list[str] = Field(default_factory=list, max_length=12)
    notes: str = Field(default="", max_length=400)


@app.post("/api/network/people")
def network_add(body: NewContact):
    """Add a contact to the investor's network. It takes part in every network answer straight away."""
    details = body.model_dump()
    details["career"] = [{"company": r.company, "title": r.title, "from": r.from_year, "to": r.to_year}
                         for r in body.career]
    try:
        person = graph.add_contact(details)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return graph.dossier(person["id"])


@app.delete("/api/network/person/{person_id}")
def network_remove(person_id: str):
    if not graph.remove_contact(person_id):
        raise HTTPException(404, "Only contacts you added can be removed")
    return {"removed": person_id}


@app.get("/api/network/person/{person_id}")
def network_person(person_id: str):
    person = graph.dossier(person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    return person


@app.get("/api/network/company/{symbol}")
def network_company(symbol: str):
    symbol = _symbol(symbol)
    return {"symbol": symbol, "who_to_call": graph.who_to_call(symbol, limit=5)}


_FILLER = re.compile(r"\b(who|whom|should|can|could|do|does|i|my|me|in|on|the|a|an|is|are|for|about|of|to|"
                     r"call|ask|talk|speak|know|knows|network|people|person|go-?to|expert|experts|"
                     r"understand|help|with|at|worked|works|anyone|someone|which|what|and|best|placed)\b", re.I)


@app.get("/api/network/ask")
def network_ask(q: str = Query(..., min_length=2, max_length=200)):
    """Direct question to the network: a company ("who do I know at Asian Paints") or a theme ("rural lending")."""
    text = q.lower()
    for symbol in [*PORTFOLIO, *RESEARCH_DEMO]:
        names = graph.names_for(symbol)          # short name, NSE symbol, registered name
        short = {graph.norm(n) for n in names} - {""}
        if any(re.search(rf"\b{re.escape(n.lower())}\b", text) for n in [*names, *short]):
            label = PORTFOLIO.get(symbol, names[-1])
            return {"kind": "company", "symbol": symbol, "title": f"Who to call on {label}",
                    "results": graph.who_to_call(symbol, limit=5)}
    for person in graph.people():
        if person["name"].lower() in text or person["name"].split()[0].lower() in text.split():
            return {"kind": "person", "title": person["name"], "results": [graph.dossier(person["id"])]}
    theme = " ".join(_FILLER.sub(" ", text).replace("?", " ").split())
    results = graph.expertise(theme) if theme else []
    if not results and theme:   # perhaps an employer outside the portfolio: "anyone from McKinsey?"
        results = [{**graph.dossier(p["id"]), "why": f"{r['title']} at {r['company']}"}
                   for p in graph.people() for r in p.get("career", [])
                   if theme in r["company"].lower()][:5]
    return {"kind": "theme", "title": f"Your go-to people on {theme}" if results else f"No one found for “{theme or q}”",
            "theme": theme, "results": results}


# ---- Frontend (built files) ---------------------------------------------------------------------

_DIST = ROOT.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (_DIST / path).resolve()
        if path and target.is_file() and _DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")
