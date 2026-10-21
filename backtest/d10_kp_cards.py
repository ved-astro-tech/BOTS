"""Score D10 (Dashamsha) and S.P. Khullar KP sub-sub-lord career rule cards against known-career charts.

    python -m backtest.d10_kp_cards cases1.yaml [cases2.yaml ...]

Sources:
- A. Writer, "Varga D/10 Dasama Mahat Phalam" (Jyotisha Bharati notes): p.2 #11 strong Sun in D10 angles = government
  job; p.3 6th stronger than 7th in D10 = service, else business; p.4 dashamsa deities (Indra = government,
  Yama = judges/bureaucrats/engineering, Kubera = tax/CA, Ishana = bankers/teachers/consultants).
- S. Rath, "Dasamsa and Dasa" lesson D10.03: house in D10 of the D1 10th lord (karmesha) - 3/7/11 favour
  business (p.15), 6th service (p.15), 1/5/9 teaching/dharma (p.8), 10th leaders and power (p.21-22).
- S.P. Khullar, "Key to Learn Sub Sub & Cuspal Interlinks Theory", Appendix B: cusp 10 with 6 = service,
  with 7 = business; 2,6,11 plus 9 = legal or politics, plus 3 = computer programmer, plus 4,9 = teaching.
  The promise is read from the cusp's sub-sub lord through its star and sub lords (Lessons 8-9).

Our readings (assumptions): "strong" = exalted, own sign or moolatrikona; house strength = occupants plus the
lord's dignity score; a KP planet signifies the houses it and its star and sub lords occupy or own.
D10 Lagna/deity and KP sub-sub lords move every few minutes, so they need accurate birth times.
"""
from __future__ import annotations

from functools import lru_cache

from astrobot.astro.chart import DIGNITY_SCORE, Chart
from astrobot.astro.constants import DASHA_ORDER, DASHA_TOTAL, DASHA_YEARS, NAK_SPAN
from astrobot.astro.kp import KPChart, star_and_sub_lord
from backtest.nadi_cards import GOV, main as score

STRONG = {"exalted", "own", "moolatrikona"}
DEITY_PLANET = ["Sun", "Venus", "Mars", "Rahu", "Saturn", "Moon", "Mercury", "Jupiter", None, None]  # Indra..Ananta


