"""The quadrant division's status, and what refuses at it.

Above the polar circle the ecliptic can coincide with the horizon or only touch
it, and at the pole nothing rises; Swiss Ephemeris returns twelve numbers all
the same, and within a second of a tangent instant it can return them slightly
out of order. These pins hold true values, from an independent construction:
never what Swiss Ephemeris does at a given input, which differs between machines.
"""
from __future__ import annotations

from markup import page_words
import ast
import copy
import datetime
import html
import json
from datetime import time
from pathlib import Path

import pytest

import engine as E
import ephemeris as M
from conftest import PAGES, READING_DEPTHS, assert_no_exception, make_app, sync_engine_to_environment
from test_split_astro_2026_10_14 import TAKEN_LAST

REPO = Path(__file__).resolve().parent.parent

# (case, latitude, ARMC, obliquity, status, the twelve cusps), from the definition,
# by a construction that shares no code with the engine or Swiss Ephemeris.
CASES = [
    ("ordinary_north", 60.000000000000, 0.000000000000, 23.439300000000, "defined", (124.565695246, 142.242240945, 160.821575584, 180.000000000, 224.764630060, 265.045859261, 304.565695246, 322.242240945, 340.821575584, 0.000000000, 44.764630060, 85.045859261)),
    ("ordinary_south", -60.000000000000, 0.000000000000, 23.439300000000, "defined", (55.434304754, 94.954140739, 135.235369940, 180.000000000, 199.178424416, 217.757759055, 235.434304754, 274.954140739, 315.235369940, 0.000000000, 19.178424416, 37.757759055)),
    ("above_circle_mc_above", 75.000000000000, 90.000000000000, 23.439300000000, "defined", (180.000000000, 212.181260906, 242.089451808, 270.000000000, 297.910548192, 327.818739094, 0.000000000, 32.181260906, 62.089451808, 90.000000000, 117.910548192, 147.818739094)),
    ("above_circle_mc_below", 80.000000000000, 210.000000000000, 23.439300000000, "defined", (25.728667621, 27.890684134, 30.041705245, 32.181260906, 88.119392817, 143.575531669, 205.728667621, 207.890684134, 210.041705245, 212.181260906, 268.119392817, 323.575531669)),
    ("near_north_pole", 89.990000000000, 180.000000000000, 23.528000000000, "defined", (180.025050276, 242.120010803, 297.901921055, 0.000000000, 0.008350092, 0.016700184, 0.025050276, 62.120010803, 117.901921055, 180.000000000, 180.008350092, 180.016700184)),
    ("near_south_pole", -89.990000000000, 0.000000000000, 23.528000000000, "defined", (0.025050276, 62.120010803, 117.901921055, 180.000000000, 180.008350092, 180.016700184, 180.025050276, 242.120010803, 297.901921055, 0.000000000, 0.008350092, 0.016700184)),
    ("swiss_precision_near_pole", 89.999000000000, 180.000000000000, 23.439300000000, "defined", (180.002513970, 242.090920705, 297.911282642, 0.000000000, 0.000837990, 0.001675980, 0.002513970, 62.090920705, 117.911282642, 180.000000000, 180.000837990, 180.001675980)),
    ("swiss_precision_near_tangent", 80.000000000000, 203.997827568018, 23.439300000000, "defined", (205.883723410, 264.489931725, 321.622514315, 25.883722352, 25.883722705, 25.883723057, 25.883723410, 84.489931725, 141.622514315, 205.883722352, 205.883722705, 205.883723057)),
    ("coincident_north", 66.560700000000, 270.000000000000, 23.439300000000, "coincidence", None),
    ("coincident_south", -66.560700000000, 90.000000000000, 23.439300000000, "coincidence", None),
    ("tangent_north_a", 75.000000000000, 218.172464086045, 23.439300000000, "tangency", None),
    ("tangent_north_b", 75.000000000000, 321.827535913955, 23.439300000000, "tangency", None),
    ("tangent_south_a", -75.000000000000, 38.172464086045, 23.439300000000, "tangency", None),
    ("exact_north_pole", 90.000000000000, 45.000000000000, 23.439300000000, "pole", None),
    ("exact_south_pole", -90.000000000000, 225.000000000000, 23.439300000000, "pole", None),
    ("below_coincidence", 66.559700000000, 270.000000000000, 23.439300000000, "defined", (0.000000000, 32.181260906, 62.089451808, 90.000000000, 117.910548192, 147.818739094, 180.000000000, 212.181260906, 242.089451808, 270.000000000, 297.910548192, 327.818739094)),
    ("above_coincidence", 66.561700000000, 270.000000000000, 23.439300000000, "defined", (0.000000000, 32.181260906, 62.089451808, 90.000000000, 117.910548192, 147.818739094, 180.000000000, 212.181260906, 242.089451808, 270.000000000, 297.910548192, 327.818739094)),
    ("tangent_north_a_before", 75.000000000000, 218.172364086045, 23.439300000000, "defined", (220.591622104, 277.506086583, 336.416134117, 40.591520411, 40.591554309, 40.591588207, 40.591622104, 97.506086583, 156.416134117, 220.591520411, 220.591554309, 220.591588207)),
    ("tangent_north_a_after", 75.000000000000, 218.172564086045, 23.439300000000, "defined", (40.591622104, 40.591656002, 40.591689899, 40.591723797, 97.506178625, 156.416240351, 220.591622104, 220.591656002, 220.591689899, 220.591723797, 277.506178625, 336.416240351)),
]
# Nineteen, as a construction independent of this file gave them; a development
# pin holds each against that construction's own table.
assert len(CASES) == 19
DEFINED = [c for c in CASES if c[4] == "defined"]
UNDEFINED = [c for c in CASES if c[4] != "defined"]
# Within a hair of a tangent instant, and at 89.999, the library's error sits
# about the tolerance and differs by machine: there the status may say so.
AT_THE_TOLERANCE = {"swiss_precision_near_pole", "swiss_precision_near_tangent"}
WITHHELD_ASCENDANT = ("tangency", "coincidence", "unresolved")
BIRTH = datetime.date(1975, 3, 14)
AN_INVENTED_JD = 2442486.25


@pytest.fixture(autouse=True)
def _engine_in_step():
    """The harness reloads the engine when the environment has moved; before a
    pin patches it, not after."""
    sync_engine_to_environment()


