"""The chart's star cells: which of Sahl's stars stand on an axis or with a planet.

A star's longitude only answers to a degree of the ecliptic. So at the Ascendant and the
Midheaven a star is in the cell when it crosses that axis within four minutes of the chart, and
with a planet when it lies within one degree across the sky, both latitudes counted. Both numbers
are this app's readings, no text's. The revolution's terminal point and degree of the distribution
neither rise nor carry a star, so those two alone go by longitude, and their rows say so.

The worked example is Lesson 6's own (its star table and its Fig. 4, whose stamp gives the clock,
the zone and the place), not a person's. Every other chart here is invented.
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import math
from pathlib import Path

import pytest
import streamlit

import ephemeris
from conftest import assert_no_exception, make_app

# Fig. 4's stamp: 93w15 49, 44n58 48, and Central Daylight is five hours behind UT.
LESSON_PLACE = (44 + 58 / 60 + 48 / 3600, -(93 + 15 / 60 + 49 / 3600))
LESSON_CLOCK = dt.datetime(2019, 6, 30, 16, 46, 47)
ASCENDANT_AT_DENEBOLA = dt.datetime(2019, 6, 30, 16, 56, 29)    # 9:42 on, the engine's Ascendant on its longitude
JD = 2451545.25
NATURE = "Nature (Rhetorius, per Dykes)"


def _chart(engine, when, place=LESSON_PLACE):
    return engine["calculate_traditional_chart"](when, *place)


def _star(engine, name, jd=JD):
    return engine["_fixed_star_sahl_places"](jd)[0][name]


def _chart_with_star_on(engine, name, axis, seconds=0.0, jd=JD, lat=40.0):
    """A full chart at jd and latitude, cast at the longitude where the star crosses the axis
    `seconds` after the chart's moment (+ after, - before)."""
    star = _star(engine, name, jd)
    goal = 0.0 if axis == "MC" else -engine["fixed_star_semi_arc"](star.declination, lat)
    armc = goal + star.right_ascension - seconds * engine["FIXED_STAR_SIDEREAL_RATE"]
    lon = (armc - engine["calculate_traditional_chart_jd"](jd, lat, 0.0)["armc"] + 180.0) % 360.0 - 180.0
    return engine["calculate_traditional_chart_jd"](jd, lat, lon)


def _chart_with(engine, jd=JD, lat=40.0, lon=10.0, **planets):
    """A full chart with chosen planets' rows moved: name=(longitude, latitude)."""
    chart = copy.deepcopy(engine["calculate_traditional_chart_jd"](jd, lat, lon))
    for name, (longitude, latitude) in planets.items():
        chart["planetary_data"][name].update(longitude=longitude, latitude=latitude)
    return chart


def _places(rows, star):
    return [r["Place"] for r in rows if r["Star"] == star]


def _root(engine, chart, jd=JD):
    out = engine["pn4_fixed_stars_in_image"](chart, jd)
    assert out["refused"] is None, out["refused"]
    return out["rows"]


def _revolution(engine, sr, year_lon=0.0, endpoint_lon=None, jd=JD):
    out = engine["pn4_fixed_stars_in_revolution"](sr, jd, year_lon, endpoint_lon)
    assert out["refused"] is None, out["refused"]
    return out["rows"]


# --- The worked example ---------------------------------------------------------------------------

@pytest.mark.parametrize("axis, clock", [("Ascendant", (11, 29, 31)), ("MC", (18, 28, 8)), ("Descendant", (1, 30, 41)),
                                         ("IC", (6, 30, 6))], ids=["rise", "culminate", "set", "anti-culminate"])
def test_the_star_table_of_the_lesson_gives_denebolas_clock_to_a_second(engine, axis, clock):
    chart = _chart(engine, LESSON_CLOCK)
    star = _star(engine, "Denebola", chart["julian_day"])
    assert star.longitude == pytest.approx(150 + 21 + 52 / 60 + 55 / 3600, abs=2 / 3600)
    assert star.latitude == pytest.approx(12 + 15 / 60 + 59 / 3600, abs=2 / 3600)
    seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, chart["armc"], chart["geo_lat"], axis)
    at_chart = 11 * 3600 + 46 * 60 + 47
    assert (at_chart + seconds) % 86400 == pytest.approx(clock[0] * 3600 + clock[1] * 60 + clock[2], abs=1.0)


def test_at_the_lessons_clock_denebola_has_risen_and_seginus_is_rising(engine):
    chart = _chart(engine, LESSON_CLOCK)
    stars, _ = engine["fixed_star_places"](chart["julian_day"])
    seconds = {r["star"].name: r["seconds"] for r in engine["fixed_star_axis_lists"](stars, engine["fixed_star_frame"](chart))["Ascendant"]["crossing"]}
    assert seconds["Seginus"] == pytest.approx(-(2 * 60 + 24), abs=1.0)
    denebola = _star(engine, "Denebola", chart["julian_day"])
    assert engine["fixed_star_crossing_seconds"](denebola.right_ascension, denebola.declination, chart["armc"], chart["geo_lat"],
                                                 "Ascendant") == pytest.approx(-(17 * 60 + 15), abs=1.0)


