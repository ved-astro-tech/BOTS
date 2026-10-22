"""HTTP API for testing the engine and readings. WhatsApp hosting comes later and calls the same functions."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from astrobot.astro.ephemeris import BirthData
from astrobot.engine import flow
from astrobot.engine.evidence import build_evidence
from astrobot.engine.rules import KNOWLEDGE_DIR
from astrobot.llm.provider import ProviderNotConfigured
from astrobot.llm.reading import answer

app = FastAPI(title="Astro bots", version="0.1.0")
DOMAINS = sorted(p.stem for p in KNOWLEDGE_DIR.glob("*.yaml"))


class BirthIn(BaseModel):
    date: date
    time: time
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    tz: str = "Asia/Kolkata"
    name: str = ""
    place: str = ""
    time_certainty: Literal["exact", "within_15_min", "rough"] = "exact"

    def to_birth(self) -> BirthData:
        return BirthData(**self.model_dump())


class EvidenceIn(BaseModel):
    birth: BirthIn
    as_of: datetime | None = None


class ReadingIn(EvidenceIn):
    question: str
    history: list[dict[str, str]] = []


def _check(domain: str) -> None:
    if domain not in DOMAINS:
        raise HTTPException(404, f"Unknown domain {domain}; available: {DOMAINS}")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "domains": DOMAINS}


@app.post("/v1/{domain}/evidence")
def evidence(domain: str, body: EvidenceIn) -> dict:
    _check(domain)
    return build_evidence(body.birth.to_birth(), domain, now=body.as_of)


@app.post("/v1/{domain}/reading")
def reading(domain: str, body: ReadingIn) -> dict:
    _check(domain)
    try:
        result = answer(body.birth.to_birth(), body.question, domain, body.history, now=body.as_of)
    except ProviderNotConfigured as e:
        raise HTTPException(503, str(e)) from e
    return {"reply": result.text, "evidence": result.evidence}


class ChatStartIn(BaseModel):
    birth: BirthIn
    as_of: date | None = None


class ChatReplyIn(BaseModel):
    state: dict
    text: str


@app.post("/v1/career/chat/start")
def chat_start(body: ChatStartIn) -> dict:
    """First message: 2-3 career guesses to confirm. Send the returned state back with each reply."""
    birth = body.birth.model_dump(mode="json")
    state, text = flow.start(birth, body.as_of.isoformat() if body.as_of else None)
    return {"reply": text, "state": state}


@app.post("/v1/career/chat/reply")
def chat_reply(body: ChatReplyIn) -> dict:
    state, text = flow.reply(body.state, body.text)
    return {"reply": text, "state": state}