def _off(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _steps(cusps):
    return [(cusps[(i + 1) % 12] - cusps[i]) % 360.0 for i in range(12)]


def _division_at(armc, lat, obliquity):
    """What the engine does with the library's set at these exact inputs."""
    cusps, ascmc = M.swe.houses_armc(armc, lat, obliquity, b"B")
    return M.judged_division(cusps, ascmc, lat, armc, obliquity)


def _force(monkeypatch, status, away_from_armc=None):
    """The division at `status`, the rest of the chart as it is; with
    `away_from_armc`, at every moment but that one's. The bands have their own pins."""
    real = M.division_status

    def division_status(lat, armc, obliquity, cusps):
        if away_from_armc is not None and abs(armc - away_from_armc) < 1e-9:
            return real(lat, armc, obliquity, cusps)
        return status
    monkeypatch.setattr(M, "division_status", division_status)


def _chart(lat=70.0):
    return E.calculate_traditional_chart_jd(AN_INVENTED_JD, lat, 20.0)


# --- the check, the status ---------------------------------------------------
@pytest.mark.parametrize("case", DEFINED, ids=[c[0] for c in DEFINED])
def test_the_check_gives_the_true_cusps(case):
    _, lat, armc, obliquity, _, truth = case
    check = M.alchabitius_check(lat, armc, obliquity)
    assert max(_off(a, b) for a, b in zip(check, truth)) < 1e-6
    assert all(step > 0.0 for step in _steps(check))
    assert abs(sum(_steps(check)) - 360.0) < 1e-6


@pytest.mark.parametrize("case", DEFINED, ids=[c[0] for c in DEFINED])
def test_a_defined_set_is_the_true_set_and_never_a_false_one(case):
    name, lat, armc, obliquity, _, truth = case
    cusps, ascmc, status = _division_at(armc, lat, obliquity)
    if name in AT_THE_TOLERANCE and status == "unresolved":
        assert cusps == () and isinstance(cusps, M.WithheldCusps)
        return
    assert status == "defined"
    assert max(_off(a, b) for a, b in zip(cusps, truth)) <= 1e-6
    assert all(step > 0.0 for step in _steps(cusps))
    assert abs(sum(_steps(cusps)) - 360.0) < 1e-6
    assert _off(ascmc[0], truth[0]) <= 1e-6


@pytest.mark.parametrize("case", UNDEFINED, ids=[c[0] for c in UNDEFINED])
def test_an_undefined_instant_has_its_own_status_and_no_cusps(case):
    _, lat, armc, obliquity, status, _ = case
    cusps, _ascmc, got = _division_at(armc, lat, obliquity)
    assert got == status
    assert cusps == () and not cusps and list(cusps) == []
    assert M.division_refusal(cusps) == M.DIVISION_REASONS[status]
    with pytest.raises(E.DivisionWithheld):
        E.get_house_number(10.0, cusps)
    with pytest.raises(E.DivisionWithheld):
        E.get_effective_house(10.0, cusps)
    with pytest.raises(E.DivisionWithheld):
        E.quadrant_strength_position(10.0, cusps)


def test_half_the_zodiac_never_lands_in_one_house():
    """80 N, a quarter of a millisecond before a tangent instant. One house read
    360 degrees wide once took half the zodiac into the sixth."""
    case = next(c for c in CASES if c[0] == "swiss_precision_near_tangent")
    _, lat, armc, obliquity, _, truth = case
    cusps, _ascmc, status = _division_at(armc, lat, obliquity)
    longitudes = [i / 2.0 for i in range(720)]
    expected = [E.get_house_number(x, truth) for x in longitudes]
    assert expected.count(6) < 180 and any(h in expected for h in range(7, 13))
    if status == "defined":
        houses = [E.get_house_number(x, cusps) for x in longitudes]
        assert houses.count(6) == expected.count(6)
        assert any(h in houses for h in range(7, 13))
    else:
        assert status == "unresolved"
        with pytest.raises(E.DivisionWithheld):
            E.get_house_number(0.0, cusps)


def _true_case():
    return next(c for c in CASES if c[0] == "above_circle_mc_below")


def test_the_bands_of_the_status():
    _, lat, armc, obliquity, _, truth = _true_case()
    assert M.division_status(lat, armc, obliquity, truth) == "defined"
    assert (M.COINCIDENCE_BAND, M.TANGENCY_BAND, M.CUSP_CHECK_TOLERANCE, M.POLE_BAND) == (1e-9, 1e-12, 1e-6, 1e-6)
    check = M.alchabitius_check(lat, armc, obliquity)
    near = list(check)
    near[4] += 5e-7
    assert M.division_status(lat, armc, obliquity, near) == "defined"
    far = list(check)
    far[4] += 2e-6
    assert M.division_status(lat, armc, obliquity, far) == "unresolved"
    assert M.division_status(89.999999, armc, obliquity, check) == "pole"
    assert M.division_status(89.9999, armc, obliquity, check) != "pole"


def test_a_set_out_of_order_by_less_than_the_tolerance_is_unresolved():
    """A quarter of a millisecond before a tangent instant three cusps lie within
    the tolerance of one another: two swapped still agree with the check, and it
    is the order that refuses them."""
    case = next(c for c in CASES if c[0] == "swiss_precision_near_tangent")
    _, lat, armc, obliquity, _, truth = case
    check = list(M.alchabitius_check(lat, armc, obliquity))
    assert M.division_status(lat, armc, obliquity, check) == "defined"
    check[4], check[5] = check[5], check[4]
    assert max(_off(a, b) for a, b in zip(check, truth)) < M.CUSP_CHECK_TOLERANCE
    assert M.division_status(lat, armc, obliquity, check) == "unresolved"


def test_an_ascendant_not_rising_is_unresolved_whatever_the_check_says(monkeypatch):
    """The setting degree's set, against a check that agrees with it: only the
    rising test can refuse it."""
    _, lat, armc, obliquity, _, truth = _true_case()
    setting = tuple(truth[6:] + truth[:6])
    monkeypatch.setattr(M, "alchabitius_check", lambda *_a: setting)
    assert M.division_status(lat, armc, obliquity, setting) == "unresolved"
    monkeypatch.setattr(M, "alchabitius_check", lambda *_a: truth)
    assert M.division_status(lat, armc, obliquity, truth) == "defined"


def test_an_exact_instant_reached_from_a_chart():
    """Not forced: the longitude chosen so that the sidereal time meets a tangent
    instant, and the latitude so that the two planes coincide."""
    jd = AN_INVENTED_JD
    gast, obliquity = M._sidereal_frame(jd)
    t = E.math.degrees(E.math.asin(-1.0 / (E.math.tan(E.math.radians(75.0)) * E.math.tan(E.math.radians(obliquity)))))
    lon = ((180.0 - t) - gast + 180.0) % 360.0 - 180.0
    chart = E.calculate_traditional_chart_jd(jd, 75.0, lon)
    assert chart["division_status"] == "tangency"
    assert chart["ascendant"] is None
    lon = (270.0 - gast + 180.0) % 360.0 - 180.0
    chart = E.calculate_traditional_chart_jd(jd, 90.0 - obliquity, lon)
    assert chart["division_status"] == "coincidence"
    assert chart["ascendant"] is None


# --- the status lives with the ephemeris, and the page's sentences word for word
def test_the_status_code_is_in_the_ephemeris_module():
    for name in ("division_status", "judged_division", "house_division", "alchabitius_check", "WithheldCusps",
                 "ascendant_turns_within_a_minute", "division_refusal", "first_cusp"):
        assert getattr(E, name).__module__ == "ephemeris", name


def test_the_page_sentences_word_for_word():
    assert M.DIVISION_REASONS["tangency"] == (
        "At this moment the ecliptic only touches the horizon here, so no degree is rising and the quadrant divisions "
        "are undefined for this birth time.")
    assert M.DIVISION_REASONS["coincidence"] == (
        "At this moment the ecliptic lies along the horizon here, so no degree is rising and the quadrant divisions "
        "are undefined for this birth time.")
    assert M.DIVISION_REASONS["unresolved"] == (
        "The quadrant divisions cannot be computed reliably for this birth time at this latitude, so they are not shown.")
    assert M.REVOLUTION_DIVISION_REASONS == {
        "tangency": ("At this moment the ecliptic only touches the horizon here, so no degree is rising and the "
                     "quadrant divisions are undefined for this revolution."),
        "coincidence": ("At this moment the ecliptic lies along the horizon here, so no degree is rising and the "
                        "quadrant divisions are undefined for this revolution."),
        "unresolved": ("The quadrant divisions cannot be computed reliably for this revolution at this latitude, "
                       "so they are not shown."),
    }
    assert M.ASCENDANT_LEAP_CAUTION == (
        "Above the polar circle the rising degree can leap across the zodiac within minutes; here a minute's "
        "difference in the birth time would turn the Ascendant to its opposite.")


def _app_constants():
    names = {}
    for node in ast.parse((REPO / "app.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in (
                "POLE_HOUSES_SENTENCE", "POLE_CROSSING_SENTENCE", "POLE_ASCENDANT_SENTENCE"):
            names[node.targets[0].id] = eval(compile(ast.Expression(node.value), "app.py", "eval"), {}, names)
    return names


def test_the_pole_keeps_its_ascendant_midheaven_and_sentences():
    app = _app_constants()
    assert app["POLE_HOUSES_SENTENCE"] == (
        "At the pole no ecliptic degree rises or sets, so the Ascendant has no semi-arc and the quadrant divisions are "
        "undefined at this latitude. The Ascendant and Midheaven shown are where the ecliptic meets the horizon and "
        "the meridian, not a rising degree.")
    assert app["POLE_ASCENDANT_SENTENCE"].startswith(
        "At the pole no ecliptic degree rises or sets, so an Ascendant cast there is where the ecliptic meets the "
        "horizon, not a rising degree. ")
    assert app["POLE_HOUSES_SENTENCE"].startswith(M.DIVISION_REASONS["pole"])
    chart = _chart(90.0)
    _, ascmc = M.chart_houses(AN_INVENTED_JD, 90.0, 20.0)
    assert chart["division_status"] == "pole"
    assert (chart["ascendant"], chart["mc"]) == (ascmc[0], ascmc[1])
    assert chart["descendant"] == (ascmc[0] + 180.0) % 360.0
    assert chart["lot_of_fortune"] is not None
    assert chart["houses"] == ()


def test_the_domain_note_says_what_the_refused_methods_need():
    source = (REPO / "engine.py").read_text(encoding="utf-8")
    note = " ".join(line.lstrip("# ").strip() for line in source[source.index("# Domain. Finding"):
                                                             source.index("RAY_ASPECTS = (")].splitlines())
    assert "Finding the Ascendant inverts the oblique ascension at one value" in note
    assert "unique among the degrees that rise" in note
    assert "oblique ascension of arbitrary degrees" in note
    assert "do not rise" in note
    assert "the oblique ascension has no unique inverse" not in source.split("def _ascensional_method_applies")[1][:200]


# --- per-angle validity ------------------------------------------------------
def test_a_defined_chart_shows_swiss_ephemeris_s_own_set():
    chart = _chart()
    cusps, ascmc = M.chart_houses(AN_INVENTED_JD, 70.0, 20.0)
    assert chart["division_status"] == "defined" and chart["division_reason"] is None
    assert chart["houses"] == cusps
    assert (chart["ascendant"], chart["mc"]) == (ascmc[0], ascmc[1])


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_no_ascendant_descendant_or_lot_the_meridian_kept(monkeypatch, status):
    plain = _chart()
    _force(monkeypatch, status)
    chart = _chart()
    assert chart["division_status"] == status
    assert chart["division_reason"] == M.DIVISION_REASONS[status]
    assert chart["ascendant"] is None and chart["descendant"] is None and chart["lot_of_fortune"] is None
    assert chart["mc"] == plain["mc"] and chart["ic"] == plain["ic"]
    assert chart["houses"] == () and chart["ascendant_leap"] is False
    assert chart["planetary_data"] == plain["planetary_data"] and chart["sect"] == plain["sect"]
    with pytest.raises(E.DivisionWithheld):
        E.get_wsh_house(10.0, chart["ascendant"])
    with pytest.raises(E.DivisionWithheld):
        M.first_cusp(chart["houses"])


# --- the readers -------------------------------------------------------------
READING_SITES = {"get_house_number", "get_effective_house", "quadrant_strength_position"}
CUSP_NAMES = {"cusps", "natal_cusps", "natal_houses", "houses"}
# Every function reading the twelve by index: a cusp's degree, or the first.
INDEX_READERS = {"get_house_number", "get_effective_house", "evaluate_prosperity", "generate_hybrid_svg",
                 "moon_third_day_rows", "_lot_house_endpoint", "pn4_turning_rows"}
# Every function taking the twelve from a chart by name, and handing them on or reading them.
CHART_KEY_READERS = {
    "engine.py": {"_pn4_lots_in_sign", "add", "evaluate_moon_third_day", "evaluate_prosperity", "generate_hybrid_svg", "lot",
                  "pn4_day_point_origins", "pn4_governor_condition", "pn4_i7_planets", "pn4_ii3_examination",
                  "pn4_revolution_image", "pn4_timing_bundle", "pn4_turning_rows", "point_summary"},
    "app.py": {None, "_house_cusp_rows", "_positions_rows", "_ring_extras"},
}
# Every function reading a division. A new one must refuse, and join its pin.
READERS = {"evaluate_strength_of_planets", "evaluate_abu_mashar_condition", "falling",
           "evaluate_planetary_years_display", "_sahl_examine_candidate", "_sahl_house_master_years_branch",
           "moon_third_day_rows", "evaluate_prosperity", "pn4_governor_condition", "add", "pn4_i7_planets",
           "point_summary", "sahl_syzygy_governor", "generate_hybrid_svg"}


def _reading_name(func):
    """The name a call reads, written bare or through the accessor wheel.py
    reaches the engine by."""
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call) \
            and getattr(func.value.func, "id", None) == "_the_engine":
        return func.attr
    return getattr(func, "id", None)


def _census(source):
    """The functions reading a division: by a reading site, by index, by a chart's key."""
    by_site, by_index, by_key = set(), set(), set()

    def walk(node, within):
        for child in ast.iter_child_nodes(node):
            inside = child.name if isinstance(child, ast.FunctionDef) else within
            if isinstance(child, ast.Call) and _reading_name(child.func) in READING_SITES \
                    and within not in READING_SITES:
                by_site.add(within)
            if isinstance(child, ast.Subscript):
                if getattr(child.value, "id", None) in CUSP_NAMES:
                    by_index.add(within)
                if getattr(child.slice, "value", None) == "houses":
                    by_key.add(within)
            if isinstance(child, ast.Call) and getattr(child.func, "attr", None) == "get" and child.args \
                    and getattr(child.args[0], "value", None) == "houses":
                by_key.add(within)
            walk(child, inside)
    walk(ast.parse(source), None)
    return by_site, by_index, by_key


def test_no_reader_of_the_divisions_is_unaccounted_for():
    # The engine's readers wherever its text stands: the wheel's are in wheel.py.
    by_site, by_index, by_key = _census("\n".join((REPO / name).read_text(encoding="utf-8")
                                                  for name in ("engine.py", *TAKEN_LAST)))
    assert by_site == READERS
    assert by_index == INDEX_READERS
    assert by_key == CHART_KEY_READERS["engine.py"]
    assert _census((REPO / "app.py").read_text(encoding="utf-8"))[2] == CHART_KEY_READERS["app.py"]


def test_the_census_sees_every_way_of_reading_a_division():
    by_site, by_index, by_key = _census(
        "def a(c): return get_house_number(1.0, c)\n"
        "def b(cusps): return cusps[7]\n"
        "def c(chart): return chart['houses']\n"
        "def d(natal_houses): return natal_houses[0]\n"
        "def e(chart): return chart.get('houses')\n"
        "def f(chart): return chart.get('ascendant')\n")
    assert (by_site, by_index, by_key) == ({"a"}, {"b", "d"}, {"c", "e"})


@pytest.fixture(params=["pole", "tangency"])
def refusing(request, monkeypatch):
    if request.param == "pole":
        return _chart(90.0), 90.0
    _force(monkeypatch, "tangency")
    return _chart(), 70.0


def _evaluators(chart):
    data, sect = chart["planetary_data"], chart["sect"]
    essential = E.evaluate_essential_dignities(data, sect)
    accidental = {} if chart["ascendant"] is None else E.evaluate_accidental_dignities(
        data, chart["houses"], sect, chart["julian_day"], armc=chart["armc"],
        obliquity=chart["obliquity"], geo_lat=chart["geo_lat"])
    return data, sect, essential, accidental


def _reason(chart):
    return chart["division_reason"]


def test_reader_syzygy_governor(refusing):
    chart, lat = refusing
    syzygy = E.calculate_prenatal_syzygy(chart["julian_day"], lat, 20.0, chart["houses"])
    got = E.sahl_syzygy_governor(syzygy, chart["planetary_data"], chart["houses"], chart["sect"])
    assert got["refused"] == got["summary"] == _reason(chart)
    assert got["governor"] is None and got["rows"] == []


def test_reader_the_planets_condition(refusing):
    chart, _ = refusing
    data, sect, essential, accidental = _evaluators(chart)
    rows = E.evaluate_abu_mashar_condition(data, chart["houses"], sect, essential, accidental, chart["julian_day"],
                                           chart["ascendant"])
    assert set(rows) == {p for p in data if p != "North Node"}
    assert {row["refused"] for row in rows.values()} == {_reason(chart)}
    assert {row["Net"].reason for row in rows.values()} == {_reason(chart)}
    labels = [x for row in rows.values() for x in (*row.get("Positive Labels", ()), *row.get("Negative Labels", ()))]
    assert not [x for x in labels if "quadrant" in x or "(26)" in x or "(39)" in x], labels
    # No verdict, and no count the withheld division leaves short.
    for row in rows.values():
        for field in ("Condition", "Strength", "Weakness", "Positive Score", "Negative Score"):
            if field in row or chart["ascendant"] is not None:
                assert E.is_unresolved(row[field]) and row[field].reason == _reason(chart), field
        assert row["Condition"].reason == _reason(chart)
        assert row["Known Net"] == _reason(chart)
    if chart["ascendant"] is not None:
        assert {row["Known Strength"] for row in rows.values()} == {_reason(chart)}
        assert {row["Known Weakness"] for row in rows.values()} == {_reason(chart)}
        assert all(isinstance(row[f], int) for row in rows.values()
                   for f in ("Known Good Fortune", "Known Misfortune", "Known Moon Defects"))


def test_good_fortune_misfortune_and_the_moons_defects_read_no_cusp():
    """What the condition keeps at a refusal: the counts no division decides, on
    charts whose cusps are moved, where Strength and Weakness do move."""
    moved = set()
    for i in range(30):
        chart = E.calculate_traditional_chart_jd(AN_INVENTED_JD + 37.3 * i, 40.0 + i, 20.0 + 11 * i)
        data, sect, essential, accidental = _evaluators(chart)
        turned = tuple((c + 150.0) % 360.0 for c in chart["houses"])
        turned = (chart["houses"][0],) + turned[1:]
        args = (sect, essential, accidental, chart["julian_day"], chart["ascendant"])
        plain = E.evaluate_abu_mashar_condition(data, chart["houses"], *args)
        other = E.evaluate_abu_mashar_condition(data, turned, *args)
        for planet in plain:
            for field in ("Known Good Fortune", "Known Misfortune", "Known Moon Defects"):
                assert plain[planet][field] == other[planet][field], (i, planet, field)
            moved |= {f for f in ("Known Strength", "Known Weakness") if plain[planet][f] != other[planet][f]}
    assert moved == {"Known Strength", "Known Weakness"}


def test_a_refused_condition_survives_the_merge_of_undecided_connections(monkeypatch):
    """The merge counts sections as numbers, then writes Known Net over the row;
    the reason is put in after it, and a label open between outcomes is still counted."""
    chart = _chart(90.0)
    data, sect, essential, accidental = _evaluators(chart)

    real = E.evaluate_with_connection_uncertainty

    def two_outcomes(function, *args, **kwargs):
        if function.__name__ != "evaluate_abu_mashar_condition":
            return real(function, *args, **kwargs)
        first = function(*args, **kwargs)
        second = copy.deepcopy(first)
        second["Mars"]["Positive Labels"] = list(second["Mars"]["Positive Labels"]) + ["An invented testimony (0)"]
        second["Mars"]["Known Misfortune"] += 1
        merged = E._connection_merge([first, second], None)
        return function._connection_finish(merged, [first, second], None)
    monkeypatch.setattr(E, "evaluate_with_connection_uncertainty", two_outcomes)
    rows = E.evaluate_abu_mashar_condition(data, chart["houses"], sect, essential, accidental, chart["julian_day"],
                                           chart["ascendant"])
    assert rows["Mars"]["Unresolved Count"] >= 1
    assert rows["Mars"]["Known Net"] == _reason(chart) and rows["Mars"]["Known Strength"] == _reason(chart)
    assert rows["Mars"]["Condition"].reason == rows["Mars"]["Net"].reason == _reason(chart)


def test_the_lean_is_the_reason_not_a_verdict():
    chart = _chart(90.0)
    data, sect, essential, accidental = _evaluators(chart)
    rows = E.evaluate_abu_mashar_condition(data, chart["houses"], sect, essential, accidental, chart["julian_day"],
                                           chart["ascendant"])
    in_houses = E.evaluate_planets_in_houses(data, rows, chart["ascendant"])
    assert len(in_houses) == len(rows) >= 7
    for row in in_houses:
        assert E.is_unresolved(row["Lean"]) and row["Lean"].reason == _reason(chart)
        assert row["Net"].reason == _reason(chart)


def test_reader_strength(refusing):
    chart, _ = refusing
    data, sect, essential, accidental = _evaluators(chart)
    rows = E.evaluate_strength_of_planets(data, essential, accidental, chart["ascendant"], sect, chart["houses"])
    assert len(rows) >= 1 and {r["refused"] for r in rows} == {_reason(chart)}
    assert not [x for r in rows for x in r.get("Labels", ()) if "(83)" in x or "(88)" in x]
    assert {r["Count"] for r in rows} == {_reason(chart)}
    assert {r["Planet"] for r in rows} == {p for p in chart["planetary_data"] if p != "North Node"}


def test_a_refused_count_survives_the_recount_of_undecided_connections():
    """A chart at the pole with a strength testimony open: the merge counts them again."""
    jd = 2442624.62
    chart = E.calculate_traditional_chart_jd(jd, 90.0, 20.0)
    data, sect, essential, accidental = _evaluators(chart)
    rows = E.evaluate_strength_of_planets(data, essential, accidental, chart["ascendant"], sect, chart["houses"])
    assert [r for r in rows if r.get("Unresolved Count")], "premise: a testimony is open"
    assert {r["Count"] for r in rows} == {_reason(chart)}


def test_the_releasers_direction_says_why_nothing_was_examined(refusing):
    chart, _ = refusing
    selection = E.sahl_releaser(chart["planetary_data"], chart["ascendant"], chart["houses"], chart["sect"],
                                chart["lot_of_fortune"], 10.0, 200.0)
    got = E.pn4_releaser_direction(chart, selection, 10.0)
    assert got["note"] == _reason(chart) and got["note"] != E.PN4_NO_RELEASER
    assert got["status"] == "unavailable" and got["identity"] is None and got["rows"] == []


def test_a_chart_with_no_qualifying_releaser_still_says_so():
    got = E.pn4_releaser_direction(_chart(), {"releaser": None, "longitude": None}, 10.0)
    assert got["note"] == E.PN4_NO_RELEASER and got["status"] == "absent"


def test_the_governors_third_testimony_says_the_same():
    chart = _chart(90.0)
    got = E.pn4_timing_bundle(chart, 90.0, 20.0, BIRTH, datetime.date(2000, 1, 1), None)
    assert got["pn4_releaser"]["note"] == _reason(chart) and got["pn4_releaser"]["status"] == "unavailable"
    third = next(r for r in got["governor"][0] if r["#"] == 3)
    assert third["Planet"] == f"unavailable: {_reason(chart)}"
    assert third["Counted"] == "no"
    assert not [r for r in got["governor"][0] if "no qualifying releaser" in str(r["Planet"])]


TURNING_DIRECTED = "Directed a year per degree"


def test_the_turning_rows_say_why_never_the_row_below():
    chart = _chart(90.0)
    rows = E.pn4_turning_rows(chart, 30)
    by_count = [r for r in rows if "(by counting)" in r["Point"]]
    assert len(by_count) == 12
    assert not [r for r in rows if "row below" in r[TURNING_DIRECTED]]
    assert [int(r["Point"].split()[1]) for r in by_count if r[TURNING_DIRECTED] == _reason(chart)] == [
        2, 3, 5, 6, 7, 8, 9, 11, 12]


def test_the_row_below_stands_where_it_is_true():
    chart = next(c for c in (E.calculate_traditional_chart_jd(AN_INVENTED_JD + i, 60.0, 20.0) for i in range(40))
                 if any("row below" in r[TURNING_DIRECTED] for r in E.pn4_turning_rows(c, 30)))
    rows = E.pn4_turning_rows(chart, 30)
    for at, row in enumerate(rows):
        if "row below" in row[TURNING_DIRECTED]:
            assert "its degree" in rows[at + 1]["Point"]


@pytest.fixture(params=E.LOT_HOUSE_CUSP_OPTIONS)
def lot_rule(request):
    E.set_readings(LOT_HOUSE_CUSP=request.param)
    yield request.param
    E.set_readings(LOT_HOUSE_CUSP=E.LOT_HOUSE_CUSP)


def _reads_a_house(definition, rule):
    return any(definition[end].startswith(("cusp", "lord")) for end in ("start", "end", "project")) and (
        (definition.get("cusp_rule") or rule) == E.LOT_HOUSE_CUSP_OPTIONS[1])


def test_every_lot_keeps_its_row(lot_rule):
    chart = _chart(90.0)
    rows = E.calculate_topical_lots(chart["planetary_data"], chart["ascendant"], chart["houses"], chart["sect"])
    assert [r["Id"] for r in rows] == [d["id"] for d in E.LOT_DEFINITIONS]
    refused = {r["Id"] for r in rows if r["Longitude"] is None}
    direct = {d["id"] for d in E.LOT_DEFINITIONS if _reads_a_house(d, lot_rule)}
    assert direct and direct <= refused
    # A Lot counted from a refused Lot is refused with it.
    for definition in E.LOT_DEFINITIONS:
        if definition["id"] in refused - direct:
            assert {definition["start"], definition["end"], definition["project"]} & refused, definition["id"]
    for row in rows:
        if row["Id"] in refused:
            assert row["Status"] == row["Position"] == _reason(chart)
            assert (row["WS place"], row["Lord"], row["Formula"]) == ("-", "-", "-")
    death = [r["Id"] for r in rows]
    assert death.index("death_ws") == death.index("death") + 1, "the variant's note reads the row above"
    assert not [r for r in E.operative_lot_rows(chart["planetary_data"], chart["ascendant"], chart["houses"],
                                                chart["sect"], True) if r["Longitude"] is None]


def test_no_lot_is_counted_at_a_withheld_ascendant(monkeypatch):
    _force(monkeypatch, "tangency")
    chart = _chart()
    rows = E.calculate_topical_lots(chart["planetary_data"], chart["ascendant"], chart["houses"], chart["sect"])
    assert [r["Id"] for r in rows] == [d["id"] for d in E.LOT_DEFINITIONS]
    assert {r["Position"] for r in rows} == {_reason(chart)} and {r["Longitude"] for r in rows} == {None}


def test_a_turning_lot_keeps_its_row_at_the_cusp_reading(lot_rule):
    chart = _chart(90.0)
    rows = E.pn4_turning_rows(chart, 30)
    assert sum(1 for r in rows if r["Source"].startswith("PN IV VI.2") and "(by counting)" not in r["Point"]
               and r["Point"] not in E.PN4_SEVEN) == len(E.PN4_TURNING_LOTS)
    held = [r for r in rows if r["Natal"] == "-"]
    assert {r[TURNING_DIRECTED] for r in held} == {_reason(chart)}
    assert (len(held) > 1) is (lot_rule == E.LOT_HOUSE_CUSP_OPTIONS[1])


def test_the_lots_in_a_sign_never_say_none_for_a_lot_refused(lot_rule):
    chart = _chart(90.0)
    named = {sign: E._pn4_lots_in_sign(chart, sign) for sign in E.SIGN_ORDER}
    assert all(_reason(chart) in names for names in named.values())


def test_reader_the_moons_corruption(refusing):
    chart, _ = refusing
    got = E.evaluate_corruption_of_the_moon(chart["planetary_data"], chart["houses"], chart["sect"])
    assert got["refused"] == _reason(chart)
    assert got["testimonies"][109]["matched"] is False or not [
        c for c in got["testimonies"][109]["clauses"] if "divisions" in str(c)]


def test_reader_planetary_years(refusing):
    chart, _ = refusing
    data, sect, essential, _ = _evaluators(chart)
    rows = E.evaluate_planetary_years_display(data, chart["houses"], chart["ascendant"], sect, essential, supplement=True)
    assert len(rows) == 7
    for column in ("Division (5 deg at the stakes)", "On Nativities 1.20 grants (as house-master)",
                   "On Times 4, 7 (a question chart, 4, 2): for comparison"):
        assert {row[column] for row in rows} == {_reason(chart)}


def test_reader_the_releasers_examination(refusing):
    chart, _ = refusing
    data, sect = chart["planetary_data"], chart["sect"]
    got = E._sahl_examine_candidate("the Sun", data["Sun"]["longitude"], data, chart["houses"], sect, {1, 4, 7, 10, 11},
                                    self_planet="Sun")
    assert got["refused"] == got["why"] == _reason(chart)
    assert got["fit"] is False and got["place"] is None
    selection = E.sahl_releaser(data, chart["ascendant"], chart["houses"], sect, chart["lot_of_fortune"], 10.0, 200.0)
    assert selection["refused"] == selection["verdict"] == _reason(chart)
    assert selection["releaser"] is None and selection["house_master"] is None and selection["candidates"] == []


def test_reader_the_house_masters_years(refusing):
    chart, _ = refusing
    data, sect = chart["planetary_data"], chart["sect"]
    essential = E.evaluate_essential_dignities(data, sect)
    got = E._sahl_house_master_years_branch("Jupiter", data, chart["houses"], sect, essential)
    assert got["refused"] == got["text"] == _reason(chart)
    assert got["grade"] is None and got["years"] is None and got["division"] is None
    assert E.jn_years_fallback("Jupiter", data, chart["houses"], sect, essential) is None


def test_reader_the_moon_on_the_third_day(refusing):
    chart, _ = refusing
    rows = E.evaluate_moon_third_day(chart)
    falling = next(r for r in rows if r["Item"] == "Falling (1.29, 3)")
    assert falling["Value"] == _reason(chart)
    assert not [r for r in rows if "No corruption found" in str(r.get("Value"))]


def test_reader_prosperity(refusing):
    chart, _ = refusing
    rows = E.evaluate_prosperity(chart)
    assert [r for r in rows if r.get("refused") == _reason(chart)]
    assert not [r for r in rows if "raw quadrant" in str(r["Ground"]) or "by the quadrant cusps" in str(r["Ground"])]


def _revolution_of(chart, lat):
    return E.calculate_traditional_chart_jd(chart["julian_day"] + 365.25, lat, 20.0)


def test_reader_the_governors_condition_at_the_pole():
    chart = _chart(90.0)
    sr = _revolution_of(chart, 90.0)
    rows = E.pn4_governor_condition("Jupiter", chart, sr)
    place = next(r for r in rows if r["Source"] == "IX.9, 13" or "IX.9, 13" in r["Test"])
    assert _reason(chart) in place["Criteria"] and "division -" in place["Criteria"]


def test_reader_the_image_of_the_revolution_at_the_pole():
    chart = _chart(90.0)
    sr = _revolution_of(chart, 90.0)
    year = E.pn4_sign_of_the_year(chart["ascendant"], 30)
    rows, counts = E.pn4_revolution_image(chart, sr, year, 30, None, None, None, 90.0)
    assert rows == [] and counts == {"refused": _reason(chart)}


def test_reader_the_planets_in_the_revolution_at_the_pole():
    chart = _chart(90.0)
    sr = _revolution_of(chart, 90.0)
    rows = E.pn4_i7_planets(chart, sr)
    assert len(rows) == 14 and {r["Stakes (23)"] for r in rows} == {_reason(chart)}


def test_reader_the_point_panel_at_the_pole():
    chart = _chart(90.0)
    data, sect, essential, accidental = _evaluators(chart)
    got = E.point_summary("Jupiter", chart, essential, accidental, [], [], [], [])
    rows = {r["Reading"]: r["Value"] for r in got["position"]}
    assert rows["Quadrant division (Alchabitius)"] == _reason(chart)
    assert rows["Whole-sign place"].isdigit()       # the pole's Ascendant stays


def test_the_point_panel_has_no_withheld_angle(monkeypatch):
    _force(monkeypatch, "tangency")
    chart = _chart()
    for name in ("Ascendant", "Descendant", "Lot of Fortune"):
        assert E.point_summary(name, chart, {}, {}, [], [], [], []) is None


def test_the_equated_lots_are_not_counted_from_withheld_cusps():
    """The Lot of death measures to the eighth's calculated cusp: no number."""
    chart = _chart(90.0)
    assert E._lot_house_endpoint(8, chart["ascendant"], chart["houses"], E.LOT_HOUSE_CUSP_OPTIONS[1]) is None


# --- nothing counted from a withheld Ascendant --------------------------------
@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_the_timing_bundle_computes_nothing_from_a_withheld_ascendant(monkeypatch, status):
    _force(monkeypatch, status)
    chart = _chart()

    def must_not_run(*_a, **_k):
        raise AssertionError("counted from a withheld Ascendant")
    monkeypatch.setattr(E, "pn4_sign_of_the_year", must_not_run)
    monkeypatch.setattr(E, "pn4_distribution_from_ascendant", must_not_run)
    monkeypatch.setattr(E, "pn4_mighty_days", must_not_run)
    monkeypatch.setattr(E, "pn4_small_days", must_not_run)
    monkeypatch.setattr(E, "pn4_monthly_indicators", must_not_run)
    got = E.pn4_timing_bundle(chart, 70.0, 20.0, BIRTH, datetime.date(2000, 1, 1), None)
    assert got == {"refused": M.DIVISION_REASONS[status]}


def test_the_profection_terminal_point_and_distribution_refuse_by_themselves(monkeypatch):
    _force(monkeypatch, "tangency")
    chart = _chart()
    assert E.pn4_sign_of_the_year(chart["ascendant"], 30) is None
    assert E.pn4_distribution_from_ascendant(chart["planetary_data"], chart["ascendant"], chart["obliquity"], 10.0) is None
    assert E.pn4_small_days(chart["planetary_data"], chart["ascendant"]) is None
    assert E.calculate_time_lords(chart["ascendant"], BIRTH, datetime.date(2000, 1, 1)) == []
    assert E.lot_by_id("fortune", chart["planetary_data"], chart["ascendant"], chart["houses"], chart["sect"]) is None


def test_the_months_revolution_alone_withheld_refuses(monkeypatch):
    """The root and the year's revolution stand; only the month's return has no Ascendant."""
    chart = _chart()
    real = E.calculate_traditional_chart_jd
    cast = []

    def casting(jd, lat, lon):
        got = real(jd, lat, lon)
        cast.append(jd)
        if len(cast) == 2:
            return dict(got, ascendant=None, descendant=None, lot_of_fortune=None, houses=M.WithheldCusps("unresolved"),
                        division_status="unresolved", division_reason=M.DIVISION_REASONS["unresolved"])
        return got
    monkeypatch.setattr(E, "calculate_traditional_chart_jd", casting)
    got = E.pn4_timing_bundle(chart, 70.0, 20.0, BIRTH, datetime.date(2000, 6, 1), None)
    assert len(cast) == 2
    assert got == {"refused": M.REVOLUTION_DIVISION_REASONS["unresolved"]}


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_a_withheld_revolution_refuses_though_the_root_stands(monkeypatch, status):
    chart = _chart()
    _force(monkeypatch, status, away_from_armc=chart["armc"])
    got = E.pn4_timing_bundle(chart, 70.0, 20.0, BIRTH, datetime.date(2000, 1, 1), None)
    assert got == {"refused": M.REVOLUTION_DIVISION_REASONS[status]}


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_root_and_revolution_withheld_together_say_the_root_s_words(monkeypatch, status):
    """The bundle reads the root first, so its words stand, not the revolution's."""
    _force(monkeypatch, status)
    got = E.pn4_timing_bundle(_chart(), 70.0, 20.0, BIRTH, datetime.date(2000, 1, 1), None)
    assert got == {"refused": M.DIVISION_REASONS[status]}
    assert M.DIVISION_REASONS[status] != M.REVOLUTION_DIVISION_REASONS[status]


def test_at_the_pole_the_year_stays_and_no_stand_in_takes_the_releasers_place(monkeypatch):
    chart = _chart(90.0)
    real = E.sahl_house_master_direction
    policies = []

    def recording(*args, **kwargs):
        policies.append(kwargs.get("target_policy"))
        return real(*args, **kwargs)
    monkeypatch.setattr(E, "sahl_house_master_direction", recording)
    got = E.pn4_timing_bundle(chart, 90.0, 20.0, BIRTH, datetime.date(2000, 1, 1), None)
    assert got["year"]["sign"] == E.pn4_sign_of_the_year(chart["ascendant"], got["cycle"])["sign"]
    assert got["releaser"]["refused"] == _reason(chart)
    assert got["releaser_note"] == _reason(chart)
    assert got["standin_moon"] is None
    assert "stand-in" not in policies


def test_the_gestations_lunation_ascendant_follows_its_own_moment(monkeypatch):
    chart = _chart()
    _force(monkeypatch, "tangency")
    rows = E.evaluate_gestation(chart, 70.0, 20.0)
    row = next(r for r in rows if r["Item"] == "The Ascendant of the meeting (1.8, 6)")
    assert row["Value"].startswith(E.GESTATION_NOT_COMPUTED)


# --- the caution, at plus or minus one minute --------------------------------
def _armc_moment(armc):
    """The longitude at which the invented moment's sidereal time is `armc`."""
    gast, obliquity = M._sidereal_frame(AN_INVENTED_JD)
    return ((armc - gast + 180.0) % 360.0) - 180.0, obliquity


def _tangent(lat, obliquity):
    t = E.math.degrees(E.math.asin(-1.0 / (E.math.tan(E.math.radians(lat)) * E.math.tan(E.math.radians(obliquity)))))
    return 180.0 - t


@pytest.mark.parametrize("seconds, shown", [(-90, False), (-50, True), (-10, True), (10, True), (50, True), (90, False)])
def test_the_caution_is_shown_only_a_minute_from_the_turn(seconds, shown):
    lat = 70.0
    _, obliquity = _armc_moment(0.0)
    instant = _tangent(lat, obliquity)
    lon, _ = _armc_moment(instant + seconds * 360.98565 / 86400.0)
    chart = E.calculate_traditional_chart_jd(AN_INVENTED_JD, lat, lon)
    assert chart["division_status"] == "defined"
    assert chart["ascendant_leap"] is shown
    # The sentence's claim, against the library's own Ascendants a minute away.
    asc = chart["ascendant"]
    apart = [_off(asc, M.chart_houses(AN_INVENTED_JD + d / 1440.0, lat, lon)[1][0]) for d in (-1.0, 1.0)]
    assert (max(apart) > 179.0) is shown


@pytest.mark.parametrize("lat", [0.0, 51.5, 66.0, -60.0])
def test_no_caution_below_the_polar_circle(lat):
    assert not any(E.calculate_traditional_chart_jd(AN_INVENTED_JD + h / 24.0, lat, 20.0)["ascendant_leap"]
                   for h in range(24))


def test_the_page_says_the_caution_only_where_it_holds():
    lat = 70.0
    jd = 2451545.0      # 2000-01-01 12:00 UT, an invented moment
    gast, obliquity = M._sidereal_frame(jd)
    instant = _tangent(lat, obliquity)
    lon = ((instant - 10 * 360.98565 / 86400.0 - gast + 180.0) % 360.0) - 180.0
    caution = M.ASCENDANT_LEAP_CAUTION
    for page, expect in (("chart", True), ("lots", True), ("reference", False)):
        at = _run(page, "2000-01-01", (12, 0), lat, lon)
        assert (caution in [str(w.value) for w in at.main.warning]) is expect, page
    at = _run("chart", "2000-01-01", (12, 0), 51.5, 0.0)
    assert caution not in [str(w.value) for w in at.main.warning]


def test_the_caution_reaches_all_three_exports():
    lat = 70.0
    jd = 2451545.0      # 2000-01-01 12:00 UT, an invented moment
    gast, obliquity = M._sidereal_frame(jd)
    lon = ((_tangent(lat, obliquity) - 10 * 360.98565 / 86400.0 - gast + 180.0) % 360.0) - 180.0
    caution = M.ASCENDANT_LEAP_CAUTION
    at = _run("chart", "2000-01-01", (12, 0), lat, lon)
    assert caution in json.dumps(at.session_state["_analysis_export"], default=str, ensure_ascii=False)
    assert caution in at.session_state["_analysis_markdown"]
    assert html.escape(caution) in at.session_state["_analysis_html"] or caution in at.session_state["_analysis_html"]
    plain = _run("chart", "2000-01-01", (12, 0), 51.5, 0.0)
    for held in (json.dumps(plain.session_state["_analysis_export"], default=str, ensure_ascii=False),
                 plain.session_state["_analysis_markdown"], plain.session_state["_analysis_html"]):
        assert caution not in held and html.escape(caution) not in held


# --- the wheel: only what must not crash or draw a withheld value
def _svg(chart):
    return E.generate_hybrid_svg(chart, "x", "y", chart["geo_lat"], 20.0, datetime.datetime(1975, 3, 14, 18), "UTC", wide=True)


def test_the_wheel_draws_no_withheld_cusp():
    assert ">Asc<" not in _svg(_chart(90.0)).split("Angles and cusps")[1]
    assert ">Asc<" in _svg(_chart(89.0)).split("Angles and cusps")[1]
    assert _svg(_chart(90.0)).count('class="pt"') == _svg(_chart(89.0)).count('class="pt"')


def test_the_wheel_is_not_drawn_without_a_rising_sign(monkeypatch):
    _force(monkeypatch, "tangency")
    svg = _svg(_chart())
    assert M.DIVISION_REASONS["tangency"] in svg and 'class="pt"' not in svg


# --- the pages ---------------------------------------------------------------
MANUAL = "Manual UTC offset"


def _run(page, date, hhmm, lat, lon):
    at = make_app(date=date, page=page, timeout=120)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, f"{page} {lat}")
    return at


