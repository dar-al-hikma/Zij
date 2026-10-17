"""Hostile pass of 2026-10-03, lane L1: astronomy and time.

One test per finding (xfail, strict, so it fails the day the finding is fixed
and the mark can go), plus passing tests for the attacks the app survived,
plus the two tools' fixtures: the astronomical oracle tool (development-only) (first-principles
spherical astronomy, written before the engine was read; 216 probes) and the Alchabitius table
parser (development-only) (the parser for Astrodienst's Alcabitius table, read against an
excerpt). Both tools, their probes and the excerpt stay in development.
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from datetime import time

import pytest
import swisseph as swe

from conftest import EXECUTABLE_DIR, assert_no_exception, find_table, make_app, table_nodes, ui_source
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import skip_without_corpus


LMT, STD, MANUAL = "LMT (Local Mean Time)", "Standard time (pytz)", "Manual UTC offset"
FLORENCE = (43.7792, 11.2463)
ARCMIN = 1.0 / 60.0
SECOND = 1.0 / 86400.0


def XF(ident, claim):
    return pytest.mark.xfail(strict=True, reason=f"{ident}: {claim}")


def _app(date, hhmm, page, lat=FLORENCE[0], lon=FLORENCE[1], standard=LMT, offset=None, **state):
    at = make_app(date=date, page=page)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = standard
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert_no_exception(at, f"{date} {hhmm} {page}")
    return at


def _sidebar_text(at):
    return "\n".join([n.value for n in at.sidebar.info] + [n.value for n in at.sidebar.error])


def _page_text(at):
    out = []
    for kind in ("markdown", "caption", "info", "warning", "error"):
        out.extend(str(n.value) for n in getattr(at.main, kind))
    return "\n".join(out)


# =============================================================================
# The findings (xfail, strict)
# =============================================================================

def test_l1_01_pytz_pre_1901_history_is_dropped():
    at = _app("1890-06-01", (12, 0), "chart", lat=40.7128, lon=-74.006, standard=STD)
    assert "UTC offset -05:00" in _sidebar_text(at), _sidebar_text(at)


def test_l1_02_above_horizon_column_follows_altitude_for_the_moon():
    """Fixed (one horizon): the Dignities Sect table's 'Above horizon' is the
    body's altitude, as the same row's hayz reads it, not the ecliptic proxy
    (lon - Asc) % 360 > 180; the Moon 3.4 degrees up by her latitude is Yes."""
    at = make_app(date="1240-10-11", page="dignities")
    at.run()
    assert_no_exception(at, "dignities 1240-10-11")
    sect = find_table(at, "Sect").value
    moon = sect[sect["Planet"] == "Moon"].iloc[0]
    assert moon["Above horizon"] == "Yes", moon.to_dict()


def test_l1_02_above_horizon_column_follows_altitude_at_the_pole():
    """Fixed (one horizon): at 85N on 2000-12-21 noon the Sun, 18 degrees
    below the horizon in a chart the app calls Nocturnal, is No."""
    at = _app("2000-12-21", (12, 0), "dignities", lat=85.0, lon=0.0)
    sect = find_table(at, "Sect").value
    sun = sect[sect["Planet"] == "Sun"].iloc[0]
    assert sun["Above horizon"] == "No", sun.to_dict()


def test_l1_03_zone_lmt_is_not_the_birthplaces():
    at = _app("1240-05-23", (14, 30), "chart", lat=28.6139, lon=77.209, standard=STD)
    text = _sidebar_text(at)
    refused = len(at.sidebar.error) > 0
    assert refused or "meridian" in text.lower() or "(LMT)" not in text, text


def test_l1_04_sect_and_hour_count_agree_on_whether_the_sun_is_up(engine):
    """Fixed (one horizon): sect and the planetary day turn together, at the
    apparent rise of the Sun's upper limb (Gr. Intr. VI.33, 4 and 17)."""
    lat, lon = FLORENCE
    rise = engine["_find_sun_event"](engine["civil_to_jd"](2000, 6, 21, 0.0), lat, lon, True)
    jd = rise + SECOND
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    before = engine["calculate_chronocrats"](rise - SECOND, lat, lon, 4, lon / 15.0)
    after = engine["calculate_chronocrats"](jd, lat, lon, 4, lon / 15.0)
    day_turned = after["Day Lord"] != before["Day Lord"]
    assert day_turned == (chart["sect"] == "Diurnal"), (before, after, chart["sect"])


