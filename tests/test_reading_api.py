from datetime import datetime, timezone

from fastapi.testclient import TestClient

from astrobot import api
from astrobot.llm import reading
from backtest import run as backtest

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self):
        self.calls = []

    def complete(self, system, messages, max_tokens=600):
        self.calls.append((system, messages))
        return "As per your chart, a good window for growth is coming."


def test_reading_sends_persona_domain_rules_and_evidence(birth):
    fake = FakeProvider()
    result = reading.answer(birth, "When will I get promoted?", provider=fake, now=NOW)
    system, messages = fake.calls[0]
    assert "Use ONLY the facts in the EVIDENCE JSON" in system
    assert "Domain: career." in system
    assert '"key_house"' in system
    assert messages[-1] == {"role": "user", "content": "When will I get promoted?"}
    assert result.text.startswith("As per your chart")


def test_api_evidence_and_reading(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(reading, "get_provider", lambda: fake)
    client = TestClient(api.app)
    birth = {"date": "1990-01-15", "time": "10:30", "latitude": 28.6139, "longitude": 77.209}
    assert "career" in client.get("/health").json()["domains"]
    r = client.post("/v1/career/evidence", json={"birth": birth, "as_of": "2026-10-21T00:00:00"})
    assert r.status_code == 200 and r.json()["key_house"]["house"] == 10
    r = client.post("/v1/career/reading", json={"birth": birth, "question": "Job change?", "as_of": "2026-10-21T00:00:00"})
    assert r.status_code == 200 and r.json()["reply"]
    assert client.post("/v1/astrology/evidence", json={"birth": birth}).status_code == 404


def test_backtest_runs_on_example_cases():
    results = []
    import random
    for case in backtest.load_cases("backtest/cases/career.example.yaml"):
        results += backtest.run_case(case, "career", random.Random(1))
    assert len(results) == 4
    assert all(0 <= r.percentile <= 1 for r in results)
    assert "Mean percentile" in backtest.report(results)


def test_reading_without_api_key_is_a_clear_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    client = TestClient(api.app)
    birth = {"date": "1990-01-15", "time": "10:30", "latitude": 28.6139, "longitude": 77.209}
    r = client.post("/v1/career/reading", json={"birth": birth, "question": "Job change?"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]
