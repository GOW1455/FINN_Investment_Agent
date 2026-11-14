"""End-to-end run of the research debate on real documents with a stand-in model.

Needs the network (screener.in and exchange PDFs), so it only runs when FINN_LIVE_TESTS=1.
It proves the orchestration and, above all, that the validator drops what it cannot trace.
"""
import os

import pytest

import fake_llm
from finn import llm
from finn.pull import research

pytestmark = pytest.mark.skipif(os.getenv("FINN_LIVE_TESTS") != "1", reason="set FINN_LIVE_TESTS=1 to run")


def test_debate_runs_and_drops_untraceable_claims(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ask", fake_llm.ask)
    monkeypatch.setattr(llm, "available", lambda tier="fast": True)
    monkeypatch.setattr(research, "PULL", tmp_path)
    monkeypatch.setattr(research, "READ_ANNUAL_REPORT", False)

    events = []
    result = research.run("RELIANCE", emit=events.append, refresh=True)

    assert result["status"] == "complete"
    assert [e["agent"] for e in events if e["type"] == "agent" and e["status"] == "done"] == \
        ["desk", "numbers", "guidance", "skeptic", "moderator"]
    # Every surviving promise is a quote that really is on the cited transcript page.
    assert result["guidance"] and all("triple our margins" not in g["quote"] for g in result["guidance"])
    # The invented fact id, the ghost scorecard row and the uncited bear point are all gone.
    assert all("N999" not in p["cites"] for p in result["numbers"]["trajectory"])
    assert [row["guidance"] for row in result["scorecard"]] == ["G1"]
    assert len(result["verdict"]["bull"]) == 3 and len(result["verdict"]["bear"]) == 2
    assert result["audit"]["dropped"] >= 4
    assert result["rebuttals"]["numbers"]["answer"] and result["rebuttals"]["guidance"]["answer"]