# The midnight Sun: the four charts of the F5 check's finding 3 (lat, lon,
# y, m, d, UT hours). At each the Sun neither rises nor sets within a day and
# his centre stands a little below the true horizon while his disk shows.
MIDNIGHT_SUN = (
    (70.0, 25.0, 2000, 5, 16, 22.0 + 20.0 / 60.0),
    (70.0, 25.0, 2000, 5, 18, 22.0 + 20.0 / 60.0),
    (70.0, 25.0, 2000, 7, 25, 23.0),
    (66.0, 25.0, 2000, 6, 21, 22.0 + 20.0 / 60.0),
)


def test_l1_04_midnight_sun_reads_diurnal_where_the_sun_neither_rises_nor_sets(engine):
    """Fixed (one horizon, second build): at the edge of polar day the Sun's
    disk never sets while his centre dips below the true horizon. No rising or
    setting lies within a day, so the fallback decides, and it asks the hours'
    own question -- is any of the disk up (the centre above the horizon
    swe.rise_trans places a rising or setting on)? -- not whether the centre
    is above 0 degrees. Gr. Intr. VI.33, 4: by his setting the night comes to
    be; no setting, no night. The midnight Sun is Diurnal, and the Chart
    page's strip says so beside its sentence on the fallback."""
    for lat, lon, y, m, d, ut in MIDNIGHT_SUN:
        jd = engine["civil_to_jd"](y, m, d, ut)
        # Nothing lies within a day ahead of any of the four. The first holds
        # a rising 23.9 hours behind and no setting since, and since ruling
        # 145 (A-02) that bracket behind decides before the altitude; at the
        # other three nothing lies within a day either side, so the fallback
        # decides.
        _rise_after_set_after = engine["_sun_bracket"](jd, lat, lon)[2:]
        assert _rise_after_set_after == (None, None), (lat, lon, y, m, d, ut)
        expected = True if (y, m, d) == (2000, 5, 16) else None
        assert engine["_sun_is_up"](jd, lat, lon) is expected, (lat, lon, y, m, d, ut)
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        sun = chart["planetary_data"]["Sun"]
        sin_alt = engine["_sin_altitude"](sun["longitude"], sun["latitude"], sun["distance"],
                                          chart["obliquity"], chart["armc"], lat)
        assert engine["sun_up_sin_altitude"](sun["distance"]) < sin_alt < 0.0, (lat, lon, y, m, d, ut, sin_alt)   # centre down, disk up
        assert chart["sect"] == "Diurnal", (lat, lon, y, m, d, ut, chart["sect"])
    at = _app("2000-05-16", (22, 20), "chart", lat=70.0, lon=25.0, standard=MANUAL, offset=0.0)
    strip = next(c.value for c in at.main.caption if " \u00b7 " in c.value)
    assert "**Diurnal" in strip, strip
    assert "whether any of his disk is above that same horizon decides" in _page_text(at)


def _sun_sin_altitude_at(engine, jd, lat, lon):
    """(sine of the Sun's centre's geometric altitude, his distance in AU) from
    the engine's own chart at jd."""
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    sun = chart["planetary_data"]["Sun"]
    return (engine["_sin_altitude"](sun["longitude"], sun["latitude"], sun["distance"],
                                    chart["obliquity"], chart["armc"], lat),
            sun["distance"], chart["sect"])


