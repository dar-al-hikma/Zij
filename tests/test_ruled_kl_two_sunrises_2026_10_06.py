"""The owner's ruling 25 of 2026-10-05 (FQ-6, K-43): two sunrises on one
civil date.

Gr. Intr. VI.33, 4: "the Sun is the planet by whose rising the day comes to
be"; 14: "the lords of the days are known by that, so that the lord of
Wednesday is Mercury ...". The texts do not contemplate two sunrises falling
on one civil date. The ruling: each planetary day keeps the civil weekday of
the sunrise that opened it, so a weekday's lord rules twice running, and the
page says so there -- the strip, the Chart page's caption and the four victor
grids' "Lord of the Day (7)" (and the wide wheel's sect line, which names him
too). Under ruling 5 (the day lord out of reach of a sunrise) the second of
the two days ends a day after its sunrise where no sunset follows it.

71.5N 25E, local mean time: the Sun rises 2000-05-09 00:35:58 and again
23:58:01 the same Tuesday, then sets no more (the polar day). Both days are
Mars's; at 2000-05-10 12:00 the hour is the equal-hour approximation. 40N 0E
at a manual offset of -7 h: sunrises 2000-02-09 00:00:50 and 23:59:42, a
Wednesday, with sunsets between, so the second Wednesday has temporal hours.
"""
import re
from datetime import time

import pytest

from conftest import assert_no_exception, make_app, natal_wheel_envelope, table_nodes

LMT, MANUAL = "LMT (Local Mean Time)", "Manual UTC offset"
REPEATED = "weekday repeated"


def _chronocrats(engine, jd, lat, lon, off):
    local_hour = int(((jd + 0.5 + off / 24.0) % 1.0) * 24.0)
    return engine["calculate_chronocrats"](jd, lat, lon, local_hour, off)


def _strip(at):
    return next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)


def _notice(at):
    return [c.value for c in at.main.caption if "not a temporal hour" in c.value or "weekday repeats" in c.value]


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


def _north(page, date, hh, mm, **state):
    at = make_app(date=date, page=page, timeout=300)
    at.session_state["time_input_key"] = time(hh, mm)
    at.session_state["manual_lat_key"] = 71.5
    at.session_state["manual_lon_key"] = 25.0
    at.session_state["time_standard_key"] = LMT
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=300)


def _manual_minus_seven(page, **state):
    """40N 0E, 2000-02-10 05:00 at UTC-7 (12:00 UT): the Sun up, the day
    opened by the second sunrise of the civil 2000-02-09, temporal hours."""
    at = make_app(date="2000-02-10", page=page, timeout=300)
    at.session_state["time_input_key"] = time(5, 0)
    at.session_state["manual_lat_key"] = 40.0
    at.session_state["manual_lon_key"] = 0.0
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = -7.0
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=300)


# --- the engine: each day keeps its opening sunrise's weekday, and says which repeats ---------------

