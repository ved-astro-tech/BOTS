"""Two or three career guesses to confirm with the person, instead of one hard prediction.

The chart cannot name a job reliably (blind tests: 0 of 4 single calls right), so the bot offers the likeliest
sectors and asks. Each sector starts from how common it is in our known-outcome charts. Every sourced rule that
fires then moves it up or down by its measured track record on those charts: smoothed precision against the base
rate, from knowledge/stats/career_votes.yaml (written by backtest/option_votes.py).

ASSUMPTIONS, labelled as such:
- votes are treated as independent (naive Bayes); they are not, so the numbers only order the options
- the track records come from a few dozen charts, so they are shrunk toward the base rate (K below)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from astrobot.astro.chart import Chart
from astrobot.astro.constants import house_from
from astrobot.astro.kp import KPChart, star_and_sub_lord, sub_sub_lord

SECTORS = ["government", "private", "business", "profession", "politics"]
SECTOR_ALIASES = {"sports": "profession"}
NO_OUTCOME = {"student", "unemployed"}
STATS_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "stats" / "career_votes.yaml"
K = 5                      # pseudo-charts of shrinkage toward the base rate
GEMINI, VIRGO = 2, 5

SECTOR_TEXT = {
    "government": "a government or public-sector post",
    "private": "a job in a private company",
    "business": "your own business or trade",
    "profession": "an independent profession (law, accounts, medicine, sport or similar)",
    "politics": "politics or public leadership",
}


@dataclass(frozen=True)
class Vote:
    id: str
    says: str
    source: str
    sectors: frozenset[str]
    test: Callable[[Chart, KPChart, dict], bool]


def karakamsha(c: Chart) -> int:
    return c.sign(c.chara_karakas["Atmakaraka"], "D9")


def tenth_ssl_signifies(kp: KPChart) -> set[int]:
    ssl = sub_sub_lord(kp.cusps[9])
    star, sub = star_and_sub_lord(kp.longitudes[ssl])
    return kp.significations(ssl) | kp.significations(sub) | {kp.house_of(star)}


GOV, JOB, BIZ = frozenset({"government"}), frozenset({"government", "private"}), frozenset({"business"})
VOTES = [
    Vote("bphs_sector_gov", "Sun or Moon act directly on the 10th", "BPHS Ch. 3 vv. 14-15", GOV,
         lambda c, k, ev: ev["sector"]["leans"] == "government"),
    Vote("kp_gov", "KP 10th cusp sub lord links to Sun, Moon or Mars with 6 and 10", "KP Reader (K.S. Krishnamurti)",
         GOV, lambda c, k, ev: ev["kp_career"]["government"]["promised"]),
    Vote("sun_karakamsha", "Sun in the Karakamsha", "BPHS Ch. 33 v. 13", GOV,
         lambda c, k, ev: c.sign("Sun", "D9") == karakamsha(c)),
    Vote("sun_10_from_saturn", "Sun 10th from Saturn: high post", "Bhrigu Nadi Sangraha p. 45",
         frozenset({"government", "politics"}), lambda c, k, ev: house_from(c.sign("Sun"), c.sign("Saturn")) == 10),
    Vote("saturn_gemini_virgo", "Saturn in Gemini or Virgo: businessman", "Bhrigu Nadi Sangraha p. 47", BIZ,
         lambda c, k, ev: c.sign("Saturn") in (GEMINI, VIRGO)),
    Vote("khullar_biz", "10th cusp sub-sub lord signifies 7, not 6", "S.P. Khullar, KP sub-sub theory, App. B", BIZ,
         lambda c, k, ev: 7 in (s := tenth_ssl_signifies(k)) and 6 not in s),
    Vote("khullar_job", "10th cusp sub-sub lord signifies 6", "S.P. Khullar, KP sub-sub theory, App. B", JOB,
         lambda c, k, ev: 6 in tenth_ssl_signifies(k)),
    Vote("kp_csl_business", "KP 10th cusp sub lord leans to business", "KP Reader (K.S. Krishnamurti)", BIZ,
         lambda c, k, ev: ev["kp_career"]["leans"] == "business"),
    Vote("kp_csl_job", "KP 10th cusp sub lord leans to service", "KP Reader (K.S. Krishnamurti)", JOB,
         lambda c, k, ev: ev["kp_career"]["leans"] == "job"),
    Vote("parashari_business", "Parashari job-or-business cards lean to business", "career.yaml orientation_cards",
         BIZ, lambda c, k, ev: ev["job_or_business"]["leans"] == "business"),
    Vote("parashari_job", "Parashari job-or-business cards lean to a job", "career.yaml orientation_cards", JOB,
         lambda c, k, ev: ev["job_or_business"]["leans"] == "job"),
    Vote("jupiter_karakamsha", "Jupiter in the Karakamsha sign (D1): learning, law", "BPHS Ch. 33 v. 15",
         frozenset({"profession"}), lambda c, k, ev: c.sign("Jupiter") == karakamsha(c)),
    Vote("mercury_karakamsha", "Mercury in the Karakamsha: arts and trade", "BPHS Ch. 33 v. 14",
         frozenset({"business", "profession"}), lambda c, k, ev: c.sign("Mercury", "D9") == karakamsha(c)),
]


def sector_of(facts: dict) -> str | None:
    s = SECTOR_ALIASES.get(facts.get("sector"), facts.get("sector"))
    return s if s in SECTORS else None


def load_stats(path: Path = STATS_PATH) -> dict:
    if not path.exists():
        return {"charts": 0, "sector_counts": {}, "votes": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def fired(chart: Chart, kp: KPChart, ev: dict) -> list[Vote]:
    return [v for v in VOTES if v.test(chart, kp, ev)]


def rank(fired_ids: list[str], stats: dict) -> list[dict]:
    counts = stats.get("sector_counts", {})
    total = sum(counts.values())
    prior = {s: (counts.get(s, 0) + 1) / (total + len(SECTORS)) for s in SECTORS}
    weight = dict(prior)
    reasons: dict[str, list[dict]] = {s: [] for s in SECTORS}
    for vid in fired_ids:
        v = next(x for x in VOTES if x.id == vid)
        rec = stats.get("votes", {}).get(vid)
        if not rec or not rec["fired"]:
            continue
        base = sum(prior[s] for s in v.sectors)
        p = (rec["right"] + K * base) / (rec["fired"] + K)
        for s in SECTORS:
            weight[s] *= p / base if s in v.sectors else (1 - p) / (1 - base)
        for s in v.sectors:
            reasons[s].append({"rule": v.says, "source": v.source,
                               "track_record": f'right {rec["right"]} of {rec["fired"]} times in our charts'})
    z = sum(weight.values())
    return sorted(({"sector": s, "text": SECTOR_TEXT[s], "share": round(w / z, 2), "reasons": reasons[s]}
                   for s, w in weight.items()), key=lambda r: -r["share"])


def options(chart: Chart, kp: KPChart, ev: dict, stats: dict | None = None, n: int = 3) -> dict:
    stats = stats or load_stats()
    votes = fired(chart, kp, ev)
    ranked = rank([v.id for v in votes], stats)
    fields = []
    for planet in [ev["karmajiva"]["livelihood_planet"]] + [f["planet"] for f in ev["likely_fields"]]:
        if planet not in fields:
            fields.append(planet)
    return {
        "options": ranked[:n],
        "fields": [{"planet": p, "fields": next((f["fields"] for f in ev["likely_fields"] if f["planet"] == p),
                                                 ev["karmajiva"]["modern"])} for p in fields[:3]],
        "rules_fired": [{"id": v.id, "rule": v.says, "source": v.source} for v in votes],
        "based_on_charts": stats.get("charts", 0),
        "assumptions": ["Rules are treated as independent; the shares only order the options.",
                        f'Track records come from {stats.get("charts", 0)} known charts, shrunk toward the base rate.',
                        "Always confirm with the person; these are guesses, not predictions."],
    }
