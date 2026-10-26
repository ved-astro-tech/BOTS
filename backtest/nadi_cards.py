"""Score Nadi career rule cards (Bhrigu Nadi Sangraha, R.G. Rao's Essence of Nadi Astrology) against known-career charts.

    python -m backtest.nadi_cards cases1.yaml [cases2.yaml ...]

Nadi rules ignore the Lagna and read planets by their sign distance from the karaka (Saturn for profession),
so the cards here depend only on planetary signs. Same lift measure as backtest/cards_explore.py.

Readings of Nadi terms (assumptions, not stated as definitions in the excerpts we have):
- "with" = same sign; "next to" = the adjacent sign on either side (2nd or 12th); "succeeding" = 2nd; "preceding" = 12th.
- "sees" / aspect in Bhrigu Nadi = same sign, 5th, 7th or 9th (trines and opposition).
- Rao's "combination" with Saturn = same direction (1st, 5th, 9th from Saturn), widened variant adds 2nd, 7th, 12th
  as used in Rao's worked examples.
"""
from __future__ import annotations

import random
import re
import sys
from datetime import date, datetime, time, timedelta

from backtest.cards_explore import load
from astrobot.astro.chart import Chart
from astrobot.astro.ephemeris import BirthData
from scipy.stats import binomtest, fisher_exact

ARIES, TAURUS, GEMINI, CANCER, LEO, VIRGO, LIBRA, SCORPIO = range(8)


def frm(c: Chart, a: str, b: str) -> int:
    """House of planet b counted from planet a (1 = same sign)."""
    return (c.sign(b) - c.sign(a)) % 12 + 1


def at(c: Chart, b: str, *houses: int, base: str = "Saturn") -> bool:
    return frm(c, base, b) in houses


def nadi_sees(c: Chart, a: str, b: str) -> bool:
    return frm(c, a, b) in (1, 5, 7, 9)


def next_to(c: Chart, b: str, base: str = "Saturn") -> bool:
    return frm(c, base, b) in (2, 12)


def rao_trine(c: Chart, p: str) -> bool:
    return at(c, p, 1, 5, 9)


def rao_wide(c: Chart, p: str) -> bool:
    return at(c, p, 1, 2, 5, 7, 9, 12)


def bc_link(c: Chart, p: str) -> bool:
    """With or in Nadi aspect (1/5/7/9) to Saturn, or Nadi-aspecting Saturn's 2nd sign (2/6/8/10 from Saturn)."""
    return at(c, p, 1, 5, 7, 9, 2, 6, 8, 10)


