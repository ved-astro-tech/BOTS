from datetime import datetime, timedelta, timezone

import pytest

from astrobot.astro import vargas
from astrobot.astro.chart import Chart
from astrobot.astro.constants import DASHA_YEARS, house_from
from astrobot.astro.dasha import DashaTree, mahadashas
from astrobot.astro.kp import KPChart, star_and_sub_lord
from astrobot.astro.transits import Snapshot


def test_positions_match_jastro_details_fetcher(birth):
    # Reference values produced by jastro-backend details_fetcher SwissEphemerisCalculator
    # (Lahiri, mean node) for the same birth, checked on 2026-10-21.
    chart = Chart.from_birth(birth)
    expected = {"Sun": 271.0598, "Moon": 140.1236, "Mars": 235.98, "Jupiter": 69.6788,
                "Saturn": 263.5587, "Rahu": 293.9878}
    for planet, lon in expected.items():
        assert chart.lon(planet) == pytest.approx(lon, abs=1e-3)
    assert chart.positions.ascendant == pytest.approx(331.4315, abs=1e-3)


def test_mahadasha_dates_match_jastro(birth):
    chart = Chart.from_birth(birth)
    mds = DashaTree(chart.lon("Moon"), birth.utc()).mds
    assert [(m.lord, m.end.date().isoformat()) for m in mds[:4]] == [
        ("Venus", "1999-11-08"), ("Sun", "2005-11-08"), ("Moon", "2015-11-08"), ("Mars", "2022-11-08")]


def test_navamsa_and_dasamsa_rules():
    assert vargas.navamsa(0.5) == 0          # Aries 0deg -> Aries navamsa
    assert vargas.navamsa(30.5) == 9         # Taurus 0deg -> Capricorn navamsa
    assert vargas.navamsa(60.5) == 6         # Gemini 0deg -> Libra navamsa
    assert vargas.dasamsa(0.5) == 0          # odd sign starts from itself
    assert vargas.dasamsa(30.5) == 9         # even sign (Taurus) starts from the 9th: Capricorn
    assert vargas.dasamsa(29.9) == 9         # last part of Aries -> 10th from Aries


def test_dasha_levels_add_up():
    birth_utc = datetime(1990, 1, 15, 5, 0, tzinfo=timezone.utc)
    mds = mahadashas(0.0, birth_utc)         # Moon at 0 Aries: full Ketu dasha first
    assert mds[0].lord == "Ketu" and mds[0].start == birth_utc
    total = sum((m.end - m.start for m in mds), timedelta())
    assert total.days == pytest.approx(120 * 365.25, abs=1)
    tree = DashaTree(0.0, birth_utc)
    ads = tree.antardashas(mds[2])
    assert ads[0].lords == (mds[2].lord, mds[2].lord)
    assert ads[-1].end == mds[2].end
    pds = tree.pratyantardashas(ads[3])
    assert pds[0].start == ads[3].start and pds[-1].end == ads[3].end
    md, ad, pd = tree.at(birth_utc + timedelta(days=4000))
    assert pd.lords[:2] == ad.lords and ad.lords[:1] == md.lords


def test_kp_sub_lord_boundaries():
    assert star_and_sub_lord(0.0) == ("Ketu", "Ketu")
    # Ketu sub in Ashwini spans 13deg20' * 7/120 = 0deg46'40"
    assert star_and_sub_lord(0.77) == ("Ketu", "Ketu")
    assert star_and_sub_lord(0.79) == ("Ketu", "Venus")
    assert star_and_sub_lord(13.34)[0] == "Venus"


def test_chart_facts(birth):
    chart = Chart.from_birth(birth)
    assert chart.lagna() == 11                       # Pisces
    assert chart.lord(10) == "Jupiter"               # Sagittarius 10th
    assert chart.house("Jupiter") == 4
    assert set(chart.chara_karakas) >= {"Atmakaraka", "Amatyakaraka", "Darakaraka"}
    assert all(1 <= h <= 12 for h in chart.significations("Rahu"))
    kp = KPChart.from_birth(birth)
    assert all(1 <= kp.house_of(p) <= 12 for p in kp.longitudes)


def test_transit_aspects():
    snap = Snapshot(moment=datetime.now(timezone.utc), signs={"Jupiter": 0, "Saturn": 0}, longitudes={})
    assert snap.aspects("Jupiter", 4)       # 5th from Aries
    assert snap.aspects("Jupiter", 8)       # 9th
    assert not snap.aspects("Jupiter", 3)
    assert snap.aspects("Saturn", 9)        # 10th
    assert house_from(9, 0) == 10