@pytest.mark.parametrize("page", PAGES)
def test_every_page_stands_at_a_tangency(monkeypatch, page):
    _force(monkeypatch, "tangency")
    at = _run(page, "1975-03-14", (18, 0), 70.0, 20.0)
    warnings = [str(w.value) for w in at.main.warning]
    assert (M.DIVISION_REASONS["tangency"] in warnings) is (page not in ("reference", "sources")), warnings


@pytest.mark.parametrize("status", ["coincidence", "unresolved"])
def test_the_chart_page_keeps_the_meridian_and_says_why(monkeypatch, status):
    _force(monkeypatch, status)
    at = _run("chart", "1975-03-14", (18, 0), 70.0, 20.0)
    assert M.DIVISION_REASONS[status] in [str(w.value) for w in at.main.warning]
    shown = [df.value for df in at.main.dataframe]
    points = next(df for df in shown if "Point" in df.columns)
    assert list(points["Point"]) == ["Midheaven", "Imum Coeli", "North Node", "South Node"]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_stands_at_the_pole(page):
    at = _run(page, "1975-03-14", (18, 0), 90.0, 20.0)
    # The Chart page gives the longer sentence beside its cusps; the star lists read no division.
    said = M.DIVISION_REASONS["pole"] in [str(w.value) for w in at.main.warning]
    assert said is (page not in ("reference", "sources", "chart", "fixed-stars", "sky"))


