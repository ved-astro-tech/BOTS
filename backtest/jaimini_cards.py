"""Score Jaimini / Karakamsha and Dashamsha (D10) career rule cards against known-career charts.

    python -m backtest.jaimini_cards cases1.yaml [cases2.yaml ...]

Karakamsha = the navamsa sign of the Atmakaraka (7-karaka scheme). BPHS 33.13-17 gives the result of each planet
in the Karakamsha: Sun royal/government work (13), Mars weapons/fire (14), Mercury arts and trade (15), Jupiter
learning/Vedas and Venus royal servant (16), Saturn family occupation and Rahu iron machinery (17).
Planets "in the Karakamsha" are read two ways: in that sign in the navamsa (D9), and in that sign in the
rasi (D1, as K.N. Rao teaches). Amatyakaraka and D10 meanings follow the same planet meanings; that mapping is
our assumption, not a verse.
"""
from __future__ import annotations

import sys

from astrobot.astro.chart import Chart
from backtest.nadi_cards import GOV, main as score


def kk(c: Chart) -> int:
    return c.sign(c.chara_karakas["Atmakaraka"], "D9")


def in_kk(c: Chart, p: str, varga: str, offset: int = 0) -> bool:
    return c.sign(p, varga) == (kk(c) + offset) % 12


def amk(c: Chart) -> str:
    return c.chara_karakas["Amatyakaraka"]


def d10(c: Chart, p: str) -> bool:
    """Planet in the D10 Lagna or 10th, or lord of the D10 10th."""
    lg = c.lagna("D10")
    return c.sign(p, "D10") in (lg, (lg + 9) % 12) or c.lord(10, "D10") == p


BUSINESS, IT, LAW = {"business"}, {"it"}, {"law"}
CARDS = {}
for v in ("D9", "D1"):
    CARDS |= {
        f"BPHS 33.13 Sun in Karakamsha ({v}) -> government": ("Jaimini", lambda c, v=v: in_kk(c, "Sun", v), GOV),
        f"BPHS 33.16 Venus in Karakamsha ({v}) -> royal servant": ("Jaimini", lambda c, v=v: in_kk(c, "Venus", v), GOV),
        f"BPHS 33.13/16 Sun or Venus in Karakamsha ({v}) -> government": ("Jaimini", lambda c, v=v: in_kk(c, "Sun", v) or in_kk(c, "Venus", v), GOV),
        f"BPHS 33.15 Mercury in Karakamsha ({v}) -> trade": ("Jaimini", lambda c, v=v: in_kk(c, "Mercury", v), BUSINESS),
        f"BPHS 33.17 Rahu in Karakamsha ({v}) -> machinery": ("Jaimini", lambda c, v=v: in_kk(c, "Rahu", v), IT),
        f"BPHS 33.16 Jupiter in Karakamsha ({v}) -> learning/law": ("Jaimini", lambda c, v=v: in_kk(c, "Jupiter", v), LAW),
        f"Sun in 10th from Karakamsha ({v}) -> government": ("Jaimini", lambda c, v=v: in_kk(c, "Sun", v, 9), GOV),
    }
CARDS |= {
    "AmK = Sun -> government": ("Jaimini", lambda c: amk(c) == "Sun", GOV),
    "AmK = Sun or Venus -> government": ("Jaimini", lambda c: amk(c) in ("Sun", "Venus"), GOV),
    "AmK = Mercury -> business": ("Jaimini", lambda c: amk(c) == "Mercury", BUSINESS),
    "AmK = Jupiter -> law/teaching": ("Jaimini", lambda c: amk(c) == "Jupiter", LAW),
    "D10 Sun in Lagna/10th or rules 10th -> government": ("D10", lambda c: d10(c, "Sun"), GOV),
    "D10 Mercury in Lagna/10th or rules 10th -> business": ("D10", lambda c: d10(c, "Mercury"), BUSINESS),
    "D10 Jupiter in Lagna/10th or rules 10th -> law": ("D10", lambda c: d10(c, "Jupiter"), LAW),
    "D10 Rahu or Mercury in Lagna/10th -> tech": ("D10", lambda c: d10(c, "Rahu") or d10(c, "Mercury"), IT),
}

if __name__ == "__main__":
    score(CARDS)
