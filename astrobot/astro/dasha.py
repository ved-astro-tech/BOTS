"""Vimshottari dasha: Mahadasha (MD), Antardasha (AD), Pratyantardasha (PD).

Same method as Jastro's details_fetcher (calculations/dasha): the Moon's nakshatra fixes the first
lord and the balance; each sub-period is proportional to its lord's years out of 120.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from astrobot.astro.constants import DASHA_ORDER, DASHA_TOTAL, DASHA_YEARS, DAYS_PER_YEAR, NAK_SPAN


@dataclass(frozen=True)
class Period:
    lords: tuple[str, ...]  # (MD,) or (MD, AD) or (MD, AD, PD)
    start: datetime
    end: datetime

    @property
    def lord(self) -> str:
        return self.lords[-1]

    @property
    def level(self) -> str:
        return ("MD", "AD", "PD")[len(self.lords) - 1]

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def label(self) -> str:
        return "/".join(self.lords)

    def as_dict(self) -> dict:
        return {"lords": list(self.lords), "start": self.start.date().isoformat(),
                "end": self.end.date().isoformat()}


def _sequence(start_lord: str) -> list[str]:
    i = DASHA_ORDER.index(start_lord)
    return DASHA_ORDER[i:] + DASHA_ORDER[:i]


def _subdivide(period: Period) -> list[Period]:
    span = period.end - period.start
    out, cursor = [], period.start
    for lord in _sequence(period.lord):
        length = span * (DASHA_YEARS[lord] / DASHA_TOTAL)
        out.append(Period(period.lords + (lord,), cursor, cursor + length))
        cursor += length
    return out


def mahadashas(moon_longitude: float, birth_utc: datetime, cycles: int = 1) -> list[Period]:
    """MDs from the (partly elapsed) first one, covering `cycles` x 120 years."""
    index = int((moon_longitude % 360) // NAK_SPAN)
    elapsed = ((moon_longitude % 360) - index * NAK_SPAN) / NAK_SPAN
    first = DASHA_ORDER[index % 9]
    cursor = birth_utc - timedelta(days=elapsed * DASHA_YEARS[first] * DAYS_PER_YEAR)
    out = []
    for lord in _sequence(first) * cycles:
        end = cursor + timedelta(days=DASHA_YEARS[lord] * DAYS_PER_YEAR)
        out.append(Period((lord,), cursor, end))
        cursor = end
    return out


class DashaTree:
    def __init__(self, moon_longitude: float, birth_utc: datetime):
        self.birth_utc = birth_utc
        self.mds = mahadashas(moon_longitude, birth_utc)

    def antardashas(self, md: Period) -> list[Period]:
        return _subdivide(md)

    def pratyantardashas(self, ad: Period) -> list[Period]:
        return _subdivide(ad)

    def at(self, moment: datetime) -> tuple[Period, Period, Period]:
        md = next(p for p in self.mds if p.contains(moment))
        ad = next(p for p in _subdivide(md) if p.contains(moment))
        pd = next(p for p in _subdivide(ad) if p.contains(moment))
        return md, ad, pd

    def pds_between(self, start: datetime, end: datetime) -> list[Period]:
        out = []
        for md in self.mds:
            if md.end <= start or md.start >= end:
                continue
            for ad in _subdivide(md):
                if ad.end <= start or ad.start >= end:
                    continue
                out.extend(pd for pd in _subdivide(ad) if pd.end > start and pd.start < end)
        return out
