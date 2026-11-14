"""The investor's network as an intelligence layer.

Everything here is deterministic: name normalisation, tenure overlap and scoring are plain code,
so the answer to "who should I call" is explainable and never invented by a model.
The network file is private to one investor; see README for the privacy model.
"""
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from .. import store
from ..config import CONTACTS, PORTFOLIO
from ..sources import screener

_DIR = Path(__file__).resolve().parent
# Words that say what kind of entity a company is, not which company it is.
_GENERIC = ("limited", "ltd", "pvt", "private", "india", "industries", "inds", "company", "co", "corporation",
            "corp", "inc", "technologies", "the", "group", "plc", "llp", "and", "enterprises", "laboratories",
            "labs", "lab", "pharmaceuticals", "pharmaceutical", "pharma")


def _tokens(name: str) -> list[str]:
    """Distinguishing words of a company name. Data sources shorten names ("Amber Enterp.", "KFin Technolog."),
    so a cut-off generic word is dropped too."""
    text = (name or "").lower().replace("&", " ")
    text = re.sub(r"\b(?:[a-z] ){2,}[a-z]\b", lambda m: m.group(0).replace(" ", ""), text)   # "N S D L" -> "nsdl"
    words = re.split(r"[^a-z0-9']+", text)
    return [w for w in words
            if w and w not in _GENERIC and not (len(w) >= 4 and any(g.startswith(w) for g in _GENERIC))]


def norm(name: str) -> str:
    return " ".join(_tokens(name))


def same_company(a: str, b: str) -> bool:
    x, y = _tokens(a), _tokens(b)
    if not x or not y:
        return False
    if x == y:
        return True
    # Same number of words, each equal or a shortened form of the other: "Kansai Nerol." = "Kansai Nerolac".
    # "HDFC Bank" vs "HDFC Life" fails on the second word; "Reliance" vs "Reliance Retail" fails on the count.
    if len(x) == len(y) and all(p == q or (min(len(p), len(q)) >= 3 and (p.startswith(q) or q.startswith(p)))
                                for p, q in zip(x, y)):
        return True
    return fuzz.ratio(" ".join(x), " ".join(y)) >= 92    # small spelling differences


@lru_cache(maxsize=1)
def _load() -> tuple:
    """The starting network that ships with the app, plus the contacts the investor added themselves."""
    people = store.read(_DIR / "people.json") or {"investor": {}, "people": []}
    added = store.read(CONTACTS) or []
    return people["investor"], [*people["people"], *added]


def add_contact(details: dict) -> dict:
    """Save a contact the investor entered and make it part of every network answer from now on."""
    added = store.read(CONTACTS) or []
    if len(added) >= 500:
        raise ValueError("The contact list is full")
    career = [{"company": r["company"].strip(), "title": (r.get("title") or "").strip() or "Role",
               "from": r.get("from"), **({"to": r["to"]} if r.get("to") else {})}
              for r in details.get("career", []) if (r.get("company") or "").strip()]
    current = next((r for r in career if not r.get("to")), career[0] if career else None)
    person = {
        "id": f"u{int(datetime.now().timestamp() * 1000):x}",
        "name": " ".join(details["name"].split()),
        "headline": (details.get("headline") or "").strip()
                    or (f"{current['title']}, {current['company']}" if current else ""),
        "relation": (details.get("relation") or "").strip(),
        "strength": max(1, min(5, int(details.get("strength") or 3))),
        "last_contact": details.get("last_contact") or date.today().isoformat(),
        "career": career,
        "education": [{"school": e["school"].strip(), "degree": (e.get("degree") or "").strip(), "year": e.get("year")}
                      for e in details.get("education", []) if (e.get("school") or "").strip()],
        "expertise": [t.strip() for t in details.get("expertise", []) if t.strip()][:12],
        "notes": (details.get("notes") or "").strip(),
        "added": True,
    }
    store.write(CONTACTS, [*added, person])
    _load.cache_clear()
    return person


