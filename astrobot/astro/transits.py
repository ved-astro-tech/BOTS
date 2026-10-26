"""Gochar (transits): sidereal positions over a date range, sampled at a fixed step."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from astrobot.astro.constants import ASPECTS, house_from
from astrobot.astro.ephemeris import julian_day, planet_positions


@dataclass(frozen=True)
class Snapshot:
    moment: datetime
    signs: dict[str, int]
    longitudes: dict[str, float]

    def aspects(self, planet: str, target_sign: int) -> bool:
        """Transiting `planet` occupies or casts graha drishti on `target_sign`."""
        return house_from(target_sign, self.signs[planet]) in ASPECTS[planet]


@lru_cache(maxsize=None)
def _snapshot_for_day(ordinal: int) -> Snapshot:
    moment = datetime.fromordinal(ordinal).replace(hour=12, tzinfo=timezone.utc)
    pos = planet_positions(julian_day(moment))
    signs = {p: int(lon // 30) for p, lon in pos.longitudes.items()}
    return Snapshot(moment=moment, signs=signs, longitudes=pos.longitudes)


def snapshots(start: datetime, end: datetime, step_days: int = 5) -> list[Snapshot]:
    out, day = [], start.date().toordinal()
    last = end.date().toordinal()
    while day <= last:
        out.append(_snapshot_for_day(day))
        day += step_days
    return out


def snapshot_at(moment: datetime) -> Snapshot:
    return _snapshot_for_day(moment.date().toordinal())


def sign_ingresses(planet: str, start: datetime, end: datetime) -> list[tuple[datetime, int]]:
    """Dates (to the day) when `planet` changes sign within the range."""
    out, prev = [], None
    for snap in snapshots(start, end, step_days=1):
        sign = snap.signs[planet]
        if prev is not None and sign != prev:
            out.append((snap.moment, sign))
        prev = sign
    return out


def window_days(start: datetime, end: datetime) -> float:
    return max((end - start) / timedelta(days=1), 1.0)
