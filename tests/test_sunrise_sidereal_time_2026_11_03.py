"""Sunrise and sunset outside 1850-2050 turn with the engine's own sidereal time.

Swiss Ephemeris turns the sky by the IAU 2006 sidereal time only strictly
between 1850-01-01 and 2050-01-01 0h UT; at and outside those instants its
own long-term model runs ahead of IAU 2006 by about 519" at -500 and 37" at
1000, so swe.rise_trans put each rising and setting there about 35 s and
2.5 s early, in a frame that was no longer the chart's. Outside the span the
engine finds each event again where the Sun's upper limb stands on the same
horizon in its own frame (_rise_trans_sun); inside it, swe.rise_trans's event
is returned bit for bit. These pins hold:

* events outside the span against an explicit search written here (the IAU
  2006 sidereal time from its published series, the Sun from Swiss
  Ephemeris, the horizon swe.rise_trans uses), found by stepping from the
  day's start and halving, not from swe.rise_trans: every one within 5 ms,
  ten times the engine search's measured bound;
* modern events: swe.rise_trans's own, bit for bit, over a seeded sample;
* the span's edges, a second either side of each; each end where Swiss
  Ephemeris switches, and an instant exactly at it treated as outside;
* the last setting before the Sun stays down, the last rising before he
  stays up, and a rising after a night of about a minute, each from a start
  just before it;
* a moment before 1850 whose sect, day lord and hour lord swe.rise_trans's
  event gave wrongly;
* a start between swe.rise_trans's event and the engine's: the engine's
  event of that day, not the next day's;
* nights of half a minute: one only the engine's frame holds (with the
  chart's sect inside it and the hours after it), two whose event Newton's
  steps carried away from Swiss Ephemeris's; and one only Swiss Ephemeris's
  frame holds, which is not returned;
* a start on an event: not answered by the search again from its mark
  where that search puts the event at or before the start.
"""
from __future__ import annotations

import math
import random

import pytest
import swisseph as swe

# The engine's search lies within 0.5 ms of its own root; against an
# independent search of the same horizon, within 0.5 ms (2,620 events, -3000
# to 3000, latitudes to 69) and about 1 ms where the Sun grazes. Every event
# outside the span is held to TIGHT, ten times BOUND.
BOUND = 0.0005                      # seconds
TIGHT = 10 * BOUND                  # seconds
SPAN = (2396758.5, 2469807.5)       # where Swiss Ephemeris's sidereal time is IAU 2006 (open)
DAY_S = 86400.0

_r, (_true, _app, _x, _y) = swe.refrac_extended(0.000001, 0.0, 1013.25, 0.0, 0.0065, swe.APP_TO_TRUE)
_REFRACTION = _app - _true          # degrees, at the apparent horizon


def _frame(jd_ut):
    """(GAST, true obliquity), degrees: the Earth rotation angle, the IAU 2006
    GMST polynomial and mean obliquity, and the equation of the equinoxes
    from Swiss Ephemeris's nutation (the complementary terms, a few
    milliarcseconds, left out)."""
    jd_tt = jd_ut + swe.deltat_ex(jd_ut, -1)
    nutation = swe.calc(jd_tt, swe.ECL_NUT, swe.FLG_MOSEPH)[0]
    t = (jd_tt - 2451545.0) / 36525.0
    tu = jd_ut - 2451545.0
    era = 360.0 * ((tu % 1.0) + 0.7790572732640 + 0.00273781191135448 * tu)
    eps_a = (84381.406 - 46.836769 * t - 0.0001831 * t ** 2 + 0.00200340 * t ** 3
             - 0.000000576 * t ** 4 - 0.0000000434 * t ** 5) / 3600.0
    gmst = era + (0.014506 + 4612.156534 * t + 1.3915817 * t ** 2 - 0.00000044 * t ** 3
                  - 0.000029956 * t ** 4 - 0.0000000368 * t ** 5) / 3600.0
    return (gmst + nutation[2] * math.cos(math.radians(eps_a))) % 360.0, eps_a + nutation[3]