def remove_contact(person_id: str) -> bool:
    """Remove a contact the investor added. The starting network cannot be removed this way."""
    added = store.read(CONTACTS) or []
    kept = [p for p in added if p["id"] != person_id]
    if len(kept) == len(added):
        return False
    store.write(CONTACTS, kept)
    _load.cache_clear()
    return True


def investor() -> dict:
    return _load()[0]


def people() -> list[dict]:
    return _load()[1]


def names_for(symbol: str, company_name: str = "", fetch: bool = False) -> list[str]:
    """Every name a company goes by: the portfolio's short name, its NSE symbol, and its registered name.
    With fetch=False only data already on disk is used, so scanning the whole portfolio costs no requests."""
    names = [company_name or PORTFOLIO.get(symbol, symbol), symbol]
    try:
        info = screener.company(symbol) if fetch else screener.known(symbol)
    except Exception:
        info = None
    if info and info.get("name"):
        names.append(info["name"])
    return list(dict.fromkeys(n for n in names if n))


def competitors(symbol: str) -> list[str]:
    """Peer companies as listed by screener.in. Nothing here is hand-written."""
    try:
        return [peer["name"] for peer in screener.company(symbol).get("peers", [])]
    except Exception:
        return []


def _year(value, default: int) -> int:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return default


def _span(role: dict) -> tuple[int, int]:
    this_year = date.today().year
    start = _year(role.get("from"), this_year)
    end = _year(role.get("to"), this_year) if role.get("to") else this_year
    return start, max(start, end)


def days_since_contact(person: dict) -> int | None:
    try:
        return (date.today() - datetime.strptime(person["last_contact"], "%Y-%m-%d").date()).days
    except (KeyError, ValueError):
        return None


def _card(person: dict) -> dict:
    """The public shape of a contact, used by every response."""
    return {
        "id": person["id"], "name": person["name"], "headline": person.get("headline", ""),
        "relation": person.get("relation", ""), "strength": person.get("strength", 3),
        "last_contact": person.get("last_contact"), "days_since_contact": days_since_contact(person),
        "added": bool(person.get("added")),
    }


# ---------- who should I call --------------------------------------------------------------

def _roles_at(person: dict, company_names: list[str]) -> list[dict]:
    return [r for r in person.get("career", []) if any(same_company(r["company"], n) for n in company_names)]


def industry(symbol: str) -> list[str]:
    """screener.in's classification for the company, broadest level first."""
    try:
        return screener.company(symbol).get("industry", [])
    except Exception:
        return []


# Everyday shortenings of industry words. General vocabulary, not company data.
_CLIPPED = {"pharma": "pharmaceutical", "telecom": "telecommunication", "auto": "automobile",
            "infra": "infrastructure", "tech": "technology", "agri": "agriculture", "fin": "financial"}


def _stem(word: str) -> str:
    """Reduce a word to its base so that different endings compare equal: banks, banking -> bank;
    deposits -> deposit; depositories -> depository. The last two stay different, as they should."""
    word = _CLIPPED.get(word, word)
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _knows_sector(tag: str, level: str) -> bool:
    """Does an expertise tag describe an industry label? Every word of the tag must appear in the label,
    compared by base form: 'pharma' fits 'Pharmaceuticals', 'banking' fits 'Private Sector Bank',
    but 'deposits' does not fit 'Depositories' and 'retail lending' does not fit 'Speciality Retail'."""
    skip = {"and", "of", "the", "other"}
    tag_stems = [_stem(w) for w in re.split(r"\W+", tag.lower()) if w and w not in skip]
    level_stems = {_stem(w) for w in re.split(r"\W+", level.lower()) if w and w not in skip}
    return bool(tag_stems) and all(t in level_stems for t in tag_stems)