def test_kl_each_planetary_day_keeps_its_opening_sunrises_weekday(engine):
    import swisseph as swe
    lat, lon, off = 71.5, 25.0, 25.0 / 15.0
    first = engine["_find_sun_event"](swe.julday(2000, 5, 8, 23.0 - off), lat, lon, True)
    second = engine["_find_sun_event"](first + 0.01, lat, lon, True)
    day = lambda jd: int((jd + off / 24.0 + 0.5) // 1)
    assert day(first) == day(second) == day(swe.julday(2000, 5, 9, 12.0 - off)), "the premise: two sunrises on 05-09"
    assert engine["DAY_LORD_BY_WEEKDAY"][engine["_weekday_from_jd"](first, off)] == "Mars", "the premise: a Tuesday"
    cases = [((9, 12.0), ("Mars", False, False)),            # the first Tuesday: nothing repeats yet
             ((10, 12.0), ("Mars", True, False)),            # the second, on a civil Wednesday
             ((10, 23.0 + 57 / 60), ("Mars", True, False)),  # a minute inside the day after its sunrise
             ((10, 23.0 + 59.5 / 60), ("Mercury", False, True))]   # past it: ruling 5's civil weekday
    assert len(cases) == 4
    for (d, h), want in cases:
        c = _chronocrats(engine, swe.julday(2000, 5, d, h - off), lat, lon, off)
        assert (c["Day Lord"], c["Day Lord Repeated"], c["Day Lord Civil"]) == want, (d, h, c)
    # a moment past the second sunrise on its own date repeats as well
    c = _chronocrats(engine, second + 1 / 1440, lat, lon, off)
    assert (c["Day Lord"], c["Day Lord Repeated"]) == ("Mars", True), c


def test_kl_an_ordinary_day_is_not_called_repeated(engine):
    import swisseph as swe
    for jd, lat, lon, off in ((swe.julday(1240, 5, 23, 13.75, swe.JUL_CAL), 43.7792, 11.2463, 0.75),
                              (swe.julday(2000, 2, 9, 19.0), 40.0, 0.0, -7.0),       # the first Wednesday
                              (swe.julday(2000, 6, 21, 23.5), 78.2, 15.6, 0.0)):     # no sunrise in reach
        c = _chronocrats(engine, jd, lat, lon, off)
        assert c["Day Lord Repeated"] is False, (jd, c)


# --- the pages: said where it is so, and only there ---------------------------------------

def test_kl_the_second_tuesday_says_its_weekday_repeats_on_every_place_that_names_him():
    chart = _north("chart", "2000-05-10", 12, 0, _wheel_layout="Wide")
    assert_no_exception(chart, "chart, the second Tuesday")
    assert re.search(r"Day lord Mars \(weekday repeated\) · ", _strip(chart)), _strip(chart)
    assert f"Lord of the day: Mars ({REPEATED})" in _wheel_sect_line(chart)
    notice = _notice(chart)
    assert len(notice) == 1 and "still exact" not in notice[0], notice
    assert "two sunrises fell on one civil date" in notice[0], notice
    assert "each planetary day keeps the weekday of the sunrise that opened it" in notice[0], notice
    # ruling 5: no sunset follows, so this day ends a day after its sunrise
    assert "ends a day after its sunrise" in notice[0], notice
    assert len(notice[0]) <= 400, len(notice[0])
    victors = _north("victors", "2000-05-10", 12, 0)
    assert_no_exception(victors, "victors, the second Tuesday")
    assert re.search(r"Day lord Mars \(weekday repeated\) · ", _strip(victors)), _strip(victors)
    rows = _day_rows(victors)
    assert len(rows) == 4 and all(r == [f"7 ({REPEATED})"] for r in rows), rows


def test_kl_the_first_tuesday_and_the_civil_wednesday_are_not_called_repeated():
    first = _north("chart", "2000-05-09", 12, 0, _wheel_layout="Wide")
    assert_no_exception(first, "chart, the first Tuesday")
    assert re.search(r"Day lord Mars · ", _strip(first)), _strip(first)
    assert REPEATED not in _wheel_sect_line(first) and not _notice(first)
    civil = _north("victors", "2000-05-10", 23, 59)
    assert_no_exception(civil, "victors, past the second Tuesday")
    assert re.search(r"Day lord Mercury \(civil weekday\) · ", _strip(civil)), _strip(civil)
    rows = _day_rows(civil)
    assert len(rows) == 4 and all(r == ["7 (civil weekday)"] for r in rows), rows


def test_kl_a_repeated_weekday_with_temporal_hours_is_said_on_the_chart_page():
    chart = _manual_minus_seven("chart", _wheel_layout="Wide")
    assert_no_exception(chart, "chart, the second Wednesday")
    assert re.search(r"Day lord Mercury \(weekday repeated\) · Hour lord \w+\n?", _strip(chart)), _strip(chart)
    assert "equal-hour" not in _strip(chart)
    notice = _notice(chart)
    assert len(notice) == 1 and "not a temporal hour" not in notice[0], notice
    assert "two sunrises fell on one civil date" in notice[0], notice
    assert "\"the Sun is the planet by whose rising the day comes to be\" (Gr. Intr. VI.33, 4)" in notice[0]
    assert "ends a day after its sunrise" not in notice[0], notice
    assert len(notice[0]) <= 400, len(notice[0])
    victors = _manual_minus_seven("victors")
    rows = _day_rows(victors)
    assert len(rows) == 4 and all(r == [f"7 ({REPEATED})"] for r in rows), rows