def _over_horizon(jd, lat, lon):
    """Sine of the Sun's centre's altitude less the sine of the altitude it
    has when his upper limb stands on swe.rise_trans's horizon (refraction
    at 1013.25 mbar and 0 C, his semi-diameter, less his parallax)."""
    gast, eps = _frame(jd)
    lon_s, lat_s, dist = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH | swe.FLG_SPEED)[0][:3]
    ra, dec, _d = swe.cotrans((lon_s, lat_s, dist), -eps)
    km = dist * 149597870.7
    horizon = math.degrees(math.asin(6378.1366 / km)) - math.degrees(math.asin(696000.0 / km)) - _REFRACTION
    p, d, h = map(math.radians, (lat, dec, gast + lon - ra))
    return math.sin(p) * math.sin(d) + math.cos(p) * math.cos(d) * math.cos(h) - math.sin(math.radians(horizon))


def _explicit_event(jd0, lat, lon, rise):
    """The first rising (or setting) after jd0: ten-minute steps to the first
    change of sign of the right kind, then halved to 0.1 ms."""
    step = 10.0 / 1440.0
    a, below_a = jd0, _over_horizon(jd0, lat, lon) < 0.0
    for _ in range(int(1.5 / step)):
        b = a + step
        below_b = _over_horizon(b, lat, lon) < 0.0
        if below_a == rise and below_b != rise:
            while (b - a) * DAY_S > 1e-4:
                m = 0.5 * (a + b)
                if (_over_horizon(m, lat, lon) < 0.0) == below_a:
                    a = m
                else:
                    b = m
            return 0.5 * (a + b)
        a, below_a = b, below_b
    raise AssertionError(("no event", jd0, lat, lon, rise))


def _rise_trans(jd, lat, lon, rise):
    res, tret = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE if rise else swe.CALC_SET, (lon, lat, 0.0),
                               flags=swe.FLG_MOSEPH)
    assert res == 0, (jd, lat, lon, rise, res)
    return tret[0]


def _jd(y, m, d, h=0.0):
    return swe.julday(y, m, d, h, swe.GREG_CAL if y > 1582 else swe.JUL_CAL)


YEARS = (-500, 1, 1000, 1500, 1800, 2200, 3000)
PLACES = ((0.0, 25.0), (43.7792, 11.2463), (60.0, 25.0))


@pytest.mark.parametrize("year", YEARS)
def test_events_outside_the_span_are_the_explicit_search_s(engine, year):
    worst = 0.0
    for lat, lon in PLACES:
        jd0 = _jd(year, 6, 21) if lat < 50 else _jd(year, 3, 21)
        for rise in (True, False):
            expected = _explicit_event(jd0, lat, lon, rise)
            got = engine["_rise_trans_sun"](jd0, lat, lon, rise)
            assert not SPAN[0] < got < SPAN[1], (year, got)
            gap = abs(got - expected) * DAY_S
            worst = max(worst, gap)
            assert gap < TIGHT, (year, lat, rise, gap)
    assert worst < TIGHT, worst


def test_modern_events_are_rise_trans_s_bit_for_bit(engine):
    rng = random.Random(20261103)
    for _ in range(120):
        jd = rng.uniform(SPAN[0] + 2.0, SPAN[1] - 2.0)
        lat, lon, rise = rng.uniform(-60.0, 64.0), rng.uniform(-180.0, 180.0), rng.random() < 0.5
        assert engine["_rise_trans_sun"](jd, lat, lon, rise) == _rise_trans(jd, lat, lon, rise), (jd, lat, lon, rise)
    for lat, lon in PLACES:                                # the 1850-2049 ends, and 2000
        for jd in (_jd(1850, 1, 2), _jd(1900, 6, 21), _jd(2000, 6, 21), _jd(2049, 12, 30)):
            for rise in (True, False):
                assert engine["_rise_trans_sun"](jd, lat, lon, rise) == _rise_trans(jd, lat, lon, rise)


def _longitude_for(edge, offset_s, lat, rise):
    """An east longitude whose rise_trans event, asked from half a day
    before the edge, falls offset_s after it (an event moves a day earlier
    per 360 degrees east)."""
    lon = 0.0
    for _ in range(6):
        event = _rise_trans(edge - 0.5, lat, lon, rise)
        lon = (lon + (event - (edge + offset_s / DAY_S)) * 360.0 + 180.0) % 360.0 - 180.0
    event = _rise_trans(edge - 0.5, lat, lon, rise)
    assert abs((event - edge) * DAY_S - offset_s) < 0.05, (edge, offset_s, lat, (event - edge) * DAY_S)
    return lon


