"""Sort exchange announcements into ENAM's categories and decide how loudly each one speaks.

Rules run first and cost nothing. Only filings with a catch-all subject ("Updates", "Press Release")
that no rule can place go to the cheap model, in one batched call.
"""
import re
from pathlib import Path

from .. import llm, store

# category -> (base priority 0-100, label). Priority decides order; tier decides what is collapsed.
_DIR = Path(__file__).resolve().parent
SETTINGS = store.read(_DIR / "priority.json")     # base scores, adjustments and tier cut-offs live in this file
LABELS = {
    "results": "Results",
    "M&A": "M&A",
    "management_change": "Management",
    "litigation": "Litigation",
    "fund_raise": "Fund raise",
    "capex": "Capex",
    "pledging": "Pledging",
    "credit_rating": "Credit rating",
    "insider_trading": "Insider trade",
    "dividend": "Dividend",
    "bonus_split": "Bonus / split",
    "press_release": "Press release",
    "earnings_call": "Earnings call",
    "agm_egm": "AGM / EGM",
    "investor_meetings": "Investor meet",
    "postal_ballot": "Postal ballot",
    "unclassified": "Routine",
}
# category -> (base priority 0-100, label). Priority decides order; tier decides what is collapsed.
CATEGORIES = {key: (SETTINGS["base"][key], label) for key, label in LABELS.items()}

# (category, pattern matched against "subject || text"). First match wins, so order matters.
_RULES = [
    ("unclassified", r"loss of share|duplicate share|newspaper publication|trading window|esop|esps|esos|"
                     r"certificate under|compliance certificate|regulation 74|regulation 40|book closure|"
                     r"business responsibility|sustainability report|change in registrar|address change|"
                     r"secretarial|investor complaints|corporate governance report|shareholding pattern"),
    ("results", r"financial result|outcome of board meeting.*(result|unaudited|audited)|"
                r"(unaudited|audited) (standalone|consolidated|financial)|integrated filing.*financial"),
    ("earnings_call", r"transcript|earnings call|con\.? ?call|conference call|audio recording|recording of"),
    ("investor_meetings", r"analyst|institutional investor|investor meet|investor conference|investor presentation"),
    ("management_change", r"appointment|resignation|cessation|change in director|change in management|"
                          r"key managerial|retirement|re-?appoint|"
                          r"\b(ceo|cfo|managing director|chief executive|chief financial)\b.*"
                          r"(appoint|resign|step|cease|join|elevat)"),
    ("M&A", r"acqui|merger|amalgamation|demerger|scheme of arrangement|joint venture|slump sale|"
            r"divest|disinvest|sale of (stake|shares|subsidiary)|incorporation of|wholly[- ]owned subsidiary|"
            r"takeover|open offer|restructuring"),
    ("fund_raise", r"qip|qualified institution|preferential|rights issue|buy-?back|commercial paper|"
                   r"non-?convertible debenture|ncd|issue of securities|raising of funds|fund raising|"
                   r"allotment of (securities|equity|debentures|ncd)|bond"),
    ("litigation", r"litigation|\bcourt\b|tribunal|\bnclt\b|penalt|\bfine\b|show cause|order passed|orders passed|"
                   r"action\(s\) taken|sebi order|demand order|gst (demand|order)|tax demand|insolvency|"
                   r"\bdispute|arbitration|\bsearch (and|operation)|\braid\b|adjudicat"),
    ("pledging", r"pledge|encumbrance|invocation"),
    ("insider_trading", r"insider trading|sast|substantial acq|reg\.? ?7|reg\.? ?29|takeover regulations|"
                        r"regulation 7\(2\)|pit regulations"),
    ("credit_rating", r"credit rating|rating (assign|upgrade|downgrade|reaffirm|revis)|\bcrisil\b|\bicra\b|\bcare ratings\b"),
    ("dividend", r"dividend|record date"),
    ("bonus_split", r"bonus|stock split|sub-?division"),
    ("capex", r"capex|capital expenditure|capacity (expansion|addition)|new (plant|facility|unit)|"
              r"greenfield|brownfield|commission(ed|ing) of|capacity expansion|expansion of (capacity|plant|facility)"),
    ("postal_ballot", r"postal ballot|e-?voting"),
    ("agm_egm", r"annual general meeting|extra-?ordinary general|\bagm\b|\begm\b|shareholders meeting|"
                r"scrutinizer|voting results"),
    ("press_release", r"press release|media release|news verification|clarification|order win|"
                      r"bagging|awarding|contract|launch|partnership|collaborat|agreement|mou\b"),
]
_COMPILED = [(category, re.compile(pattern, re.I)) for category, pattern in _RULES]
_VAGUE_SUBJECT = re.compile(r"^(updates?|general updates?|press release|media release|"
                            r"disclosure of other upsi.*|miscellaneous|others?|intimation)$", re.I)