def test_l1_04_the_fallback_horizon_is_the_one_rise_trans_places_its_events_on(engine):
    """Fixed (one horizon, third build): the sect fallback's threshold is not a
    figure of our own but the horizon swe.rise_trans itself uses -- its own
    refraction at the apparent horizon, the Sun's semi-diameter at his
    distance, less his parallax (engine.sun_up_altitude). Witness: at every
    rising and setting rise_trans reports, across the year and the ephemeris's
    span, the Sun's centre stands at exactly that altitude (within 0.02'). The
    conventional flat -50' is more than 2' above it, which is why a Sun that
    never set could read Nocturnal (F5 re-check, R1)."""
    worst = 0.0
    for y, m, d in ((2000, 6, 21), (2000, 12, 21), (2000, 3, 20), (1500, 6, 21), (2100, 1, 3)):
        jd0 = engine["civil_to_jd"](y, m, d, 0.0)
        for lat, lon in ((0.0, 25.0), (43.7792, 11.2463), (-33.87, 151.21), (60.0, 25.0)):
            for rsmi in (swe.CALC_RISE, swe.CALC_SET):
                res, tret = swe.rise_trans(jd0, swe.SUN, rsmi, (lon, lat, 0.0))
                assert res == 0, (y, m, d, lat, rsmi)
                sin_alt, distance, _sect = _sun_sin_altitude_at(engine, tret[0], lat, lon)
                horizon = engine["sun_up_altitude"](distance)
                gap = abs(math.degrees(math.asin(sin_alt)) - horizon) * 60.0
                worst = max(worst, gap)
                assert gap < 0.02, (y, m, d, lat, rsmi, gap)
                assert -53.0 / 60.0 < horizon < -52.0 / 60.0, horizon       # about -52.3' (June) to -52.9' (December)
                assert horizon < -50.0 / 60.0 - 2.0 / 60.0, horizon         # the flat convention sits above it
    assert worst < 0.02, worst


def test_l1_04_a_sun_that_never_set_reads_diurnal_in_the_band_above_rise_trans_s_horizon(engine):
    """Fixed (one horizon, third build; F5 re-check, R1): 65.7N 25E 2000-06-21
    22:22 UT. swe.rise_trans finds no setting within the day (its own answer,
    not the oracle's: the oracle shared the old -50' and cannot witness this),
    so no night has come -- Gr. Intr. VI.33, 4 -- yet the Sun's centre, at
    about -51.9', lies between rise_trans's horizon and the flat -50' the
    fallback used to ask. The fallback now asks rise_trans's horizon, and the
    chart, and the Chart page's strip, read Diurnal."""
    lat, lon = 65.7, 25.0
    noon = engine["civil_to_jd"](2000, 6, 21, 12.0)
    res, _tret = swe.rise_trans(noon, swe.SUN, swe.CALC_SET, (lon, lat, 0.0))
    assert res == -2, res                                      # SE: no setting within the day
    jd = engine["civil_to_jd"](2000, 6, 21, 22.0 + 22.0 / 60.0)
    assert engine["_sun_is_up"](jd, lat, lon) is True          # a dip sets 23.95 h ahead (ruling 74)
    sin_alt, distance, sect = _sun_sin_altitude_at(engine, jd, lat, lon)
    centre = math.degrees(math.asin(sin_alt)) * 60.0
    assert -52.4 < centre < -50.0, centre                      # between the two horizons
    assert sect == "Diurnal", sect
    assert engine["sun_up_altitude"](distance) * 60.0 < centre, (engine["sun_up_altitude"](distance) * 60.0, centre)
    at = _app("2000-06-21", (22, 22), "chart", lat=lat, lon=lon, standard=MANUAL, offset=0.0)
    strip = next(c.value for c in at.main.caption if " \u00b7 " in c.value)
    assert "**Diurnal" in strip, strip


