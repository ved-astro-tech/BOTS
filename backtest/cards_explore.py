"""Score candidate career rule cards from B.V. Raman's Notable Horoscopes against charts with known careers.

    python -m backtest.cards_explore cases1.yaml [cases2.yaml ...]

For each card: how often it holds for charts in its target groups versus all other charts. A card is useful
only when it holds clearly more often for its targets (lift well above 1) on a reasonable number of charts.
"""
from __future__ import annotations

import sys
from datetime import date, time

import yaml

from astrobot.astro.chart import Chart
from astrobot.astro.constants import SIGN_LORDS, house_from
from astrobot.astro.ephemeris import BirthData

SEVEN = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]


def tenth_signs(c: Chart) -> list[int]:
    """10th sign from the Lagna and from the Moon (R1, judged from both)."""
    return [(c.lagna() + 9) % 12, (c.sign("Moon") + 9) % 12]


def on_tenth(c: Chart, planet: str) -> bool:
    """Planet occupies or aspects the 10th from the Lagna or the Moon."""
    return any(c.aspects_sign(planet, s) for s in tenth_signs(c))


def in_tenth(c: Chart, planet: str) -> bool:
    return c.sign(planet) in tenth_signs(c)


def tenth_lords(c: Chart) -> set[str]:
    return {SIGN_LORDS[s] for s in tenth_signs(c)}


def linked(c: Chart, a: str, b: str) -> bool:
    return a == b or c.connected(a, b) in ("conjunction", "exchange", "mutual aspect")


def touches(c: Chart, planet: str, houses: list[int]) -> bool:
    """Planet occupies, aspects or owns one of the houses from the Lagna."""
    return any(c.aspects_sign(planet, c.house_sign(h)) or c.lord(h) == planet for h in houses)


CARDS = {
    "R5/R6 royal planet (Sun or Moon) in the 10th or ruling it": (
        lambda c: in_tenth(c, "Sun") or in_tenth(c, "Moon") or bool({"Sun", "Moon"} & tenth_lords(c)),
        {"royalty", "politics", "government"}),
    "R6 Sun occupies or aspects the 10th": (lambda c: on_tenth(c, "Sun"), {"royalty", "politics", "government"}),
    "R7 Mars in the 10th": (lambda c: in_tenth(c, "Mars"), {"government", "royalty", "politics", "sports"}),
    "R3 Saturn in or aspecting the 10th": (lambda c: on_tenth(c, "Saturn"), {"politics", "spiritual"}),
    "R4 four or more planets on the 10th (Lagna or Moon)": (
        lambda c: max(sum(c.aspects_sign(p, s) for p in SEVEN) for s in tenth_signs(c)) >= 4,
        {"politics", "royalty", "spiritual"}),
    "R8 9th and 10th lords linked": (lambda c: linked(c, c.lord(9), c.lord(10)), {"royalty", "politics", "government"}),
    "R11 industrialist: 3+ of Mars, Mercury, Saturn, Jupiter on 10/2/11": (
        lambda c: sum(touches(c, p, [10, 2, 11]) for p in ("Mars", "Mercury", "Saturn", "Jupiter")) >= 3 and
        linked(c, c.lord(2), c.lord(11)), {"business"}),
    "R12 lords of 1, 2, 9, 10, 11 blended (3+ linked to each other)": (
        lambda c: max(sum(linked(c, c.lord(a), c.lord(b)) for b in (1, 2, 9, 10, 11) if b != a)
                      for a in (1, 2, 9, 10, 11)) >= 3, {"business", "royalty"}),
    "R14 law: Mercury strong and Jupiter or Saturn linked to Sun or Mercury": (
        lambda c: c.strength("Mercury") >= 0.6 and any(linked(c, x, y) for x in ("Jupiter", "Saturn") for y in ("Sun", "Mercury")),
        {"law"}),
    "R15 writing: Venus linked to Mercury, and either on the 10th or 2nd": (
        lambda c: linked(c, "Venus", "Mercury") and (touches(c, "Venus", [10, 2]) or touches(c, "Mercury", [10, 2])), {"arts"}),
    "R16 science: Rahu with Mercury in the Lagna, or with Mars in the 10th": (
        lambda c: (c.sign("Rahu") == c.sign("Mercury") == c.lagna()) or (in_tenth(c, "Mars") and c.sign("Rahu") == c.sign("Mars")),
        {"science"}),
    "R17 Jupiter in the Lagna, 9th or 10th": (lambda c: c.house("Jupiter") in (1, 9, 10), {"spiritual", "science"}),
    "R18 Saturn or Rahu in the Lagna, or Saturn aspecting the Moon": (
        lambda c: c.house("Saturn") == 1 or c.house("Rahu") == 1 or c.aspects_sign("Saturn", c.sign("Moon")), {"spiritual"}),
}


def groups(case: dict) -> set[str]:
    f = case.get("facts") or {}
    g = {f.get("category") or f.get("sector")}
    if "lawyer" in str(f.get("field", "")) or "judge" in str(f.get("field", "")):
        g.add("law")
    return {x for x in g if x and x != "student", "unemployed"}  # students have no career outcome yet


def load(paths: list[str]) -> list[tuple[str, set[str], Chart]]:
    out = []
    for path in paths:
        for case in yaml.safe_load(open(path, encoding="utf-8"))["cases"]:
            if case.get("use") is False or not case.get("date") or not case.get("time") or not groups(case):
                continue
            d = case["date"] if isinstance(case["date"], date) else date.fromisoformat(str(case["date"]))
            b = BirthData(d, time.fromisoformat(str(case["time"])), case["latitude"], case["longitude"],
                          tz=case.get("tz", "Asia/Kolkata"))
            out.append((case["name"], groups(case), Chart.from_birth(b)))
    return out


def main() -> None:
    charts = load(sys.argv[1:])
    print(f"{len(charts)} charts\n")
    print("| Card | Targets | Holds for targets | Holds for others | Lift |")
    print("| --- | --- | --- | --- | --- |")
    for name, (rule, targets) in CARDS.items():
        t = [rule(c) for _, g, c in charts if g & targets]
        o = [rule(c) for _, g, c in charts if not g & targets]
        rt, ro = sum(t) / max(len(t), 1), sum(o) / max(len(o), 1)
        lift = rt / ro if ro else float("inf")
        print(f"| {name} | {', '.join(sorted(targets))} | {sum(t)}/{len(t)} ({rt:.0%}) | {sum(o)}/{len(o)} ({ro:.0%}) | {lift:.2f} |")


if __name__ == "__main__":
    main()