@pytest.mark.parametrize("page", PAGES)
def test_a_withheld_revolution_leaves_every_page_standing(monkeypatch, page):
    """The pages on the bundle say why; the others do not read it."""
    monkeypatch.setattr(E, "pn4_timing_bundle", lambda *a, **k: {"refused": M.REVOLUTION_DIVISION_REASONS["unresolved"]})
    at = _run(page, "1975-03-14", (18, 0), 70.0, 20.0)
    said = M.REVOLUTION_DIVISION_REASONS["unresolved"] in [str(w.value) for w in at.main.warning]
    assert said is (page in ("timing", "releaser", "days", "fardar", "fixed-stars", "sky"))


# --- whose moment is withheld: each says its own words, on every page ----------
ON_THE_BUNDLE = ("timing", "releaser", "days", "fardar", "fixed-stars", "sky")


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_a_withheld_revolution_prints_its_words_and_not_the_births(monkeypatch, status):
    _force(monkeypatch, status, away_from_armc=_chart()["armc"])
    for page in PAGES:
        at = _run(page, "1975-03-14", (18, 0), 70.0, 20.0)
        said = _said(at)
        assert (M.REVOLUTION_DIVISION_REASONS[status] in [str(w.value) for w in at.main.warning]) is (
            page in ON_THE_BUNDLE), page
        assert not [x for x in said if "for this birth time" in x or x == M.DIVISION_REASONS[status]], page


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_a_withheld_root_prints_the_ruled_words_and_not_the_revolutions(monkeypatch, status):
    _force(monkeypatch, status)
    for page in PAGES:
        at = _run(page, "1975-03-14", (18, 0), 70.0, 20.0)
        said = _said(at)
        assert (M.DIVISION_REASONS[status] in [str(w.value) for w in at.main.warning]) is (
            page not in ("reference", "sources")), page
        assert not [x for x in said if "for this revolution" in x or x in M.REVOLUTION_DIVISION_REASONS.values()], page