def who_to_call(symbol: str, company_name: str = "", limit: int = 4) -> list[dict]:
    """Rank contacts by how much real context they can give on this company, and say why."""
    names = names_for(symbol, company_name, fetch=True)
    rivals = competitors(symbol)
    levels = industry(symbol)
    this_year = date.today().year
    ranked = []
    for person in people():
        best, total = None, 0.0

        def consider(score, angle, why, knows):
            nonlocal best, total
            total += score
            if best is None or score > best["score"]:
                best = {"score": score, "angle": angle, "why": why, "knows": knows}

        for role in _roles_at(person, names):
            start, end = _span(role)
            current = not role.get("to")
            recency = 1.0 if current else max(0.4, 1 - 0.05 * (this_year - end))
            tenure = min(1.0, 0.5 + 0.1 * (end - start))
            when = f"since {start}" if current else f"{start}–{end}"
            consider(100 * recency * tenure, "insider" if current else "alumnus",
                     f"{role['title']} at {role['company']} ({when})",
                     role.get("knows") or f"How {role['company']} runs from the inside: people, culture, execution.")
        for role in _roles_at(person, rivals):
            start, end = _span(role)
            current = not role.get("to")
            recency = 1.0 if current else max(0.4, 1 - 0.08 * (this_year - end))
            when = f"since {start}" if current else f"{start}–{end}"
            consider(60 * recency, "competitor",
                     f"{role['title']} at {role['company']} ({when}), a peer of {names[0]}",
                     f"How {names[0]} is seen by a rival: pricing, share shifts, who is winning deals.")
        if levels and best is None:
            # Match the most specific level first: knowing "Paints" says more than knowing "Consumer Discretionary".
            for depth, level in reversed(list(enumerate(levels))):
                tags = [t for t in person.get("expertise", []) if _knows_sector(t, level)]
                if tags:
                    specific = depth >= len(levels) - 2
                    consider(38 if specific else 26, "sector expert", f"Knows {level.lower()}: {', '.join(tags[:3])}",
                             f"The sector backdrop for {names[0]}: demand, regulation, who the credible operators are.")
                    break
        if best:
            warmth = person.get("strength", 3) / 5
            # Someone who has seen the company from two sides (ex-employee, now at a rival) knows more.
            combined = best["score"] + 0.35 * (total - best["score"])
            ranked.append({**_card(person), **best, "score": round(combined * (0.6 + 0.4 * warmth), 1)})
    ranked.sort(key=lambda r: -r["score"])
    return ranked[:limit]


# ---------- second-degree reach and diligence on people ------------------------------------

def paths_to(profile: dict, limit: int = 4) -> list[dict]:
    """Who in the network overlaps with an outside person (e.g. an incoming CFO), and how strong is the link.

    `profile` needs: name, career [{company, title, from, to}], education [{school, year}].
    Missing years are treated as unknown: same employer still counts, but as a weaker link.
    """
    target_name = norm(profile.get("name", ""))
    results = []
    for person in people():
        if target_name and fuzz.token_sort_ratio(norm(person["name"]), target_name) >= 93:
            results.append({**_card(person), "score": 100.0, "degree": 1,
                            "links": [{"kind": "direct", "detail": "Already in your network"}]})
            continue
        links, score = [], 0.0
        for theirs in profile.get("career", []):
            for mine in person.get("career", []):
                if not same_company(theirs.get("company", ""), mine["company"]):
                    continue
                known = theirs.get("from") or theirs.get("to")
                if known:
                    a0, a1 = _span(theirs)
                    b0, b1 = _span(mine)
                    years = min(a1, b1) - max(a0, b0)
                    if years < 0:
                        links.append({"kind": "same_employer",
                                      "detail": f"Both worked at {mine['company']}, at different times"})
                        score = max(score, 22)
                        continue
                    period = f"{max(a0, b0)}–{min(a1, b1)}"
                    links.append({"kind": "worked_together",
                                  "detail": f"Overlapped at {mine['company']} ({period}); "
                                            f"{person['name'].split()[0]} was {mine['title']}"})
                    score = max(score, min(90, 55 + 9 * years))
                else:
                    links.append({"kind": "same_employer", "detail": f"Both worked at {mine['company']}"})
                    score = max(score, 35)
        for theirs in profile.get("education", []):
            for mine in person.get("education", []):
                if not same_company(theirs.get("school", ""), mine["school"]):
                    continue
                gap = abs(_year(theirs.get("year"), 0) - _year(mine.get("year"), 9999))
                if gap <= 2:
                    links.append({"kind": "studied_together",
                                  "detail": f"Same batch era at {mine['school']} (class of {mine.get('year')})"})
                    score = max(score, 50)
                else:
                    links.append({"kind": "same_school", "detail": f"Both alumni of {mine['school']}"})
                    score = max(score, 18)
        if links:
            warmth = person.get("strength", 3) / 5
            # Path strength = how well you know the contact x how well the contact knows the target.
            results.append({**_card(person), "score": round(score * (0.5 + 0.5 * warmth), 1), "degree": 2,
                            "links": links[:3]})
    results.sort(key=lambda r: -r["score"])
    return results[:limit]