def test_l1_04_no_night_without_a_setting_reads_nocturnal_across_the_polar_day_edge(engine):
    """Fixed (one horizon, third build): the F5 re-check's span, May-August
    2000 at 65.5-73.3N (25E), at 22:20 UT each night -- the Sun's lowest
    point -- on a 0.2 degree grid every second day. Wherever swe.rise_trans
    finds neither a rising nor a setting within a day (the Sun never set), the
    chart is Diurnal; and over the polar night (November-January, at noon)
    wherever it finds neither (the Sun never rose) the chart is Nocturnal. The
    re-check found sixteen summer nights reading Nocturnal on this grid with
    the flat -50'; the assertion names any that remain."""
    lon = 25.0
    lats = [65.5 + 0.2 * i for i in range(40)]              # 65.5 .. 73.3
    wrong, fallback_nights = [], 0
    jd_may1 = engine["civil_to_jd"](2000, 5, 1, 22.0 + 20.0 / 60.0)
    for day in range(0, 123, 2):                            # 2000-05-01 .. 2000-08-31
        jd = jd_may1 + day
        for lat in lats:
            if engine["_sun_is_up"](jd, lat, lon) is not None:
                continue
            fallback_nights += 1
            _sin_alt, _distance, sect = _sun_sin_altitude_at(engine, jd, lat, lon)
            if sect != "Diurnal":
                wrong.append(("summer", lat, 2000, 5, 1, day, sect))
    assert fallback_nights > 500, fallback_nights           # the polar day is on this grid
    fallback_noons = 0
    jd_nov15 = engine["civil_to_jd"](2000, 11, 15, 10.0 + 20.0 / 60.0)
    for day in range(0, 78, 2):                             # 2000-11-15 .. 2001-01-31
        jd = jd_nov15 + day
        for lat in lats:
            if engine["_sun_is_up"](jd, lat, lon) is not None:
                continue
            fallback_noons += 1
            _sin_alt, _distance, sect = _sun_sin_altitude_at(engine, jd, lat, lon)
            if sect != "Nocturnal":
                wrong.append(("winter", lat, 2000, 11, 15, day, sect))
    assert fallback_noons > 300, fallback_noons             # the polar night is on this grid
    assert wrong == [], wrong[:20]


def test_l1_04_export_sect_caption_explains_above_horizon_in_the_band():
    """Fixed (one horizon, second build): in the minutes after the visible
    sunrise at Florence (2000-06-21 03:35:45 UT) the chart is Diurnal while
    the Sun's centre is still below the true horizon, so the Sect table's Sun
    row reads "Above horizon: No / Of the chart's sect: Yes". The export's
    Sect caption is the page's -- one string -- and explains the pair in both
    the Markdown and the HTML."""
    at = _app("2000-06-21", (3, 35, 45), "chart", standard=MANUAL, offset=0.0)
    strip = next(c.value for c in at.main.caption if " \u00b7 " in c.value)
    assert "**Diurnal" in strip, strip
    md = at.session_state["_analysis_markdown"]
    section = re.search(r"\n#+ Sect\n(.*?)(?=\n#+ )", md, re.S).group(1)
    assert "| Sun | Diurnal | No | Yes |" in section, section
    for text in (md, html.unescape(at.session_state["_analysis_html"])):
        i = text.find("Above horizon: the body's centre against the true horizon by its own altitude")
        assert i >= 0, text[:400]
        assert "divided at the Sun's visible rising and setting" in text[i:i + 400], text[i:i + 400]
    # the sentence sits in the Sect section itself, not elsewhere in the export
    assert "centre against the true horizon by its own altitude" in section, section


def test_l1_05_first_day_after_polar_night_has_temporal_hours(engine):
    """Fixed (one horizon): the first day of sunlight after a polar night has
    temporal hours -- its own sunrise and sunset both exist (70N 25E
    2000-01-17: sunrise 10:13:23, sunset 10:47:10 UT), so the day is 33.8
    minutes long and each of its twelve hours 2.82 minutes. Ten minutes
    after sunrise is day hour 4 of Monday: Moon, Saturn, Jupiter, Mars."""
    lat, lon = 70.0, 25.0
    jd = engine["civil_to_jd"](2000, 1, 17, 10.0 + 23.0 / 60.0)     # ten minutes after the first sunrise
    cr = engine["calculate_chronocrats"](jd, lat, lon, 12, lon / 15.0)
    assert cr["Approximate"] is False, cr
    assert (cr["Day Lord"], cr["Hour Lord"]) == ("Moon", "Mars"), cr      # Monday, day hour 4 of a 34-minute day
    first = engine["calculate_chronocrats"](engine["civil_to_jd"](2000, 1, 17, 10.0 + 14.0 / 60.0), lat, lon, 12, lon / 15.0)
    assert first["Approximate"] is False and (first["Day Lord"], first["Hour Lord"]) == ("Moon", "Moon"), first   # day hour 1