def test_at_the_lessons_clock_no_star_of_sahls_stands_at_the_ascendant(engine):
    """The cell is empty, and Rigel, whose longitude lies within a degree of the Midheaven's, is not
    in it. Acamar crosses the Descendant with the chart, on the page's list: no cell holds that axis."""
    chart = _chart(engine, LESSON_CLOCK)
    assert _root(engine, chart, chart["julian_day"]) == []
    rigel = _star(engine, "Rigel", chart["julian_day"])
    assert abs(engine["fixed_star_longitude_offset"](rigel.longitude, chart["mc"])) <= 1.0, "the premise"
    stars, _ = engine["fixed_star_places"](chart["julian_day"])
    lists = engine["fixed_star_axis_lists"]([s for s in stars if s.nature is not None], engine["fixed_star_frame"](chart))
    assert [r["star"].name for r in lists["Descendant"]["crossing"]] == ["Acamar"], "the premise"


def test_when_the_ascendant_comes_to_denebolas_longitude_she_is_still_not_on_it(engine):
    """The lesson's argument: the same longitude as the Ascendant, and long since risen. What the
    cell holds then is what is crossing the Midheaven."""
    chart = _chart(engine, ASCENDANT_AT_DENEBOLA)
    assert chart["ascendant"] == pytest.approx(_star(engine, "Denebola", chart["julian_day"]).longitude, abs=0.01), "the premise"
    rows = _root(engine, chart, chart["julian_day"])
    assert [(r["Star"], r["Place"], r["Crossing"], r["Separation"]) for r in rows] == [
        ("Rigel", "on the Midheaven", "−1:52", "—"), ("Capella", "on the Midheaven", "+0:46", "—")]


# --- The test at an axis --------------------------------------------------------------------------

@pytest.mark.parametrize("name, lat", [("Spica", 40.0), ("Sirius", -33.0), ("Regulus", 0.0), ("Capella", 40.0)])
@pytest.mark.parametrize("axis, place", [("Ascendant", "on the Ascendant"), ("MC", "on the Midheaven")])
def test_a_star_is_on_an_axis_within_the_window_and_not_past_it(engine, name, lat, axis, place):
    for seconds, inside in ((0.0, True), (-239.9, True), (239.9, True), (-240.1, False), (240.1, False), (600.0, False)):
        chart = _chart_with_star_on(engine, name, axis, seconds, lat=lat)
        rows = [r for r in _root(engine, chart) if r["Star"] == name and r["Place"] == place]
        assert bool(rows) is inside, (name, axis, seconds)
        if inside:
            assert rows[0]["Crossing"] == engine["fixed_star_crossing_text"](seconds, axis)
            assert rows[0]["Separation"] == "—"


def test_the_window_is_four_minutes_and_its_edges_stand_inclusive_on_unrounded_values(engine, monkeypatch):
    assert engine["FIXED_STAR_CROSSING_WINDOW"] == 240.0
    chart = _chart_with(engine)
    edge = 240.0
    for seconds, inside in ((edge, True), (-edge, True), (math.nextafter(edge, 1e9), False), (-math.nextafter(edge, 1e9), False),
                            (240.4, False)):             # 240.4 prints as 4:00, and it is past the window
        monkeypatch.setitem(engine, "fixed_star_crossing_seconds", lambda *a, seconds=seconds: seconds)
        rows = [r for r in _root(engine, chart) if r["Place"] == "on the Ascendant"]
        assert len(rows) == (28 if inside else 0), seconds


def test_a_star_that_never_crosses_the_horizon_here_is_not_on_the_ascendant_at_any_longitude(engine):
    """Vega never sets at 60 north. Its longitude on the Ascendant gets it no row; the meridian
    every star crosses, so it can still stand on the Midheaven."""
    vega = _star(engine, "Vega")
    assert engine["fixed_star_semi_arc"](vega.declination, 60.0) is None, "the premise"
    chart = _chart_with(engine, lat=60.0)
    chart["ascendant"] = vega.longitude
    assert "on the Ascendant" not in _places(_root(engine, chart), "Vega")
    assert _places(_root(engine, _chart_with_star_on(engine, "Vega", "MC", lat=60.0)), "Vega") == ["on the Midheaven"]


def test_a_longitude_on_an_axis_alone_is_no_hit(engine):
    """The star rising, with the axis's longitude moved off it, stays in; and the axis moved onto
    the longitude of a star not crossing stays out. Only the crossing reads."""
    chart = _chart_with_star_on(engine, "Spica", "Ascendant")
    moved = copy.deepcopy(chart)
    moved["ascendant"] = (chart["ascendant"] + 90.0) % 360.0
    assert "on the Ascendant" in _places(_root(engine, moved), "Spica")
    away = _chart_with_star_on(engine, "Spica", "Ascendant", 3600.0)
    away["ascendant"] = _star(engine, "Spica").longitude
    away["mc"] = _star(engine, "Spica").longitude
    assert _places(_root(engine, away), "Spica") == []


def test_the_cells_take_the_ascendant_and_the_midheaven_only(engine):
    for axis in ("Descendant", "IC"):
        star = _star(engine, "Spica")
        semi_arc = engine["fixed_star_semi_arc"](star.declination, 40.0)
        goal = semi_arc if axis == "Descendant" else 180.0
        lon = (goal + star.right_ascension - engine["calculate_traditional_chart_jd"](JD, 40.0, 0.0)["armc"] + 180.0) % 360.0 - 180.0
        chart = engine["calculate_traditional_chart_jd"](JD, 40.0, lon)
        frame_seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, chart["armc"], 40.0, axis)
        assert abs(frame_seconds) < 1.0, "the premise"
        assert _places(_root(engine, chart), "Spica") == []


# --- The test with a planet -----------------------------------------------------------------------