def link_strength(score: float) -> str:
    return "strong" if score >= 60 else "medium" if score >= 35 else "weak"


# ---------- expertise map --------------------------------------------------------------------

def expertise(theme: str, limit: int = 5) -> list[dict]:
    theme_l = theme.lower().strip()
    words = [w for w in re.split(r"\W+", theme_l) if len(w) > 2]
    ranked = []
    for person in people():
        score, evidence = 0.0, []
        for tag in person.get("expertise", []):
            if theme_l in tag.lower() or fuzz.token_set_ratio(theme_l, tag.lower()) >= 85:
                score += 40
                evidence.append(tag)
        blob = " ".join([person.get("headline", ""), person.get("notes", ""),
                         *[f"{r['company']} {r['title']}" for r in person.get("career", [])]]).lower()
        hits = sum(1 for w in words if w in blob)
        if words and hits:
            score += 25 * hits / len(words)
        if score >= 25:
            years = sum(_span(r)[1] - _span(r)[0] for r in person.get("career", []))
            ranked.append({**_card(person), "score": round(score + min(15, years / 2), 1),
                           "why": (", ".join(evidence) or person.get("headline", "")),
                           "notes": person.get("notes", "")})
    ranked.sort(key=lambda r: -r["score"])
    return ranked[:limit]


# ---------- keeping the network warm ---------------------------------------------------------

def keep_warm(announcements: list[dict], cold_after_days: int = 75, limit: int = 4) -> list[dict]:
    """A material filing at a contact's current or former employer is a natural reason to reconnect."""
    nudges = {}
    for item in announcements:
        if item.get("tier") != "material":
            continue
        names = [item["company"], *names_for(item["symbol"])]
        for person in people():
            days = days_since_contact(person)
            if days is None or days < cold_after_days:
                continue
            roles = _roles_at(person, names)
            if not roles:
                continue
            role = roles[0]
            verb = "works" if not role.get("to") else "used to work"
            current = nudges.get(person["id"])
            if current is None or item["priority"] > current["priority"]:
                nudges[person["id"]] = {
                    **_card(person), "priority": item["priority"], "symbol": item["symbol"],
                    "announcement_id": item["id"], "label": item["label"],
                    "reason": f"{person['name'].split()[0]} {verb} at {role['company']} ({role['title']}). "
                              f"{role['company']} just filed: {item['label'].lower()}. "
                              f"You last spoke {days} days ago.",
                }
    return sorted(nudges.values(), key=lambda n: (-n["priority"], -n["days_since_contact"]))[:limit]


# ---------- dossier --------------------------------------------------------------------------

def dossier(person_id: str) -> dict | None:
    person = next((p for p in people() if p["id"] == person_id), None)
    if not person:
        return None
    me = investor()
    shared = []
    for role in person.get("career", []):
        for mine in me.get("career", []):
            if same_company(role["company"], mine["company"]):
                shared.append(f"You both worked at {role['company']}")
    for school in person.get("education", []):
        for mine in me.get("education", []):
            if same_company(school["school"], mine["school"]):
                shared.append(f"You both studied at {school['school']}")
    covers = [symbol for symbol in PORTFOLIO
              if _roles_at(person, names_for(symbol))]
    return {**_card(person), "career": person.get("career", []), "education": person.get("education", []),
            "expertise": person.get("expertise", []), "notes": person.get("notes", ""),
            "shared_with_you": sorted(set(shared)), "portfolio_companies": covers}