def test_l1_06_help_text_does_not_claim_every_table_keys_on_civil_years():
    assert "Every table on the Prediction pages keys on completed civil anniversaries" not in ui_source()


def test_l1_07_pole_is_qualified():
    """Fixed (one horizon): at latitude 90 the Chart page says no ecliptic
    degree rises, the quadrant divisions are undefined, and withholds them."""
    at = _app("2000-12-21", (12, 0), "chart", lat=90.0, lon=0.0)
    text = _page_text(at).lower()
    assert re.search(r"\bpole\b|no (ecliptic )?degree rises|not defined at this latitude|undefined at this latitude", text), text[:500]


def test_l1_08_lmt_offset_string_is_exact():
    at = _app("1982-06-01", (12, 0), "chart", lat=0.0, lon=-179.70)
    assert "-11:58:48" in _sidebar_text(at), _sidebar_text(at)


def test_l1_09_out_of_range_seed_is_refused_not_flipped():
    at = make_app(date="1982-06-01", page="chart")
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 14.25
    at.run()
    assert_no_exception(at, "manual 14.25")
    text = _sidebar_text(at)
    assert "UTC-14:00" not in text, text


def test_l1_10_target_hour_is_stated_as_ut():
    src = ui_source()
    assert re.search(r"target date at noon[,( ]{0,3}(UT|UTC|universal time)", src, re.I), "the Days page says 'noon' without UT"


# =============================================================================
# The oracle and its fixture
# =============================================================================


# =============================================================================
# Attacks that held
# =============================================================================

def test_standard_time_controls_1902_and_1982_new_york():
    at = _app("1902-06-01", (12, 0), "chart", lat=40.7128, lon=-74.006, standard=STD)
    assert "UTC offset -05:00 (EST)" in _sidebar_text(at)
    at = _app("1982-06-01", (12, 0), "chart", lat=40.7128, lon=-74.006, standard=STD)
    assert "UTC offset -04:00 (EDT)" in _sidebar_text(at)


def test_the_fact_behind_l1_02_the_moon_is_up_on_1240_10_11(engine):
    lat, lon = FLORENCE
    jd = engine["civil_local_to_jd_ut"](1240, 10, 11, 14.5, lon / 15.0)
    ch = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    moon = ch["planetary_data"]["Moon"]
    sin_alt = engine["_sin_altitude"](moon["longitude"], moon["latitude"], moon["distance"], ch["obliquity"], ch["armc"], lat)
    assert math.degrees(math.asin(sin_alt)) > 3.0
    assert (moon["longitude"] - ch["ascendant"]) % 360.0 < 180.0        # the proxy says "below"


def test_the_fact_behind_l1_05_both_events_exist_on_2000_01_17_at_70n(engine):
    lat, lon = 70.0, 25.0
    jd0 = engine["civil_to_jd"](2000, 1, 17, 0.0)
    rise = engine["_find_sun_event"](jd0, lat, lon, True)
    sett = engine["_find_sun_event"](jd0, lat, lon, False)
    assert 10.0 < (rise - jd0) * 24.0 < 10.5 and 10.5 < (sett - jd0) * 24.0 < 11.0
    with pytest.raises(engine["_CircumpolarSunError"]):
        engine["_find_sun_event"](jd0 - 1.0, lat, lon, False)                # the 16th had no sunset