@pytest.mark.parametrize("edge", SPAN)
@pytest.mark.parametrize("lat", (0.0, 45.0))
def test_a_second_either_side_of_the_span_s_edges(engine, edge, lat):
    """Inside the span the event is rise_trans's, bit for bit; a second
    outside it, the explicit search's. Swiss Ephemeris's own sidereal time
    steps there by 0.1" (1850) and 1.9" (2050), 6 ms and 0.13 s of an event;
    the engine's steps only by rise_trans's own unsettled root."""
    for rise in (True, False):
        for offset in (-1.0, 1.0):
            lon = _longitude_for(edge, offset, lat, rise)
            raw = _rise_trans(edge - 0.5, lat, lon, rise)
            got = engine["_rise_trans_sun"](edge - 0.5, lat, lon, rise)
            if SPAN[0] < raw < SPAN[1]:
                assert got == raw, (edge, lat, rise, offset)
            else:
                assert abs(got - _explicit_event(edge - 0.5, lat, lon, rise)) * DAY_S < TIGHT, (edge, lat, rise, offset)


# The flip: year 500, 36 N 0 E, 21 March. swe.rise_trans's sunrise comes
# about 11 s before the explicit search's; a moment between the two is
# still night.
FLIP = (500, 3, 21, 36.0, 0.0)


def test_a_moment_rise_trans_called_day_is_the_night_s_last_hour(engine):
    year, month, day, lat, lon = FLIP
    jd0 = _jd(year, month, day)
    sunrise = _explicit_event(jd0, lat, lon, True)
    old_sunrise = _rise_trans(jd0, lat, lon, True)
    assert 5.0 < (sunrise - old_sunrise) * DAY_S < 20.0, (sunrise - old_sunrise) * DAY_S
    moment = 0.5 * (sunrise + old_sunrise)
    # The explicit search's events around the moment.
    last_sunrise = _explicit_event(jd0 - 1.0, lat, lon, True)
    last_sunset = _explicit_event(last_sunrise, lat, lon, False)
    assert last_sunrise < last_sunset < moment < sunrise
    offset = lon / 15.0

    def weekday(jd):                                  # Monday = 0, the civil date at the local mean time
        return int(math.floor(jd + offset / 24.0 + 0.5)) % 7

    order = list(engine["CHALDEAN_HOUR_ORDER"])
    lords = engine["DAY_LORD_BY_WEEKDAY"]
    day_lord = lords[weekday(last_sunrise)]           # the planetary day opened by the last sunrise
    hour_number = int((moment - last_sunset) / ((sunrise - last_sunset) / 12.0)) + 1
    assert hour_number == 12
    hour_lord = order[(order.index(day_lord) + 12 + hour_number - 1) % 7]
    # What swe.rise_trans's sunrise made of it: day, the new day's lord, his first hour.
    old_day_lord = lords[weekday(old_sunrise)]
    assert old_day_lord != day_lord and old_day_lord != hour_lord

    chart = engine["calculate_traditional_chart_jd"](moment, lat, lon)
    assert chart["sect"] == "Nocturnal", chart["sect"]
    local_hour = ((moment + offset / 24.0 + 0.5) % 1.0) * 24.0
    lords_now = engine["calculate_chronocrats"](moment, lat, lon, local_hour, offset)
    assert lords_now["Approximate"] is False
    assert (lords_now["Day Lord"], lords_now["Hour Lord"]) == (day_lord, hour_lord), lords_now


def test_a_start_between_rise_trans_s_event_and_the_engine_s_finds_that_day_s(engine):
    for year, lat, lon, rise in ((500, 36.0, 0.0, True), (1, 50.0, 10.0, False), (1000, -30.0, 140.0, True)):
        jd0 = _jd(year, 3, 21)
        expected = _explicit_event(jd0, lat, lon, rise)
        start = 0.5 * (expected + _rise_trans(jd0, lat, lon, rise))
        got = engine["_rise_trans_sun"](start, lat, lon, rise)
        assert got > start and abs(got - expected) * DAY_S < TIGHT, (year, lat, rise, (got - expected) * DAY_S)


