"""Rule cards: classical conditions checked against a chart by named predicates.

A card in knowledge/<domain>.yaml names a predicate and its params. The predicate returns a short
detail string when the condition holds, or None. Adding a card never needs new code unless it
introduces a new kind of condition.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import yaml

from astrobot.astro.chart import Chart
from astrobot.astro.constants import KENDRA, SIGNS, TRIKONA

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

Predicate = Callable[..., "str | None"]
PREDICATES: dict[str, Predicate] = {}


def predicate(fn: Predicate) -> Predicate:
    PREDICATES[fn.__name__] = fn
    return fn


def _place(chart: Chart, planet: str, varga: str) -> str:
    return f"{planet} in house {chart.house(planet, varga)} ({SIGNS[chart.sign(planet, varga)]}, {varga})"


@predicate
def lord_in_houses(chart: Chart, house: int, houses: list[int], varga: str = "D1") -> str | None:
    lord = chart.lord(house, varga)
    if chart.house(lord, varga) in houses:
        return f"lord of {house}, {_place(chart, lord, varga)}"
    return None


@predicate
def lord_strength(chart: Chart, house: int, min: float = 0.0, max: float = 1.0, varga: str = "D1") -> str | None:
    lord = chart.lord(house, varga)
    score = chart.strength(lord, varga)
    if min <= score <= max:
        return f"lord of {house} {lord} is {chart.dignity(lord, varga)} in {varga}"
    return None


@predicate
def lord_dignity_is(chart: Chart, house: int, dignities: list[str], varga: str = "D1") -> str | None:
    lord = chart.lord(house, varga)
    if chart.dignity(lord, varga) in dignities:
        return f"lord of {house} {lord} is {chart.dignity(lord, varga)} in {varga}"
    return None


@predicate
def lord_combust(chart: Chart, house: int) -> str | None:
    lord = chart.lord(house)
    return f"lord of {house} {lord} is combust" if chart.combust(lord) else None


@predicate
def lord_placed_and_strong(chart: Chart, house: int, houses: list[int], min: float) -> str | None:
    lord = chart.lord(house)
    if chart.house(lord) in houses and chart.strength(lord) >= min:
        return f"lord of {house}, {_place(chart, lord, 'D1')}, {chart.dignity(lord)}"
    return None


@predicate
def lord_vargottama(chart: Chart, house: int) -> str | None:
    lord = chart.lord(house)
    return f"lord of {house} {lord} is vargottama in {SIGNS[chart.sign(lord)]}" if chart.vargottama(lord) else None


@predicate
def planets_in_house(chart: Chart, house: int, planets: list[str], varga: str = "D1") -> str | None:
    found = [p for p in planets if chart.house(p, varga) == house]
    return f"{', '.join(found)} in house {house} ({varga})" if found else None


@predicate
def house_aspected_by(chart: Chart, house: int, planets: list[str]) -> str | None:
    found = [p for p in planets if p in chart.aspecting(house)]
    return f"{', '.join(found)} aspects house {house}" if found else None


@predicate
def lords_connected(chart: Chart, house_a: int, house_b: int) -> str | None:
    a, b = chart.lord(house_a), chart.lord(house_b)
    if a == b:
        return f"{a} rules both {house_a} and {house_b}"
    how = chart.connected(a, b)
    if how:
        return f"lord of {house_a} {a} and lord of {house_b} {b}: {how}"
    if chart.house(a) == house_b:
        return f"lord of {house_a} {a} sits in house {house_b}"
    if chart.house(b) == house_a:
        return f"lord of {house_b} {b} sits in house {house_a}"
    return None


@predicate
def raja_yoga(chart: Chart) -> str | None:
    """Lord of a kendra (4, 7, 10) linked with lord of a trikona (5, 9) by conjunction, exchange or mutual aspect.
    The lagna is both, so it is left out to avoid trivial matches."""
    for k in sorted(KENDRA - {1}):
        for t in sorted(TRIKONA - {1}):
            a, b = chart.lord(k), chart.lord(t)
            if a == b:
                return f"{a} rules both kendra {k} and trikona {t} (yogakaraka)"
            how = chart.connected(a, b)
            if how in ("conjunction", "exchange", "mutual aspect"):
                return f"lord of {k} {a} and lord of {t} {b}: {how}"
    return None


@predicate
def karaka_strength(chart: Chart, karaka: str, min: float = 0.0, max: float = 1.0) -> str | None:
    planet = chart.chara_karakas[karaka]
    score = chart.strength(planet)
    return f"{karaka} {planet} is {chart.dignity(planet)}" if min <= score <= max else None


@predicate
def karaka_dignity_is(chart: Chart, karaka: str, dignities: list[str]) -> str | None:
    planet = chart.chara_karakas[karaka]
    return f"{karaka} {planet} is {chart.dignity(planet)}" if chart.dignity(planet) in dignities else None


@predicate
def planet_strength(chart: Chart, planet: str, min: float = 0.0, max: float = 1.0) -> str | None:
    score = chart.strength(planet)
    return f"{planet} is {chart.dignity(planet)}" if min <= score <= max else None


@dataclass(frozen=True)
class Card:
    id: str
    title: str
    predicate: str
    params: dict
    weight: float
    effect: str
    source: str
    phrasing_en: str


@dataclass(frozen=True)
class OrientationCard(Card):
    leans: str = ""


@dataclass(frozen=True)
class Match:
    card: Card
    detail: str

    def as_dict(self) -> dict:
        c = self.card
        return {"id": c.id, "title": c.title, **({"leans": c.leans} if hasattr(c, "leans") else {}), "weight": c.weight, "detail": self.detail,
                "effect": c.effect, "source": c.source, "phrasing": c.phrasing_en}


@lru_cache(maxsize=None)
def load_domain(domain: str) -> dict:
    with open(KNOWLEDGE_DIR / f"{domain}.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["cards"] = [Card(**card) for card in data.get("cards", [])]
    data["orientation_cards"] = [OrientationCard(**card) for card in data.get("orientation_cards", [])]
    for card in data["cards"] + data["orientation_cards"]:
        if card.predicate not in PREDICATES:
            raise ValueError(f"{domain}: card {card.id} uses unknown predicate {card.predicate}")
    return data


def evaluate(chart: Chart, cards: list[Card]) -> list[Match]:
    matches = []
    for card in cards:
        detail = PREDICATES[card.predicate](chart, **card.params)
        if detail:
            matches.append(Match(card, detail))
    return matches