def test_fardar_row_runs_on_elapsed_years_not_the_civil_age(engine):
    """The fardar at 1242-05-22 for the default chart: civil age 1, elapsed
    1.996 years; the fardar's second sub-period (Sun / Venus) has opened, as the Count
    row says it does. The Timing page's #4 is the fardar as it stood at the
    revolution's moment (the 1st return, 0.999 years elapsed: Sun / Sun), which is
    neither the civil age's nor the target's, and says so."""
    lat, lon = FLORENCE
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, 14.5, lon / 15.0)
    ch = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    bundle = engine["pn4_timing_bundle"](ch, lat, lon, engine["CivilDate"](1240, 5, 23), engine["CivilDate"](1242, 5, 22), "Sahl")
    assert bundle["fardar"]["lord"] == "Sun" and bundle["fardar"]["sub_lord"] == "Venus"
    assert next(r for r in bundle["fardar_rows"] if r["Active"] == "yes")["Lord"] == "Sun"
    row4 = next(r for r in bundle["year_rows"] if r["#"] == 4)
    assert row4["Ruler"] == "Sun / Sun" and row4["Active point"].startswith("at the revolution's moment, 0.999 years elapsed")
    assert engine["pn4_fardar_at_age"](1, ch["sect"])["sub_lord"] == "Sun"
    assert "1 completed civil years" in next(r for r in bundle["revolution_rows"] if r["Item"] == "Count of the year")["Value"]


def test_the_target_hour_behind_l1_10(engine):
    jd_birth = engine["civil_local_to_jd_ut"](1990, 3, 10, 23.0, 9.0)
    ch = engine["calculate_traditional_chart_jd"](jd_birth, 35.6762, 139.6503)
    bundle = engine["pn4_timing_bundle"](ch, 35.6762, 139.6503, engine["CivilDate"](1990, 3, 10), engine["CivilDate"](1991, 3, 10), "Sahl")
    count = next(r for r in bundle["revolution_rows"] if r["Item"] == "Count of the year")["Value"]
    assert count.startswith("1 completed civil years") and "0 solar returns completed" in count and "0.999 years elapsed" in count


def test_completed_years_and_birthdays_across_the_calendar_edges(engine):
    CD, birthday, completed = engine["CivilDate"], engine["pn4_birthday"], engine["pn4_completed_years"]
    b = CD(1300, 2, 29)
    assert [str(birthday(b, a)) for a in (1, 2, 282, 283, 300)] == ["1301-03-01", "1302-03-01", "1582-03-01", "1583-03-01", "1600-02-29"]
    assert birthday(b, 282).calendar_name() == "Julian" and birthday(b, 283).calendar_name() == "Gregorian"
    assert all(completed(b, birthday(b, a)) == a for a in (1, 2, 282, 283, 300))
    assert [str(birthday(CD(1904, 2, 29), a)) for a in (1, 4, 96, 100)] == ["1905-03-01", "1908-02-29", "2000-02-29", "2004-02-29"]
    b = CD(1582, 10, 4)
    assert completed(b, CD(1583, 10, 3)) == 0 and completed(b, CD(1583, 10, 4)) == 1 and completed(b, CD(1583, 10, 14)) == 1
    assert CD(1583, 10, 14) - b == 365 and CD(1583, 10, 4) - b == 355


def test_reform_crossing_ut_prints_as_julian_on_the_chart_and_timing_pages():
    at = _app("1582-10-15", (0, 30), "chart", standard=MANUAL, offset=5.0)
    calc = {r["Quantity"]: r["Value"] for _, r in find_table(at, "Calculation").value.iterrows()}
    assert calc["Universal time"].startswith("1582-10-04 19:30:00 UT"), calc["Universal time"]
    assert "Julian" in calc["Universal time"] and "Gregorian" in calc["Universal time"]
    assert "UT 1582-10-04 19:30:00" in _sidebar_text(at)
    at = _app("1582-10-15", (0, 30), "timing", standard=MANUAL, offset=5.0, _target_mode="Age", _target_age=0)
    rev = find_table(at, "The revolution of the year").value
    # (L5-08: the row now says UT and names its calendar, as the sidebar does)
    moment = rev[rev["Item"] == "Moment of the revolution"]["Value"].iloc[0]
    assert moment == "1582-10-04 19:30:00 UT (Julian calendar)", moment


