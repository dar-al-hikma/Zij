"""Lane KT (wave 5): one boundary for day and night, the chart's sect and the
planetary hours alike.

The chart's sect and the planetary hours divide day and night at the Sun's
visible rising and setting: Gr. Intr. VI.33, 17 (p. 403), "the beginning of the
hours of the day are from the inception of the Sun's rising from the eastern
horizon, while the beginning of the hours of the night are from the
disappearance of the Sun's body from the horizon of the west". So the two must
agree at every instant, and an event's own instant begins the period it opens.

Until this lane they did not. The sect asked swe.rise_trans from an hour before
the moment, the hours' bracket asked it again from a day before, and the two
searches return one event's root a few ulps (Florence) to a third of a second
(64 degrees) apart; the search behind the moment also left out an event equal to
the moment. At the engine's own sunrise or sunset, and within about a
millisecond of it, a chart could read day with the equal-hour fallback, or day
with the previous day's lords, or night counted to a sunrise already passed
(the second hostile pass's R2-10, `hostile_pass_sol_2026-10-06/R2_REPRODUCTION.md`
section 5; the astronomy audit's F1). And the search ahead of the moment said
it reached a day and reached about an hour more (the audit's F2).

The expectations below are counted here, from literal lists (the weekday's lord
and the Chaldean order), not read from the engine's tables.
"""
import math
import re
from datetime import time

import pytest

from conftest import FLORENCE, make_app

MS = 1.0 / 86400000.0
SECOND = 1.0 / 86400.0
MANUAL = "Manual UTC offset"

# Monday = 0, as the Julian Day counts it (floor(JD + 0.5) % 7 == 0 is a Monday).
WEEKDAY_LORD = ("Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Sun")
CHALDEAN = ("Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon")


def _weekday(jd, off):
    return int(math.floor(jd + off / 24.0 + 0.5)) % 7


def _hour_lord(day_lord, step):
    """The lord of the hour `step` steps on from the day's first (0-11 the
    day's twelve hours, 12-23 the night's)."""
    return CHALDEAN[(CHALDEAN.index(day_lord) + step) % 7]


def _local_hour(jd, off):
    return int(((jd + 0.5 + off / 24.0) % 1.0) * 24.0)


def _read(engine, jd, lat, lon, off):
    """(the chart's sect, the planetary day and hour) at one instant."""
    sect = engine["calculate_traditional_chart_jd"](jd, lat, lon)["sect"]
    return sect, engine["calculate_chronocrats"](jd, lat, lon, _local_hour(jd, off), off)


# --- R2-10: the engine's own sunrise is the day's first hour -------------------------------

# Florence's sunrises in R2-10, each with its weekday's lord: a Saturday, two
# Wednesdays and a Tuesday.
R2_10_SUNRISES = {(2000, 1, 1): "Saturn", (2000, 3, 1): "Mercury", (2000, 5, 10): "Mercury",
                  (2000, 8, 1): "Mars"}


@pytest.mark.parametrize("off", [0.0, 1.0])
@pytest.mark.parametrize("ymd", sorted(R2_10_SUNRISES))
def test_kt_r2_10_the_engines_own_sunrise_is_the_days_first_hour(engine, ymd, off):
    """Florence: the sunrise _find_sun_event finds from civil midnight. At that
    instant the day has begun (VI.33, 17), so the chart is Diurnal and the hour
    is the day's first, temporal, its lord the day lord: 2000-01-01 is a
    Saturday, Saturn and Saturn, at a UTC offset of 0 and of +1 alike (R2-10:
    on 55c2e92 the equal-hour fallback, whose lord is Saturn at +1 only by the
    count from civil midnight); 2000-05-10 a Wednesday, Mercury and Mercury
    (on 55c2e92 Tuesday's Mars, from a sunrise 23.98 hours back)."""
    lat, lon = FLORENCE
    ev = engine["_find_sun_event"](engine["civil_to_jd"](*ymd), lat, lon, True)
    sect, c = _read(engine, ev, lat, lon, off)
    lord = R2_10_SUNRISES[ymd]
    assert WEEKDAY_LORD[_weekday(ev, off)] == lord, (ymd, off)
    assert sect == "Diurnal", (ymd, off, sect, c)
    assert c["Approximate"] is False and c["Hour Bracketed"] is True, (ymd, off, c)
    assert (c["Day Lord"], c["Hour Lord"]) == (lord, lord), (ymd, off, c)
    assert c["Day Lord Civil"] is False and c["Hour Reason"] == "", c