def test_a_planet_at_the_stars_own_place_is_with_it(engine):
    """Spica lies two degrees south: with the planet there too, both latitudes counted, it is with it."""
    spica = _star(engine, "Spica")
    assert spica.latitude < -2.0, "the premise"
    rows = _root(engine, _chart_with(engine, Sun=(spica.longitude, spica.latitude)))
    row = next(r for r in rows if r["Star"] == "Spica" and r["Place"] == "with the Sun")
    assert (row["Crossing"], row["Separation"]) == ("—", "0.00 deg")


def test_a_planet_on_the_stars_longitude_and_not_its_latitude_is_not_with_it(engine):
    spica = _star(engine, "Spica")
    assert "with the Sun" not in _places(_root(engine, _chart_with(engine, Sun=(spica.longitude, 0.0))), "Spica")
    assert "with the Moon" not in _places(_root(engine, _chart_with(engine, Moon=(spica.longitude, spica.latitude + 1.5))), "Spica")


@pytest.mark.parametrize("offset, inside", [(0.99, True), (-0.99, True), (1.01, False), (-1.01, False)])
def test_the_one_degree_counts_across_the_latitude(engine, offset, inside):
    regulus = _star(engine, "Regulus")
    rows = _root(engine, _chart_with(engine, Moon=(regulus.longitude, regulus.latitude + offset)))
    assert ("with the Moon" in _places(rows, "Regulus")) is inside


def test_the_one_degree_is_across_the_sky_not_of_longitude(engine):
    """Vega lies over sixty degrees north, where two degrees of longitude are under one across the sky."""
    vega = _star(engine, "Vega")
    assert vega.latitude > 60.0, "the premise"
    far = _root(engine, _chart_with(engine, Moon=((vega.longitude + 2.0) % 360.0, vega.latitude)))
    assert "with the Moon" in _places(far, "Vega")
    near = _root(engine, _chart_with(engine, Moon=((vega.longitude + 2.5) % 360.0, vega.latitude)))
    assert "with the Moon" not in _places(near, "Vega")


def test_the_edge_of_the_degree_stands_inclusive_on_unrounded_values(engine, monkeypatch):
    assert engine["FIXED_STAR_PLANET_SEPARATION"] == 1.0
    chart = _chart_with(engine)
    for apart, count in ((1.0, 2 * 28), (math.nextafter(1.0, 2.0), 0), (1.004, 0)):   # 1.004 prints as 1.00
        monkeypatch.setitem(engine, "fixed_star_separation", lambda *a, apart=apart: apart)
        rows = [r for r in _root(engine, chart) if r["Place"] in ("with the Sun", "with the Moon")]
        assert len(rows) == count, apart


def test_no_side_of_the_ecliptic_is_asked(engine):
    """Regulus north, the planet south of the ecliptic, within the degree: with it."""
    regulus = _star(engine, "Regulus")
    assert regulus.latitude > 0.3, "the premise"
    rows = _root(engine, _chart_with(engine, Moon=(regulus.longitude, -0.3)))
    assert "with the Moon" in _places(rows, "Regulus")


def test_the_separation_is_the_great_circle(engine):
    apart = engine["fixed_star_separation"]
    assert apart(10.0, 0.0, 11.0, 0.0) == pytest.approx(1.0, abs=1e-12)
    assert apart(10.0, 1.0, 10.0, -1.0) == pytest.approx(2.0, abs=1e-12)
    assert apart(359.5, 0.0, 0.5, 0.0) == pytest.approx(1.0, abs=1e-12)
    assert apart(10.0, 90.0, 200.0, 90.0) == pytest.approx(0.0, abs=1e-12)
    assert apart(10.0, 0.0, 190.0, 0.0) == pytest.approx(180.0, abs=1e-12)
    a, b = (123.0, 40.0), (123.7, 40.5)
    by_the_cosine = math.degrees(math.acos(
        math.sin(math.radians(a[1])) * math.sin(math.radians(b[1]))
        + math.cos(math.radians(a[1])) * math.cos(math.radians(b[1])) * math.cos(math.radians(a[0] - b[0]))))
    assert apart(*a, *b) == pytest.approx(by_the_cosine, abs=1e-9)
    assert apart(10.0, 20.0, 10.0, 20.0 + 1e-7) == pytest.approx(1e-7, rel=1e-5)         # small, and its digits kept


def test_a_real_moon_beside_spica_and_real_suns_at_the_stars_longitudes(engine):
    """Three real charts, on the chart's own places: the Moon near occulting Spica (late 2024) is
    with it; the Sun on Spica's longitude is not, two degrees above it; on Regulus's, half a degree
    from it, he is."""
    jd_moon = engine["civil_to_jd"](2024, 12, 24, 20.0)
    moon = next(r for r in _root(engine, engine["calculate_traditional_chart_jd"](jd_moon, 40.0, 10.0), jd_moon)
                if r["Star"] == "Spica" and r["Place"] == "with the Moon")
    assert moon["Separation"] == "0.23 deg"
    jd_spica = engine["civil_to_jd"](2024, 10, 17, 1.85285)
    chart = engine["calculate_traditional_chart_jd"](jd_spica, 40.0, 10.0)
    assert chart["planetary_data"]["Sun"]["longitude"] == pytest.approx(_star(engine, "Spica", jd_spica).longitude, abs=0.01), "the premise"
    assert _places(_root(engine, chart, jd_spica), "Spica") == []
    jd_regulus = engine["civil_to_jd"](2024, 8, 22, 19.14797)
    chart = engine["calculate_traditional_chart_jd"](jd_regulus, 40.0, 10.0)
    assert chart["planetary_data"]["Sun"]["longitude"] == pytest.approx(_star(engine, "Regulus", jd_regulus).longitude, abs=0.01), "the premise"
    assert "with the Sun" in _places(_root(engine, chart, jd_regulus), "Regulus")


