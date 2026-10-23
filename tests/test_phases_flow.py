from datetime import datetime, timezone

from fastapi.testclient import TestClient

from astrobot import api
from astrobot.astro.chart import Chart
from astrobot.astro.dasha import DashaTree
from astrobot.engine import career_options, flow
from astrobot.engine.phases import Phases, lord_quality

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
BIRTH = {"date": "1990-01-15", "time": "10:30", "latitude": 28.6139, "longitude": 77.209, "name": "Test"}


def test_every_factor_is_sourced_and_unit(birth):
    chart = Chart.from_birth(birth)
    for lord in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
        for f in lord_quality(chart, lord).factors:
            assert f.value in (1, -1) and f.source


def test_phases_are_relative_and_cover_now(birth):
    chart = Chart.from_birth(birth)
    ph = Phases(chart, DashaTree(chart.lon("Moon"), birth.utc()), NOW)
    pcts = [p.percentile for p in ph.antardashas]
    assert min(pcts) < 0.25 and max(pcts) > 0.75
    assert ph.current().period.contains(NOW)
    s = ph.summary()
    assert all(t["date"] > NOW.date().isoformat() for t in s["upcoming_transitions"])
    assert all(p["end"] > NOW.date().isoformat() for p in s["next_months"])


def test_options_rank_all_sectors_and_votes_move_them():
    stats = {"charts": 10, "sector_counts": {"private": 5, "business": 5},
             "votes": {"saturn_gemini_virgo": {"fired": 4, "right": 4}}}
    plain = {o["sector"]: o["share"] for o in career_options.rank([], stats)}
    voted = {o["sector"]: o["share"] for o in career_options.rank(["saturn_gemini_virgo"], stats)}
    assert len(plain) == len(career_options.SECTORS)
    assert voted["business"] > plain["business"] and voted["private"] < plain["private"]


def test_classify_answers():
    offered = ["private", "business", "government"]
    assert flow.classify("2", offered) == "business"
    assert flow.classify("I have my own shop", offered) == "business"
    assert flow.classify("sarkari naukri, railway", offered) == "government"
    assert flow.classify("software engineer at an MNC", offered) == "private"
    assert flow.classify("still looking for a job", offered) == "seeking"


def test_intents():
    assert flow.intent("I am very worried, will I ever settle?") == "worry"
    assert flow.intent("When will I get a promotion?") == "timing"
    assert flow.intent("Should I switch to business?") == "direction"
    assert flow.intent("Tell me about my boss") == "general"


def test_flow_runs_end_to_end_without_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(flow, "DATA_DIR", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    state, text = flow.start(BIRTH, "2026-10-21")
    assert "1." in text and "2." in text and state["step"] == "confirm"
    state, text = flow.reply(state, "private company job")
    assert state["step"] == "questions" and "cannot decide your direction" in text
    state, text = flow.reply(state, "When will I get a promotion?")
    assert "Compared with the rest of your own life" in text and "KP" in text
    state, text = flow.reply(state, "I feel stuck and worried")
    assert "What else would you like to know?" in text
    rows = (tmp_path / "career_confirmations.jsonl").read_text().splitlines()
    assert '"sector": "private"' in rows[0]


def test_next_weeks_are_sookshmas(birth):
    chart = Chart.from_birth(birth)
    weeks = Phases(chart, DashaTree(chart.lon("Moon"), birth.utc()), NOW).sookshmas()
    assert weeks and all(len(w["period"].split("/")) == 4 for w in weeks)


def test_chat_api(tmp_path, monkeypatch):
    monkeypatch.setattr(flow, "DATA_DIR", tmp_path)
    client = TestClient(api.app)
    r = client.post("/v1/career/chat/start", json={"birth": BIRTH, "as_of": "2026-10-21"}).json()
    r = client.post("/v1/career/chat/reply", json={"state": r["state"], "text": "own business"}).json()
    assert r["state"]["answers"]["occupation"]["sector"] == "business"
