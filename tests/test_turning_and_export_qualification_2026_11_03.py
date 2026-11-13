"""A planet on an axial degree in the turning table; II.22's qualification in the exports.

The turning table. PN IV VI.2, 1 has every planet "directed from its degree", and III.1, 12 (PN IV pp. 287-288) says how:
"the Ascendant and the things in it" by the ascensions of the country, "what is in the Midheaven or the fourth" by the
ascensions of the right sphere, "what is not in these three positions" by the book it defers to (fn 16: proportional
semi-arcs). The planets' own table already chose by position; the turning table sent every planet through the third
case, so Jupiter on the Midheaven was named wrongly, and at latitude 70 refused. "On" is floating-point equality with
the degree, not an orb (`PN4_AXIS_TOLERANCE`, 1e-9 of a degree).

The charts below are all 1958-08-22 00:00 UT, Jupiter at about 27 Libra. Each geographic longitude was found by
bisection on the chart's own wrapped gap (Jupiter less the axis) from a one-degree scan of the whole circle, to a gap under
1e-13 of a degree; `_on_the_axis` reads the gap again in every test, so a moved chart fails as a broken premise. Below
1e-9 of a degree a planet is on the degree; there is no other floor.

The exports. PN IV II.22, 1 (PN IV p. 264) opens "If the Moon was the lord of the year". The Revolutions page says that it
is computed in every year, and the JSON, the Markdown and the HTML carried the two tables without saying so. One string
now serves the page and the exports' citation, with this year's lord, as the fixed stars' reading does. A void year
draws neither table on the page, and so neither table nor sentence in the exports.

The charts: the default chart, Target by Date. 2026-10-09 is a year of Mars's; 1249-06-01 is the Moon's own; 1242-06-01
is a void year of Jupiter's, and 1273-06-01 a void year of the Moon's own: each read off the page in the test.
"""
from __future__ import annotations

import ast
import html as H
import re
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app

JD = (1958, 8, 22, 0.0, 0.0)
MC_LON, IC_LON = -124.52203770101613, 55.47796229898387
ASC = {70.0: 176.05064600930928, 40.0: 154.41445547662767, 0.0: 145.47796229898387}
COLUMN = "Directed a year per degree"
ELAPSED = 30.5


def _chart(engine, lat, lon):
    return engine["calculate_traditional_chart_jd"](engine["civil_local_to_jd_ut"](*JD), lat, lon)


def _on_the_axis(engine, chart):
    jupiter = chart["planetary_data"]["Jupiter"]["longitude"]
    return engine["pn4_axis_of"](jupiter, chart["ascendant"], chart["mc"])


def _row(engine, chart, age=30, elapsed=ELAPSED):
    rows = engine["pn4_turning_rows"](chart, age, elapsed=elapsed)
    return next(r for r in rows if r["Point"] == "Jupiter")[COLUMN]


def _dispatcher(engine, chart, elapsed=ELAPSED):
    return engine["pn4_point_distribution"](chart, chart["planetary_data"]["Jupiter"]["longitude"], elapsed, "Jupiter",
                                            significator="Jupiter")


def _agrees_with_the_dispatcher(row, direction):
    assert direction["status"] == "available"
    assert row.startswith(f"by {direction['method']}: in "), row
    assert f"distributor {direction['distributor']}, partner " in row, row
    assert f"partner {direction['partner']} (age " in row, row
    assert row.endswith(" (PN IV III.1, 12)"), row


# --- the turning table: a planet on an axial degree ---------------------------------------------------------


@pytest.mark.parametrize("lat, lon, axis, method", [
    (70.0, MC_LON, "Midheaven", "right ascension"),
    (0.0, MC_LON, "Midheaven", "right ascension"),
    (70.0, IC_LON, "Fourth (IC)", "right ascension"),
    (0.0, IC_LON, "Fourth (IC)", "right ascension"),
    (40.0, ASC[40.0], "Ascendant", "oblique ascension of the birth latitude"),
    (0.0, ASC[0.0], "Ascendant", "oblique ascension of the birth latitude"),
])
def test_a_planet_on_an_axial_degree_is_directed_as_that_degree_is(engine, lat, lon, axis, method):
    chart = _chart(engine, lat, lon)
    assert _on_the_axis(engine, chart) == axis, "premise: the bisected chart"
    direction = _dispatcher(engine, chart)
    assert direction["method"] == method
    row = _row(engine, chart)
    _agrees_with_the_dispatcher(row, direction)
    assert "semi-arcs" not in row and "refused" not in row


def test_jupiter_on_the_midheaven_at_latitude_70_names_the_dispatchers_distributor_and_partner(engine):
    """Saturn and Mars at 30.5 years, read by the dispatcher and the row alike."""
    chart = _chart(engine, 70.0, MC_LON)
    direction = _dispatcher(engine, chart)
    assert (direction["distributor"], direction["partner"]) == ("Saturn", "Mars")
    assert "distributor Saturn, partner Mars (age " in _row(engine, chart)