def bc_alone(c: Chart) -> bool:
    return not any(at(c, p, 1, 5, 7, 9) for p in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Rahu", "Ketu"))


GOV = {"government"}
CARDS = {
    # Bhrigu Nadi Sangraha (N. Srinivasan Shastry), Saturn chapter pp. 44-49
    "BN p44 Saturn sees Sun and Ketu -> govt": ("Bhrigu", lambda c: nadi_sees(c, "Saturn", "Sun") and nadi_sees(c, "Saturn", "Ketu"), GOV),
    "BN p44 Saturn in Leo -> govt": ("Bhrigu", lambda c: c.sign("Saturn") == LEO, GOV),
    "BN p44 Saturn next to Sun -> govt": ("Bhrigu", lambda c: next_to(c, "Sun"), GOV),
    "BN p49 Saturn exalted with Sun next -> high govt post": ("Bhrigu", lambda c: c.sign("Saturn") == LIBRA and next_to(c, "Sun"), GOV),
    "BN p45 Sun 10th from Saturn -> high post": ("Bhrigu", lambda c: at(c, "Sun", 10), GOV | {"politics", "royalty"}),
    "BN any govt rule (p44, p49)": ("Bhrigu", lambda c: (nadi_sees(c, "Saturn", "Sun") and nadi_sees(c, "Saturn", "Ketu"))
                                    or c.sign("Saturn") == LEO or next_to(c, "Sun"), GOV),
    "BN p47 Saturn in Gemini/Virgo -> businessman": ("Bhrigu", lambda c: c.sign("Saturn") in (GEMINI, VIRGO), {"business"}),
    "BN p45 Saturn's 10th Scorpio or Mars 10th from Saturn -> industry": ("Bhrigu", lambda c: (c.sign("Saturn") + 9) % 12 == SCORPIO or at(c, "Mars", 10), {"business"}),
    "BN p46 Saturn with Mars -> obstacles to appointment (not govt)": ("Bhrigu", lambda c: at(c, "Mars", 1), {"business", "profession", "private", "sports", "politics"}),
    "BN p47 Rahu 2nd from Saturn -> low-paid job": ("Bhrigu", lambda c: at(c, "Rahu", 2), {"lowpaid"}),
    "BN p49 Mars 7th from Saturn -> low-paid servant": ("Bhrigu", lambda c: at(c, "Mars", 7), {"lowpaid"}),
    "BN p47 Sun, Venus, Mercury next to Saturn -> good salaried job": ("Bhrigu", lambda c: all(next_to(c, p) for p in ("Sun", "Venus", "Mercury")), {"government", "private"}),
    "BN p47 Mercury, Venus, Mars preceding Saturn -> money lender": ("Bhrigu", lambda c: all(at(c, p, 12) for p in ("Mercury", "Venus", "Mars")), {"finance"}),
    "BN p48 Venus 2nd, Sun+Mercury 4th from Saturn -> treasury/finance": ("Bhrigu", lambda c: at(c, "Venus", 2) and at(c, "Sun", 4) and at(c, "Mercury", 4), {"finance"}),
    "BN p48 Sun+Mercury 7th from Saturn -> rich concern": ("Bhrigu", lambda c: at(c, "Sun", 7) and at(c, "Mercury", 7), {"private"}),
    "BN p48 Saturn in Aries/Scorpio, nothing adjacent -> unsettled": ("Bhrigu", lambda c: c.sign("Saturn") in (ARIES, SCORPIO) and not any(
        next_to(c, p) for p in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Rahu", "Ketu")), {"lowpaid"}),
    "BN p46-47 Saturn with Ketu, or with Mars and Sun -> machinery": ("Bhrigu", lambda c: at(c, "Ketu", 1) or (at(c, "Mars", 1) and at(c, "Sun", 1)), {"it"}),

    # R.G. Rao, Essence of Nadi Astrology: Saturn = profession karaka (p. 3, p. 203); planet meanings p. 202-203
    "Rao Sun in trine to Saturn -> govt": ("Rao", lambda c: rao_trine(c, "Sun"), GOV),
    "Rao Sun combined with Saturn (wide) -> govt": ("Rao", lambda c: rao_wide(c, "Sun"), GOV),
    "Rao Sun+Jupiter combined with Saturn -> govt officer/admin": ("Rao", lambda c: rao_wide(c, "Sun") and rao_wide(c, "Jupiter"), GOV),
    "Rao Rahu combined with Saturn -> computers": ("Rao", lambda c: rao_wide(c, "Rahu"), {"it"}),
    "Rao Rahu 2nd or with Saturn -> computers": ("Rao", lambda c: at(c, "Rahu", 1, 2), {"it"}),
    "Rao Saturn+Mars+Rahu combined -> computer/engineer": ("Rao", lambda c: rao_wide(c, "Mars") and rao_wide(c, "Rahu"), {"it"}),
    "Rao Mercury combined with Saturn -> commerce": ("Rao", lambda c: rao_wide(c, "Mercury"), {"business"}),
    "Rao Mercury 11th from Saturn -> commercial dealings": ("Rao", lambda c: at(c, "Mercury", 11), {"business"}),
    "Rao Venus combined with Saturn -> finance/wealth work": ("Rao", lambda c: rao_wide(c, "Venus"), {"finance"}),
    "Rao Mercury+Ketu with Jupiter 2nd -> lawyer": ("Rao", lambda c: c.sign("Mercury") == c.sign("Ketu") and at(c, "Jupiter", 2, base="Mercury"), {"law"}),
    "Rao Ketu combined with Saturn -> disputes/law": ("Rao", lambda c: rao_wide(c, "Ketu"), {"law"}),
    "Rao Jupiter in 2/5/7/9 from Saturn -> administrative power": ("Rao", lambda c: at(c, "Jupiter", 2, 5, 7, 9), GOV | {"politics", "royalty"}),

    # Bhaskar Chakraborty, "Nadi Easy Method of Determining Profession" (Saptarishis, 3 Jan 2015), quoting Bhrigu Nadi:
    # planets with or in Nadi aspect to Saturn, or aspecting Saturn's 2nd sign, show the profession. The upload's
    # planet-to-profession pages are blank, so the meanings below are Rao's (pp. 202-203).
    "BC Sun linked to Saturn or its 2nd -> govt": ("Chakraborty", lambda c: bc_link(c, "Sun"), GOV),
    "BC Rahu linked to Saturn or its 2nd -> computers": ("Chakraborty", lambda c: bc_link(c, "Rahu"), {"it"}),
    "BC Mercury linked to Saturn or its 2nd -> commerce": ("Chakraborty", lambda c: bc_link(c, "Mercury"), {"business"}),
    "BC Venus linked to Saturn or its 2nd -> finance": ("Chakraborty", lambda c: bc_link(c, "Venus"), {"finance"}),
    "BC Ketu linked to Saturn or its 2nd -> disputes/law": ("Chakraborty", lambda c: bc_link(c, "Ketu"), {"law"}),
    "BC Jupiter linked to Saturn or its 2nd -> law/advice/admin": ("Chakraborty", lambda c: bc_link(c, "Jupiter"), {"law", "government"}),
    "BC Saturn alone -> profession from the next sign (fiery/earthy 2nd = business)": ("Chakraborty", lambda c: bc_alone(c) and (c.sign("Saturn") + 1) % 4 in (0, 1), {"business"}),
}


def tags(name: str, g: set[str], field: str) -> set[str]:
    t = set(g)
    f = field.lower()
    if re.search(r"\b(it|tech|software|computer)\b", f) and "startup" not in f:
        t.add("it")
    if any(k in f for k in ("bank", "account", "finance")):
        t.add("finance")
    if "low income" in f:
        t.add("lowpaid")
    return t


def population(n: int = 2000, seed: int = 7) -> list[Chart]:
    """Random births 1900-2010 (Meerut): the base rate of each card in the general population."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        dt = datetime(1900, 1, 1) + timedelta(minutes=rnd.randrange(110 * 365 * 24 * 60))
        out.append(Chart.from_birth(BirthData(dt.date(), dt.time(), 28.9845, 77.7064, tz="Asia/Kolkata")))
    return out


def main(cards: dict | None = None) -> None:
    cards = cards or CARDS
    import yaml
    fields = {}
    for p in sys.argv[1:]:
        for case in yaml.safe_load(open(p, encoding="utf-8"))["cases"]:
            fields[case["name"]] = str((case.get("facts") or {}).get("field", ""))
    charts = [(n, tags(n, g, fields.get(n, "")), c) for n, g, c in load(sys.argv[1:])]
    pop = population()
    print(f"{len(charts)} charts, {len(pop)} random population charts\n")
    print("| Book | Card | Targets | Holds for targets | Holds for others | Population | Lift vs others | p (Fisher) | p (vs population) | Hits |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, (book, rule, targets) in cards.items():
        res = [(n, rule(c), bool(g & targets)) for n, g, c in charts]
        t = [r for _, r, tg in res if tg]
        o = [r for _, r, tg in res if not tg]
        base = sum(rule(c) for c in pop) / len(pop)
        rt, ro = sum(t) / max(len(t), 1), sum(o) / max(len(o), 1)
        lift = "n/a" if not t or not sum(t) and not sum(o) else ("inf" if not ro else f"{rt / ro:.2f}")
        pf = fisher_exact([[sum(t), len(t) - sum(t)], [sum(o), len(o) - sum(o)]], alternative="greater")[1] if t else 1
        pb = binomtest(sum(t), len(t), base, alternative="greater").pvalue if t else 1
        hits = ", ".join(n.split("(")[-1].rstrip(")").split()[0] for n, r, tg in res if r and tg)
        print(f"| {book} | {name} | {', '.join(sorted(targets))} | {sum(t)}/{len(t)} ({rt:.0%}) | "
              f"{sum(o)}/{len(o)} ({ro:.0%}) | {base:.0%} | {lift} | {pf:.2f} | {pb:.2f} | {hits} |")


if __name__ == "__main__":
    main()
