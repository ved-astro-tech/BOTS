"""Divisional chart (varga) sign rules, BPHS Shodashavarga chapter."""


def rasi(longitude: float) -> int:
    return int((longitude % 360) // 30)


def navamsa(longitude: float) -> int:
    """D9: 3deg20' parts counted continuously from Aries (movable signs start from themselves,
    fixed from the 9th, dual from the 5th; the continuous count gives the same result)."""
    return int((longitude % 360) // (30 / 9)) % 12


def dasamsa(longitude: float) -> int:
    """D10: 3deg parts; odd signs count from the sign itself, even signs from the 9th sign."""
    sign = rasi(longitude)
    part = int((longitude % 30) // 3)
    start = sign if sign % 2 == 0 else (sign + 8) % 12  # index 0 (Aries) is an odd sign
    return (start + part) % 12


VARGAS = {"D1": rasi, "D9": navamsa, "D10": dasamsa}