def test_the_five_planets_stand_in_the_cell_only_from_a_stake(engine):
    """I.6, 7's seven-in-the-stakes: the luminaries always, the five by their whole-sign place."""
    chart = _chart_with(engine)
    regulus = _star(engine, "Regulus")
    chart["ascendant"] = (regulus.longitude // 30 * 30 + 15.0) % 360.0
    chart["planetary_data"]["Mars"].update(longitude=regulus.longitude, latitude=regulus.latitude)
    assert "with Mars, in a stake (whole-sign place 1)" in _places(_root(engine, chart), "Regulus")
    chart["ascendant"] = (chart["ascendant"] + 30.0) % 360.0
    assert not [p for p in _places(_root(engine, chart), "Regulus") if p.startswith("with Mars")]


# --- The revolution -------------------------------------------------------------------------------

@pytest.mark.parametrize("axis, place", [("Ascendant", "on the Ascendant of the year"), ("MC", "on the tenth from it")])
def test_the_revolutions_axes_take_the_crossing_on_its_own_frame(engine, axis, place):
    for seconds, inside in ((30.0, True), (-239.9, True), (240.1, False)):
        sr = _chart_with_star_on(engine, "Spica", axis, seconds)
        rows = [r for r in _revolution(engine, sr) if r["Star"] == "Spica" and r["Place"] == place]
        assert bool(rows) is inside, seconds
        if inside:
            assert rows[0]["Crossing"] == engine["fixed_star_crossing_text"](seconds, axis)


@pytest.mark.parametrize("point", ["terminal", "distribution"])
def test_the_two_points_go_by_longitude_with_a_label_and_latitude_ignored(engine, point):
    """Vega, sixty degrees off the ecliptic and crossing nothing, stands at either point by its
    longitude: to one degree, and the row says it is by longitude."""
    sr = _chart_with(engine)
    vega = _star(engine, "Vega")
    label = {"terminal": "the degree of the terminal point, by longitude", "distribution": "the degree of the distribution, by longitude"}[point]

    def rows_at(shift):
        at = (vega.longitude + shift) % 360.0
        args = (at, 137.0) if point == "terminal" else (137.0, at)
        return [r for r in _revolution(engine, sr, *args) if r["Star"] == "Vega" and r["Place"] == label]
    for shift in (0.0, 0.99, -0.99):
        rows = rows_at(shift)
        assert rows and rows[0]["Crossing"] == "—" and rows[0]["Separation"] == f"{abs(shift):.2f} deg of longitude", shift
    assert not rows_at(1.01) and not rows_at(-1.01)
    assert engine["FIXED_STAR_ORB"] == 1.0


def test_only_the_two_points_rows_say_by_longitude(engine):
    regulus = _star(engine, "Regulus")
    sr = copy.deepcopy(_chart_with_star_on(engine, "Regulus", "MC"))
    sr["planetary_data"]["Sun"].update(longitude=regulus.longitude, latitude=regulus.latitude)
    rows = _revolution(engine, sr, regulus.longitude, regulus.longitude)
    by_row = {r["Place"]: r for r in rows if r["Star"] == "Regulus"}
    assert {"on the tenth from it", "with the Sun of the revolution", "the degree of the terminal point, by longitude",
            "the degree of the distribution, by longitude"} <= set(by_row)
    for place, row in by_row.items():
        assert ("by longitude" in place) is (place.startswith("the degree of the")), place
        assert (row["Crossing"] != "—") is place.startswith("on the"), place
        assert (row["Separation"] != "—") is (not place.startswith("on the")), place


def test_no_distribution_no_distribution_row(engine):
    sr = _chart_with(engine)
    vega = _star(engine, "Vega")
    rows = _revolution(engine, sr, vega.longitude, None)
    assert not [r for r in rows if "distribution" in r["Place"]]


def test_a_points_lord_is_a_planet_and_takes_the_planets_test(engine):
    """The terminal point in Leo: its lord the Sun, in the revolution. The Sun on Spica's longitude
    alone is nothing, whichever point it rules; at Spica's place it is with it."""
    spica = _star(engine, "Spica")
    terminal_in_leo = 125.0
    label = "with Sun, lord of the degree of the terminal point"
    assert label not in _places(_revolution(engine, _chart_with(engine, Sun=(spica.longitude, 0.0)), terminal_in_leo), "Spica")
    rows = _revolution(engine, _chart_with(engine, Sun=(spica.longitude, spica.latitude)), terminal_in_leo)
    assert label in _places(rows, "Spica") and "with the Sun of the revolution" in _places(rows, "Spica")


def test_the_axes_lords_are_named_as_their_axes_are(engine):
    regulus = _star(engine, "Regulus")
    sr = _chart_with(engine)
    sr["ascendant"], sr["mc"] = 5.0, 275.0                 # Aries and Capricorn: Mars and Saturn rule them
    sr["planetary_data"]["Mars"].update(longitude=regulus.longitude, latitude=regulus.latitude)
    sr["planetary_data"]["Saturn"].update(longitude=regulus.longitude, latitude=regulus.latitude)
    places = _places(_revolution(engine, sr, 200.0), "Regulus")
    assert "with Mars, lord of the Ascendant of the year" in places
    assert "with Saturn, lord of the tenth from it" in places


# --- Which stars ----------------------------------------------------------------------------------

def test_the_cells_read_sahls_28_by_name_and_never_the_catalogue_around_them(engine, monkeypatch):
    """Growing the Full Catalogue can change nothing here: the cells ask the library for these 28
    names and no other, and never open the rows the page's lists read."""
    import swisseph
    assert engine["_fixed_star_catalogue_ready"]() is True
    sr = _chart_with_star_on(engine, "Spica", "MC")
    names = {name for name, _nature in engine["SAHL_FIXED_STARS"]}
    assert len(names) == 28
    terminal_point = _star(engine, "Vega").longitude
    before = (_root(engine, sr), _revolution(engine, sr, terminal_point, 200.0))
    assert before[0] and before[1], "the premise: rows to hold still"
    asked = []
    real = swisseph.fixstar2_ut

    def spy(name, *args, **kwargs):
        asked.append(name)
        return real(name, *args, **kwargs)

    def closed(*_args, **_kwargs):
        raise AssertionError("the cells opened the whole catalogue")
    monkeypatch.setattr(swisseph, "fixstar2_ut", spy)
    monkeypatch.setitem(engine, "_fixed_star_catalogue_read", closed)
    monkeypatch.setitem(engine, "_fixed_star_places_read", closed)
    monkeypatch.setitem(engine, "fixed_star_places", closed)
    monkeypatch.setitem(engine, "_fixed_star_rows_read", closed)
    after = (_root(engine, sr), _revolution(engine, sr, terminal_point, 200.0))
    assert after == before
    assert set(asked) == names


def test_no_cell_holds_a_star_of_the_catalogue_outside_sahls_list(engine):
    """Seginus rises with the lesson's chart inside the window: on the page's list and in no cell.
    Over a sweep of the sky every row of the cell names one of Sahl's stars."""
    chart = _chart(engine, LESSON_CLOCK)
    stars, _ = engine["fixed_star_places"](chart["julian_day"])
    assert "Seginus" in [r["star"].name for r in engine["fixed_star_axis_lists"](stars, engine["fixed_star_frame"](chart))["Ascendant"]["crossing"]]
    natures = dict(engine["SAHL_FIXED_STARS"])
    names = {engine["FIXED_STAR_PAGE_NAME"].get(n, n) for n in natures}
    seen = set()
    for year in (1240, 2019, 2030):
        jd = engine["civil_to_jd"](year, 3, 21, 6.0)
        for lon in range(-180, 180, 7):
            rows = engine["pn4_fixed_stars_in_image"](engine["calculate_traditional_chart_jd"](jd, 40.0, float(lon)), jd)["rows"]
            seen |= {r["Star"] for r in rows}
    assert seen <= names and len(seen) >= 10, seen
    row = _root(engine, _chart_with_star_on(engine, "Zuben Eschamali", "MC"))[0]
    assert row["Star"] == "Zuben Eschemali" and row[NATURE] == "Jupiter-Mercury"            # the book's spelling, as before


def test_a_star_unread_in_either_frame_is_named_and_gets_no_row(engine, monkeypatch):
    """The ecliptic place read and the equatorial not, then the other way: one star not placed,
    named in the table's own sentence, and the other 27 read."""
    import swisseph
    real = swisseph.fixstar2_ut
    chart = _chart_with_star_on(engine, "Algol", "MC")
    assert "on the Midheaven" in _places(_root(engine, chart), "Algol"), "the premise"
    for unread_when in (lambda flags: flags & swisseph.FLG_EQUATORIAL, lambda flags: not flags & swisseph.FLG_EQUATORIAL):
        def flaky(name, jd, flags, unread_when=unread_when):
            if name == "Algol" and unread_when(flags):
                raise OSError("not read in this frame (the test's)")
            return real(name, jd, flags)
        monkeypatch.setattr(swisseph, "fixstar2_ut", flaky)
        places, missing = engine["_fixed_star_sahl_places"](JD)
        assert len(places) == 27 and list(missing) == ["Algol"]
        out = engine["pn4_fixed_stars_in_image"](chart, JD)
        assert out["refused"] is None and "Algol" in out["missing"] and _places(out["rows"], "Algol") == []
        monkeypatch.undo()


# --- A chart with no frame ------------------------------------------------------------------------

FRAME_KEYS = ("ascendant", "descendant", "mc", "ic", "armc", "geo_lat", "obliquity", "julian_day")


@pytest.mark.parametrize("key", FRAME_KEYS)
def test_a_chart_without_a_part_of_its_frame_is_refused_and_nothing_falls_back(engine, key):
    """The star is on the Ascendant and at its longitude; the planet at its place. With a key of
    the frame gone or empty, no row at all, and the table says why."""
    regulus = _star(engine, "Regulus")
    full = _chart_with_star_on(engine, "Regulus", "Ascendant")
    full["ascendant"] = full["mc"] = regulus.longitude
    full["planetary_data"]["Sun"].update(longitude=regulus.longitude, latitude=regulus.latitude)
    assert _root(engine, full), "the premise"
    for thin in ({k: v for k, v in full.items() if k != key}, {**full, key: None}):
        for out in (engine["pn4_fixed_stars_in_image"](thin, JD),
                    engine["pn4_fixed_stars_in_revolution"](thin, JD, regulus.longitude, regulus.longitude)):
            assert out["rows"] == [] and out["refused"] == engine["FIXED_STAR_NO_FRAME"], key


@pytest.mark.parametrize("planet", ["Sun", "Moon", "Mars"])
def test_a_planet_without_a_latitude_is_refused_and_nothing_falls_back(engine, planet):
    regulus = _star(engine, "Regulus")
    chart = _chart_with(engine, **{planet: (regulus.longitude, regulus.latitude)})
    del chart["planetary_data"][planet]["latitude"]
    for out in (engine["pn4_fixed_stars_in_image"](chart, JD), engine["pn4_fixed_stars_in_revolution"](chart, JD, 0.0, None)):
        assert out["rows"] == [] and out["refused"] == engine["FIXED_STAR_NO_FRAME"], planet


@pytest.mark.parametrize("planet", ["Sun", "Moon"])
def test_a_chart_without_a_luminary_is_refused(engine, planet):
    chart = _chart_with(engine)
    del chart["planetary_data"][planet]
    assert engine["pn4_fixed_stars_in_image"](chart, JD)["refused"] == engine["FIXED_STAR_NO_FRAME"]


def test_the_page_says_the_revolutions_refusal_and_no_none_sentence_over_it(monkeypatch, engine):
    """The root's table computed and the revolution's refused: the page says not computed, and does
    not say that no star stands there."""
    refused = {"rows": [], "refused": engine["FIXED_STAR_NO_FRAME"], "missing": ""}
    monkeypatch.setitem(engine, "pn4_fixed_stars_in_revolution", lambda *_a, **_k: refused)
    at = make_app(page="timing", timeout=300).run()
    assert_no_exception(at, "the Timing page")
    assert f"Not computed: {engine['FIXED_STAR_NO_FRAME']}." in [w.value for w in at.main.warning]
    assert not [m for m in at.main.markdown if str(m.value).startswith("None on the year's Ascendant")]


# --- A chart whose status withholds its Ascendant ---------------------------------------------------

WITHHELD = ("tangency", "coincidence", "unresolved")


def _at_status(monkeypatch, status):
    """Every chart cast from here on stands at `status`, the rest of it as cast."""
    monkeypatch.setattr(ephemeris, "division_status", lambda *_args: status)


@pytest.mark.parametrize("status", WITHHELD)
def test_a_withheld_ascendant_has_no_row_though_a_star_crosses_it(engine, monkeypatch, status):
    assert "on the Ascendant" in _places(_root(engine, _chart_with_star_on(engine, "Spica", "Ascendant")), "Spica")
    _at_status(monkeypatch, status)
    chart = _chart_with_star_on(engine, "Spica", "Ascendant")
    assert chart["ascendant"] is None and chart["division_status"] == status
    assert "on the Ascendant" not in _places(_root(engine, chart), "Spica")


@pytest.mark.parametrize("status", WITHHELD)
def test_a_withheld_ascendant_leaves_the_midheaven_and_the_luminaries(engine, monkeypatch, status):
    _at_status(monkeypatch, status)
    assert "on the Midheaven" in _places(_root(engine, _chart_with_star_on(engine, "Spica", "MC")), "Spica")
    spica = _star(engine, "Spica")
    place = (spica.longitude, spica.latitude)
    held = _places(_root(engine, _chart_with(engine, Sun=place, Moon=place)), "Spica")
    assert "with the Sun" in held and "with the Moon" in held


@pytest.mark.parametrize("status", WITHHELD)
def test_a_withheld_ascendant_gives_the_five_planets_no_stake(engine, monkeypatch, status):
    """Every one of the five at the star's own place: at a defined status those in a stake have
    their rows; at a withheld one none has."""
    regulus = _star(engine, "Regulus")
    place = (regulus.longitude, regulus.latitude)
    five = {planet: place for planet in ("Saturn", "Jupiter", "Mars", "Venus", "Mercury")}
    standing = _chart_with(engine, **five)
    standing["ascendant"] = regulus.longitude
    assert [p for p in _places(_root(engine, standing), "Regulus") if "in a stake" in p]
    _at_status(monkeypatch, status)
    # Whatever a stake might be counted from, here each of the five would be in one.
    monkeypatch.setitem(engine, "get_wsh_house", lambda *_args: 1)
    assert not [p for p in _places(_root(engine, _chart_with(engine, **five)), "Regulus") if "stake" in p]


@pytest.mark.parametrize("status", WITHHELD)
def test_a_status_is_not_a_thin_chart_and_a_thin_chart_still_refuses(engine, monkeypatch, status):
    """No status, or a defined one, and no Ascendant: refused. A withheld status with some other
    part of the frame gone: refused."""
    thin = _chart_with(engine)
    thin["ascendant"] = None
    thin.pop("division_status")
    assert engine["pn4_fixed_stars_in_image"](thin, JD)["refused"] == engine["FIXED_STAR_NO_FRAME"]
    thin["division_status"] = "defined"
    assert engine["pn4_fixed_stars_in_image"](thin, JD)["refused"] == engine["FIXED_STAR_NO_FRAME"]
    _at_status(monkeypatch, status)
    for key in ("mc", "ic", "armc", "geo_lat", "obliquity", "julian_day"):
        chart = _chart_with(engine)
        chart[key] = None
        assert engine["pn4_fixed_stars_in_image"](chart, JD)["refused"] == engine["FIXED_STAR_NO_FRAME"], key
        assert engine["pn4_fixed_stars_in_revolution"](chart, JD, 0.0, None)["refused"] == engine["FIXED_STAR_NO_FRAME"], key


def test_at_the_pole_the_ascendants_row_and_the_stakes_stay(engine, monkeypatch):
    _at_status(monkeypatch, "pole")
    chart = _chart_with_star_on(engine, "Spica", "Ascendant")
    assert chart["ascendant"] is not None
    assert "on the Ascendant" in _places(_root(engine, chart), "Spica")
    regulus = _star(engine, "Regulus")
    chart = _chart_with(engine, Mars=(regulus.longitude, regulus.latitude))
    chart["ascendant"] = regulus.longitude
    assert "with Mars, in a stake (whole-sign place 1)" in _places(_root(engine, chart), "Regulus")


def test_a_chart_truly_at_the_pole_reads_its_tables(engine):
    chart = engine["calculate_traditional_chart_jd"](JD, 90.0, 10.0)
    assert chart["division_status"] == "pole" and chart["ascendant"] is not None
    assert engine["pn4_fixed_stars_in_image"](chart, JD)["refused"] is None
    assert engine["pn4_fixed_stars_in_revolution"](chart, JD, 0.0, 30.0)["refused"] is None


@pytest.mark.parametrize("status", WITHHELD)
def test_a_withheld_revolution_loses_all_counted_from_its_ascendant(engine, monkeypatch, status):
    """A star on the year's Ascendant, the lord of that Ascendant at the star's place, and the
    terminal point and the distribution at its longitude: at a defined status each has its row, at
    a withheld one none has; the tenth and the luminaries stand."""
    spica = _star(engine, "Spica")
    place = (spica.longitude, spica.latitude)
    # Spica's own sign rising, so the lord of the Ascendant is a planet to set on it.
    cast = _chart_with_star_on(engine, "Spica", "Ascendant")
    lord = engine["SIGN_TO_DOMICILE"][engine["get_zodiac_sign"](cast["ascendant"])]

    def rows(sr):
        sr = copy.deepcopy(sr)
        sr["planetary_data"][lord].update(longitude=place[0], latitude=place[1])
        return _places(_revolution(engine, sr, spica.longitude, spica.longitude), "Spica")

    standing = rows(cast)
    for label in ("on the Ascendant of the year", f"with {lord}, lord of the Ascendant of the year",
                  "the degree of the terminal point, by longitude", "the degree of the distribution, by longitude"):
        assert label in standing, label
    _at_status(monkeypatch, status)
    held = rows(_chart_with_star_on(engine, "Spica", "Ascendant"))
    for word in ("Ascendant", "terminal point", "distribution"):
        assert not [p for p in held if word in p], word
    assert "on the tenth from it" in _places(_revolution(engine, _chart_with_star_on(engine, "Spica", "MC")), "Spica")
    sun_and_moon = _chart_with(engine, Sun=place, Moon=place)
    both = _places(_revolution(engine, sun_and_moon), "Spica")
    assert "with the Sun of the revolution" in both and "with the Moon of the revolution" in both


def test_a_root_withholding_its_own_takes_the_two_points_and_not_the_years_ascendant(engine):
    """No terminal point to read, the root's Ascendant withheld; the revolution stands by its own."""
    sr = _chart_with_star_on(engine, "Spica", "Ascendant")
    held = _places(_revolution(engine, sr, None, _star(engine, "Spica").longitude), "Spica")
    assert "on the Ascendant of the year" in held
    assert not [p for p in held if "terminal point" in p or "distribution" in p]


def test_at_a_withheld_status_the_bundle_still_refuses_whole_and_at_the_pole_it_reads(engine, monkeypatch):
    """The pages built on the bundle never reach the tables at those statuses; at the pole they do."""
    birth, target = dt.date(1985, 3, 14), dt.date(2000, 4, 20)
    pole = engine["calculate_traditional_chart"](dt.datetime(1985, 3, 14, 12), 90.0, 10.0)
    assert engine["pn4_timing_bundle"](pole, 90.0, 10.0, birth, target, None)["fixed_stars"]["refused"] is None
    _at_status(monkeypatch, "tangency")
    chart = engine["calculate_traditional_chart"](dt.datetime(1985, 3, 14, 12), 70.0, 10.0)
    assert "fixed_stars" not in engine["pn4_timing_bundle"](chart, 70.0, 10.0, birth, target, None)


# --- The planets' test and the bundle's frame, each directly ----------------------------------------

@pytest.mark.parametrize("planet", ["Saturn", "Jupiter", "Mars", "Venus", "Mercury"])
def test_a_planet_in_a_stake_at_the_stars_longitude_past_a_degree_across_has_no_row(engine, planet):
    regulus = _star(engine, "Regulus")
    chart = _chart_with(engine, **{planet: (regulus.longitude, regulus.latitude + 1.2)})
    chart["ascendant"] = regulus.longitude
    assert not [p for p in _places(_root(engine, chart), "Regulus") if p.startswith(f"with {planet}")]
    chart["planetary_data"][planet]["latitude"] = regulus.latitude + 0.8
    assert f"with {planet}, in a stake (whole-sign place 1)" in _places(_root(engine, chart), "Regulus")


@pytest.mark.parametrize("axis, label", [("Ascendant", "on the Ascendant of the year"), ("MC", "on the tenth from it")])
def test_the_bundle_reads_the_revolutions_axes_on_its_own_frame(engine, axis, label):
    """A place chosen so a star crosses the axis at the revolution's own moment. The row comes from
    the bundle, and the same revolution on the root's sidereal time has none."""
    lat, when = 40.0, dt.datetime(1985, 3, 14, 12)
    natal = engine["calculate_traditional_chart"](when, lat, 0.0)
    jd_sr = engine["pn4_solar_revolution_jd"](natal["julian_day"], natal["planetary_data"]["Sun"]["longitude"], 15)
    on_it = _chart_with_star_on(engine, "Spica", axis, jd=jd_sr, lat=lat)
    lon = (on_it["armc"] - engine["calculate_traditional_chart_jd"](jd_sr, lat, 0.0)["armc"] + 180.0) % 360.0 - 180.0
    chart = engine["calculate_traditional_chart"](when, lat, lon)
    bundle = engine["pn4_timing_bundle"](chart, lat, lon, when.date(), dt.date(2000, 4, 20), None)
    assert label in _places(bundle["fixed_stars_revolution"]["rows"], "Spica")
    assert abs(chart["armc"] - on_it["armc"]) > 2.0     # the root's sidereal time is another
    on_the_root = {**on_it, "armc": chart["armc"]}
    assert label not in _places(_revolution(engine, on_the_root, jd=jd_sr), "Spica")


# --- The words of the rows, the reading and the refusal ---------------------------------------------

def test_a_by_longitude_measure_says_so_and_a_planets_does_not(engine):
    spica = _star(engine, "Spica")
    rows = _revolution(engine, _chart_with(engine, Moon=(spica.longitude + 0.23, spica.latitude)), spica.longitude + 0.49)
    measures = {r["Place"]: r["Separation"] for r in rows if r["Star"] == "Spica"}
    assert measures["the degree of the terminal point, by longitude"] == "0.49 deg of longitude"
    assert measures["with the Moon of the revolution"].endswith(" deg")


def test_the_no_frame_refusal_says_not_computed_once(engine):
    assert "computed" not in engine["FIXED_STAR_NO_FRAME"]
    assert engine["FIXED_STAR_NO_FRAME"].endswith("or no latitude for a planet")


def _app_text(name):
    tree = ast.parse((Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", None) == name)


def test_the_reading_is_short_sentences_each_number_the_apps_own():
    reading = _app_text("FIXED_STARS_READING")
    tests = reading.split("no stars of its own. ")[1]
    assert ";" not in tests
    sentences = tests.split(". ")
    assert sentences[0].startswith("This app reads") and "four minutes" in sentences[0]
    assert sentences[1].startswith("It reads") and sentences[1].count("one degree") == 2
    assert sentences[2].startswith('The planets "in the stakes"')


# --- The long nature on the page --------------------------------------------------------------------

def _star_rows_on_the_page(engine, monkeypatch, star, place, measure, beside=None, longitude="0° Ari 00'"):
    natures = dict(engine["SAHL_FIXED_STARS"])
    nature = natures[star]
    row = {"Star": star, "Longitude": longitude, NATURE: nature, "Place": place, "Crossing": "—", "Separation": measure}
    rows = [row] + ([{**row, "Star": beside, NATURE: natures[beside]}] if beside else [])
    table = {"rows": rows, "refused": None, "missing": ""}
    monkeypatch.setitem(engine, "pn4_fixed_stars_in_revolution", lambda *_a, **_k: table)
    drawn = streamlit.dataframe
    heights = {}

    def dataframe(data, *args, **kwargs):
        heights[tuple(data.columns) if hasattr(data, "columns") else None] = kwargs.get("height")
        return drawn(data, *args, **kwargs)
    monkeypatch.setattr(streamlit, "dataframe", dataframe)
    at = make_app(page="timing", timeout=300).run()
    assert_no_exception(at, "the Timing page")
    height = heights[tuple(row)]
    return nature, {**row, "height": height}, next(g for g in at.main.dataframe if NATURE in g.value.columns and "Place" in g.value.columns
                             and g.value["Star"].tolist() == [row_["Star"] for row_ in rows])


@pytest.mark.parametrize("star", ["Menkalinan", "Alphecca"])
def test_a_long_nature_wraps_on_the_page_and_leaves_the_measure_in_view(engine, monkeypatch, star):
    """An ordinary by-longitude row: the page's narrowest of the usual windows holds 904 px.
    The widest row is another's, below."""
    nature, row, grid = _star_rows_on_the_page(engine, monkeypatch, star, "the degree of the terminal point, by longitude",
                                               "0.49 deg of longitude")
    cell = grid.value[NATURE].iloc[0]
    assert cell.replace("\n", " ") == nature and cell.count("\n") == 2
    assert row[NATURE] == nature        # what the export prints
    assert grid.proto.row_height > 64   # Streamlit wraps only above 4rem
    assert row["height"] >= 35 + grid.proto.row_height  # the head and the whole of the tall row
    widths = [column["width"] for column in json.loads(grid.proto.columns).values() if "width" in column]
    assert len(widths) == 6
    assert sum(widths) + 2 <= 904


def test_the_widest_row_is_a_lord_s_beside_the_longest_star_name(engine, monkeypatch):
    """What the table can reach, measured: a lord's Place wraps once the row would pass the page's
    narrowest width, which holds it inside the 904 px of the narrowest usual window on a rare chart.
    Taking the wrap away moves these numbers; read that, then change them."""
    star = max((name for name, _nature in engine["SAHL_FIXED_STARS"]), key=len)
    _, _, grid = _star_rows_on_the_page(engine, monkeypatch, star, "with Mercury, lord of the degree of the terminal point",
                                        "0.49 deg of longitude", beside="Menkalinan", longitude="29° Sgr 00'")
    widths = {name: column["width"] for name, column in json.loads(grid.proto.columns).items() if "width" in column}
    assert (star, widths["Place"]) == ("Zuben Eschamali", 210)
    assert sum(widths.values()) + 2 == 844
    assert widths["Place"] > 175, "wider than the terminal point's by-longitude row"


def test_a_short_nature_keeps_the_grids_own_row(engine, monkeypatch):
    star = next(name for name, nature in engine["SAHL_FIXED_STARS"] if len(nature) <= 32)
    _, _, grid = _star_rows_on_the_page(engine, monkeypatch, star, "on the tenth from it", "—")
    assert "\n" not in grid.value[NATURE].iloc[0]
    assert grid.proto.row_height == 28
