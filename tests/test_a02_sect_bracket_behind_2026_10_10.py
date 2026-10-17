"""Ruling 145, A-02: with nothing ahead, the sect reads the bracket behind.

The day runs from the apparent rising of the Sun's upper limb to its apparent
setting, and the rising's own instant is day, the setting's night: Gr. Intr.
VI.33, 4 (Gr. Intr. p. 402), "the Sun is the planet by whose rising the day
comes to be, and by his setting the night comes to be"; VI.33, 17 (Gr. Intr.
p. 403), the hours of the day begin "from the inception of the Sun's rising
from the eastern horizon", with Dykes's fn 357 there, "so long as any part of
the Sun's disk is still above the horizon, it is still daytime".

Where no rising or setting lay within a day ahead, the sect asked the Sun's
altitude. Just after the last sunrise before a polar day the bracket of events
already held that rising, with no setting since, but the altitude, the Sun's
centre on its threshold, said night: at the pole from the rising's instant to
1.8 s after it, past the polar circles at the instant itself. The ruling: where
nothing lies ahead, the most recent event behind decides (a rising behind with
no setting since is day, a setting behind with no rising since night), and only
where neither lies within a day does the altitude decide.
"""
import pytest

from conftest import FLORENCE

SECOND = 1.0 / 86400.0

# The reproduction's two inputs (lat, y, m, d, UT hours; lon 0): just after the
# seasonal sunrise at each pole.
NORTH = (90.0, 2024, 3, 17, 21.0 + 49.0 / 60.0 + 19.0 / 3600.0)
SOUTH = (-90.0, 2024, 9, 20, 6.0 + 41.0 / 60.0 + 33.0 / 3600.0)
# Its polar-circle cases at the last sunrise before polar day: a moment within a
# second of the rising, whose bracket holds it behind (lat, y, m, d, UT hours).
POLAR_CIRCLE = (
    (70.0, 2024, 5, 15, 0.0 + 28.0 / 60.0 + 59.0 / 3600.0),
    (-75.0, 2024, 10, 30, 0.0 + 26.0 / 60.0 + 12.0 / 3600.0),
)
# A moment an hour after each pole's seasonal setting, whose bracket holds it.
NORTH_SET_AFTER = (90.0, 2024, 9, 24, 19.75)
SOUTH_SET_AFTER = (-90.0, 2024, 3, 22, 9.5)


def _jd(engine, y, m, d, ut):
    return engine["civil_to_jd"](y, m, d, ut)


def _sect(engine, jd, lat, lon=0.0):
    return engine["calculate_traditional_chart_jd"](jd, lat, lon)["sect"]


def _fortune_by(chart, day):
    """The Lot of Fortune by the day formula (Ascendant + Moon - Sun) or the
    night one (Ascendant + Sun - Moon), counted here from the chart's places."""
    asc = chart["ascendant"]
    sun = chart["planetary_data"]["Sun"]["longitude"]
    moon = chart["planetary_data"]["Moon"]["longitude"]
    return (asc + moon - sun) % 360.0 if day else (asc + sun - moon) % 360.0


def _rising_behind(engine, jd, lat, lon=0.0):
    rise_before, set_before, rise_after, set_after = engine["_sun_bracket"](jd, lat, lon)
    assert rise_before is not None, (jd, lat)                               # premise: a rising behind,
    assert set_before is None or set_before < rise_before, (jd, lat)        # and no setting since
    assert rise_after is None and set_after is None, (jd, lat)              # premise: nothing within a day ahead
    return rise_before


@pytest.mark.parametrize("where, expected_fortune", [(NORTH, 278.6409243581), (SOUTH, 30.7378637306)],
                         ids=["north", "south"])
def test_the_reproductions_moments_are_diurnal_with_fortune_by_day(engine, where, expected_fortune):
    lat, y, m, d, ut = where
    jd = _jd(engine, y, m, d, ut)
    rise = _rising_behind(engine, jd, lat)
    assert 0.0 < (jd - rise) / SECOND < 2.0, (jd - rise) / SECOND                # the rising a second or so back
    chart = engine["calculate_traditional_chart_jd"](jd, lat, 0.0)
    assert chart["sect"] == "Diurnal"
    assert engine["_sun_is_up"](jd, lat, 0.0) is True                            # the bracket behind decides
    assert chart["lot_of_fortune"] == pytest.approx(_fortune_by(chart, True), abs=1e-9)
    assert chart["lot_of_fortune"] == pytest.approx(expected_fortune, abs=1e-6)
    assert abs(chart["lot_of_fortune"] - _fortune_by(chart, False)) > 1.0


