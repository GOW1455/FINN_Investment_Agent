"""Fast, offline checks of the deterministic parts: arithmetic, thresholds, labels, name matching."""
from finn.network import graph
from finn.push import classify, enrich
from finn.sources import prices


def test_pct_change():
    assert enrich.pct(110, 100) == 10.0
    assert enrich.pct(90, 100) == -10.0
    assert enrich.pct(-50, -100) == 50.0      # a loss that halved is an improvement
    assert enrich.pct(5, 0) is None and enrich.pct(None, 5) is None


def test_quarter_reported():
    assert enrich.quarter_reported("2026-11-12 10:00:00") == "Sep 2026"
    assert enrich.quarter_reported("2026-01-20 10:00:00") == "Dec 2025"
    assert enrich.quarter_reported("2026-05-02 10:00:00") == "Mar 2026"


def _bars(closes, volumes):
    return [{"date": f"2026-01-{i + 1:02d}", "close": c, "volume": v} for i, (c, v) in enumerate(zip(closes, volumes))]


def test_unusual_move_thresholds():
    quiet = _bars([100] * 21 + [101], [1000] * 22)
    assert prices.unusual_move(quiet, 2.0, 4.0, 20)["triggered"] == []
    spike = _bars([100] * 21 + [106], [1000] * 21 + [2500])
    move = prices.unusual_move(spike, 2.0, 4.0, 20)
    assert move["triggered"] == ["price", "volume"] and move["volume_x"] == 2.5 and move["change_pct"] == 6.0
    assert prices.unusual_move(spike, 3.0, 8.0, 20)["triggered"] == []   # the investor's thresholds decide


def test_reaction_to_a_filing():
    bars = _bars([100] * 21 + [106, 106], [1000] * 21 + [2500, 1000])      # day 22 is the unusual one
    during = prices.reaction_to(bars, "2026-01-22 11:00:00", 2.0, 4.0, 20)
    assert during == {"date": "2026-01-22", "change_pct": 6.0, "volume_x": 2.5}
    # Filed after the close the evening before: the market first reacts on the next session.
    assert prices.reaction_to(bars, "2026-01-21 18:30:00", 2.0, 4.0, 20)["date"] == "2026-01-22"
    assert prices.reaction_to(bars, "2026-01-10 11:00:00", 2.0, 4.0, 20) is None     # an ordinary day
    assert prices.reaction_to(bars, "2026-01-23 18:30:00", 2.0, 4.0, 20) is None     # no session yet


def test_ranking_is_explained_and_adjustable():
    points, reasons = classify.score("management_change", "Change in Management", "Resignation of Chief Financial Officer")
    assert points == 90 and "start at 82" in reasons[0] and "+8" in reasons[1]
    # The investor's own weight replaces the default, and a market reaction adds to it.
    points, reasons = classify.score("dividend", "Dividend", "Final dividend declared", weights={"dividend": 20},
                                     reaction={"date": "2026-01-22", "change_pct": 6.0, "volume_x": 2.5})
    assert points == 20 + classify.SETTINGS["market_reaction_points"]
    assert "your setting" in reasons[0] and "stock moved" in reasons[-1]


def test_classification_rules():
    label = lambda subject, text="": classify.classify_by_rules(subject, text)[0]
    assert label("Financial Result Updates") == "results"
    assert label("Loss of Share Certificates") == "unclassified"
    assert label("Acquisition") == "M&A"
    assert label("Updates", "Six Promising Research Projects win a prize") == "press_release"   # not 'search'
    assert label("Analysts/Institutional Investor Meet/Con. Call Updates", "one-on-one meeting") == "investor_meetings"
    assert label("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of earnings call") == "earnings_call"


def test_priority_judgment():
    cfo = classify.priority("management_change", "Change in Management", "Resignation of Chief Financial Officer")
    director = classify.priority("management_change", "Appointment", "Appointment of an Independent Director")
    assert cfo >= 70 > director
    assert classify.tier(classify.priority("fund_raise", "Updates", "Redemption of Commercial Paper")) == "routine"


def test_company_name_matching():
    same = graph.same_company
    assert same("HDFC Bank Ltd.", "HDFC Bank")
    assert same("Larsen & Toubro Limited", "Larsen and Toubro")
    assert not same("HDFC Bank", "HDFC Life")
    assert not same("Tata Consultancy Services", "Tata Sons")
    assert not same("Reliance Industries", "Reliance Retail")      # a subsidiary is a different company
    # Data sources shorten names; the shortened form must still match the full one.
    assert same("Dr Reddy's Labs", "Dr. Reddy's Laboratories")
    assert same("Amber Enterp.", "Amber Enterprises")
    assert same("Sun Pharma.Inds.", "Sun Pharmaceutical Industries")
    assert same("N S D L", "NSDL")


def test_who_to_call_ranks_insider_then_peer(monkeypatch):
    # Peers normally come from screener.in; fix them here so the test needs no network.
    monkeypatch.setattr(graph, "competitors", lambda symbol: ["Berger Paints", "Kansai Nerolac"])
    monkeypatch.setattr(graph, "names_for", lambda symbol, company_name="", fetch=False: ["Asian Paints", symbol])
    monkeypatch.setattr(graph, "industry", lambda symbol: ["Consumer Discretionary", "Paints"])
    ranked = graph.who_to_call("ASIANPAINT")
    assert ranked[0]["name"] == "Neha Kulkarni" and ranked[0]["angle"] == "insider"
    assert ranked[1]["name"] == "Rohan Deshpande" and ranked[1]["angle"] == "competitor"
    assert {r["angle"] for r in ranked} <= {"insider", "alumnus", "competitor", "sector expert"}


def test_expertise_tag_fits_industry_label():
    fits = graph._knows_sector
    assert fits("paints", "Paints")
    assert fits("pharma", "Pharmaceuticals")
    assert fits("banking", "Private Sector Bank")
    assert fits("specialty chemicals", "Specialty Chemicals")
    assert not fits("retail lending", "Speciality Retail")      # a lender is not a retail expert
    assert not fits("consumer", "Computers - Software & Consulting")
    assert not fits("consumer", "Oil, Gas & Consumable Fuels")
    assert not fits("deposits", "Depositories, Clearing Houses and Other Intermediaries")   # a banker is not a depository expert
    assert fits("depositories", "Depositories, Clearing Houses and Other Intermediaries")
    assert fits("telecom", "Telecommunication")


def test_second_degree_path():
    outsider = {"name": "Someone New", "education": [],
                "career": [{"company": "McKinsey & Company", "title": "Partner", "from": 2005, "to": 2014}]}
    paths = graph.paths_to(outsider)
    assert paths and paths[0]["degree"] == 2 and paths[0]["links"][0]["kind"] == "worked_together"
    assert graph.paths_to({"name": "Nobody", "career": [{"company": "Acme Unknown"}], "education": []}) == []