def test_kt_no_window_at_ulp_resolution_where_sect_and_hours_disagree(engine):
    """R2-10 measured the inconsistent window at 2 to about 60 ulps of the JD
    (one ulp is about 40 microseconds here). Every representable instant from
    60 ulps before each of its four sunrises, and before F1's sunset, to 60
    after: the hours are temporal, and whichever side the chart's sect puts
    the instant on, the hour is that side's -- before a sunrise the night's
    last hour of the day before, after it the day's first; before a sunset the
    day's last, after it the night's first."""
    lat, lon = FLORENCE
    events = [(engine["_find_sun_event"](engine["civil_to_jd"](*ymd), lat, lon, True), lat, lon, 1.0, True)
              for ymd in R2_10_SUNRISES]
    import swisseph as swe
    events.append((engine["_find_sun_event"](swe.julday(2024, 6, 21, 0.0), -60.0, -120.0, False),
                   -60.0, -120.0, 0.0, False))
    assert len(events) == 5
    wrong, seen = [], {"Diurnal": 0, "Nocturnal": 0}
    for ev, la, lo, off, rising in events:
        jd = ev
        for _ in range(60):
            jd = math.nextafter(jd, 0.0)
        for k in range(-60, 61):
            sect, c = _read(engine, jd, la, lo, off)
            seen[sect] += 1
            day = WEEKDAY_LORD[_weekday(ev, off)]
            if rising:
                want = ((day, day) if sect == "Diurnal" else
                        (WEEKDAY_LORD[(_weekday(ev, off) - 1) % 7], _hour_lord(WEEKDAY_LORD[(_weekday(ev, off) - 1) % 7], 23)))
            else:
                want = (day, _hour_lord(day, 11 if sect == "Diurnal" else 12))
            if c["Approximate"] or (c["Day Lord"], c["Hour Lord"]) != want:
                wrong.append((ev, k, sect, c["Day Lord"], c["Hour Lord"], c["Approximate"], want))
            jd = math.nextafter(jd, math.inf)
    assert seen["Diurnal"] > 0 and seen["Nocturnal"] > 0, seen
    assert wrong == [], (len(wrong), wrong[:6])


# --- the app: a whole second typed at a sunrise --------------------------------------------

def _strip_reading(at):
    strip = next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)
    sect = re.search(r"\*\*(Diurnal|Nocturnal) · ", strip)
    lords = re.search(r"Day lord (\w+)[^·]*· Hour lord (\w+)", strip)
    assert sect and lords, strip
    return sect.group(1), lords.group(1), lords.group(2), strip


def test_kt_the_apps_whole_second_at_a_sunrise_reads_one_side():
    """Florence, 2006-05-20 (a Saturday), Manual UTC offset +1: the Sun rises
    within 3 ms of 04:44:37 by the clock. The strip at 04:44:36 is the night's
    (Friday's), at 04:44:38 the day's (Saturn, Saturn); at 04:44:37 its sect
    and its lords must be one side's, whichever the chart's sect names (R2-10
    found Diurnal with Friday's Venus and Venus, unflagged)."""
    readings = {}
    for second in (36, 37, 38):
        at = make_app(date="2006-05-20", page="chart", timeout=300)
        at.session_state["time_input_key"] = time(4, 44, second)
        at.session_state["time_standard_key"] = MANUAL
        at.session_state["utc_offset_key"] = 1.0
        at.run(timeout=300)
        assert not at.exception, [e.value for e in at.exception]
        readings[second] = _strip_reading(at)
        assert "equal-hour" not in readings[second][3], readings[second][3]
    assert readings[36][:3] == ("Nocturnal", "Venus", "Moon"), readings[36]
    assert readings[38][:3] == ("Diurnal", "Saturn", "Saturn"), readings[38]
    side = readings[38] if readings[37][0] == "Diurnal" else readings[36]
    assert readings[37][:3] == side[:3], (readings[37], side)