def classify_by_rules(subject: str, text: str) -> tuple[str, bool]:
    """Return (category, confident). Not confident means: vague subject and no rule hit in the body."""
    vague = bool(_VAGUE_SUBJECT.match(subject.strip()))
    if re.search(r"analysts?/institutional|investor meet", subject, re.I):
        # NSE files meetings and earnings calls under one subject; the body tells them apart.
        is_call = re.search(r"transcript|recording|earnings (call|conference)|results? (call|conference)", text, re.I)
        return ("earnings_call" if is_call else "investor_meetings"), True
    # A specific subject is the exchange's own label, so trust it before the body text.
    if not vague:
        for category, pattern in _COMPILED:
            if pattern.search(subject):
                return category, True
    for category, pattern in _COMPILED:
        if pattern.search(text):
            return category, True
    return ("press_release" if vague and text else "unclassified"), not vague


_ADJUSTMENTS = [{**rule, "_pattern": re.compile(rule["pattern"], re.I),
                 "_strip": re.compile(rule["strip"], re.I) if rule.get("strip") else None}
                for rule in SETTINGS["adjustments"]]


def score(category: str, subject: str, text: str, weights: dict | None = None,
          reaction: dict | None = None) -> tuple[int, list[str]]:
    """Priority 0-100 and the reasons behind it, so every card can say why it ranks where it does.

    weights:  the investor's own base score per category, overriding the settings file.
    reaction: the stock's unusual move around the filing, if there was one. This is evidence the market
              cared, and it applies to any company and any kind of filing.
    """
    base = (weights or {}).get(category, SETTINGS["base"][category])
    points = base
    reasons = [f"{LABELS[category]} filings start at {base}"
               + (" (your setting)" if category in (weights or {}) else "")]
    blob = f"{subject} {text}"
    for rule in _ADJUSTMENTS:
        if rule["category"] != category:
            continue
        haystack = rule["_strip"].sub(" ", blob) if rule["_strip"] else blob
        matched = bool(rule["_pattern"].search(haystack))
        change = rule["points"] if matched else rule.get("otherwise", 0)
        if change:
            points += change
            reasons.append(f"{change:+d}: {rule.get('why') if matched else rule.get('why_otherwise', 'no match')}")
        if matched and rule.get("stop"):
            break
    if reaction:
        bonus = SETTINGS["market_reaction_points"]
        points += bonus
        reasons.append(f"{bonus:+d}: the stock moved {reaction['change_pct']:+.1f}% on {reaction['volume_x']:.1f}x "
                       f"its usual volume on {reaction['date']}")
    return max(0, min(100, points)), reasons


def priority(category: str, subject: str, text: str, weights: dict | None = None) -> int:
    return score(category, subject, text, weights)[0]


def tier(points: int) -> str:
    cut = SETTINGS["tiers"]
    return "material" if points >= cut["material"] else "notable" if points >= cut["notable"] else "routine"


def summarise(text: str, limit: int = 190) -> str:
    """The exchange already carries a short description; trim it rather than pay a model to rewrite it."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"   # cutting at ". " breaks on "Mr. V. Rao"


_SYSTEM = (
    "You label Indian stock-exchange announcements. For each item pick exactly one category from: "
    + ", ".join(CATEGORIES) + ". 'unclassified' means routine paperwork that does not move a stock. "
    'Reply as JSON: {"labels": [{"id": "...", "category": "..."}]}.'
)


def classify(items: list[dict], weights: dict | None = None, reactions: dict | None = None) -> list[dict]:
    """Add category, label, priority, tier, the reasons for the rank, and a summary to each announcement.
    `reactions` maps a filing id to the stock's unusual move around it."""
    unsure = []
    for item in items:
        category, confident = classify_by_rules(item["subject"], item["text"])
        item["category"] = category
        if not confident and item["text"]:
            unsure.append(item)
    if unsure and llm.available("fast"):
        listing = "\n".join(f'- id={a["id"]} | {a["subject"]} | {a["text"][:300]}' for a in unsure[:60])
        try:
            labels = llm.ask(_SYSTEM, listing, tier="fast")["labels"]
            by_id = {str(row["id"]): row["category"] for row in labels if row.get("category") in CATEGORIES}
            for item in unsure:
                item["category"] = by_id.get(item["id"], item["category"])
        except Exception:
            pass  # the rule-based guess stands
    for item in items:
        reaction = (reactions or {}).get(item["id"])
        points, reasons = score(item["category"], item["subject"], item["text"], weights, reaction)
        item.update(label=LABELS[item["category"]], priority=points, tier=tier(points), why=reasons,
                    summary=summarise(item["text"]) or item["subject"])
        if reaction:
            item["reaction"] = reaction
    return items
