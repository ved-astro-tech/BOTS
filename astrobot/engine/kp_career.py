"""KP job, business and government verdict, and when each can happen by Dasha-Bhukti-Antara.

Verdict: the 10th cusp sub lord's significations decide service (6) against business (7, 11), and its
links to Sun, Moon or Mars decide government. Timing: an outcome happens only in a joint period whose
Mahadasha, Antardasha and Pratyantardasha lords are all significators of its houses (KP joint period).
"""
from __future__ import annotations

from datetime import datetime

from astrobot.astro.chart import Chart
from astrobot.astro.dasha import DashaTree
from astrobot.astro.kp import KPChart, star_and_sub_lord
from astrobot.engine.timing import ad_from_md


def _linked(chart: Chart, kp: KPChart, planet: str, targets: set[str]) -> list[str]:
    """How `planet` connects to any of `targets`: is one, sits in one's star, is conjunct or aspected by one."""
    out = []
    if planet in targets:
        out.append(f"{planet} itself")
    star = star_and_sub_lord(kp.longitudes[planet])[0]
    if star in targets and star != planet:
        out.append(f"in the star of {star}")
    for t in sorted(targets - {planet}):
        if chart.sign(t) == chart.sign(planet):
            out.append(f"conjunct {t}")
        elif t in chart.aspecting(chart.house(planet)):
            out.append(f"aspected by {t}")
    return out


def verdict(chart: Chart, kp: KPChart, spec: dict) -> dict:
    csl = kp.cusp_sub_lord(10)
    star = star_and_sub_lord(kp.longitudes[csl])[0]
    sig = kp.significations(csl)
    star_sig = kp.significations(star)
    outcomes = {}
    for name, o in spec["outcomes"].items():
        needs = set(o["cusp_needs"])
        outcomes[name] = {"cusp_sub_lord_signifies": sorted(sig & set(o["houses"])),
                          "denying": sorted(sig & set(o["deny"])), "promised": needs <= sig}
    job, biz = outcomes["job"]["promised"], outcomes["business"]["promised"]
    leans = "both" if job and biz else "job" if job else "business" if biz else "neither clearly"

    gov = set(spec["government_planets"])
    links = {p: _linked(chart, kp, p, gov) for p in dict.fromkeys([csl, star])}
    # The star lord shows the matter, so it is the star lord that must signify 6 and 10.
    gov_houses = set(spec["government_houses"]) <= star_sig
    government = {
        "links": {p: l for p, l in links.items() if l},
        "star_lord_signifies_6_and_10": gov_houses,
        "kind": sorted({spec["government_planets"][t] for p, ls in links.items() for l in ls
                        for t in gov if t in l}),
        "contested_links": {p: _linked(chart, kp, p, set(spec["contested_government_planets"]))
                            for p in dict.fromkeys([csl, star])},
    }
    government["promised"] = bool(government["links"]) and gov_houses and job
    return {"cusp_sub_lord": csl, "star_lord": star, "cusp_sub_lord_signifies": sorted(sig),
            "star_lord_signifies": sorted(star_sig), "leans": leans, "outcomes": outcomes,
            "government": government}


def timeline(chart: Chart, kp: KPChart, tree: DashaTree, spec: dict, start: datetime, end: datetime) -> dict:
    """Joint periods (MD, AD, PD) in which every lord signifies the outcome's houses."""
    gov = set(spec["government_planets"])
    out = {}
    for name, o in spec["outcomes"].items():
        houses, core, deny = set(o["houses"]), set(o["core"]), set(o["deny"])
        windows: list[dict] = []
        for pd in tree.pds_between(start, end):
            sigs = {lord: kp.significations(lord) for lord in pd.lords}
            if not all(s & houses for s in sigs.values()):
                continue
            union = set().union(*sigs.values())
            # A lord tied to more denying houses than event houses gives the event with losses or reversal.
            clean = all(len(s & houses) > len(s & deny) for s in sigs.values())
            entry = {
                "start": max(pd.start, start).date().isoformat(), "end": min(pd.end, end).date().isoformat(),
                "periods": ["/".join(pd.lords)],
                "strength": ("full" if core <= union else "partial") + ("" if clean else ", mixed"),
                "denying_houses": sorted(union & deny),
                "ad_from_md": ad_from_md(chart, *pd.lords[:2])["nature"],
                "government_lords": sorted(l for l in set(pd.lords) if _linked(chart, kp, l, gov)),
            }
            last = windows[-1] if windows else None
            if last and last["end"] == entry["start"] and last["strength"] == entry["strength"]:
                last["end"] = entry["end"]
                last["periods"] += entry["periods"]
                last["denying_houses"] = sorted(set(last["denying_houses"]) | set(entry["denying_houses"]))
                last["government_lords"] = sorted(set(last["government_lords"]) | set(entry["government_lords"]))
                if entry["ad_from_md"] != last["ad_from_md"]:
                    last["ad_from_md"] = "mixed"
            else:
                windows.append(entry)
        out[name] = windows
    return out