# --- what a page says beside a refusal, at the pole ---------------------------
POLE_REASON = M.DIVISION_REASONS["pole"]


def _at_the_pole(page, depth=None, jd_date="1975-03-14", seed=None):
    at = make_app(date=jd_date, page=page, timeout=120)
    at.session_state["manual_lat_key"] = 90.0
    at.session_state["manual_lon_key"] = 20.0
    at.session_state["time_input_key"] = time(18, 0)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 0.0
    if depth:
        at.session_state["_reading_depth"] = depth
    for key, value in (seed or {}).items():
        at.session_state[key] = value
    at.run()
    assert_no_exception(at, page)
    return at


def _said(at):
    return [str(e.value) for kind in (at.main.markdown, at.main.caption, at.main.warning, at.main.subheader) for e in kind]


def _table(at, column):
    return next(node.value for _heading, node in __import__('conftest').table_nodes(at) if column in node.value.columns)


@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_the_page_prints_no_verdict_and_no_short_count(depth):
    at = _at_the_pole("configurations", depth)
    table = _table(at, "Moon Defects")
    assert not {"Net", "Verdict"} & set(table.columns)
    assert {str(v) for v in table["Strength"]} == {POLE_REASON}
    assert {str(v) for v in table["Weakness"]} == {POLE_REASON}
    assert all(str(v).isdigit() for v in table["Good Fortune"])
    assert all(str(v).isdigit() for v in table["Misfortune"])
    defects = table.set_index("Planet")["Moon Defects"]
    assert defects["Moon"] == 2 and defects.drop("Moon").isna().all(), "a count, on the Moon's row alone"
    grid = _table(at, "advancing")
    assert {str(v) for v in grid["Count"]} == {POLE_REASON}
    moon = next(node.value for _h, node in __import__("conftest").table_nodes(at) if "Defects" in node.value.columns and "Count" in node.value.columns)
    assert {str(v) for v in moon["Count"]} == {POLE_REASON}
    assert not [x for x in _said(at) if "possible totals" in x]


