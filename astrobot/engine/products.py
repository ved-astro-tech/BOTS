"""Pick a JASTRO store product for the person's career, from their chart.

Which planet: the first of the 10th lord, the running Mahadasha lord, the Antardasha lord and the Lagna lord that
is a functional benefic for this Lagna. Which stone: the Navaratna gem of that planet (Garuda Purana, Ratna
Pariksha chapters; the planet-gem pairs are the ones the store lists), plus a lower-priced substitute from the store.

ASSUMPTION, labelled as such: "strengthen a functional benefic, never a lord of 6, 8 or 12" is the common
practitioner rule for gem advice; BPHS gives no gemstone rule. Rahu and Ketu own no sign, so they are skipped.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from astrobot.astro.chart import Chart

CATALOG = Path(__file__).resolve().parent.parent / "knowledge" / "products.yaml"
NAVARATNA = {"Sun": r"\bruby\b", "Moon": r"\bpearl\b", "Mars": r"coral|moonga", "Mercury": r"emerald",
             "Jupiter": r"pukhraj", "Venus": r"diamond|opal", "Saturn": r"neelam", "Rahu": r"hessonite",
             "Ketu": r"cat'?s eye"}
BRACELET_THEMES = {"job": r"confiden|focus|courage|strength|success|decision",
                   "business": r"merchant|business|wealth|money|prosperity"}
GOOD_HOUSES, BAD_HOUSES = {1, 5, 9}, {6, 8, 12}


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    if not CATALOG.exists():
        return []
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["products"]


def functional_benefic(chart: Chart, planet: str) -> bool:
    owned = set(chart.houses_owned(planet))
    return bool(owned & GOOD_HOUSES) or bool(owned) and not owned & BAD_HOUSES


def pick_planet(chart: Chart, md: str, ad: str) -> dict | None:
    for role, planet in (("10th lord", chart.lord(10)), ("Mahadasha lord", md), ("Antardasha lord", ad),
                         ("Lagna lord", chart.lord(1))):
        if functional_benefic(chart, planet):
            return {"planet": planet, "role": role, "owns": chart.houses_owned(planet)}
    return None


def _brief(p: dict) -> dict:
    return {"title": p["title"], "price_inr": p["price_inr"], "benefits": p["benefits"], "handle": p["handle"]}


def recommend(chart: Chart, md: str, ad: str, sector: str | None = None, gender: str = "") -> dict | None:
    items = catalog()
    if not items:
        return None
    women = gender.lower().startswith(("f", "w"))
    out: dict = {"source": "JASTRO store catalogue", "rule": __doc__.split("\n\n")[1].replace("\n", " ")}
    choice = pick_planet(chart, md, ad)
    if choice:
        stones = sorted((p for p in items if p["type"] == "Gemstone" and p["planet"] == choice["planet"]),
                        key=lambda p: p["price_inr"])
        main = [p for p in stones if re.search(NAVARATNA[choice["planet"]], p["title"], re.I)]
        subs = [p for p in stones if p not in main]
        out.update(choice, gemstone=_brief(main[0]) if main else None, substitute=_brief(subs[0]) if subs else None)
    theme = BRACELET_THEMES["business" if sector == "business" else "job"]
    bracelets = sorted((p for p in items if p["type"] == "Bracelet" and (women or not p["for_women"])
                        and re.search(theme, p["benefits"] + " " + p["title"], re.I)), key=lambda p: p["price_inr"])
    out["bracelet"] = _brief(bracelets[0]) if bracelets else None
    return out
