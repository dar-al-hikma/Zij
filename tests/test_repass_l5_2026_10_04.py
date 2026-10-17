"""Re-pass of 2026-10-04, lane L5 -- the same fact in two places, after the fixes.

The hostile pass of 2026-10-03 found L5-01..L5-12 (and the outside pass's HP-16,
HP-27) at cb7390d; the repair lanes fixed them and their strict xfails are green
on main 428e05e. This file keeps what the re-pass found at 428e05e: a finding
fixed for its reported input but not for a neighbour ("partly"), and new
defects beside a fix. Every test is a strict xfail asserting the RIGHT
behaviour, so it XFAILS today and turns XPASS (failing the run) when fixed.

* L5R-01 -- where the hour is the equal-hour approximation but a sunrise lies
  behind (the first night after the last sunset of the year at 70N), the day
  lord is the civil weekday, not the weekday of that sunrise, while the Chart
  page says "The Lord of the Day is still exact."
* L5-02 (partly) -- the wheel now carries the table's minute across a sign
  boundary but takes the sign glyph from the uncarried longitude.
* L5R-03 -- get_degree_string's whole-minute carry crosses a sign the engine
  does not: one row prints "00° Gem 00'" while its own sign columns say Taurus.
* L5-04 (partly) -- the JSON's precision paragraph still promises unrounded
  values while the ages, arcs and degrees of other tables reach it as the
  page's rounded strings.
* L5-08 (partly) -- a distribution table's Date column runs across the reform
  (Julian dates, then Gregorian ones) and nothing names its calendar.
* L5-10 (partly) -- at the supplement depth the Lots page heads its topical
  table "...; three rows of Abu Ma'shar's" and the export files it under
  "Topical Lots (Sahl, On Nativities)"; past the direction table the export
  files under the releaser's heading a table the page does not draw.
* L5R-02 -- at the supplement depth the Releaser page draws the releaser's
  distribution, its Now line and PN IV's releaser table under the subheader
  "Additions and subtractions to the house-master's years (Abu 'Ali)" (standing
  "Supplement · display only"); the export files them under the releaser's.
* L5R-04 -- an unresolved result whose alternatives are truth values prints
  "if Mercury is diurnal: True; if Mercury is nocturnal: False".
* L5R-05 -- the L5-03 test cannot fail any more: its "or" accepts the word
  "modified" anywhere in the status, and the status now always has that key.
* L5R-06 -- the consistency sweep has lost the second place of facts it
  extracts (the revolution's moment, the elapsed years, the ranking score),
  so its "0 disagreements" no longer compares them.
"""
import json
import re
import sys
from collections import Counter
from datetime import time
from pathlib import Path

import pytest

from conftest import EXECUTABLE_DIR, assert_no_exception, make_app, natal_wheel_envelope, table_nodes

MANUAL = "Manual UTC offset"
SUPPLEMENT = "Course text and supplement"
RELEASER = "The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)"


def _rows(df):
    return [{str(k): v for k, v in row.items()} for row in df.to_dict("records")]


def _tables(at):
    out = {}
    for heading, node in table_nodes(at):
        out.setdefault(heading, node.value)
    return out


def _all_tables(at):
    return [(heading, node.value) for heading, node in table_nodes(at)]


def _markdown_bodies(at):
    out = []
    for node in at.main:
        if getattr(node, "type", "") in ("markdown", "caption"):
            body = getattr(node, "value", None)
            if body is None:
                body = getattr(getattr(node, "proto", None), "body", "")
            out.append(str(body))
    return out


def _strip(at):
    return next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)


def _wheel_texts(at):
    svg = natal_wheel_envelope(at.main)["svg"]
    return [re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)]


def _headings_and_grids(at):
    """As test_f8b_exports_2026_10_04._walk: every subheader and non-notes
    expander over the page's tables, and how many grids stand under each."""
    from test_f8b_exports_2026_10_04 import _walk
    return _walk(at)


# --- L5R-01: the day lord of an approximate hour ------------------------------------