def test_the_dignities_page_says_the_reason_and_draws_no_lean_and_no_net():
    at = _at_the_pole("dignities")
    assert POLE_REASON in [str(w.value) for w in at.main.warning]
    assert not [df for df in at.main.dataframe if {"Lean", "Net", "Standing"} & set(df.value.columns)]
    assert not [x for x in _said(at) if "possible totals" in x or "known subtotal" in x]


def _one_row_left_open(monkeypatch):
    real = E.evaluate_abu_mashar_condition

    def opened(*args, **kwargs):
        rows = real(*args, **kwargs)
        rows["Mars"]["Unresolved Count"] = 1
        if "refused" not in rows["Mars"]:
            rows["Mars"]["Net"] = E.UnresolvedResult("an invented reason", "an invented source")
        return rows
    monkeypatch.setattr(E, "evaluate_abu_mashar_condition", opened)


def test_the_captions_of_an_open_net_only_where_their_words_are_true(monkeypatch):
    _one_row_left_open(monkeypatch)
    at = _at_the_pole("dignities")
    assert "Unresolved" in _table(at, "Shared PN IV passages").columns, "premise: a row is left open"
    assert not [x for x in _said(at) if "known subtotal" in x or "possible totals" in x]
    assert not [x for x in _said(_at_the_pole("configurations")) if "possible totals" in x]
    for page, words in (("dignities", "possible counts"), ("configurations", "left open")):
        at = make_app(date="1975-03-14", page=page, timeout=120)
        at.run()
        assert_no_exception(at, page)
        assert [x for x in _said(at) if words in x], page