def test_civil_moment_near_midnight_carries_the_date(engine):
    CM = engine["CivilMoment"]
    for eps in (-2e-6, -1e-6, -1e-7, 0.0, 1e-7, 1e-6):
        assert str(CM.from_jd(2451545.5 + eps)) == "2000-01-02 00:00:00", eps
    assert str(CM.from_jd(engine["civil_local_to_jd_ut"](1582, 10, 15, 0.5, 5.0))) == "1582-10-04 19:30:00"


def test_rate_ladder_and_fardar_cycle_boundaries(engine):
    fmt = engine["pn4_format_arc_time"]
    assert [fmt(a) for a in (1.0, 5 / 60, 1 / 60, 1 / 3600)] == ["1y 0m 0d 0.0h", "0y 1m 0d 0.0h", "0y 0m 6d 0.0h", "0y 0m 0d 2.4h"]
    at_age = engine["pn4_fardar_at_age"]
    assert at_age(74.999999, "Nocturnal")["lord"] == "Tail"
    assert (at_age(75.0, "Nocturnal")["lord"], at_age(75.0, "Nocturnal")["cycle"]) == ("Moon", 2)
    assert (at_age(75.0, "Diurnal")["lord"], at_age(75.0, "Diurnal")["cycle"]) == ("Sun", 2)
    assert at_age(9 / 7 - 1e-9, "Nocturnal")["sub_lord"] == "Moon" and at_age(9 / 7, "Nocturnal")["sub_lord"] == "Saturn"


def test_anniversary_in_a_dst_gap_is_unresolved(engine):
    r = engine["anniversary_moment"](engine["CivilMoment"](2006, 3, 11, 2, 30, 0), 1, time_standard=STD, zone_name="America/New_York")
    assert isinstance(r, engine["UnresolvedResult"]) and "does not exist in America/New_York" in r.reason


def test_planetary_day_begins_at_sunrise_in_the_engine_and_the_cited_text(engine):
    skip_without_corpus()
    text = corpus_file("pn4/pn4_complete/persian_nativities_iv.md").read_text(encoding="utf-8")
    assert "starting with the Sun at sunrise on Sunday" in text
    assert "before the week begins again at sunrise on Sunday" in text
    lat, lon = FLORENCE
    rise = engine["_find_sun_event"](engine["civil_to_jd"](2000, 6, 21, 0.0), lat, lon, True)
    before = engine["calculate_chronocrats"](rise - SECOND, lat, lon, 4, lon / 15.0)
    after = engine["calculate_chronocrats"](rise + SECOND, lat, lon, 4, lon / 15.0)
    assert (before["Day Lord"], before["Hour Lord"]) == ("Mars", "Venus")        # Tuesday's night, hour 12
    assert (after["Day Lord"], after["Hour Lord"]) == ("Mercury", "Mercury")     # Wednesday, day hour 1


def test_ephemeris_edges_render_chart_and_timing():
    for date, target in (("2999-01-01", "3000-09-20"), ("3000-09-20", "3000-09-20")):
        for page in ("chart", "timing"):
            at = _app(date, (12, 0), page, _target_mode="Date", _target_date=target)
            assert "outside it" not in _sidebar_text(at)
    at = _app("3000-09-21", (12, 0), "chart")
    assert "covers 3000 BC to 3000-09-20" in _sidebar_text(at)


def test_manual_offset_labels_for_fractional_offsets():
    for offset, label in ((5.75, "UTC+05:45"), (5.5, "UTC+05:30"), (-0.5, "UTC-00:30")):
        at = _app("1982-06-01", (12, 0), "chart", standard=MANUAL, offset=offset)
        assert label in _sidebar_text(at), (offset, _sidebar_text(at))
