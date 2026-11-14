"""A stand-in model for tests: answers each agent's prompt with well-formed JSON built from the evidence
it was shown, plus one deliberately bad citation per agent so the validator has something to catch."""
import re


def ask(system, user, tier="fast", as_json=True, max_tokens=4000):
    if "in a research debate" in system:
        return {"answer": "A direct answer.", "cites": re.findall(r"\[(N\d+)\]", user)[:1], "concede": False}
    if system.startswith("You are the Numbers Analyst"):
        ids = re.findall(r"\[(N\d+)\]", user)
        return {"snapshot": [{"text": "Snapshot point.", "cites": ids[:1]}],
                "trajectory": [{"text": "Revenue has grown.", "cites": ids[9:11]},
                               {"text": "Invented claim.", "cites": ["N999"]}],
                "balance_sheet": [{"text": "Debt is rising.", "cites": ids[15:16]}],
                "cash_quality": [{"text": "Cash conversion is fine.", "cites": ids[20:21]}]}
    if system.startswith("You are the Guidance Analyst"):
        page = re.search(r"\[(C\d+:\d+)\]\n(.*?)(?=\n\n\[C\d+:\d+\]|\Z)", user, re.S)
        words = " ".join(page.group(2).split()).split(" ")
        real = " ".join(words[20:38])
        return {"quarter": "Q2 FY27", "tone": "Confident.",
                "guidance": [{"metric": "growth", "statement": "A real promise.", "quote": real,
                              "cite": page.group(1), "horizon": "FY27", "kind": "directional"},
                             {"metric": "margin", "statement": "A made-up promise.",
                              "quote": "we will certainly triple our margins by next tuesday afternoon",
                              "cite": page.group(1), "horizon": "FY27", "kind": "numeric"}],
                "pressure": [{"text": "Analysts asked about capex.", "cites": [page.group(1)]}]}
    if system.startswith("You describe what a company does"):
        pages = re.findall(r"\[(A:\d+)\]", user)
        return {"what": {"text": "It does things.", "cites": pages[:1]},
                "segments": [{"name": "Segment", "text": "A segment.", "cites": pages[1:2] or pages[:1]}]}
    if system.startswith("You are the Skeptic"):
        promises = re.findall(r"\[(G\d+)\]", user)
        facts = re.findall(r"\[(N\d+)\]", user)
        return {"scorecard": [{"guidance": promises[0], "delivered": "Growth came through.",
                               "verdict": "delivered", "cites": facts[10:11]},
                              {"guidance": "G99", "delivered": "Ghost row.", "verdict": "missed", "cites": facts[:1]}],
                "divergences": [{"text": "Story and numbers differ.", "cites": [promises[0], facts[12]]}],
                "challenge_numbers": "What about working capital?",
                "challenge_guidance": "Has management hit past targets?"}
    if system.startswith("You are the Moderator"):
        facts = re.findall(r"\[(N\d+)\]", user)
        point = lambda t, i: {"text": t, "cites": [facts[i]]}
        return {"headline": "A headline.", "narrative_vs_numbers": point("Mostly matches.", 10),
                "bull": [point("Bull 1", 10), point("Bull 2", 11), point("Bull 3", 12)],
                "bear": [point("Bear 1", 13), point("Bear 2", 14), {"text": "Bear 3 uncited", "cites": []}],
                "ask_management": ["Q1?", "Q2?", "Q3?"]}
    raise AssertionError(f"unexpected prompt: {system[:60]}")