# --- F1: the engine's own sunset is the night's first hour --------------------------------

F1_SUNSET = 2460483.457364960108       # the audit's: _find_sun_event(2024-06-21 00:00 UT, -60, -120, set)


def test_kt_f1_the_sunset_is_the_nights_first_hour(engine):
    """60S 120W, UTC offset 0. The sunset the audit took from the engine
    (Friday 2024-06-21, 22:58 UT). The night has begun at it (VI.33, 17): the
    chart is Nocturnal, the hour temporal and the night's first, Friday's
    Venus counted on twelve hours, Mars (the audit's own count). On 55c2e92:
    Mercury, the equal-hour approximation, a millisecond later Mars."""
    import swisseph as swe
    lat, lon = -60.0, -120.0
    own = engine["_find_sun_event"](swe.julday(2024, 6, 21, 0.0), lat, lon, False)
    assert abs(own - F1_SUNSET) < 10 * MS, (own - F1_SUNSET) / MS          # the premise: the engine's event
    sect, c = _read(engine, F1_SUNSET, lat, lon, 0.0)
    assert sect == "Nocturnal", (sect, c)
    assert c["Approximate"] is False and c["Hour Bracketed"] is True, c
    assert (c["Day Lord"], c["Hour Lord"]) == ("Venus", "Mars"), c
    assert _hour_lord("Venus", 12) == "Mars"


# --- a sample: 160 sunrises and sunsets, at -1 ms, 0 and +1 ms -----------------------------

SAMPLE_LATS = (-64.0, -60.0, -45.0, -33.9, 0.0, 23.4, 43.7792, 51.5, 60.0, 64.0)
SAMPLE_PLACES = ((-120.0, -8.0), (11.2463, 1.0))          # longitude, UTC offset
SAMPLE_DATES = ((2000, 3, 20), (2000, 6, 21), (2000, 12, 21), (2024, 9, 22))


def test_kt_around_sunrises_and_sunsets_the_sect_and_the_hour_agree(engine):
    """Ten latitudes from 64S to 64N (64 degrees is where swe.rise_trans's
    roots for one event differ most with the starting instant), two places,
    four seasons: each day's sunrise and sunset as _find_sun_event finds them
    from local midnight, and 1 ms either side. Every period exists here, so
    the hours are always temporal; the hour is the half of the day the chart's
    sect names (a sunrise: the day's first hour and the day's lord, or the
    night's last of the day before; a sunset: the day's last hour or the
    night's first); and at the event's own instant the period it begins holds
    it -- the sunrise is the day's, the sunset the night's (VI.33, 17)."""
    wrong, events, moments = [], 0, 0
    for lat in SAMPLE_LATS:
        for lon, off in SAMPLE_PLACES:
            for ymd in SAMPLE_DATES:
                midnight = engine["civil_to_jd"](*ymd) - off / 24.0
                rise = engine["_find_sun_event"](midnight, lat, lon, True)
                sett = engine["_find_sun_event"](rise, lat, lon, False)
                # the premise: both on the local civil date, so the day before
                # is the weekday before
                assert 0.0 < (rise - midnight) * 24.0 < 12.0 < (sett - midnight) * 24.0 < 24.0, (lat, lon, ymd)
                day = WEEKDAY_LORD[_weekday(rise, off)]
                eve = WEEKDAY_LORD[(_weekday(rise, off) - 1) % 7]
                for ev, rising in ((rise, True), (sett, False)):
                    events += 1
                    for dt in (-MS, 0.0, MS):
                        moments += 1
                        sect, c = _read(engine, ev + dt, lat, lon, off)
                        if rising:
                            want = (day, day) if sect == "Diurnal" else (eve, _hour_lord(eve, 23))
                        else:
                            want = (day, _hour_lord(day, 11 if sect == "Diurnal" else 12))
                        own = dt == 0.0 and sect != ("Diurnal" if rising else "Nocturnal")
                        if c["Approximate"] or (c["Day Lord"], c["Hour Lord"]) != want or own:
                            wrong.append((lat, lon, ymd, "rise" if rising else "set", dt / MS, sect,
                                          c["Day Lord"], c["Hour Lord"], c["Approximate"], want))
    assert (events, moments) == (160, 480), (events, moments)
    assert wrong == [], (len(wrong), wrong[:6])


