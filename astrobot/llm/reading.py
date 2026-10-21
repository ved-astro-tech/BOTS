"""Turn an Evidence Pack and a question into an astrologer's reply."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from astrobot.astro.ephemeris import BirthData
from astrobot.engine.evidence import build_evidence
from astrobot.llm.provider import LLMProvider, get_provider

PROMPTS = Path(__file__).resolve().parent / "prompts"


def system_prompt(domain: str, evidence: dict) -> str:
    persona = (PROMPTS / "persona.md").read_text(encoding="utf-8")
    domain_rules = (PROMPTS / f"{domain}.md").read_text(encoding="utf-8")
    return f"{persona}\n\n{domain_rules}\n\nEVIDENCE (the only facts you may use):\n{json.dumps(evidence, ensure_ascii=False)}"


@dataclass
class Reading:
    text: str
    evidence: dict


def answer(birth: BirthData, question: str, domain: str = "career", history: list[dict[str, str]] | None = None,
           provider: LLMProvider | None = None, now: datetime | None = None) -> Reading:
    evidence = build_evidence(birth, domain, now=now)
    provider = provider or get_provider()
    messages = [*(history or []), {"role": "user", "content": question}]
    return Reading(text=provider.complete(system_prompt(domain, evidence), messages), evidence=evidence)