def deity(lon: float) -> str | None:
    part = int((lon % 30) // 3)
    if int(lon // 30) % 2 == 1:  # even signs (Taurus, ...) run in reverse
        part = 9 - part
    return DEITY_PLANET[part]


def strong_d10(c: Chart, p: str) -> bool:
    return c.dignity(p, "D10") in STRONG


def house_strength(c: Chart, h: int) -> float:
    return len(c.occupants(h, "D10")) + DIGNITY_SCORE[c.dignity(c.lord(h, "D10"), "D10")]


def karmesha_d10_house(c: Chart) -> int:
    return c.house(c.lord(10), "D10")


def sub_sub_lord(lon: float) -> str:
    star, sub = star_and_sub_lord(lon)
    nak_start = int((lon % 360) // NAK_SPAN) * NAK_SPAN
    cursor = nak_start
    s = DASHA_ORDER.index(star)
    for lord in DASHA_ORDER[s:] + DASHA_ORDER[:s]:
        width = NAK_SPAN * DASHA_YEARS[lord] / DASHA_TOTAL
        if lord == sub:
            break
        cursor += width
    k = DASHA_ORDER.index(sub)
    for lord in DASHA_ORDER[k:] + DASHA_ORDER[:k]:
        cursor += width * DASHA_YEARS[lord] / DASHA_TOTAL
        if (lon % 360) < cursor - 1e-9:
            return lord
    return DASHA_ORDER[k - 1]


@lru_cache(maxsize=4096)
def _kp(key) -> KPChart:
    return KPChart.from_birth(_births[key])


_births: dict = {}


def kp(c: Chart) -> KPChart:
    _births[id(c.birth)] = c.birth
    return _kp(id(c.birth))


def ssl_signifies(c: Chart, cusp: int) -> set[int]:
    k = kp(c)
    ssl = sub_sub_lord(k.cusps[cusp - 1])
    star, sub = star_and_sub_lord(k.longitudes[ssl])
    return k.significations(ssl) | k.significations(sub) | {k.house_of(star)}


def kh(c: Chart, cusp: int, need: set[int], extra: set[int] = frozenset()) -> bool:
    s = ssl_signifies(c, cusp)
    return need <= s and (not extra or bool(extra & s))


JOB, BUSINESS, LAW, IT = {"government", "private"}, {"business"}, {"law"}, {"it"}
CARDS = {
    # A. Writer, D10 notes
    "Writer p2 strong Sun in D10 kendra -> govt job": ("D10 Writer", lambda c: strong_d10(c, "Sun") and c.house("Sun", "D10") in (1, 4, 7, 10), GOV),
    "Writer p2 Sun in D10 kendra (any strength) -> govt": ("D10 Writer", lambda c: c.house("Sun", "D10") in (1, 4, 7, 10), GOV),
    "Writer p3 D10 6th stronger than 7th -> service": ("D10 Writer", lambda c: house_strength(c, 6) > house_strength(c, 7), JOB),
    "Writer p3 D10 7th stronger than 6th -> business": ("D10 Writer", lambda c: house_strength(c, 7) > house_strength(c, 6), BUSINESS),
    "Writer p4 Lagna deity Indra (Sun) -> govt": ("D10 Writer", lambda c: deity(c.positions.ascendant) == "Sun", GOV),
    "Writer p4 Lagna deity Yama (Mars) -> judges/bureaucrats": ("D10 Writer", lambda c: deity(c.positions.ascendant) == "Mars", GOV | LAW),
    "Writer p4 10th lord on Indra or Yama -> govt/judges": ("D10 Writer", lambda c: deity(c.lon(c.lord(10))) in ("Sun", "Mars"), GOV | LAW),
    "Writer p4 10th lord on Kubera or Ishana -> CA/banking/law": ("D10 Writer", lambda c: deity(c.lon(c.lord(10))) in ("Mercury", "Jupiter"), {"finance", "law"}),
    # S. Rath, Dasamsa and Dasa
    "Rath D1 10th lord in D10 3/7/11 -> business": ("D10 Rath", lambda c: karmesha_d10_house(c) in (3, 7, 11), BUSINESS),
    "Rath D1 10th lord in D10 6th -> service": ("D10 Rath", lambda c: karmesha_d10_house(c) == 6, JOB),
    "Rath D1 10th lord in D10 10th -> leadership/power": ("D10 Rath", lambda c: karmesha_d10_house(c) == 10, GOV | {"politics", "royalty"}),
    "Rath D1 10th lord in D10 1/5/9 -> teaching/law/dharma": ("D10 Rath", lambda c: karmesha_d10_house(c) in (1, 5, 9), LAW | {"spiritual"}),
    "Rath D1 10th lord exalted/own in D10 -> great achievement": ("D10 Rath", lambda c: strong_d10(c, c.lord(10)), GOV | {"politics", "royalty"}),
    # S.P. Khullar, KP sub-sub lord, Appendix B
    "Khullar 10th SSL signifies 6 -> service": ("KP Khullar", lambda c: kh(c, 10, {6}), JOB),
    "Khullar 10th SSL signifies 7, not 6 -> business": ("KP Khullar", lambda c: 7 in ssl_signifies(c, 10) and 6 not in ssl_signifies(c, 10), BUSINESS),
    "Khullar 6th SSL signifies 6, 2, 10 -> earning by service": ("KP Khullar", lambda c: kh(c, 6, {2, 6, 10}), JOB),
    "Khullar 10th SSL 2,6,11 + 9 -> legal": ("KP Khullar", lambda c: kh(c, 10, {2, 6, 11}, {9}), LAW),
    "Khullar 10th SSL 2,6,11 + 9 -> politics": ("KP Khullar", lambda c: kh(c, 10, {2, 6, 11}, {9}), {"politics"}),
    "Khullar 10th SSL 2,6,11 + 3 -> computer programmer": ("KP Khullar", lambda c: kh(c, 10, {2, 6, 11}, {3}), IT),
}

if __name__ == "__main__":
    score(CARDS)