def test_a_planet_on_the_ascendant_above_the_polar_circle_takes_the_ascendants_refusal(engine):
    """The Ascendant's method rests on the oblique ascension, and refuses there."""
    chart = _chart(engine, 70.0, ASC[70.0])
    assert _on_the_axis(engine, chart) == "Ascendant", "premise: the bisected chart"
    assert _dispatcher(engine, chart)["status"] == "unavailable"
    assert _row(engine, chart) == ("by oblique ascension of the birth latitude: refused at this latitude, where some "
                                   "degrees never rise or set (PN IV III.1, 12)")


def test_an_axial_planet_past_the_table_says_so_under_its_own_method(engine):
    chart = _chart(engine, 70.0, MC_LON)
    assert _dispatcher(engine, chart, elapsed=500.0)["status"] == "unavailable"
    row = _row(engine, chart, age=500, elapsed=None)
    assert row.startswith("by right ascension: age 500 is past the ") and row.endswith(" (PN IV III.1, 12)"), row


def test_without_an_elapsed_age_the_row_stands_at_the_whole_age(engine):
    chart = _chart(engine, 70.0, MC_LON)
    _agrees_with_the_dispatcher(_row(engine, chart, elapsed=None), _dispatcher(engine, chart, elapsed=30))


def test_the_row_stands_at_the_elapsed_age_and_not_at_the_whole_one(engine):
    """Age 30 holds the period running to about 30.9; 31 years elapsed stand in the next."""
    chart = _chart(engine, 70.0, MC_LON)
    at_thirty, at_elapsed = _dispatcher(engine, chart, elapsed=30), _dispatcher(engine, chart, elapsed=31.0)
    assert at_thirty["current"] != at_elapsed["current"], "premise: two periods"
    _agrees_with_the_dispatcher(_row(engine, chart, age=30, elapsed=31.0), at_elapsed)
    assert _row(engine, chart, age=30, elapsed=31.0) != _row(engine, chart, age=30, elapsed=None)


def test_the_turning_row_and_the_planets_table_agree_in_the_bundle(engine):
    chart = _chart(engine, 70.0, MC_LON)
    chronocrats = engine["calculate_chronocrats"](engine["civil_local_to_jd_ut"](*JD), 70.0, MC_LON, 0.0, 0.0)
    bundle = engine["pn4_timing_bundle"](chart, 70.0, MC_LON, engine["CivilDate"](1958, 8, 22), engine["CivilDate"](1989, 2, 20),
                                         engine["PN4_MONTHLY_TURN_OPTIONS"][0], chronocrats)
    planet = next(p for p in bundle["angle_planets"] if p["planet"] == "Jupiter")
    assert planet["axis"] == "Midheaven" and planet["how"] == "right ascension"
    row = next(r for r in bundle["turning_rows"] if r["Point"] == "Jupiter")[COLUMN]
    assert row.startswith("by right ascension: in ")
    assert f"distributor {planet['current']['distributor']}, partner {planet['current']['partner']} (age " in row


# --- the turning table: off the degree, as it was ---------------------------------------------------------


@pytest.mark.parametrize("moved", [1e-6, -1e-6, 1e-8])
@pytest.mark.parametrize("lat, lon", [(70.0, MC_LON), (0.0, MC_LON), (70.0, IC_LON), (40.0, ASC[40.0])])
def test_off_the_degree_a_planet_is_the_third_case(engine, lat, lon, moved):
    chart = _chart(engine, lat, lon + moved)
    assert _on_the_axis(engine, chart) is None, "premise: off the degree"
    jupiter = chart["planetary_data"]["Jupiter"]["longitude"]
    expected = engine["pn4_semi_arc_stand"](chart["planetary_data"], jupiter, chart["obliquity"], chart["geo_lat"],
                                            chart["armc"], ELAPSED, significator="Jupiter")
    assert expected.startswith("by proportional semi-arcs: ")
    assert ("refused" in expected) == (lat == 70.0)
    assert _row(engine, chart) == expected + " (III.1, 12 fn 16)"


def test_the_wording_off_the_degree_is_the_wording_it_was(engine):
    chart = _chart(engine, 40.0, 10.0)
    assert _on_the_axis(engine, chart) is None
    row = _row(engine, chart)
    assert re.fullmatch(r"by proportional semi-arcs: in \w+, standing from [^;]+; distributor \w+, partner .+ "
                        r"\(age [\d.]+ to [\d.]+\) \(III\.1, 12 fn 16\)", row), row
    past = _row(engine, chart, age=500, elapsed=None)
    assert re.fullmatch(r"by proportional semi-arcs: age 500 is past the \d+-year table \(III\.1, 12 fn 16\)", past), past


def test_a_lot_and_a_cusp_are_not_read_as_a_planet_is(engine):
    """III.1, 12's dispatch here is for the seven planets; the Lots and the cusps keep their rows."""
    chart = _chart(engine, 70.0, MC_LON)
    rows = engine["pn4_turning_rows"](chart, 30, elapsed=ELAPSED)
    others = [r[COLUMN] for r in rows if r["Point"] not in engine["PN4_SEVEN"] and "by counting" not in r["Point"]]
    assert others and all(cell.startswith("by proportional semi-arcs") for cell in others), others