# The last setting before the Sun stays down (-105, 68.27 N 26.68 W) and the
# last rising before he stays up (JD 1885019.832, 67.49 S 134.54 W): Swiss
# Ephemeris's event lies 24 s and 13 s before the explicit one (its last
# member), and it has no later one of the kind, so from a start between the
# two swe.rise_trans finds none.
LAST_BEFORE_POLAR = ((1682680.773, 68.27, -26.68, False, 23.8), (1885019.832, -67.49, -134.54, True, 12.5))


@pytest.mark.parametrize("case", LAST_BEFORE_POLAR)
@pytest.mark.parametrize("before_s", (1.0, 5.0, 10.0, 20.0))
def test_the_last_event_before_the_sun_stays_down_or_up_is_found_from_just_before_it(engine, case, before_s):
    jd0, lat, lon, rise, swiss_early_s = case
    expected = _explicit_event(jd0, lat, lon, rise)
    start = expected - before_s / DAY_S
    res, _tret = swe.rise_trans(start, swe.SUN, swe.CALC_RISE if rise else swe.CALC_SET, (lon, lat, 0.0),
                                flags=swe.FLG_MOSEPH)
    assert (res == -2) == (before_s < swiss_early_s), (case, before_s, res)   # none from a start after Swiss's
    for name in ("_rise_trans_sun", "_find_sun_event"):
        got = engine[name](start, lat, lon, rise)
        assert got > start and abs(got - expected) * DAY_S < TIGHT, (name, case, before_s, res,
                                                                      (got - expected) * DAY_S)


def _swiss_less_iau(jd):
    """Swiss Ephemeris's sidereal time less the IAU 2006 one of _frame, arcseconds."""
    return ((swe.sidtime(jd) * 15.0 - _frame(jd)[0] + 180.0) % 360.0 - 180.0) * 3600.0


@pytest.mark.parametrize("edge", SPAN)
def test_the_span_s_ends_are_where_swiss_ephemeris_switches_and_count_as_outside(engine, monkeypatch, edge):
    """Swiss Ephemeris's sidereal time is IAU 2006 one ulp inside each end
    and its own long-term model at the end itself and beyond (0.1" ahead at
    1850, 1.9" behind at 2050); so an event, or a start, exactly at an end is
    found in the engine's own frame."""
    assert tuple(engine["SWISS_IAU_SIDEREAL_SPAN"]) == SPAN
    inward = math.inf if edge == SPAN[0] else -math.inf
    assert abs(_swiss_less_iau(math.nextafter(edge, inward))) < 0.01
    assert abs(_swiss_less_iau(edge)) > 0.05
    assert abs(_swiss_less_iau(math.nextafter(edge, -inward))) > 0.05

    lat, rise = 0.0, True
    lon = _longitude_for(edge, 0.0, lat, rise)
    seeds = []
    own, swiss = engine["_sun_event_in_own_frame"], engine["_swiss_rise_trans_sun"]

    def spy(seed, *args):
        seeds.append(seed)
        return own(seed, *args)

    monkeypatch.setitem(engine, "_sun_event_in_own_frame", spy)
    monkeypatch.setitem(engine, "_swiss_rise_trans_sun", lambda jd, *args: edge)   # an event exactly at the end
    got = engine["_rise_trans_sun"](edge - 0.5, lat, lon, rise)
    assert seeds == [edge], seeds
    assert abs(got - _explicit_event(edge - 0.5, lat, lon, rise)) * DAY_S < TIGHT

    lon = _longitude_for(edge, 5.0, lat, rise)          # a start exactly at the end, from which none is found

    def none_from_the_end(jd, *args):
        if jd == edge:
            raise engine["_CircumpolarSunError"]("none from the end")
        return swiss(jd, *args)

    monkeypatch.setitem(engine, "_swiss_rise_trans_sun", none_from_the_end)
    got = engine["_rise_trans_sun"](edge, lat, lon, rise)
    lead = swiss(edge - engine["SUN_EVENT_OWN_LEAD_DAYS"], lat, lon, rise)
    assert got > edge, (edge, (got - edge) * DAY_S)
    if SPAN[0] < lead < SPAN[1]:                        # 5 s inside 1850: Swiss Ephemeris's own, as it is
        assert got == lead
    else:                                               # 5 s past 2050: the engine's own
        assert abs(got - _explicit_event(edge, lat, lon, rise)) * DAY_S < TIGHT


