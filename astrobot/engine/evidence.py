"""Evidence Pack: every chart fact the LLM is allowed to use, for one person and one domain.

The LLM never calculates. It receives this pack and is told not to state any position, date or
yoga that is not in it.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from astrobot.astro.chart import Chart
from astrobot.astro.constants import PLANETS, SIGN_LORDS, SIGNS
from astrobot.astro.dasha import DashaTree
from astrobot.astro.ephemeris import BirthData
from astrobot.astro.kp import KPChart, star_and_sub_lord
from astrobot.engine import timing
from astrobot.engine.rules import evaluate, load_domain

YEAR = timedelta(days=365.25)


def promise(chart: Chart, cfg: dict) -> dict:
    matches = evaluate(chart, cfg["cards"])
    score = max(0.0, min(100.0, 50 + sum(m.card.weight for m in matches)))
    label = "strong" if score >= 70 else "moderate" if score >= 45 else "weak"
    return {"score": round(score), "label": label,
            "supports": [m.as_dict() for m in matches if m.card.weight > 0],
            "challenges": [m.as_dict() for m in matches if m.card.weight < 0]}


def kp_verdict(kp: KPChart, spec: dict) -> dict:
    csl = kp.cusp_sub_lord(spec["cusp"])
    signified = kp.significations(csl)
    yes = sorted(signified & set(spec["yes_houses"]))
    no = sorted(signified & set(spec["no_houses"]))
    verdict = "supports" if yes and len(yes) >= len(no) else "mixed" if yes else "denies"
    return {"cusp": spec["cusp"], "cusp_sub_lord": csl, "signifies": sorted(signified),
            "supporting_houses": yes, "obstructing_houses": no, "verdict": verdict}


def orientation(chart: Chart, kp: KPChart, cfg: dict, running_lords: list[str],
                antardashas: list | None = None) -> dict | None:
    """Job or business: card totals, the KP 10th cusp sub lord's links to 6 and 7, and which
    of the two the running dasha lords activate."""
    cards = cfg.get("orientation_cards")
    if not cards:
        return None
    matches = evaluate(chart, cards)
    totals = {"job": 0.0, "business": 0.0}
    for m in matches:
        totals[m.card.leans] += m.card.weight
    csl = kp.cusp_sub_lord(cfg["kp"]["cusp"])
    csl_houses = kp.significations(csl)
    if 6 in csl_houses:
        totals["job"] += 2
    if 7 in csl_houses:
        totals["business"] += 2
    gap = totals["job"] - totals["business"]
    leans = "job" if gap >= 2 else "business" if gap <= -2 else "both"
    dasha = {p: {"job": 6 in chart.significations(p), "business": 7 in chart.significations(p)}
             for p in dict.fromkeys(running_lords)}
    # Each Antardasha lord delivers its own houses within the Mahadasha, so list which Antardashas of the
    # running Mahadasha open the job (6) or business (7) house, and where each sits from the MD lord.
    timeline = [{**ad.as_dict(), "job": 6 in chart.significations(ad.lord),
                 "business": 7 in chart.significations(ad.lord),
                 "ad_from_md": timing.ad_from_md(chart, ad.lords[0], ad.lord)} for ad in antardashas or []]
    return {"leans": leans, "totals": totals, "kp_cusp_sub_lord_houses": sorted(csl_houses),
            "running_dasha_activates": dasha, "antardasha_timeline": timeline, "matches": [m.as_dict() for m in matches],
            "eighth_house_planets": chart.occupants(8)}


def karmajiva(chart: Chart, cfg: dict) -> dict | None:
    """Brihat Jataka Ch. 10: strongest of the 10th lords from Lagna, Moon and Sun, then the lord of the
    navamsa it occupies names the livelihood. Strength here is our dignity score, as there is no Shadbala yet."""
    if "karmajiva" not in cfg:
        return None
    refs = {"Lagna": chart.lagna(), "Moon": chart.sign("Moon"), "Sun": chart.sign("Sun")}
    candidates = []
    for ref, sign in refs.items():
        tenth = (sign + 9) % 12
        lord = SIGN_LORDS[tenth]
        candidates.append({"from": ref, "tenth_sign": SIGNS[tenth], "lord": lord,
                           "lord_strength": round(chart.strength(lord), 2),
                           "planets_in_tenth": [p for p in PLANETS if chart.sign(p) == tenth]})
    best = max(candidates, key=lambda c: c["lord_strength"])
    navamsa = chart.sign(best["lord"], "D9")
    ruler = SIGN_LORDS[navamsa]
    return {"candidates": candidates, "strongest_tenth_lord": best["lord"],
            "navamsa_sign": SIGNS[navamsa], "livelihood_planet": ruler, **cfg["karmajiva"][ruler],
            "source": "Brihat Jataka Ch. 10 (Karmajiva)"}


def sector(chart: Chart, kp: KPChart, cfg: dict) -> dict | None:
    """Government or private: the BPHS role (Ch. 3 vv. 14-15) of each planet tied to the 10th.
    Kings (Sun, Moon) acting directly on the 10th point to government; tied only indirectly, possible."""
    roles = cfg.get("royal_roles")
    if not roles:
        return None
    csl = kp.cusp_sub_lord(cfg["kp"]["cusp"])
    direct = {"10th lord": [chart.lord(10)], "in 10th": chart.occupants(10), "aspects 10th": chart.aspecting(10),
              "D10 10th lord": [chart.lord(10, "D10")], "D10 lagna lord": [chart.lord(1, "D10")],
              "KP 10th cusp sub lord": [csl]}
    indirect = {"Amatyakaraka": [chart.chara_karakas["Amatyakaraka"]],
                "star lord of the 10th cusp sub lord": [star_and_sub_lord(kp.longitudes[csl])[0]]}
    links = [{"planet": p, "role": roles[p], "link": why, "direct": d}
             for d, group in ((True, direct), (False, indirect)) for why, ps in group.items() for p in ps]
    kings_direct = [l for l in links if l["role"] == "king" and l["direct"]]
    kings_indirect = [l for l in links if l["role"] == "king" and not l["direct"]]
    leans = "government" if kings_direct else "government possible" if kings_indirect else "private"
    return {"leans": leans, "links": links, "source": "BPHS Ch. 3 vv. 14-15 (planetary cabinet)"}


def likely_fields(chart: Chart, cfg: dict) -> list[dict]:
    key = cfg["key_house"]
    votes = Counter()
    votes[chart.lord(key)] += 3
    for p in chart.occupants(key):
        votes[p] += 2
    votes[chart.chara_karakas["Amatyakaraka"]] += 2
    votes[chart.lord(1, "D10")] += 1
    votes[chart.lord(key, "D10")] += 1
    return [{"planet": p, "fields": cfg["fields"][p]} for p, _ in votes.most_common(3)]


def confidence(score: float, kp: str, certainty: str) -> str:
    level = "high" if score >= 0.7 and kp == "supports" else "medium" if score >= 0.55 else "low"
    if certainty == "rough" and level == "high":
        level = "medium"
    return level


class Engine:
    def __init__(self, birth: BirthData, domain: str):
        self.birth = birth
        self.cfg = load_domain(domain)
        self.chart = Chart.from_birth(birth)
        self.kp = KPChart.from_birth(birth)
        self.tree = DashaTree(self.chart.lon("Moon"), birth.utc())
        self.points = timing.transit_points(self.chart, self.cfg["transit_points"])

    def _houses(self, profile: str | None) -> dict[int, float]:
        if not profile:
            return {}
        return {int(h): w for h, w in self.cfg["events"][profile]["houses"].items()}

    def score(self, event: str, start: datetime, end: datetime) -> list[timing.ScoredPeriod]:
        profile = self.cfg["event_types"].get(event, event)
        houses = self._houses(profile)
        against = self._houses(self.cfg["events"][profile].get("against"))
        nature = self.cfg["events"][profile].get("nature", "neutral")
        return timing.score_periods(self.chart, self.tree, houses, self.points, start, end, against, nature)

    def build(self, now: datetime | None = None, horizon_years: float = 3, lookback_years: float = 10) -> dict:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        birth_utc = self.birth.utc()
        past_start = max(now - lookback_years * YEAR, birth_utc + 18 * YEAR)
        future_end = now + horizon_years * YEAR
        kp = kp_verdict(self.kp, self.cfg["kp"])
        md, ad, pd = self.tree.at(now)

        future, past = {}, {}
        for event in self.cfg["events"]:
            future[event] = timing.windows(self.score(event, now, future_end))
            past[event] = timing.windows(self.score(event, past_start, now)) if past_start < now else []
        for event, wins in future.items():
            for w in wins:
                w["confidence"] = confidence(w["score"], kp["verdict"], self.birth.time_certainty)

        key = self.cfg["key_house"]
        lord = self.chart.lord(key)
        return {
            "domain": self.cfg["domain"],
            "as_of": now.date().isoformat(),
            "birth": {"name": self.birth.name, "date": self.birth.date.isoformat(),
                      "time": self.birth.time.strftime("%H:%M"), "place": self.birth.place,
                      "time_certainty": self.birth.time_certainty},
            "chart": self.chart.summary(),
            "key_house": {
                "house": key, "sign": SIGNS[self.chart.house_sign(key)], "lord": lord,
                "lord_house": self.chart.house(lord), "lord_sign": SIGNS[self.chart.sign(lord)],
                "lord_dignity": self.chart.dignity(lord), "lord_D9_sign": SIGNS[self.chart.sign(lord, "D9")],
                "lord_D10_dignity": self.chart.dignity(lord, "D10"),
                "occupants": self.chart.occupants(key), "aspected_by": self.chart.aspecting(key),
            },
            "promise": promise(self.chart, self.cfg),
            "kp": kp,
            "likely_fields": likely_fields(self.chart, self.cfg),
            "karmajiva": karmajiva(self.chart, self.cfg),
            "sector": sector(self.chart, self.kp, self.cfg),
            "job_or_business": orientation(self.chart, self.kp, self.cfg, list(md.lords + ad.lords),
                                           self.tree.antardashas(md)),
            "current_dasha": {
                "mahadasha": md.as_dict(), "antardasha": ad.as_dict(), "pratyantardasha": pd.as_dict(),
                "lord_houses": {p: sorted(self.chart.significations(p)) for p in dict.fromkeys(pd.lords)},
            },
            "future_windows": future,
            "past_windows": past,
            "transit_points": {SIGNS[s]: w for s, w in sorted(self.points.items())},
            "notes": _notes(self.birth.time_certainty),
        }


def _notes(certainty: str) -> list[str]:
    notes = ["Windows are periods of higher likelihood, not guarantees.",
             "Event types: rise = new job/promotion; change = switch or transfer; setback = loss or break."]
    if certainty != "exact":
        notes.append("Birth time is not exact: speak in seasons or half-years, not specific months, "
                     "and ask about past events to confirm the chart.")
    return notes


def build_evidence(birth: BirthData, domain: str = "career", now: datetime | None = None, **kwargs) -> dict:
    return Engine(birth, domain).build(now=now, **kwargs)
