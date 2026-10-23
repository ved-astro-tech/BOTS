"""Life phases by relativity: how each dasha period compares with the rest of this person's own life.

No absolute "good" or "bad". Every dasha lord gets a small tally of classical factors, each Antardasha is scored
from its Mahadasha and Antardasha lords, and the score is ranked against all of the person's adult Antardashas.
The reading then says "better than usual for you", "tougher than usual for you", and where the shifts come.

Factors (each +1 or -1, summed; equal weights are an ASSUMPTION, the books give no weights):
- dignity in D1, and in D9 (BPHS dasha-phala chapters: exalted or own sign gives good results, debilitated bad;
  Phaladeepika Ch. 19-20 likewise)
- house from Lagna: kendra or trikona good, 6/8/12 bad (Phaladeepika Ch. 20; BPHS dasha-phala chapters)
- functional nature: lord of a trikona or of the Lagna good, lord of only 6/8/12 bad (BPHS Ch. 34)
- combust bad (Phaladeepika Ch. 19)
- KP: a lord signifying 11 (fulfilment) or 2/10 more than 8/12 gives gains, the reverse gives losses
  (K.S. Krishnamurti, KP Reader IV and VI)
- Antardasha lord from the Mahadasha lord: kendra, trikona or 11th flows, 6/8/12 obstructs (BPHS antardasha
  chapters; see engine/timing.py)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property

from astrobot.astro.chart import Chart
from astrobot.astro.constants import DUSTHANA, KENDRA, TRIKONA
from astrobot.astro.dasha import DashaTree, Period
from astrobot.engine.timing import ad_from_md

YEAR = timedelta(days=365.25)
GOOD_DIGNITY = {"exalted", "moolatrikona", "own"}
BAD_DIGNITY = {"debilitated"}
KP_GAIN, KP_LOSS = {2, 10, 11}, {8, 12}
BETTER, TOUGHER = 0.75, 0.25          # top and bottom quarter of the person's own periods
SHIFT = 0.35                          # percentile jump that counts as a turning point
ADULT_AGE = 16

# What a lord's houses bring up during its period. Whole-sign significations (Chart.significations).
THEMES = {
    10: "work and status", 6: "competition, service, debts or health", 7: "partnerships and business",
    11: "gains and goals met", 2: "income and family", 12: "expenses, moves or foreign links",
    8: "sudden changes and obstacles", 4: "home, property and peace of mind", 9: "luck, mentors and dharma",
    5: "studies, children and new ideas", 3: "effort, skills and short travel", 1: "self and health",
}


@dataclass(frozen=True)
class Factor:
    text: str
    value: int
    source: str


@dataclass
class LordQuality:
    lord: str
    factors: list[Factor] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(f.value for f in self.factors)

    def as_dict(self) -> dict:
        return {"lord": self.lord, "score": self.score,
                "factors": [{"text": f.text, "value": f.value, "source": f.source} for f in self.factors]}


def lord_quality(chart: Chart, lord: str) -> LordQuality:
    q = LordQuality(lord)
    add = q.factors.append
    for varga, src in (("D1", "BPHS dasha-phala chapters"), ("D9", "BPHS dasha-phala chapters (Navamsa)")):
        d = chart.dignity(lord, varga)
        if d in GOOD_DIGNITY:
            add(Factor(f"{lord} {d} in {varga}", 1, src))
        elif d in BAD_DIGNITY:
            add(Factor(f"{lord} debilitated in {varga}", -1, src))
    h = chart.house(lord)
    if h in KENDRA | TRIKONA:
        add(Factor(f"{lord} in house {h} (kendra/trikona)", 1, "Phaladeepika Ch. 20"))
    elif h in DUSTHANA:
        add(Factor(f"{lord} in house {h} (6/8/12)", -1, "Phaladeepika Ch. 20"))
    owned = set(chart.houses_owned(lord))
    if owned & {1, 5, 9}:
        add(Factor(f"{lord} lords {sorted(owned & {1, 5, 9})} (lagna/trikona)", 1, "BPHS Ch. 34"))
    elif owned and owned <= DUSTHANA:
        add(Factor(f"{lord} lords only {sorted(owned)} (dusthana)", -1, "BPHS Ch. 34"))
    if chart.combust(lord):
        add(Factor(f"{lord} combust", -1, "Phaladeepika Ch. 19"))
    sig = chart.significations(lord)
    gain, loss = sig & KP_GAIN, sig & KP_LOSS
    if 11 in sig and len(gain) > len(loss):
        add(Factor(f"{lord} signifies {sorted(gain)} over {sorted(loss)}", 1, "KP Reader (11th = fulfilment)"))
    elif len(loss) > len(gain):
        add(Factor(f"{lord} signifies {sorted(loss)} over {sorted(gain)}", -1, "KP Reader (8/12 = obstacles, loss)"))
    return q


def themes(chart: Chart, lords: list[str]) -> list[str]:
    """Life areas the running lords switch on, most shared first."""
    counts: dict[int, int] = {}
    for lord in lords:
        for h in chart.significations(lord):
            counts[h] = counts.get(h, 0) + 1
    ranked = sorted(counts, key=lambda h: (-counts[h], h))
    return [THEMES[h] for h in ranked[:4]]


@dataclass
class Phase:
    period: Period
    score: float
    percentile: float = 0.0
    ad_from_md: dict | None = None
    themes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return ("better than usual for you" if self.percentile >= BETTER else
                "tougher than usual for you" if self.percentile <= TOUGHER else "an average stretch for you")

    def as_dict(self) -> dict:
        return {"period": "/".join(self.period.lords), "start": self.period.start.date().isoformat(),
                "end": self.period.end.date().isoformat(), "score": self.score,
                "percentile": round(self.percentile, 2), "label": self.label,
                "ad_from_md": self.ad_from_md, "themes": self.themes}


def _percentiles(phases: list[Phase]) -> None:
    scores = sorted(p.score for p in phases)
    n = len(scores)
    for p in phases:
        below = sum(s < p.score for s in scores)
        equal = sum(s == p.score for s in scores)
        p.percentile = (below + 0.5 * equal) / n if n else 0.5


class Phases:
    """Antardasha phases from age 16 to `ahead` years after `now`, ranked against each other."""

    def __init__(self, chart: Chart, tree: DashaTree, now: datetime, ahead_years: float = 15):
        self.chart, self.tree, self.now = chart, tree, now
        self.start = tree.birth_utc + ADULT_AGE * YEAR
        self.end = now + ahead_years * YEAR

    @cached_property
    def quality(self) -> dict[str, LordQuality]:
        return {lord: lord_quality(self.chart, lord) for lord in {md.lord for md in self.tree.mds}}

    def score(self, md: str, ad: str) -> tuple[float, dict]:
        rel = ad_from_md(self.chart, md, ad)
        bonus = 1 if rel["nature"] == "supportive" else -1 if rel["nature"] == "obstructed" else 0
        if md == ad:
            bonus = 0
        return self.quality[md].score + self.quality[ad].score + bonus, rel

    @cached_property
    def antardashas(self) -> list[Phase]:
        out = []
        for md in self.tree.mds:
            if md.end <= self.start or md.start >= self.end:
                continue
            for ad in self.tree.antardashas(md):
                if ad.end <= self.start or ad.start >= self.end:
                    continue
                s, rel = self.score(md.lord, ad.lord)
                out.append(Phase(ad, s, ad_from_md=rel, themes=themes(self.chart, list(dict.fromkeys(ad.lords)))))
        _percentiles(out)
        return out

    def current(self) -> Phase:
        return next(p for p in self.antardashas if p.period.contains(self.now))

    def transitions(self) -> list[dict]:
        """Turning points: a new Mahadasha, or an Antardasha whose rank jumps by SHIFT or more."""
        out = []
        for prev, nxt in zip(self.antardashas, self.antardashas[1:]):
            md_change = prev.period.lords[0] != nxt.period.lords[0]
            jump = nxt.percentile - prev.percentile
            if not md_change and abs(jump) < SHIFT:
                continue
            kind = "relief" if jump >= SHIFT else "pressure" if jump <= -SHIFT else "new chapter"
            out.append({"date": nxt.period.start.date().isoformat(), "from": "/".join(prev.period.lords),
                        "to": "/".join(nxt.period.lords), "kind": kind, "mahadasha_change": md_change,
                        "jump": round(jump, 2), "past": nxt.period.start <= self.now})
        return out

    def _sub_phases(self, parent: Period, subs: list[Period], base: float) -> list[Phase]:
        """Score each sub-period from its parent's score plus its own lord, ranked within the parent only."""
        rows = []
        for sub in subs:
            rel = ad_from_md(self.chart, parent.lord, sub.lord)
            bonus = 0 if sub.lord == parent.lord else 1 if rel["nature"] == "supportive" else \
                -1 if rel["nature"] == "obstructed" else 0
            rows.append(Phase(sub, base + self.quality[sub.lord].score + bonus, ad_from_md=rel,
                              themes=themes(self.chart, [sub.lord])))
        _percentiles(rows)
        return rows

    def _upcoming(self, rows: list[Phase], days: float) -> list[dict]:
        horizon = self.now + timedelta(days=days)
        return [p.as_dict() for p in rows if p.period.end > self.now and p.period.start < horizon]

    def pratyantardashas(self, months: int = 12) -> list[dict]:
        """Sub-periods for the next months, ranked within the running Antardasha only (relative again)."""
        md, ad, _ = self.tree.at(self.now)
        base, _ = self.score(md.lord, ad.lord)
        return self._upcoming(self._sub_phases(ad, self.tree.pratyantardashas(ad), base), 30.44 * months)

    def sookshmas(self, weeks: int = 8) -> list[dict]:
        """Sookshma dashas for the next weeks, ranked within the running Pratyantardasha: how the coming days feel."""
        md, ad, pd = self.tree.at(self.now)
        base = next(p.score for p in self._sub_phases(ad, self.tree.pratyantardashas(ad), self.score(md.lord, ad.lord)[0])
                    if p.period.lords == pd.lords)
        return self._upcoming(self._sub_phases(pd, self.tree.sookshmas(pd), base), 7 * weeks)

    def mahadashas(self) -> list[dict]:
        rows = [Phase(md, self.quality[md.lord].score) for md in self.tree.mds
                if md.end > self.tree.birth_utc and md.start < self.end]
        _percentiles(rows)
        return [{"lord": p.period.lord, "start": p.period.start.date().isoformat(),
                 "end": p.period.end.date().isoformat(), "label": p.label,
                 "quality": self.quality[p.period.lord].as_dict()} for p in rows]

    def past_checks(self, n: int = 2, within_years: float = 12) -> list[dict]:
        """The clearest past shifts between neighbouring Antardashas, to ask whether life really changed then."""
        since = self.now - within_years * YEAR
        rows = []
        for prev, nxt in zip(self.antardashas, self.antardashas[1:]):
            if not since <= nxt.period.start <= self.now:
                continue
            jump = nxt.percentile - prev.percentile
            rows.append({"date": nxt.period.start.date().isoformat(), "from": "/".join(prev.period.lords),
                         "to": "/".join(nxt.period.lords), "kind": "easier" if jump > 0 else "harder",
                         "jump": round(jump, 2), "themes": nxt.themes,
                         "why": self._why(nxt.period.lords[-1], jump > 0)})
        rows = [r for r in sorted(rows, key=lambda r: -abs(r["jump"])) if abs(r["jump"]) >= 0.2][:n]
        return sorted(rows, key=lambda r: r["date"])

    def _why(self, lord: str, better: bool) -> str | None:
        """The lord's strongest factor pointing the same way as the shift, in plain words."""
        same = [f for f in self.quality[lord].factors if (f.value > 0) == better]
        return f"{same[0].text} ({same[0].source})" if same else None

    def summary(self) -> dict:
        cur = self.current()
        upcoming = [t for t in self.transitions() if not t["past"]][:4]
        return {"method": "relative to this person's own adult periods (Antardasha level)",
                "current": cur.as_dict(),
                "lords": {l: q.as_dict() for l, q in self.quality.items() if l in cur.period.lords},
                "next_months": self.pratyantardashas(), "next_weeks": self.sookshmas(),
                "upcoming_transitions": upcoming, "past_checks": self.past_checks(),
                "mahadashas": self.mahadashas(),
                "assumptions": ["Each factor counts +1 or -1 with equal weight; the books give no weights.",
                                "Labels compare periods within this one life, not against other people."]}
