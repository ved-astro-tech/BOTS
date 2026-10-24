"""Swiss Ephemeris wrapper.

Settings match Jastro's details_fetcher (calculations/planet_degree_calculator/swiss_ephemeris_calculator.py):
Lahiri ayanamsa, mean node for Rahu, Placidus for bhava cusps, Krishnamurti ayanamsa for KP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

from astrobot.astro.constants import PLANETS

_SWE_IDS = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
            "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}

LAHIRI = swe.SIDM_LAHIRI
KRISHNAMURTI = swe.SIDM_KRISHNAMURTI


@dataclass(frozen=True)
class BirthData:
    date: date
    time: time
    latitude: float
    longitude: float
    tz: str = "Asia/Kolkata"
    name: str = ""
    place: str = ""
    # exact | within_15_min | rough: limits how fine a timing the engine may claim
    time_certainty: str = "exact"

    def utc(self) -> datetime:
        local = datetime.combine(self.date, self.time).replace(tzinfo=ZoneInfo(self.tz))
        return local.astimezone(timezone.utc)


@dataclass
class Positions:
    jd_ut: float
    ayanamsa: float
    longitudes: dict[str, float]
    speeds: dict[str, float]
    ascendant: float | None = None
    cusps: list[float] = field(default_factory=list)  # Placidus, sidereal, index 0 = house 1

    def retrograde(self, planet: str) -> bool:
        if planet in ("Rahu", "Ketu"):
            return True
        return self.speeds[planet] < 0


def julian_day(moment: datetime) -> float:
    moment = moment.astimezone(timezone.utc)
    hours = moment.hour + moment.minute / 60 + moment.second / 3600
    return swe.julday(moment.year, moment.month, moment.day, hours)


def planet_positions(jd_ut: float, sidereal_mode: int = LAHIRI) -> Positions:
    swe.set_sid_mode(sidereal_mode)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    longitudes, speeds = {}, {}
    for name, body in _SWE_IDS.items():
        pos, _ = swe.calc_ut(jd_ut, body, flags)
        longitudes[name] = pos[0] % 360
        speeds[name] = pos[3]
    longitudes["Ketu"] = (longitudes["Rahu"] + 180) % 360
    speeds["Ketu"] = speeds["Rahu"]
    assert set(longitudes) == set(PLANETS)
    return Positions(jd_ut=jd_ut, ayanamsa=swe.get_ayanamsa_ut(jd_ut), longitudes=longitudes, speeds=speeds)


def birth_positions(birth: BirthData, sidereal_mode: int = LAHIRI) -> Positions:
    jd = julian_day(birth.utc())
    positions = planet_positions(jd, sidereal_mode)
    cusps, ascmc = swe.houses_ex(jd, birth.latitude, birth.longitude, b"P", 0)
    positions.ascendant = (ascmc[0] - positions.ayanamsa) % 360
    positions.cusps = [(c - positions.ayanamsa) % 360 for c in cusps[:12]]
    return positions