def test_the_strength_panel_says_why_not_how_many():
    seed = {"strength_of_the_planets_detail": "Sun"}
    at = _at_the_pole("configurations", seed=seed)
    heads = [str(s.value) for s in at.main.subheader]
    assert f"Sun: {POLE_REASON}" in heads
    assert not [h for h in heads if "testimonies" in h and h.startswith("Sun:")]


def test_the_conditions_detail_prints_no_verdict():
    at = _at_the_pole("configurations", seed={"planetary_condition_detail": "Sun"})
    line = next(x for x in _said(at) if x.startswith("**Sun.** Good Fortune"))
    assert POLE_REASON in line and "Net" not in line and "Verdict" not in line


def test_the_fardar_page_names_no_house_master_it_cannot_name():
    said = _said(_at_the_pole("fardar", READING_DEPTHS[1]))
    assert not [x for x in said if "Applied to one planet only" in x or "beside each" in x]


def test_the_releaser_page_offers_no_stand_in_and_no_absence():
    said = _said(_at_the_pole("releaser", READING_DEPTHS[1]))
    assert not [x for x in said if "The stand-in" in x or "No house-master to direct" in x
                or "Sahl's fallback" in x or x == E.PN4_NO_RELEASER]
    assert POLE_REASON in said


def test_the_image_of_the_revolution_leaves_no_count_line_behind():
    at = _at_the_pole("timing")
    said = _said(at)
    assert POLE_REASON in said
    assert not [x for x in said if "the count line excludes them" in x]
    assert not [df for df in at.main.dataframe if not len(df.value.columns)]


def test_the_lunation_page_describes_no_verdict_it_withholds():
    alone = ("**The verdict** names a planet only where the text's clear subcases decide, and otherwise says "
             "\"unresolved\" with each candidate's profile.")
    assert alone not in _said(_at_the_pole("victors"))
    ordinary = make_app(date="1975-03-14", page="victors", timeout=120)
    ordinary.run()
    assert alone in _said(ordinary)


def test_the_export_says_the_same_at_the_pole():
    at = _at_the_pole("chart")
    markdown = at.session_state["_analysis_markdown"]
    for gone in ("no qualifying releaser", "No qualifying longevity releaser", "in the row below (PN IV VI.2, 21-24)",
                 "the row's details give"):
        assert gone not in markdown, gone
    exported = at.session_state["_analysis_export"]["results"]
    rows = [row for section in exported.values() for table in section.values() for entry in table
            for row in (entry.get("rows", ()) if isinstance(entry, dict) else ())]
    verdicts = [row["Verdict"] for row in rows if "Verdict" in row and "Good Fortune" in row]
    assert len(verdicts) >= 7 and {v.split(" — ", 1)[-1] for v in verdicts} == {POLE_REASON}


# --- the jump strip draws only where the page goes on to draw its headings --------
STRIP_KEY = "days-sections"
STRIP_TEXT = ("[The small days](#the-small-days) [The mighty days](#the-mighty-days) "
              "[The nine methods](#the-nine-methods) [The seven indicators](#the-seven-indicators)")


def _strip_of(at):
    return [m.value for m in at.main.markdown if m.value.count("](#") > 1]


def _index_on_the_page(at, wanted):
    """Where on the page, among its direct children, the element `wanted` picks is."""
    def within(node):
        return wanted(node) or any(within(c) for c in getattr(node, "children", {}).values())
    return next(i for i, child in enumerate(at.main.children.values()) if within(child))


def _says_the_chart(node):
    return getattr(node, "type", "") == "caption" and "lunation" in str(node.value)


def _is_the_strip(node):
    return getattr(node, "type", "") == "markdown" and node.value == STRIP_TEXT


@pytest.mark.parametrize("lat", [70.0, 90.0])
def test_the_strip_stands_above_the_chart_strip_where_the_page_draws(lat):
    at = _run("days", "1975-03-14", (18, 0), lat, 20.0)
    assert _strip_of(at) == [STRIP_TEXT]
    assert _index_on_the_page(at, _is_the_strip) < _index_on_the_page(at, _says_the_chart)
    assert [h.proto.anchor for h in at.main.subheader if h.proto.anchor] == [
        "the-small-days", "the-mighty-days", "the-nine-methods", "the-seven-indicators"]


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_no_strip_above_a_withheld_root(monkeypatch, status):
    _force(monkeypatch, status)
    at = _run("days", "1975-03-14", (18, 0), 70.0, 20.0)
    assert not _strip_of(at) and not at.main.subheader
    assert [str(w.value) for w in at.main.warning] == [M.DIVISION_REASONS[status]]


@pytest.mark.parametrize("status", WITHHELD_ASCENDANT)
def test_no_strip_above_a_withheld_revolution(monkeypatch, status):
    monkeypatch.setattr(E, "pn4_timing_bundle", lambda *a, **k: {"refused": M.REVOLUTION_DIVISION_REASONS[status]})
    at = _run("days", "1975-03-14", (18, 0), 70.0, 20.0)
    assert not _strip_of(at) and not at.main.subheader
    assert [str(w.value) for w in at.main.warning] == [M.REVOLUTION_DIVISION_REASONS[status]], "said once"