# --- F2: the search ahead reaches the day it says ------------------------------------------

def test_kt_f2_the_search_ahead_reaches_one_day(engine):
    """_next_sun_events says an event is None where none falls within the day
    ahead, as the page says ("Where he neither rises nor sets within a day")
    and as the owner's ruling 36 reads a night "whose sunset and next sunrise
    both lie within a day". The audit's case: 80S 25E, 2024-02-26 00:00 UT, the
    next sunrise 24.175 hours ahead, returned. And over a polar grid (every
    fifth day of 2024 at four hours, 66-80 degrees either side) every event the
    search returns lies within the day ahead."""
    import swisseph as swe
    jd = 2460367.5
    rise, sett = engine["_next_sun_events"](jd, -80.0, 25.0)
    assert rise is None, (rise - jd) * 24.0
    assert sett is not None and 0.0 < sett - jd <= 1.0, sett
    beyond, returned = [], 0
    for lat in (-80.0, -70.0, -68.0, -66.0, 66.0, 68.0, 70.0, 80.0):
        for day in range(0, 366, 5):
            for hour in (0.0, 6.0, 12.0, 18.0):
                now = swe.julday(2024, 1, 1, hour) + day
                for event in engine["_next_sun_events"](now, lat, 25.0):
                    if event is not None:
                        returned += 1
                        if not 0.0 < event - now <= 1.0:
                            beyond.append((lat, day, hour, (event - now) * 24.0))
    assert returned > 1000, returned
    assert beyond == [], beyond[:10]


# --- the guard: no ordinary chart's hours move ---------------------------------------------

GUARD_PLACES = ((43.7792, 11.2463, 1.0), (-33.87, 151.21, 10.0), (0.0, -78.5, -5.0), (51.5, -0.13, 0.0),
                (64.13, -21.9, 0.0), (-45.0, 170.5, 12.0))
GUARD_DATES = ((1240, 5, 23), (2000, 1, 1), (2000, 3, 20), (2000, 6, 21), (2000, 9, 22), (2000, 12, 21),
               (2024, 2, 29))


def test_kt_no_ordinary_hour_moves_at_the_hours_midpoints(engine):
    """The middle of each of the 24 temporal hours of 42 days (six places, seven
    dates, one before the Gregorian reform): the chart's sect is the hour's
    half, the hours are temporal, the day lord is the weekday's lord of the
    sunrise that opened the day, and the hour lord is counted on from him in
    the Chaldean order. Passes on main 55c2e92 (the base) and on this lane's
    head alike: the boundary moved, nothing between the boundaries did."""
    wrong, moments = [], 0
    for lat, lon, off in GUARD_PLACES:
        for ymd in GUARD_DATES:
            midnight = engine["civil_to_jd"](*ymd) - off / 24.0
            rise = engine["_find_sun_event"](midnight, lat, lon, True)
            sett = engine["_find_sun_event"](rise, lat, lon, False)
            rise2 = engine["_find_sun_event"](sett, lat, lon, True)
            assert rise < sett < rise2 < rise + 1.1, (lat, lon, ymd)
            day = WEEKDAY_LORD[_weekday(rise, off)]
            for step in range(24):
                start, end = (rise, sett) if step < 12 else (sett, rise2)
                jd = start + ((step % 12) + 0.5) * (end - start) / 12.0
                moments += 1
                sect, c = _read(engine, jd, lat, lon, off)
                got = (sect, c["Approximate"], c["Day Lord"], c["Hour Lord"])
                want = ("Diurnal" if step < 12 else "Nocturnal", False, day, _hour_lord(day, step))
                if got != want:
                    wrong.append((lat, lon, ymd, step, got, want))
    assert moments == 6 * 7 * 24, moments
    assert wrong == [], (len(wrong), wrong[:6])
