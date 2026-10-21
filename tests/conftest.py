import sys
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from astrobot.astro.ephemeris import BirthData  # noqa: E402


@pytest.fixture
def birth() -> BirthData:
    return BirthData(date(1990, 1, 15), time(10, 30), 28.6139, 77.2090, name="Test", place="New Delhi")
