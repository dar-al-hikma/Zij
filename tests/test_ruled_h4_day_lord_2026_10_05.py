"""The owner's ruling 5 of 2026-10-05 (the re-pass's Q7): the day lord out of
reach of a sunrise.

Gr. Intr. VI.33, 4: "the Sun is the planet by whose rising the day comes to
be"; 17: "the beginning of the hours of the day are from the inception of the
Sun's rising from the eastern horizon"; 14 names the weekdays' lords. The
texts do not say what the day lord is where no rising lies in reach. The
ruling: where no sunrise lies within a day behind the moment, the Lord of the
Day is the civil weekday's lord, and the page says so -- the Chart page's
caption, the strip and the four victor grids' "Lord of the Day (7)" (and the
wide wheel's sect line, which names him too). "Within a day" is one day: the
search behind the moment reaches 24 hours, not the 1.2 days lane G5 left, so a
sunrise 24-28.8 hours old no longer gives the day lord (the re-pass's check
of that lane, notes N1 and N2), and the page's sentence is true on both sides
of the reach. A night whose sunset and next sunrise both lie within a day
takes the sunrise that opened its day from within a day before its sunset
(Gr. Intr. VI.33, 10: the night continues its day's count). An independent
check against the astronomical oracle stands beside this file, in the
development-only tests.
"""
import re
from datetime import time

import pytest

from conftest import assert_no_exception, make_app, natal_wheel_envelope, table_nodes

MANUAL = "Manual UTC offset"
CIVIL = "civil weekday"
STILL_EXACT = "The Lord of the Day is still exact."


def _chronocrats(engine, jd, lat, lon, off):
    local_hour = int(((jd + 0.5 + off / 24.0) % 1.0) * 24.0)
    return engine["calculate_chronocrats"](jd, lat, lon, local_hour, off)


def _civil_lord(engine, jd, off):
    return engine["DAY_LORD_BY_WEEKDAY"][engine["_weekday_from_jd"](jd, off)]


# --- the engine: the reach is one day -------------------------------------------------

def test_h4_the_sunrise_gives_the_day_lord_for_one_day_and_no_longer(engine):
    """70N 25E at UTC+2: the Sun rose 2000-11-25 09:52 UT for the last time
    that year (a Saturday). A day after it the civil Sunday's lord takes over,
    not at 1.2 days (the re-pass check's note N1: Saturn turned to the Sun at 14:40 UT on
    the 26th, 28.8 hours after the sunrise)."""
    import swisseph as swe
    lat, lon, off = 70.0, 25.0, 2.0
    rise = engine["_previous_sun_event"](swe.julday(2000, 11, 25, 23.5), lat, lon, True)
    assert rise is not None and abs(rise - swe.julday(2000, 11, 25, 9 + 52 / 60)) < 2 / 1440, rise
    inside, outside = rise + 1.0 - 2 / 1440, rise + 1.0 + 2 / 1440
    assert engine["_previous_sun_event"](inside, lat, lon, True) == pytest.approx(rise, abs=1e-6)
    assert engine["_previous_sun_event"](outside, lat, lon, True) is None
    a, b = _chronocrats(engine, inside, lat, lon, off), _chronocrats(engine, outside, lat, lon, off)
    assert (a["Day Lord"], a["Day Lord Civil"]) == ("Saturn", False), a
    assert (b["Day Lord"], b["Day Lord Civil"]) == ("Sun", True), b
    assert b["Day Lord"] == _civil_lord(engine, outside, off)
    # the hour lord is the equal-hour approximation on both sides, and the
    # reach does not move it (one Chaldean chain: VI.33, 7)
    assert a["Approximate"] and b["Approximate"]
    assert a["Hour Lord"] == "Saturn" and b["Hour Lord"] == "Saturn", (a, b)


def test_h4_a_sunrise_more_than_a_day_old_gives_no_day_lord(engine):
    """The re-pass check's note N1: 68N 25E 2000-05-26 00:20 UT (a Friday) at UTC+0.
    The last sunrise was 25.6 hours back, on the Wednesday, whose Mercury the
    1.2-day search read; Thursday's lord never appeared. Out of reach, the day
    lord is the civil Friday's Venus, and says so."""
    import swisseph as swe
    lat, lon, off = 68.0, 25.0, 0.0
    jd = swe.julday(2000, 5, 26, 20 / 60)
    assert engine["_previous_sun_event"](jd, lat, lon, True) is None
    c = _chronocrats(engine, jd, lat, lon, off)
    assert (c["Day Lord"], c["Day Lord Civil"]) == ("Venus", True), c


