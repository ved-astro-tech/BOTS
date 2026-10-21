"""Backtest: hide known life events, run the timing engine, and check where the events land.

    python -m backtest.run backtest/cases/career.yaml [--out report.md]

Three measures per event, each with its chance level so we know whether the engine beats guessing:
- percentile: rank of the event's Pratyantardasha among all PDs within +/-5 years (chance = 0.50)
- top20: event falls in the top 20% of those PDs (chance = 20%)
- window hit: event falls inside one of the top-3 windows found within +/-2 years
  (chance = the share of that 4-year span the windows cover)
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import yaml

from astrobot.astro.ephemeris import BirthData
from astrobot.engine import timing
from astrobot.engine.evidence import Engine

YEAR = timedelta(days=365.25)
RANDOM_CONTROLS = 20


@dataclass
class EventResult:
    case: str
    event_date: date
    event_type: str
    profile: str
    percentile: float
    control: float
    window_hit: bool
    window_coverage: float


def _utc(d: date) -> datetime:
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc)


def load_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def run_case(case: dict, domain: str, rng: random.Random) -> list[EventResult]:
    b = case["birth"]
    birth = BirthData(date.fromisoformat(str(b["date"])), time.fromisoformat(str(b["time"])),
                      float(b["lat"]), float(b["lon"]), tz=b.get("tz", "Asia/Kolkata"),
                      name=case.get("id", ""), place=b.get("place", ""),
                      time_certainty=b.get("time_certainty", "exact"))
    engine = Engine(birth, domain)
    results = []
    for event in case["events"]:
        when = _utc(date.fromisoformat(str(event["date"])))
        etype = event["type"]
        profile = engine.cfg["event_types"].get(etype, etype)

        wide = engine.score(etype, when - 5 * YEAR, when + 5 * YEAR)
        pct = timing.percentile_of(wide, when)
        span = (wide[-1].period.end - wide[0].period.start).days
        controls = [timing.percentile_of(wide, wide[0].period.start + timedelta(days=rng.randrange(span)))
                    for _ in range(RANDOM_CONTROLS)]

        near_start, near_end = when - 2 * YEAR, when + 2 * YEAR
        wins = timing.windows(engine.score(etype, near_start, near_end), top=3)
        covered = sum((min(date.fromisoformat(w["end"]), near_end.date())
                       - max(date.fromisoformat(w["start"]), near_start.date())).days for w in wins)
        hit = any(w["start"] <= when.date().isoformat() < w["end"] for w in wins)

        results.append(EventResult(case.get("id", "?"), when.date(), etype, profile, pct or 0.0,
                                   statistics.mean(c for c in controls if c is not None), hit,
                                   covered / (near_end - near_start).days))
    return results


def report(results: list[EventResult]) -> str:
    if not results:
        return "No events to score."
    lines = ["| Case | Event | Date | Percentile | Random control | In top-3 window | Window coverage |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r.case} | {r.event_type} | {r.event_date} | {r.percentile:.2f} | {r.control:.2f} | "
                     f"{'yes' if r.window_hit else 'no'} | {r.window_coverage:.0%} |")
    n = len(results)
    pct = statistics.mean(r.percentile for r in results)
    ctl = statistics.mean(r.control for r in results)
    top20 = sum(r.percentile >= 0.8 for r in results) / n
    hits = sum(r.window_hit for r in results) / n
    cover = statistics.mean(r.window_coverage for r in results)
    lines += ["", f"Events scored: {n}",
              f"Mean percentile: {pct:.2f} (random dates: {ctl:.2f}, chance 0.50)",
              f"Events in top 20% of periods: {top20:.0%} (chance 20%)",
              f"Events inside a top-3 window: {hits:.0%} (windows cover {cover:.0%} of the time, so chance is {cover:.0%})"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases")
    parser.add_argument("--domain", default="career")
    parser.add_argument("--out")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    results = [r for case in load_cases(args.cases) for r in run_case(case, args.domain, rng)]
    text = report(results)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