def _first_night_of_the_polar_night(page):
    """70N 25E, 2000-11-26 01:30 at UTC+2 (2000-11-25 23:30 UT): the Sun set at
    10:21 UT on the 25th for the last time that year, after rising at 09:52."""
    at = make_app(date="2000-11-26", page=page)
    at.session_state["time_input_key"] = time(1, 30)
    at.session_state["manual_lat_key"] = 70.0
    at.session_state["manual_lon_key"] = 25.0
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 2.0
    return at.run(timeout=300)


def test_l5r_01_a_day_lord_called_exact_is_the_one_the_sunrise_rule_gives(engine):
    import swisseph as swe
    lat, lon, jd = 70.0, 25.0, swe.julday(2000, 11, 25, 23.5)
    chronocrats = engine["calculate_chronocrats"](jd, lat, lon, 1, 2.0)
    # premise: the night has no end within a day, so the hour is approximate ...
    assert chronocrats["Approximate"] is True, chronocrats
    # ... but the day it belongs to has a beginning: a sunrise 13.6 hours back
    rise = engine["_previous_sun_event"](jd, lat, lon, True)
    assert rise is not None and 0.0 < jd - rise < 1.0, rise
    by_rule = engine["DAY_LORD_BY_WEEKDAY"][engine["_weekday_from_jd"](rise, 2.0)]
    assert by_rule == "Saturn"          # Saturday 2000-11-25's sunrise; the night before reads Venus this way
    at = _first_night_of_the_polar_night("chart")
    assert_no_exception(at, "70N, the first night of the polar night")
    strip = _strip(at)
    shown = re.search(r"Day lord (\w+)", strip).group(1)
    called_exact = any("The Lord of the Day is still exact" in b for b in _markdown_bodies(at))
    # the right behaviour: a day lord the page calls exact is the sunrise rule's;
    # a civil-weekday stand-in is not called exact (and is qualified where it is shown)
    assert shown == by_rule or not called_exact, (shown, by_rule, strip)


# --- L5-02 (partly) and L5R-03: a whole-minute carry across a sign boundary ----------

