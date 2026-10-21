"""Event timing: score every Pratyantardasha by dasha activation and transit triggers.

promise  -> does the chart allow the event at all (engine/promise.py)
period   -> do the MD, AD and PD lords signify the event's houses
trigger  -> are Jupiter and Saturn both touching the domain's points (double transit)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from astrobot.astro.chart import Chart
from astrobot.astro.dasha import DashaTree, Period
from astrobot.astro.transits import snapshots

LEVEL_WEIGHTS = (0.3, 0.4, 0.3)   # MD, AD, PD
DASHA_SHARE = 0.65                # rest is the transit trigger
LINK_DAMPING = 0.7                # keeps one weak house from looking like a full link
POINT_WEIGHTS = {"lagna": 1.0, "moon": 0.7, "lord": 0.7}
TRANSIT_STEP_DAYS = 5


@dataclass(frozen=True)
class ScoredPeriod:
    period: Period
    dasha: float
    transit: float
    score: float
    links: dict[str, list[int]]

    def as_dict(self) -> dict:
        return {**self.period.as_dict(), "score": round(self.score, 3), "dasha": round(self.dasha, 3),
                "transit": round(self.transit, 3), "lord_houses": self.links}


def lord_link(chart: Chart, lord: str, houses: dict[int, float],
              against: dict[int, float] | None = None) -> tuple[float, list[int]]:
    """How strongly a dasha lord delivers the event: weight of the event's houses it signifies,
    relative to the opposing houses it also signifies (a lord tied to both 10 and 12 is mixed)."""
    signified = chart.significations(lord)
    hit = sorted(h for h in signified if h in houses)
    pos = sum(houses[h] for h in hit)
    neg = sum(w for h, w in (against or {}).items() if h in signified and h not in houses)
    return pos / (pos + neg + LINK_DAMPING), hit


def transit_points(chart: Chart, spec: dict) -> dict[int, float]:
    """Signs the slow planets must touch, with weight by how directly they stand for the domain."""
    points: dict[int, float] = {}

    def add(sign: int, weight: float) -> None:
        points[sign] = max(points.get(sign, 0.0), weight)

    for h in spec.get("houses_from_lagna", []):
        add(chart.house_sign(h), POINT_WEIGHTS["lagna"])
    for h in spec.get("houses_from_moon", []):
        add((chart.sign("Moon") + h - 1) % 12, POINT_WEIGHTS["moon"])
    for h in spec.get("lords_of", []):
        add(chart.sign(chart.lord(h)), POINT_WEIGHTS["lord"])
    return points


def transit_activation(points: dict[int, float], start: datetime, end: datetime) -> dict[str, float]:
    """Average over the window of: double transit (Jupiter and Saturn on the same point),
    Jupiter alone, Saturn alone, each weighted by the point."""
    snaps = snapshots(start, end, TRANSIT_STEP_DAYS)
    double = jup = sat = 0.0
    for s in snaps:
        j = {p: w for p, w in points.items() if s.aspects("Jupiter", p)}
        t = {p: w for p, w in points.items() if s.aspects("Saturn", p)}
        double += max((w for p, w in j.items() if p in t), default=0.0)
        jup += max(j.values(), default=0.0)
        sat += max(t.values(), default=0.0)
    n = len(snaps)
    return {"double": double / n, "jupiter": jup / n, "saturn": sat / n}


def transit_score(activation: dict[str, float]) -> float:
    jup_only = activation["jupiter"] - activation["double"]
    sat_only = activation["saturn"] - activation["double"]
    return min(1.0, activation["double"] + 0.3 * jup_only + 0.15 * sat_only)


def score_periods(chart: Chart, tree: DashaTree, houses: dict[int, float], points: dict[int, float],
                  start: datetime, end: datetime, against: dict[int, float] | None = None) -> list[ScoredPeriod]:
    out = []
    link_cache: dict[str, tuple[float, list[int]]] = {}
    for pd in tree.pds_between(start, end):
        links, dasha = {}, 0.0
        for weight, lord in zip(LEVEL_WEIGHTS, pd.lords):
            if lord not in link_cache:
                link_cache[lord] = lord_link(chart, lord, houses, against)
            value, hit = link_cache[lord]
            dasha += weight * value
            links[lord] = hit
        transit = transit_score(transit_activation(points, max(pd.start, start), min(pd.end, end)))
        out.append(ScoredPeriod(pd, dasha, transit, DASHA_SHARE * dasha + (1 - DASHA_SHARE) * transit, links))
    return out


def windows(scored: list[ScoredPeriod], top: int = 3, quantile: float = 0.8) -> list[dict]:
    """Merge neighbouring high-scoring PDs into windows and return the strongest ones."""
    if not scored:
        return []
    cutoff = sorted(s.score for s in scored)[int(quantile * (len(scored) - 1))]
    groups: list[list[ScoredPeriod]] = []
    for s in sorted(scored, key=lambda s: s.period.start):
        if s.score >= cutoff:
            if groups and groups[-1][-1].period.end >= s.period.start:
                groups[-1].append(s)
                continue
            groups.append([s])
    ranked = sorted(groups, key=lambda g: max(x.score for x in g), reverse=True)[:top]
    out = []
    for g in ranked:
        best = max(g, key=lambda x: x.score)
        out.append({"start": g[0].period.start.date().isoformat(), "end": g[-1].period.end.date().isoformat(),
                    "score": round(best.score, 3), "peak": best.as_dict(),
                    "periods": [x.period.label() for x in g]})
    return sorted(out, key=lambda w: w["start"])


def percentile_of(scored: list[ScoredPeriod], moment: datetime) -> float | None:
    """Share of periods in `scored` that score below the period containing `moment` (0 = worst, 1 = best)."""
    target = next((s for s in scored if s.period.contains(moment)), None)
    if target is None:
        return None
    below = sum(s.score < target.score for s in scored)
    ties = sum(s.score == target.score for s in scored) - 1
    return (below + ties / 2) / max(len(scored) - 1, 1)