@pytest.mark.parametrize("where", [NORTH, SOUTH], ids=["north", "south"])
def test_the_seasonal_rising_is_day_from_its_own_instant(engine, where):
    lat, y, m, d, ut = where
    rise = _rising_behind(engine, _jd(engine, y, m, d, ut), lat)
    for dt in (0.0, 0.5, 1.2, 1.8):
        assert _sect(engine, rise + dt * SECOND, lat) == "Diurnal", dt
    assert _sect(engine, rise - SECOND, lat) == "Nocturnal"                     # the near miss: still the polar night


@pytest.mark.parametrize("where", [NORTH_SET_AFTER, SOUTH_SET_AFTER], ids=["north", "south"])
def test_the_seasonal_setting_is_day_up_to_it_and_night_at_it(engine, where):
    lat, y, m, d, ut = where
    _rise_before, sunset, rise_after, set_after = engine["_sun_bracket"](_jd(engine, y, m, d, ut), lat, 0.0)
    assert sunset is not None and rise_after is None and set_after is None
    for dt in (-1.0, -0.1):
        assert _sect(engine, sunset + dt * SECOND, lat) == "Diurnal", dt
    for dt in (0.0, 0.1, 1.0, 60.0):
        assert _sect(engine, sunset + dt * SECOND, lat) == "Nocturnal", dt
    # The bracket behind decides the night too, as the altitude already did.
    assert engine["_sun_is_up"](sunset + SECOND, lat, 0.0) is False
    assert engine["_sun_is_up"](sunset + 1.0 - SECOND, lat, 0.0) is False      # the day-long reach's far edge
    assert engine["_sun_is_up"](sunset + 1.0 + SECOND, lat, 0.0) is None       # beyond it the altitude decides
    assert _sect(engine, sunset + 1.0 + SECOND, lat) == "Nocturnal"


@pytest.mark.parametrize("where", POLAR_CIRCLE, ids=["70N", "75S"])
def test_the_last_sunrise_before_polar_day_is_day_at_its_instant(engine, where):
    lat, y, m, d, ut = where
    jd = _jd(engine, y, m, d, ut)
    rise = engine["_sun_bracket"](jd + 30.0 * SECOND, lat, 0.0)[0]
    assert rise is not None and abs(rise - jd) < SECOND
    _rising_behind(engine, rise, lat)
    assert _sect(engine, rise, lat) == "Diurnal"
    assert _sect(engine, rise - SECOND, lat) == "Nocturnal"


def test_the_bracket_behind_reaches_a_day_and_the_altitude_takes_over_beyond(engine):
    """At the pole, a day less a second after the seasonal rising the rising
    still lies within the bracket and decides; a second beyond the day nothing
    lies within a day either side and the altitude decides, as it did."""
    lat, y, m, d, ut = NORTH
    rise = _rising_behind(engine, _jd(engine, y, m, d, ut), lat)
    assert engine["_sun_is_up"](rise + 1.0 - SECOND, lat, 0.0) is True
    assert _sect(engine, rise + 1.0 - SECOND, lat) == "Diurnal"
    assert engine["_sun_is_up"](rise + 1.0 + SECOND, lat, 0.0) is None
    assert _sect(engine, rise + 1.0 + SECOND, lat) == "Diurnal"


def test_sun_up_behind_reads_the_most_recent_event(engine):
    behind = engine["_sun_up_behind"]
    assert behind(None, None) is None
    assert behind(10.0, None) is True                  # a rising behind, no setting since
    assert behind(None, 10.0) is False                 # a setting behind, no rising since
    assert behind(10.2, 10.1) is True                  # rose after it set
    assert behind(10.1, 10.2) is False                 # set after it rose


def test_an_ordinary_latitude_is_unchanged(engine):
    """Florence: the events ahead decide, as before; the rising's instant is
    day, the setting's night, and a second before each the other."""
    lat, lon = FLORENCE
    rise = engine["_find_sun_event"](_jd(engine, 2000, 6, 21, 0.0), lat, lon, True)
    sunset = engine["_find_sun_event"](rise, lat, lon, False)
    assert 0.5 < sunset - rise < 0.7
    for jd, want in ((rise - SECOND, "Nocturnal"), (rise, "Diurnal"), (rise + SECOND, "Diurnal"),
                     (sunset - SECOND, "Diurnal"), (sunset, "Nocturnal"), (sunset + SECOND, "Nocturnal")):
        _rb, _sb, rise_after, set_after = engine["_sun_bracket"](jd, lat, lon)
        assert engine["_sun_up_ahead"](rise_after, set_after) is not None     # decided ahead, never behind
        assert _sect(engine, jd, lat, lon) == want, (jd, want)
    noon = engine["calculate_traditional_chart_jd"]((rise + sunset) / 2.0, lat, lon)
    assert noon["sect"] == "Diurnal"
    assert noon["lot_of_fortune"] == pytest.approx(_fortune_by(noon, True), abs=1e-9)