# -500, 67 S 56.321 E: the last night before the Sun stays up lasts about a
# minute in the engine's frame, and swe.rise_trans puts its sunrise 18 s
# early; the night's setting and rising lie within a minute of each other,
# so no bracket centred near the early sunrise holds the engine's own.
SHORT_NIGHT = (1538772.34, -67.0, 56.321)            # a moment inside that night


@pytest.mark.parametrize("before_s", (1.0, 5.0, 10.0, 20.0, 60.0))
def test_the_sunrise_after_a_night_of_a_minute_is_the_engine_s_own(engine, before_s):
    jd0, lat, lon = SHORT_NIGHT
    assert _over_horizon(jd0, lat, lon) < 0.0
    expected = _explicit_event(jd0, lat, lon, True)
    assert _over_horizon(expected - 70.0 / DAY_S, lat, lon) > 0.0        # the setting lies within 70 s before it
    assert 15.0 < (expected - _rise_trans(expected - 0.1, lat, lon, True)) * DAY_S < 20.0
    start = expected - before_s / DAY_S
    for name in ("_rise_trans_sun", "_find_sun_event"):
        got = engine[name](start, lat, lon, True)
        assert got > start and abs(got - expected) * DAY_S < TIGHT, (name, before_s, (got - expected) * DAY_S)


def _explicit_event_near(jd0, lat, lon, rise, within_s=400.0, step_s=0.25):
    """The first rising (or setting) within within_s after jd0, by steps of
    step_s (a night of half a minute passes between two of _explicit_event's
    ten-minute steps), then halved to 0.1 ms; None if there is none."""
    a, below_a = jd0, _over_horizon(jd0, lat, lon) < 0.0
    for k in range(1, int(within_s / step_s) + 1):
        b = jd0 + k * step_s / DAY_S
        below_b = _over_horizon(b, lat, lon) < 0.0
        if below_a == rise and below_b != rise:
            while (b - a) * DAY_S > 1e-4:
                m = 0.5 * (a + b)
                if (_over_horizon(m, lat, lon) < 0.0) == below_a:
                    a = m
                else:
                    b = m
            return 0.5 * (a + b)
        a, below_a = b, below_b
    return None


# Nights of half a minute outside the span, each from a start 120 s before
# its setting: -500, 66.8955 N 145.0734 E, a night only the engine's frame
# holds (Swiss Ephemeris's next sunrise is the next day's); -500, 66.8354 S
# 30.9491 E, and year 1, 66.8379 S 17.1434 W, nights both frames hold, whose
# event Newton's steps carried away from Swiss Ephemeris's (10-60 s off),
# no bracket around the carried estimate holding it.
GRAZING = ((1538633.0963858985, 66.89550812654197, 145.0734028144081, True),
           (1538773.409026878, -66.83540653921663, 30.949090247450158, False),
           (1721760.5417887964, -66.83790798410773, -17.143360736465297, True))


def _grazing_night(case):
    jd0, lat, lon, _rise = case
    setting = _explicit_event_near(jd0, lat, lon, False)
    sunrise = _explicit_event_near(setting, lat, lon, True)
    assert 100.0 < (setting - jd0) * DAY_S < 140.0 and 20.0 < (sunrise - setting) * DAY_S < 40.0, case
    return setting, sunrise


@pytest.mark.parametrize("case", GRAZING)
def test_a_night_of_half_a_minute_outside_the_span_is_the_engine_s_own(engine, case):
    jd0, lat, lon, rise = case
    setting, sunrise = _grazing_night(case)
    expected = sunrise if rise else setting
    assert abs(_rise_trans(jd0, lat, lon, rise) - expected) * DAY_S > 5.0     # Swiss Ephemeris's is not it
    over = engine["_sun_over_horizon"]
    for name in ("_rise_trans_sun", "_find_sun_event"):
        got = engine[name](jd0, lat, lon, rise)
        assert got > jd0 and abs(got - expected) * DAY_S < TIGHT, (name, case, (got - expected) * DAY_S)
        # a crossing of the engine's own function, of the kind asked
        assert (over(got - 0.001 / DAY_S, lat, lon) < 0.0) == rise != (over(got + 0.001 / DAY_S, lat, lon) < 0.0)