# --- a Lot with no place: nothing to direct from, so nothing offered ----------------
def _pole_page(page, chart=("1975-03-14", (18, 0), 90.0, 20.0), rule=None, depth=None, seed=None):
    date, hhmm, lat, lon = chart
    at = make_app(date=date, page=page, timeout=120)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 0.0
    if rule:
        at.session_state["_lot_house_cusp"] = rule
    if depth:
        at.session_state["_reading_depth"] = depth
    for key, value in (seed or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _small_days_control(at):
    return next(box for box in at.main.selectbox if box.label.startswith("Also direct"))


def test_a_lot_with_no_place_is_not_offered(lot_rule):
    chart = _chart(90.0)
    for supplement in (False, True):
        points = E.pn4_day_point_origins(chart, chart, supplement)
        assert not [key for key in points if key.startswith("house:")]
        assert len(points) > len(E.PN4_SEVEN), "the seven and the Lots that have a place"
        for definition in E.operative_lot_definitions():
            if definition.get("supplement") and not supplement:
                continue
            place = E.lot_by_id(definition["id"], chart["planetary_data"], chart["ascendant"], chart["houses"], chart["sect"])
            assert (("lot:" + definition["id"]) in points) is (place is not None), definition["id"]
        for key, point in points.items():
            assert isinstance(point["natal"], float) and isinstance(point["revolution"], float), key
    assert "lot:death" not in points


def test_a_lot_with_no_place_at_one_chart_alone_is_not_offered(lot_rule):
    """The natal Lot stands and the revolution's has none, and the other way about."""
    placed, placeless = _chart(), _chart(90.0)
    for natal, revolution in ((placed, placeless), (placeless, placed)):
        assert "lot:death" not in E.pn4_day_point_origins(natal, revolution, True)
    assert "lot:death" in E.pn4_day_point_origins(placed, placed, True)


@pytest.mark.parametrize("rule", E.LOT_HOUSE_CUSP_OPTIONS)
@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_every_option_of_the_small_days_control_stands_at_the_pole(rule, depth):
    at = _pole_page("days", rule=rule, depth=depth)
    assert_no_exception(at, "days")
    options = list(_small_days_control(at).options)
    assert options[0].startswith("the Ascendant") and "Lot of death" not in options
    assert not [o for o in options if o.startswith("house ")]
    if rule == E.LOT_HOUSE_CUSP_OPTIONS[1]:
        assert not {"Lot of the killer", "Lot of travel", "Lot of assets (lord of the 2nd)"} & set(options)
    for option in options:
        chosen = _pole_page("days", rule=rule, depth=depth, seed={"_pn4_day_point": option.replace("Māshā'allāh", "Masha'allah").replace("Abū Ma'shar", "Abu Ma'shar")})
        assert_no_exception(chosen, option)
        assert page_words(_small_days_control(chosen).value) == option
        if option != options[0]:
            assert [m for m in chosen.main.markdown if m.value.startswith("**Small days from")], option


def test_a_stale_choice_falls_to_the_ascendant_when_the_pole_is_typed():
    at = _run("days", "1975-03-14", (18, 0), 70.0, 20.0)
    _small_days_control(at).set_value("Lot of death")
    at.run()
    assert_no_exception(at, "chosen")
    assert _small_days_control(at).value == "Lot of death"
    next(box for box in at.sidebar.number_input if box.key == "manual_lat_key").set_value(90.0)
    at.run()
    assert_no_exception(at, "typed 90")
    assert _small_days_control(at).value.startswith("the Ascendant")
    assert not [m for m in at.main.markdown if m.value.startswith("**Small days from")]


def test_a_stale_choice_falls_when_the_lots_reading_takes_its_place():
    chosen = _pole_page("days", seed={"_pn4_day_point": "Lot of travel"}, rule=E.LOT_HOUSE_CUSP_OPTIONS[0])
    assert_no_exception(chosen, "whole-sign")
    assert _small_days_control(chosen).value == "Lot of travel"
    moved = _pole_page("days", seed={"_pn4_day_point": "Lot of travel"}, rule=E.LOT_HOUSE_CUSP_OPTIONS[1])
    assert_no_exception(moved, "quadrant cusp")
    assert _small_days_control(moved).value.startswith("the Ascendant")


# Every way a Lot's place is read. A new one must refuse or be unable to receive None, and be named here.
LOT_BY_ID_READERS = {"_pn4_lots_in_sign", "calculate_classical_lots", "calculate_traditional_chart_jd", "lot",
                     "pn4_turning_rows"}
LOT_LONGITUDE_READERS = {"calculate_topical_lots", "father_lot_selection", "lot_by_id"}
LOT_ROW_PLACE_READERS = {"engine.py": {"operative_lot_rows", "pn4_revolution_image"},
                         "app.py": {"_ring_extras", "_topical_lot_rows"}}


def _lot_readers(source):
    by_id, by_formula, by_row = set(), set(), set()

    def walk(node, within):
        for child in ast.iter_child_nodes(node):
            inside = child.name if isinstance(child, ast.FunctionDef) else within
            if isinstance(child, ast.Call):
                called = getattr(child.func, "id", None)
                if called == "lot_by_id":
                    by_id.add(within)
                if called == "_lot_longitude":
                    by_formula.add(within)
                if getattr(child.func, "attr", None) == "get" and child.args \
                        and getattr(child.args[0], "value", None) == "Longitude":
                    by_row.add(within)
            if isinstance(child, ast.Subscript) and getattr(child.slice, "value", None) == "Longitude":
                by_row.add(within)
            walk(child, inside)
    walk(ast.parse(source), None)
    return by_id, by_formula, by_row


def test_no_reader_of_a_lots_place_is_unaccounted_for():
    by_id, by_formula, by_row = _lot_readers((REPO / "engine.py").read_text(encoding="utf-8"))
    assert by_id == LOT_BY_ID_READERS
    assert by_formula == LOT_LONGITUDE_READERS
    assert by_row == LOT_ROW_PLACE_READERS["engine.py"]
    assert _lot_readers((REPO / "app.py").read_text(encoding="utf-8")) == (set(), set(), LOT_ROW_PLACE_READERS["app.py"])


def test_the_lots_a_reader_takes_without_a_guard_have_a_place_at_the_pole(lot_rule):
    """The chart's Fortune, the four classical Lots and the father's selection read no cusp."""
    chart = _chart(90.0)
    assert isinstance(chart["lot_of_fortune"], float)
    lots = E.calculate_classical_lots(chart["ascendant"], chart["planetary_data"]["Sun"]["longitude"],
                                      chart["planetary_data"]["Moon"]["longitude"], chart["sect"])
    assert [row["Lot Name"] for row in lots] == ["Lot of Fortune", "Lot of Spirit", "Lot of Exaltation", "Lot of Basis"]
    assert POLE_REASON not in {row["Position"] for row in lots}
    assert isinstance(E.father_lot_selection(chart["planetary_data"], chart["ascendant"], chart["houses"],
                                             chart["sect"])["longitude"], float)


# --- the third day: nothing found, with falling not examined, is no finding ----------
THIRD_DAY_CHART = ("2021-04-27", (1, 0), 90.0, 77.0)
THIRD_DAY_11, THIRD_DAY_12 = "1.29, 11, the third-day component", "1.29, 12, its first-clause components"
CORRUPTION_ROW = "Third-day Moon: corruption checks (limited reading of 1.29, 3)"


def _third_day(year, lat, lon):
    jd = M.swe.julday(year, 4, 27, 1.0)
    return {row["Item"]: row["Value"] for row in E.evaluate_moon_third_day(E.calculate_traditional_chart_jd(jd, lat, lon))}


def test_the_third_day_component_at_a_refusal_with_nothing_found():
    rows = _third_day(2021, 90.0, 77.0)
    assert rows["Falling (1.29, 3)"] == rows[CORRUPTION_ROW] == POLE_REASON
    assert rows[THIRD_DAY_11] == POLE_REASON
    assert str(rows[THIRD_DAY_12]).startswith("Not met:") and rows[THIRD_DAY_12].endswith("no corruption was established")


def test_the_first_clause_at_a_refusal_with_both_there_and_nothing_found():
    """Both infortunes in the Ascendant or seventh and nothing found: the clause's other half turns on falling, which refused."""
    jd = M.swe.julday(1980, 2, 7, 14.0)
    chart = E.calculate_traditional_chart_jd(jd, -90.0, 177.5)
    rows = {row["Item"]: row["Value"] for row in E.evaluate_moon_third_day(chart)}
    assert rows["Falling (1.29, 3)"] == rows[CORRUPTION_ROW] == POLE_REASON
    assert rows[THIRD_DAY_11] == rows[THIRD_DAY_12] == POLE_REASON


def test_the_clause_s_sentence_stands_where_nothing_refused():
    """Both infortunes there and nothing found, the divisions standing: the row keeps
    its sentence, for only a refusal gives the row the reason."""
    chart = E.calculate_traditional_chart_jd(M.swe.julday(1772, 2, 20, 6.0), 40.0, 11.0)
    rows = {row["Item"]: row["Value"] for row in E.evaluate_moon_third_day(chart)}
    assert rows[THIRD_DAY_12] == ("Not met: the two infortunes are in the Ascendant or seventh (Saturn in the 7th, "
                                  "Mars in the 1st); no corruption was established")


def test_the_page_says_it_too():
    at = _pole_page("delineations", THIRD_DAY_CHART)
    assert_no_exception(at, "delineations")
    table = next(df.value for df in at.main.dataframe if any(str(v) == THIRD_DAY_11 for v in df.value.iloc[:, 0]))
    rows = dict(zip(table.iloc[:, 0], table.iloc[:, 1]))
    assert rows[THIRD_DAY_11] == POLE_REASON
    assert rows[THIRD_DAY_12].endswith("no corruption was established")
    assert not [x for x in _said(at) if "Third-day component holds" in x]


def test_a_found_corruption_stands_at_the_pole_and_nothing_found_stands_elsewhere():
    found = _third_day(1950, 90.0, 20.0)
    assert found[THIRD_DAY_11].startswith("Third-day component does not hold: corruption found in these checks")
    plain = _third_day(1954, 50.0, 20.0)
    assert plain[THIRD_DAY_11].startswith("Third-day component holds: no corruption found in these checks")
    assert plain[THIRD_DAY_11].endswith("separate conditions not tested here")


# --- every control on every page that reads the chart, at the pole ------------------
CHART_PAGES = [page for page in PAGES if page not in ("reference", "sources")]
CONTROLS = ("selectbox", "radio", "checkbox")


def _choose(widget, shown):
    """As the browser does, by the option as shown: a control's format_func has no inverse here."""
    if isinstance(shown, bool):
        widget.set_value(shown)
        return
    widget.__class__ = type("ChosenAsShown", (type(widget),), {"index": property(lambda self: None if self._value is None else self.options.index(self._value))})
    widget._value = shown


def _shown_now(kind, widget):
    return widget.value if kind == "checkbox" else None if widget.index is None else widget.options[widget.index]


@pytest.mark.parametrize("page", CHART_PAGES)
def test_every_control_stands_at_the_pole_under_both_lot_readings(page):
    walked = 0
    for rule in E.LOT_HOUSE_CUSP_OPTIONS:
        at = _pole_page(page, rule=rule, depth=READING_DEPTHS[1])
        assert_no_exception(at, page)
        for kind in CONTROLS:
            # By position: three boxes on one page can carry one label.
            for at_position, label in enumerate([widget.label for widget in getattr(at.main, kind)]):
                def control():
                    return getattr(at.main, kind)[at_position]
                was = _shown_now(kind, control())
                for shown in ((True, False) if kind == "checkbox" else list(control().options)):
                    _choose(control(), shown)
                    at.run()
                    assert_no_exception(at, f"{page}, {label}: {shown}")
                    walked += 1
                _choose(control(), was)
                at.run()
    assert walked or page == "victors" or page == "fixed-stars" or page == "sky"