@pytest.mark.parametrize("lat, lon, y, m, d", [
    (43.7792, 11.2463, 2000, 10, 15),     # Florence: the sunrise comes later each day
    (72.0, 25.0, 2000, 8, 12),            # 72N: a 20-hour day, then a short night
])
def test_h4_a_night_with_both_its_ends_keeps_its_days_sunrise_past_24_hours(engine, lat, lon, y, m, d):
    """The reach is one day, but a night whose sunset and next sunrise both lie
    within a day continues the count of the day its sunset ended (Gr. Intr.
    VI.33, 10), so its sunrise is sought within a day before that sunset.
    Half a minute before the sunrise, the one before it is more than 24 hours
    old here; the hour stays temporal and the day lord that sunrise's (a reach
    measured from the moment made these minutes approximate and civil, and
    broke two of test_hostile_l1_2026_10_03's sunrise pins)."""
    import swisseph as swe
    rise = engine["_find_sun_event"](swe.julday(y, m, d, 0.0), lat, lon, True)
    jd = rise - 0.5 / 1440
    sunset = engine["_previous_sun_event"](jd, lat, lon, False)
    day_rise = engine["_find_sun_event"](sunset - 1.0, lat, lon, True)
    assert day_rise < sunset and jd - day_rise > 1.0, (jd - day_rise) * 24     # premise: over a day old
    assert engine["_previous_sun_event"](jd, lat, lon, True) is None
    c = _chronocrats(engine, jd, lat, lon, 0.0)
    assert c["Approximate"] is False and c["Day Lord Civil"] is False, c
    assert c["Day Lord"] == _civil_lord(engine, day_rise, 0.0), c


# --- the pages: said where it is so, and only there -----------------------------------------

def _strip(at):
    return next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)


def _notice(at):
    return [c.value for c in at.main.caption if "not a temporal hour" in c.value]


def _day_rows(at):
    rows = []
    for _, node in table_nodes(at):
        df = node.value
        if "Row" in df.columns:
            for _, r in df[df["Row"] == "Lord of the Day (7)"].iterrows():
                rows.append([str(v) for k, v in r.items() if k != "Row" and str(v).strip()])
    return rows


def _wheel_sect_line(at):
    svg = natal_wheel_envelope(at.main)["svg"]
    texts = [re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)]
    return next(t for t in texts if t.startswith("Sect: "))


def _polar(page, **state):
    """78.2N 15.6E on the default date (1240-05-23): the Sun circumpolar, no
    sunrise within a day on either side."""
    at = make_app(page=page)
    at.session_state["manual_lat_key"] = 78.2
    at.session_state["manual_lon_key"] = 15.6
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=300)


def _first_night_of_the_polar_night(page, **state):
    """70N 25E, 2000-11-26 01:30 at UTC+2: the night after the year's last
    sunset, whose sunrise lies 13.6 hours back -- the hour approximate, the day
    lord that sunrise's (lane G5, L5R-01)."""
    at = make_app(date="2000-11-26", page=page)
    at.session_state["time_input_key"] = time(1, 30)
    at.session_state["manual_lat_key"] = 70.0
    at.session_state["manual_lon_key"] = 25.0
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 2.0
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=300)


def test_h4_the_chart_page_says_whose_day_lord_it_is_on_both_sides_of_the_reach():
    # no sunrise within a day: the civil weekday's, said in the caption, the strip and the wheel
    polar = _polar("chart", _wheel_layout="Wide")
    assert_no_exception(polar, "chart, circumpolar")
    notice = _notice(polar)
    assert len(notice) == 1 and STILL_EXACT not in notice[0], notice
    assert "The Lord of the Day is the civil weekday's lord" in notice[0], notice
    assert "\"the Sun is the planet by whose rising the day comes to be\" (Gr. Intr. VI.33, 4)" in notice[0]
    assert "no sunrise lies within a day behind this moment" in notice[0]
    assert len(notice[0]) <= 400
    day = re.search(r"Day lord (\w+)( \(civil weekday\))?", _strip(polar))
    assert day and day.group(2), _strip(polar)
    assert f"Lord of the day: {day.group(1)} ({CIVIL})" in _wheel_sect_line(polar)
    # a sunrise 13.6 hours back: the hour approximate, the day lord exact and unqualified
    night = _first_night_of_the_polar_night("chart", _wheel_layout="Wide")
    assert_no_exception(night, "chart, first night of the polar night")
    notice = _notice(night)
    assert len(notice) == 1 and notice[0].endswith(STILL_EXACT), notice
    assert re.search(r"Day lord Saturn · ", _strip(night)), _strip(night)
    assert CIVIL not in _strip(night) and CIVIL not in _wheel_sect_line(night)


def test_h4_the_four_victor_grids_qualify_a_civil_day_lord_and_only_it():
    polar = _polar("victors")
    assert_no_exception(polar, "victors, circumpolar")
    rows = _day_rows(polar)
    assert len(rows) == 4 and all(r == [f"7 ({CIVIL})"] for r in rows), rows
    night = _first_night_of_the_polar_night("victors")
    assert_no_exception(night, "victors, first night of the polar night")
    rows = _day_rows(night)
    assert len(rows) == 4 and all(r == ["7"] for r in rows), rows