def _timing(tmp_path, monkeypatch, target):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / target))
    at = make_app(page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = target
    at.run(timeout=180)
    assert_no_exception(at, "timing")
    assert at.session_state["_analysis_export"]["target"]["date"] == target
    return at


# --- the page's note on the column --------------------------------------------------------------------------


def test_the_page_says_a_planet_on_a_degree_is_directed_as_that_degree_is(tmp_path, monkeypatch):
    at = _timing(tmp_path, monkeypatch, "2026-10-09")
    notes = [str(m.value) for m in at.main.markdown if "The Ascendant's and the meridian's directions" in str(m.value)]
    assert any("The Ascendant's and the meridian's directions are the distributions above, and a planet on one of "
               "those degrees is directed as that degree is." in note for note in notes), notes


# --- the exports: II.22's qualification ------------------------------------------------------------------------

HEADING = "The Moon's connections in her sign, and the portions of the year (PN IV II.22)"
BEFORE_THE_LORD = "This year's lord is "
AFTER_THE_LORD = "; II.22 states the division for a year whose lord is the Moon, and it is computed here in every year."
MOON_TABLE = "| Day from the revolution | Planet | By | Moon at |"
PORTION_TABLE = "| Portion | Owned by | From day | To day |"


def _exports(at):
    return (at.session_state["_analysis_export"], at.session_state["_analysis_markdown"],
            at.session_state["_analysis_html"])


def _page_lines(at, text):
    return [str(m.value) for m in at.main.markdown if text in str(m.value)]


def _sentence(lord):
    return f"{BEFORE_THE_LORD}{lord}{AFTER_THE_LORD}"


@pytest.fixture(scope="module", params=[("2026-10-09", "Mars"), ("1249-06-01", "Moon")], ids=["a-year-of-mars", "the-moons-year"])
def year(request, tmp_path_factory):
    target, lord = request.param
    mp = pytest.MonkeyPatch()
    try:
        return _timing(tmp_path_factory.mktemp("year"), mp, target), lord
    finally:
        mp.undo()


def test_the_page_prints_the_sentence_as_it_did(year):
    at, lord = year
    lines = _page_lines(at, "II.22 states the division")
    assert len(lines) == 1
    assert lines[0].endswith(f" (II.22, 2). This year's lord is **{lord}**; II.22 states the division for a year whose "
                             "lord is the Moon, and it is computed here in every year."), lines[0]


def test_the_json_carries_it_with_each_table(year):
    at, lord = year
    entries = _exports(at)[0]["results"]["Prediction"][HEADING]
    assert [sorted(e["columns"]) for e in entries] == [sorted(["Day from the revolution", "Planet", "By", "Moon at"]),
                                                       sorted(["Portion", "Owned by", "From day", "To day"])]
    assert [e.get("citation") for e in entries] == [_sentence(lord), _sentence(lord)]
    assert ["label" in e for e in entries] == [False, False]


def test_the_markdown_carries_it_once_beside_each_table(year):
    at, lord = year
    _, md, _ = _exports(at)
    assert md.count(_sentence(lord)) == 2
    for head in (MOON_TABLE, PORTION_TABLE):
        assert md.count(f"*{_sentence(lord)}*\n\n{head}") == 1, head


def test_the_html_carries_it_once_beside_each_table(year):
    at, lord = year
    _, _, doc = _exports(at)
    assert doc.count(H.escape(_sentence(lord))) == 2
    for first in ("Day from the revolution", "Portion"):
        block = f"<p class='cite'>{H.escape(_sentence(lord))}</p><div class='wrap'><table><thead><tr><th>{first}</th>"
        assert doc.count(block) == 1, first


def test_the_page_and_the_exports_read_one_string():
    """The sentence's words stand once in the program, and the page and the two entries all call for them."""
    tree = ast.parse((Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8"))
    words = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and "for a year whose lord is the Moon" in node.value]
    assert len(words) == 1, words
    reading = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                   and node.name == "_moon_division_reading")
    assert words[0] in list(ast.walk(reading))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "_moon_division_reading"]
    assert len(calls) == 3


@pytest.mark.parametrize("target, lord", [("1242-06-01", "Jupiter"), ("1273-06-01", "Moon")], ids=["jupiters", "the-moons"])
def test_a_void_year_draws_neither_the_tables_nor_the_sentence(tmp_path, monkeypatch, target, lord):
    at = _timing(tmp_path, monkeypatch, target)
    assert len(_page_lines(at, "**without perfecting a connection**")) == 1, "premise: a void year"
    assert _page_lines(at, f"This year's lord is **{lord}**"), "premise: this year's lord"
    assert _page_lines(at, "II.22 states the division") == []
    exp, md, doc = _exports(at)
    assert HEADING not in exp["results"]["Prediction"]
    assert AFTER_THE_LORD not in md and H.escape(AFTER_THE_LORD) not in doc
    assert MOON_TABLE not in md and PORTION_TABLE not in md
