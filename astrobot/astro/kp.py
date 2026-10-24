"""Krishnamurti Paddhati: Placidus cusps, star and sub lords, house significators.

Same ayanamsa (Krishnamurti) and sub-lord division as Jastro's details_fetcher/calculations/kp.
"""
from __future__ import annotations

from dataclasses import dataclass

from astrobot.astro.constants import DASHA_ORDER, DASHA_TOTAL, DASHA_YEARS, NAK_SPAN, PLANETS, SIGN_LORDS
from astrobot.astro.ephemeris import KRISHNAMURTI, BirthData, birth_positions


def star_and_sub_lord(longitude: float) -> tuple[str, str]:
    lon = longitude % 360
    index = int(lon // NAK_SPAN)
    star = DASHA_ORDER[index % 9]
    offset = lon - index * NAK_SPAN
    start = DASHA_ORDER.index(star)
    cursor = 0.0
    for lord in DASHA_ORDER[start:] + DASHA_ORDER[:start]:
        cursor += NAK_SPAN * DASHA_YEARS[lord] / DASHA_TOTAL
        if offset < cursor - 1e-9:
            return star, lord
    return star, DASHA_ORDER[start - 1]


def sub_sub_lord(lon: float) -> str:
    """Third-level division: the sub is split again in Vimshottari proportions, starting from the sub lord."""
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


@dataclass
class KPChart:
    cusps: list[float]           # sidereal (KP ayanamsa), index 0 = cusp 1
    longitudes: dict[str, float]

    @classmethod
    def from_birth(cls, birth: BirthData) -> "KPChart":
        pos = birth_positions(birth, sidereal_mode=KRISHNAMURTI)
        return cls(cusps=pos.cusps, longitudes=pos.longitudes)

    def house_of(self, planet: str) -> int:
        lon = self.longitudes[planet]
        for i in range(12):
            start, end = self.cusps[i], self.cusps[(i + 1) % 12]
            span = (end - start) % 360
            if (lon - start) % 360 < span:
                return i + 1
        return 12

    def houses_owned(self, planet: str) -> list[int]:
        return [i + 1 for i, c in enumerate(self.cusps) if SIGN_LORDS[int(c // 30)] == planet]

    def significations(self, planet: str) -> set[int]:
        """Four-step significators, simplified: houses occupied and owned by the planet and by its
        star lord. Rahu and Ketu add their sign lord's houses."""
        star, _ = star_and_sub_lord(self.longitudes[planet])
        houses = {self.house_of(planet), *self.houses_owned(planet),
                  self.house_of(star), *self.houses_owned(star)}
        if planet in ("Rahu", "Ketu"):
            dispositor = SIGN_LORDS[int(self.longitudes[planet] // 30)]
            houses |= {self.house_of(dispositor), *self.houses_owned(dispositor)}
        return houses

    def cusp_sub_lord(self, house: int) -> str:
        return star_and_sub_lord(self.cusps[house - 1])[1]

    def summary(self) -> dict:
        return {
            "cusps": {i + 1: {"degree": round(c, 2), "star_lord": star_and_sub_lord(c)[0],
                              "sub_lord": star_and_sub_lord(c)[1]} for i, c in enumerate(self.cusps)},
            "planets": {p: {"house": self.house_of(p), "star_lord": star_and_sub_lord(self.longitudes[p])[0],
                            "sub_lord": star_and_sub_lord(self.longitudes[p])[1],
                            "signifies": sorted(self.significations(p))} for p in PLANETS},
        }
