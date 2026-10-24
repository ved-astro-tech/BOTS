"""Classical reference tables (Parashari unless noted). Signs are 0-indexed: 0 = Aries ... 11 = Pisces."""

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
SEVEN = PLANETS[:7]  # planets with sign lordship, used for chara karakas and dignity

SIGN_LORDS = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
              "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]

EXALTATION = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3,
              "Venus": 11, "Saturn": 6, "Rahu": 1, "Ketu": 7}
DEBILITATION = {p: (s + 6) % 12 for p, s in EXALTATION.items()}
MOOLATRIKONA = {"Sun": 4, "Moon": 1, "Mars": 0, "Mercury": 5, "Jupiter": 8, "Venus": 6, "Saturn": 10}
OWN_SIGNS = {p: [s for s, lord in enumerate(SIGN_LORDS) if lord == p] for p in SEVEN}

# Naisargika (natural) relationships, BPHS
FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
ENEMIES = {
    "Sun": {"Venus", "Saturn"},
    "Moon": set(),
    "Mars": {"Mercury"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"},
    "Saturn": {"Sun", "Moon", "Mars"},
}

# Graha drishti, counted as houses from the planet (1 = conjunction, always included)
ASPECTS = {"Sun": (1, 7), "Moon": (1, 7), "Mercury": (1, 7), "Venus": (1, 7),
           "Mars": (1, 4, 7, 8), "Jupiter": (1, 5, 7, 9), "Saturn": (1, 3, 7, 10),
           "Rahu": (1, 5, 7, 9), "Ketu": (1, 5, 7, 9)}

NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
NATURAL_MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

# Degrees from the Sun within which a planet is combust (Surya Siddhanta values)
COMBUST_ORB = {"Moon": 12, "Mars": 17, "Mercury": 14, "Jupiter": 11, "Venus": 10, "Saturn": 15}
COMBUST_ORB_RETRO = {"Mercury": 12, "Venus": 8}

KENDRA = {1, 4, 7, 10}
TRIKONA = {1, 5, 9}
DUSTHANA = {6, 8, 12}
UPACHAYA = {3, 6, 10, 11}

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
    "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
NAK_SPAN = 360 / 27

DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
               "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}
DASHA_TOTAL = 120
DAYS_PER_YEAR = 365.25


def nakshatra_lord(longitude: float) -> str:
    return DASHA_ORDER[int((longitude % 360) // NAK_SPAN) % 9]


def house_from(sign: int, reference_sign: int) -> int:
    """Whole-sign house (1-12) of `sign` counted from `reference_sign`."""
    return (sign - reference_sign) % 12 + 1
