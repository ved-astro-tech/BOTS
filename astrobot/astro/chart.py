"""A natal chart with the Parashari facts the rules need: houses, lords, dignity, aspects, karakas."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from astrobot.astro import vargas
from astrobot.astro.constants import (
    ASPECTS, COMBUST_ORB, COMBUST_ORB_RETRO, DEBILITATION, ENEMIES, EXALTATION, FRIENDS, KENDRA,
    MOOLATRIKONA, NAK_SPAN, NAKSHATRAS, OWN_SIGNS, PLANETS, SEVEN, SIGN_LORDS, SIGNS, house_from,
    nakshatra_lord,
)
from astrobot.astro.ephemeris import BirthData, Positions, birth_positions

DIGNITY_SCORE = {"exalted": 1.0, "moolatrikona": 0.85, "own": 0.75, "friend": 0.6,
                 "neutral": 0.5, "enemy": 0.35, "debilitated_cancelled": 0.45, "debilitated": 0.1}


@dataclass
class Chart:
    birth: BirthData
    positions: Positions

    @classmethod
    def from_birth(cls, birth: BirthData) -> "Chart":
        return cls(birth=birth, positions=birth_positions(birth))

    # ---- placements -------------------------------------------------------------------------
    def lon(self, planet: str) -> float:
        return self.positions.longitudes[planet]

    def sign(self, planet: str, varga: str = "D1") -> int:
        return vargas.VARGAS[varga](self.lon(planet))

    def lagna(self, varga: str = "D1") -> int:
        return vargas.VARGAS[varga](self.positions.ascendant)

    def house(self, planet: str, varga: str = "D1") -> int:
        return house_from(self.sign(planet, varga), self.lagna(varga))

    def house_sign(self, house: int, varga: str = "D1") -> int:
        return (self.lagna(varga) + house - 1) % 12

    def lord(self, house: int, varga: str = "D1") -> str:
        return SIGN_LORDS[self.house_sign(house, varga)]

    def houses_owned(self, planet: str, varga: str = "D1") -> list[int]:
        return [h for h in range(1, 13) if self.lord(h, varga) == planet]

    def occupants(self, house: int, varga: str = "D1") -> list[str]:
        return [p for p in PLANETS if self.house(p, varga) == house]

    def moon_house(self, sign: int) -> int:
        return house_from(sign, self.sign("Moon"))

    # ---- aspects ----------------------------------------------------------------------------
    def aspects_sign(self, planet: str, sign: int, varga: str = "D1") -> bool:
        """True if `planet` occupies or casts graha drishti on `sign`."""
        return house_from(sign, self.sign(planet, varga)) in ASPECTS[planet]

    def aspecting(self, house: int, varga: str = "D1") -> list[str]:
        target = self.house_sign(house, varga)
        return [p for p in PLANETS if self.aspects_sign(p, target, varga) and self.house(p, varga) != house]

    def connected(self, a: str, b: str, varga: str = "D1") -> str | None:
        """How two planets are linked: conjunction, mutual aspect, exchange, or one-way aspect."""
        sa, sb = self.sign(a, varga), self.sign(b, varga)
        if sa == sb:
            return "conjunction"
        if a in SEVEN and b in SEVEN and SIGN_LORDS[sa] == b and SIGN_LORDS[sb] == a:
            return "exchange"
        ab, ba = self.aspects_sign(a, sb, varga), self.aspects_sign(b, sa, varga)
        if ab and ba:
            return "mutual aspect"
        if ab or ba:
            return "aspect"
        return None

    # ---- strength ---------------------------------------------------------------------------
    def dignity(self, planet: str, varga: str = "D1") -> str:
        sign = self.sign(planet, varga)
        if planet in ("Rahu", "Ketu"):
            if sign == EXALTATION[planet]:
                return "exalted"
            if sign == DEBILITATION[planet]:
                return "debilitated"
            return "neutral"
        if sign == EXALTATION[planet]:
            return "exalted"
        if sign == DEBILITATION[planet]:
            return "debilitated_cancelled" if self.neecha_bhanga(planet) else "debilitated"
        if varga == "D1" and sign == MOOLATRIKONA[planet]:
            return "moolatrikona"
        if sign in OWN_SIGNS[planet]:
            return "own"
        dispositor = SIGN_LORDS[sign]
        if dispositor in FRIENDS[planet]:
            return "friend"
        if dispositor in ENEMIES[planet]:
            return "enemy"
        return "neutral"

    def strength(self, planet: str, varga: str = "D1") -> float:
        score = DIGNITY_SCORE[self.dignity(planet, varga)]
        if varga == "D1" and self.combust(planet):
            score -= 0.15
        return max(score, 0.0)

    def neecha_bhanga(self, planet: str) -> bool:
        """Debilitation cancelled: lord of the debilitation sign or of the exaltation sign is in a
        kendra from Lagna or Moon (BPHS / Phaladeepika, simplest common condition)."""
        deb_lord = SIGN_LORDS[DEBILITATION[planet]]
        exa_lord = SIGN_LORDS[EXALTATION[planet]]
        for helper in {deb_lord, exa_lord}:
            if self.house(helper) in KENDRA or self.moon_house(self.sign(helper)) in KENDRA:
                return True
        return False

    def combust(self, planet: str) -> bool:
        if planet not in COMBUST_ORB:
            return False
        orb = COMBUST_ORB_RETRO.get(planet, COMBUST_ORB[planet]) if self.positions.retrograde(planet) \
            else COMBUST_ORB[planet]
        gap = abs((self.lon(planet) - self.lon("Sun") + 180) % 360 - 180)
        return gap <= orb

    def vargottama(self, planet: str) -> bool:
        return self.sign(planet, "D1") == self.sign(planet, "D9")

    # ---- karakas and nakshatras -------------------------------------------------------------
    @cached_property
    def chara_karakas(self) -> dict[str, str]:
        """Jaimini 7-karaka scheme by degree within sign: AK, AmK, BK, MK, PK, GK, DK."""
        names = ["Atmakaraka", "Amatyakaraka", "Bhratrikaraka", "Matrikaraka",
                 "Putrakaraka", "Gnatikaraka", "Darakaraka"]
        ranked = sorted(SEVEN, key=lambda p: self.lon(p) % 30, reverse=True)
        return dict(zip(names, ranked))

    def nakshatra(self, planet: str) -> tuple[str, int]:
        lon = self.lon(planet)
        index = int(lon // NAK_SPAN)
        pada = int((lon - index * NAK_SPAN) // (NAK_SPAN / 4)) + 1
        return NAKSHATRAS[index], pada

    def star_lord(self, planet: str) -> str:
        return nakshatra_lord(self.lon(planet))

    def significations(self, planet: str) -> set[int]:
        """Houses a planet delivers in its dasha: occupied and owned, plus its star lord's
        occupied and owned houses (KP-style star-lord rule, applied to whole-sign houses).
        Rahu and Ketu also act for their dispositor."""
        houses = {self.house(planet), *self.houses_owned(planet)}
        star = self.star_lord(planet)
        houses |= {self.house(star), *self.houses_owned(star)}
        if planet in ("Rahu", "Ketu"):
            dispositor = SIGN_LORDS[self.sign(planet)]
            houses |= {self.house(dispositor), *self.houses_owned(dispositor)}
        return houses

    # ---- summary ----------------------------------------------------------------------------
    def summary(self) -> dict:
        planets = {}
        for p in PLANETS:
            nak, pada = self.nakshatra(p)
            planets[p] = {
                "sign": SIGNS[self.sign(p)], "degree": round(self.lon(p) % 30, 2), "house": self.house(p),
                "nakshatra": nak, "pada": pada, "retrograde": self.positions.retrograde(p),
                "combust": self.combust(p), "dignity": self.dignity(p),
                "D9_sign": SIGNS[self.sign(p, "D9")], "D10_sign": SIGNS[self.sign(p, "D10")],
            }
        return {
            "lagna": SIGNS[self.lagna()], "lagna_degree": round(self.positions.ascendant % 30, 2),
            "moon_sign": SIGNS[self.sign("Moon")], "D9_lagna": SIGNS[self.lagna("D9")],
            "D10_lagna": SIGNS[self.lagna("D10")], "ayanamsa": round(self.positions.ayanamsa, 4),
            "planets": planets, "chara_karakas": self.chara_karakas,
        }