def _carried_saturn(monkeypatch, page, longitude=60.0 - 1e-10):
    """Saturn a ten-billionth of a degree short of 00° Gemini: inside
    get_degree_string's millionth-of-a-minute tolerance. The carry stops at
    the sign boundary (owner's ruling 4, 2026-10-05), so the table prints
    29° Tau 59', the sign the engine reads."""
    at = make_app(page=page)
    at.session_state["_wheel_layout"] = "Wide"
    import engine
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart["planetary_data"]["Saturn"]["longitude"] = longitude
        return chart
    monkeypatch.setattr(engine, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    assert_no_exception(at, "Saturn at a carried minute")
    return at


def test_l5_02_partly_the_wheel_prints_the_sign_its_carried_minute_is_in(engine, monkeypatch):
    at = _carried_saturn(monkeypatch, "chart")
    table = {r["Planet"]: r for r in _rows(_tables(at)["Planetary Positions"])}["Saturn"]["Position"]
    assert table == "29° Tau 59'", table                      # premise: the carry stops at the boundary (ruling 4)
    texts = _wheel_texts(at)
    shown = texts[texts.index("Saturn") + 1]                   # the Wide panel's Saturn row
    d, glyph, m = re.match(r"(\d{2})° (.)︎? (\d{2})′", shown).groups()
    sign = engine["SIGN_ORDER"][engine["SIGN_GLYPHS"].index(glyph)][:3]
    assert f"{d}° {sign} {m}'" == table, (shown, table)


def test_l5r_03_the_printed_sign_is_the_sign_the_engine_reads(engine, monkeypatch):
    for lon in (30.0 - 1e-10, 60.0 - 1e-10, 360.0 - 1e-12):
        printed = engine["get_degree_string"](lon)
        assert printed[4:7] == engine["get_zodiac_sign"](lon)[:3], (lon, printed, engine["get_zodiac_sign"](lon))
    at = _carried_saturn(monkeypatch, "chart")
    position = {r["Planet"]: r for r in _rows(_tables(at)["Planetary Positions"])}["Saturn"]["Position"]
    signs = [r["Sign"] for _h, df in _all_tables(at) for r in _rows(df)
             if r.get("Point") == "Saturn" and "Sign" in r]
    assert signs, "the sign-categories row for Saturn"
    assert all(position[4:7] == s[:3] for s in signs), (position, signs)


# --- L5-04 (partly): the precision paragraph against every numeric column -------------

def test_l5_04_partly_the_json_rounds_nothing_it_says_it_does_not_round():
    """Ruling 11 (owner, 2026-10-05; Q14, block B1): the JSON keeps the page's
    printed values and its precision paragraph says so -- no "never rounds",
    no "Values are the engine's own" -- and names every column whose bare
    numbers run past the four places a report prints (Planetary Positions'
    Absolute, F8), and no other."""
    at = make_app(page="chart").run(timeout=300)
    assert_no_exception(at, "default chart")
    export = at.session_state["_analysis_export"]
    precision = export["precision"]
    cells = [(heading, column, value)
             for headings in export["results"].values() for heading, entries in headings.items()
             for entry in entries for row in entry["rows"] if isinstance(row, dict)
             for column, value in row.items()]
    rounded = [c for c in cells if isinstance(c[2], str) and re.fullmatch(r"-?\d+\.\d+°?", c[2])]
    full = {f"{column} ({heading})" for heading, column, value in cells
            if isinstance(value, float) and round(value, 4) != value}
    assert rounded, "premise: the JSON carries numbers as the page's rounded strings"
    assert "Absolute (Planetary Positions)" in full, "premise: Positions' Absolute is the calculation's float"
    for claim in ("never rounds", "where a page or a report rounds", "Values are the engine's own", "engine"):
        assert claim not in precision, (claim, precision)
    assert "the values the pages print, as they print them" in precision, precision
    named = {f"{column} ({heading})" for heading, column, _value in cells if f"{column} ({heading})" in precision}
    assert named == full, (sorted(full - named), sorted(named - full))


# --- L5-08 (partly): a Date column across the reform ------------------------------------

def test_l5_08_partly_a_date_column_across_the_reform_names_its_calendar():
    at = make_app(date="1500-05-23", page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1600-06-01"
    at.run(timeout=300)
    assert_no_exception(at, "timing, 1500 birth, target 1600")
    crossing = []
    for heading, node in table_nodes(at):
        df = node.value
        if "Date" in df.columns:
            dates = [str(d) for d in df["Date"].tolist()]
            if any(d[:10] < "1582-10-05" for d in dates) and any(d[:10] > "1582-10-14" for d in dates):
                crossing.append((heading, dates, str(getattr(node, "proto", ""))))
    assert crossing, "premise: a Date column runs across the reform"
    page = _markdown_bodies(at)
    for heading, dates, proto in crossing:
        in_cells = any("Julian" in d for d in dates) and any("Gregorian" in d for d in dates)
        in_help = "Julian" in proto
        on_page = any("Date" in b and "Julian" in b for b in page)
        assert in_cells or in_help or on_page, (heading, [d for d in dates if d.startswith("158")][:4])


# --- L5-10 (partly): export headings and tables against the page -----------------------

def test_l5_10_partly_every_lots_export_heading_is_on_the_page_at_the_supplement_depth():
    at = make_app(page="lots")
    at.session_state["_reading_depth"] = SUPPLEMENT
    at.run(timeout=300)
    assert_no_exception(at, "lots, supplement")
    heads, _grids = _headings_and_grids(at)
    export = at.session_state["_analysis_export"]["results"]["Lots"]
    assert export, "premise: the Lots section is exported"
    missing = sorted(h for h in export if h not in heads)
    assert not missing, (missing, sorted(heads))


def test_l5_10_partly_the_export_files_no_more_releaser_tables_than_the_page_draws():
    at = make_app(page="releaser")
    at.session_state["_reading_depth"] = "Course text"          # no Abu 'Ali block (L5R-02) in the way
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "2026-09-15"              # 786 years: past the 120-year table
    at.run(timeout=300)
    assert_no_exception(at, "releaser, past the table")
    _heads, grids = _headings_and_grids(at)
    entries = at.session_state["_analysis_export"]["results"]["Prediction"][RELEASER]
    assert grids[RELEASER] >= 1, "premise: the page draws tables under the releaser's heading"
    assert len(entries) <= grids[RELEASER], ([(e.get("citation"), len(e["rows"])) for e in entries], grids[RELEASER])


# --- L5R-02: the releaser's tables under Abu 'Ali's heading ------------------------------

def _grids_under_headings(at):
    """[(the last subheader above it, the grid)] in page order."""
    out, heading = [], None
    for node in at.main:
        kind = getattr(node, "type", None)
        if kind == "subheader":
            heading = node.value
        elif kind in ("dataframe", "table"):
            out.append((heading, node.value))
    return out


def test_l5r_02_the_releasers_distribution_stands_under_the_releasers_heading():
    at = make_app(page="releaser")
    at.session_state["_reading_depth"] = SUPPLEMENT
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 30
    at.run(timeout=300)
    assert_no_exception(at, "releaser, supplement, age 30")
    exported = [e for e in at.session_state["_analysis_export"]["results"]["Prediction"][RELEASER]
                if "Distributor" in e["columns"] and not e.get("citation")]
    assert len(exported) == 1, "premise: the export files Sahl's releaser distribution under the releaser's heading"
    n, first = len(exported[0]["rows"]), exported[0]["rows"][0]
    drawn = [heading for heading, df in _grids_under_headings(at)
             if "Distributor" in df.columns and len(df) == n
             and str(df.iloc[0]["Distributor"]) == str(first["Distributor"]) and str(df.iloc[0]["Date"]) == str(first["Date"])]
    assert len(drawn) == 1, ("premise: the page draws that table once", drawn)
    assert drawn[0] == RELEASER, drawn[0]


# --- L5R-04: an alternative that is a truth value ----------------------------------------

def test_l5r_04_an_alternative_that_is_a_truth_value_prints_in_words(monkeypatch):
    at = make_app(page="dignities")
    at.session_state["_reading_depth"] = SUPPLEMENT
    import engine
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart["planetary_data"]["Mercury"]["longitude"] = chart["planetary_data"]["Sun"]["longitude"]
        return chart
    monkeypatch.setattr(engine, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    assert_no_exception(at, "Mercury on the Sun")
    cell = str({r["Planet"]: r for r in _rows(_tables(at)["Sect"])}["Mercury"]["Domain (hayz)"])
    assert cell.startswith("Unassigned"), cell                     # premise: his domain is open
    report = [line for line in at.session_state["_analysis_markdown"].splitlines()
              if line.startswith("| Mercury |") and "depends on its unassigned phase sect" in line]
    assert report, "premise: the open domain reaches the Markdown"
    for text in (cell, *report):
        assert not re.search(r": (True|False)\b", text), text


# --- L5R-05: the L5-03 test, with the defect put back ---------------------------------------

def test_l5r_05_the_l5_03_test_fails_when_the_export_drops_the_modified_name(tmp_path, monkeypatch):
    import test_hostile_l5_2026_10_03 as l5
    app_path = Path(l5.APP_PATH)
    source = app_path.read_text(encoding="utf-8")
    fixed = '_export_name = f"{chart_name} (modified)" if chart_modified else chart_name'
    assert source.count(fixed) == 1, "premise: the fix's one line"
    mutant = tmp_path / "app" / "app.py"
    mutant.parent.mkdir()
    mutant.write_text(source.replace(fixed, "_export_name = chart_name"), encoding="utf-8")
    for name in ("atlas.db", "app_icon.ico"):
        (mutant.parent / name).symlink_to(app_path.parent / name)
    monkeypatch.setattr(l5, "APP_PATH", mutant)
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(AssertionError):
        l5.test_l5_03_an_edited_record_is_named_modified_in_the_export_too(data, monkeypatch)