@pytest.mark.parametrize("case", GRAZING[1:])
def test_swiss_ephemeris_s_event_carried_off_by_newton_s_steps_is_found_beside_it(engine, case):
    """The search from Swiss Ephemeris's own event alone, its Newton's
    steps carried away: the brackets around that event hold the engine's."""
    jd0, lat, lon, rise = case
    setting, sunrise = _grazing_night(case)
    expected = sunrise if rise else setting
    got = engine["_sun_event_in_own_frame"](_rise_trans(jd0, lat, lon, rise), lat, lon, rise)
    assert got is not None and abs(got - expected) * DAY_S < TIGHT, (case, got)


def test_the_sect_and_the_hours_beside_a_night_only_the_engine_s_frame_holds(engine):
    """Inside the night the chart is nocturnal; an hour after its sunrise
    the hours are the temporal ones, under the lord of that sunrise's day."""
    jd0, lat, lon, _rise = GRAZING[0]
    setting, sunrise = _grazing_night(GRAZING[0])
    moment = 0.5 * (setting + sunrise)
    assert _over_horizon(moment, lat, lon) < 0.0
    assert engine["calculate_traditional_chart_jd"](moment, lat, lon)["sect"] == "Nocturnal"
    later, offset = sunrise + 1.0 / 24.0, lon / 15.0
    local_hour = ((later + offset / 24.0 + 0.5) % 1.0) * 24.0
    lords = engine["calculate_chronocrats"](later, lat, lon, local_hour, offset)
    weekday = int(math.floor(sunrise + offset / 24.0 + 0.5)) % 7          # Monday = 0, local mean time
    assert lords["Approximate"] is False, lords
    assert lords["Day Lord"] == engine["DAY_LORD_BY_WEEKDAY"][weekday], lords


# Year 1, 66.837924 S 17.1434 W, a little nearer the pole than the third
# grazing night: Swiss Ephemeris's frame still holds a night of about 40 s,
# the engine's none for days, so the engine finds no sunrise or sunset.
SWISS_ONLY_NIGHT = (1721760.5417887964, -66.837924, -17.143360736465297)


def test_a_night_only_swiss_ephemeris_s_frame_holds_is_not_returned(engine):
    jd0, lat, lon = SWISS_ONLY_NIGHT
    swiss_setting, swiss_sunrise = _rise_trans(jd0, lat, lon, False), _rise_trans(jd0, lat, lon, True)
    assert 0.0 < (swiss_setting - jd0) * DAY_S < (swiss_sunrise - jd0) * DAY_S < 200.0
    for rise in (True, False):
        assert _explicit_event_near(jd0, lat, lon, rise) is None
        with pytest.raises(AssertionError, match="no event"):
            _explicit_event(jd0 + 400.0 / DAY_S, lat, lon, rise)
        for name in ("_rise_trans_sun", "_find_sun_event"):
            with pytest.raises(engine["_CircumpolarSunError"]):
                engine[name](jd0, lat, lon, rise)
    assert engine["_sun_is_up"](0.5 * (swiss_setting + swiss_sunrise), lat, lon) is True


# Year 1000, starts within a millisecond of an event (a day of 60 s at
# 67.9605 N 39.6279 W, its setting; a night of 90 s at 66.8691 S 51.7356 W,
# its rising), where the search again from the fixed mark puts the event at
# or before the start.
ON_AN_EVENT = ((2086670.1153790313, 67.96046300940216, -39.62793169106914, False),
               (2086675.6509131142, -66.86907031871378, -51.73557652344322, True))


@pytest.mark.parametrize("case", ON_AN_EVENT)
def test_a_start_on_an_event_is_not_answered_by_a_search_at_or_before_it(engine, case):
    start, lat, lon, rise = case
    expected = _explicit_event_near(start - 300.0 / DAY_S, lat, lon, rise)
    assert abs(expected - start) * DAY_S < 0.001, (case, (expected - start) * DAY_S)
    anchor = math.floor((engine["_rise_trans_sun"](start, lat, lon, rise) - 2.0 / 24.0) / 0.25) * 0.25
    assert engine["_rise_trans_sun"](anchor, lat, lon, rise) <= start      # the search from the mark
    got = engine["_find_sun_event"](start, lat, lon, rise)
    assert got > start and got == engine["_rise_trans_sun"](start, lat, lon, rise), (case, (got - start) * DAY_S)
    assert abs(got - expected) * DAY_S < TIGHT
