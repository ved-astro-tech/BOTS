from datetime import datetime, timezone

from astrobot.astro.chart import Chart
from astrobot.engine import timing
from astrobot.engine.evidence import Engine, build_evidence
from astrobot.engine.rules import PREDICATES, evaluate, load_domain

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def test_career_cards_load_and_use_known_predicates():
    cfg = load_domain("career")
    assert len(cfg["cards"]) >= 20
    assert all(c.predicate in PREDICATES for c in cfg["cards"])
    assert len({c.id for c in cfg["cards"]}) == len(cfg["cards"])


def test_rules_report_details(birth):
    chart = Chart.from_birth(birth)
    matches = evaluate(chart, load_domain("career")["cards"])
    ids = {m.card.id for m in matches}
    assert "CAR-001" in ids          # Jupiter, 10th lord, in the 4th
    assert "CAR-002" not in ids
    assert all(m.detail for m in matches)


def test_evidence_pack_shape(birth):
    ev = build_evidence(birth, "career", now=NOW)
    assert ev["key_house"]["lord"] == "Jupiter"
    assert 0 <= ev["promise"]["score"] <= 100
    assert ev["kp"]["verdict"] in {"supports", "mixed", "denies"}
    assert ev["current_dasha"]["mahadasha"]["lords"] == ["Rahu"]
    assert set(ev["future_windows"]) == {"rise", "setback", "change"}
    for wins in ev["future_windows"].values():
        for w in wins:
            assert w["start"] <= w["end"] and w["confidence"] in {"high", "medium", "low"}


def test_scores_are_bounded_and_discriminate(birth):
    engine = Engine(birth, "career")
    scored = engine.score("job_start", datetime(2010, 1, 1, tzinfo=timezone.utc), NOW)
    scores = [s.score for s in scored]
    assert all(0 <= s <= 1 for s in scores)
    assert max(scores) - min(scores) > 0.2       # periods are told apart, not all saturated
    assert timing.percentile_of(scored, datetime(2015, 6, 1, tzinfo=timezone.utc)) is not None


def test_rough_birth_time_caps_confidence(birth):
    from dataclasses import replace
    ev = build_evidence(replace(birth, time_certainty="rough"), "career", now=NOW)
    assert all(w["confidence"] != "high" for wins in ev["future_windows"].values() for w in wins)
    assert any("not exact" in n for n in ev["notes"])


def test_job_or_business_orientation():
    from datetime import date, time
    from astrobot.astro.ephemeris import BirthData
    birth = BirthData(date(2002, 8, 7), time(16, 55), 28.9845, 77.7064, place="Meerut")
    ori = build_evidence(birth, "career", now=NOW)["job_or_business"]
    ids = {m["id"] for m in ori["matches"]}
    assert {"ORI-J01", "ORI-J02", "ORI-B01", "ORI-B02"} <= ids   # Venus 6L in 10th, Rahu in 6th, Mercury 7L+10L, Saturn 3L in 7th
    assert ori["leans"] in {"job", "business", "both"}
    assert ori["running_dasha_activates"]["Venus"]["job"] is True
    assert len(ori["eighth_house_planets"]) == 4
