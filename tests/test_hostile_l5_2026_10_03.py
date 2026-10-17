"""Hostile pass of 2026-10-03, lane L5 -- the same fact in two places.

The lane's question: a value, verdict, count or label computed once and
shown on several pages, or on a page and in the three exports -- does it
always agree, is every qualification carried to every place the value
appears, and is every "Not present in this chart" line honest about a
bounded search? The sweep that asks it over a list of charts is
the consistency sweep (development-only); this file keeps the reproductions.

The ``xfail(strict=True)`` tests assert the RIGHT behaviour and fail today,
so they mark open defects; when one is fixed the strict marker says
"un-xfail me". The plain tests are the attacks that held, pinned.

Findings (ids as in the lane report):

* L5-01 -- where no temporal hour exists, the strip says "Hour lord Sun
  (equal-hour approximation)" but the wheel's own sect line prints the hour
  lord unqualified, and so do the tables built from it.
* L5-02 -- _wheel_dm lacks get_degree_string's whole-minute tolerance, so
  the wheel and the Positions table can print a minute apart.
* L5-03 -- a loaded record edited since it was saved is "Rec (modified)"
  on the strip and "Rec" in every export, with no field saying so.
* L5-04 -- the JSON's precision paragraph promises the engine's own values,
  but the Positions table's Absolute column is the page's rounded string.
* L5-05 -- with the supplement off, the syzygy table attributes its
  triplicity table (and a Virgo partner) to the Great Introduction.
* L5-06 -- Mercury's sect: Diurnal / of the chart's sect on the Dignities
  page, "One sect: no" and "In the sect of the chart: no" on Configurations.
* L5-07 -- an empty Prevented connections joins "Not present in this
  chart" although two of its kinds are a 200-day forward search.
"""
import json
import os
import re
import subprocess
import sys
from datetime import time
from pathlib import Path

import pytest

from conftest import (APP_PATH, EXECUTABLE_DIR, assert_no_exception, make_app, natal_wheel_envelope,
                      sync_engine_to_environment, table_nodes)


PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00",
            "time_standard": "Standard time (pytz)", "utc_offset": None,
            "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533,
            "target_mode": "Date", "target_date": "2026-09-15", "target_age": 43}
MANUAL = "Manual UTC offset"



def _markdown_bodies(at):
    """Every markdown and caption body on the rendered page, in order (Block.__iter__
    walks the tree, as conftest.table_nodes relies on)."""
    out = []
    for node in at.main:
        if getattr(node, "type", "") in ("markdown", "caption"):
            body = getattr(node, "value", None)
            if body is None:
                body = getattr(getattr(node, "proto", None), "body", "")
            out.append(str(body))
    return out

def _tables(at):
    """{heading: the FIRST dataframe under it}; several tables share the
    governor's heading, so a lookup there wants _all_rows."""
    out = {}
    for heading, node in table_nodes(at):
        out.setdefault(heading, node.value)
    return out


def _all_rows(at, prefix):
    """Every row of every dataframe whose heading starts with prefix."""
    return [row for heading, node in table_nodes(at) if heading.startswith(prefix) for row in _rows(node.value)]


def _rows(df):
    return [{str(k): v for k, v in row.items()} for row in df.to_dict("records")]


def _strip(at):
    return next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)


def _polar(page, layout="Wide"):
    at = make_app(date="2000-06-21", page=page)
    at.session_state["time_input_key"] = time(12, 0)
    at.session_state["manual_lat_key"] = 70.0
    at.session_state["manual_lon_key"] = 25.0
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 2.0
    at.session_state["_wheel_layout"] = layout
    return at.run(timeout=300)


def _wheel_texts(at):
    svg = natal_wheel_envelope(at.main)["svg"]
    return [re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)]


# --- L5-08: every UT on the Prediction pages names its calendar ----------------

_UT_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}\**\s+\d{2}:\d{2}")       # a date and a clock, the date perhaps in bold


def _prediction_page(page, target):
    at = make_app(date="1240-05-23", page=page)
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = target
    at.run(timeout=300)
    assert_no_exception(at, f"{page} at {target}")
    return at


@pytest.mark.parametrize("target,calendar", [("1281-05-23", "Julian calendar"), ("1600-06-01", "Gregorian calendar")])
def test_l5_08_every_ut_on_the_prediction_pages_names_its_calendar(target, calendar):
    for page in ("timing", "releaser", "days", "fardar"):
        at = _prediction_page(page, target)
        bodies = [b for b in _markdown_bodies(at) if b != _strip(at)]       # the strip is the birth's LOCAL moment
        cells = [str(v) for heading, node in table_nodes(at) for row in _rows(node.value) for v in row.values()]
        texts = bodies + cells
        assert len(texts) > 20 and [t for t in texts if "UTC" in t] == [], [t for t in texts if "UTC" in t][:3]
        clocks = [t for t in texts if _UT_CLOCK.search(t)]
        assert clocks, f"{page}: no UT moment found"          # the header's revolution moment at the least
        for t in clocks:
            assert "UT" in t and "calendar" in t, (page, t[:160])
        # the calendar named is the one the moment falls in, as the sidebar names it
        assert any(calendar in t for t in clocks), (page, target, clocks[:3])


# --- L5-01: the hour lord's qualification travels with the value --------------

def test_l5_01_wheel_sect_line_carries_the_hour_lord_qualification():
    """Fixed (one horizon): the wheel's sect line qualifies the hour lord as
    the strip does where no temporal hour exists."""
    at = _polar("chart")
    assert_no_exception(at, "polar chart")
    strip = _strip(at)
    assert "equal-hour approximation" in strip, strip
    line = next(t for t in _wheel_texts(at) if t.startswith("Sect:"))
    assert "Lord of the hour:" in line, line
    assert "approx" in line.lower(), f"the wheel qualifies the hour lord as the strip does: {line!r}"


def test_l5_01_coverage_the_strip_and_the_indicator_qualify_the_equal_hour():
    """What held: the strip on every page, the export's status flag and
    the lord-of-the-orb indicator all say the hour is an approximation."""
    at = _polar("timing")
    assert_no_exception(at, "polar timing")
    assert "equal-hour approximation" in _strip(at)
    assert at.session_state["_analysis_export"]["status"]["equal_hour_approximation"] is True
    rows = next(_rows(df) for h, df in _tables(at).items() if h.startswith("Indicators of the year"))
    five = next(r for r in rows if str(r["#"]) == "5")
    assert "approximate" in str(five["Active point"]), five


# --- L5-02: two truncations of one minute ---------------------------------------

def test_l5_02_wheel_minutes_follow_get_degree_string_at_a_whole_minute(engine):
    for lon in (30 + 1 / 60, 0.0166666666, 89.99999999999, 59.999999999):
        table = engine["get_degree_string"](lon)
        d, m = engine["_wheel_dm"](lon)
        # compare the numbers: the sign is the seam tests' (the carry stops at a sign's end, ruling on Q6)
        assert (f"{d:02d}", f"{m:02d}") == (table[:2], table[-3:-1]), (lon, table, (d, m))


def test_l5_02_coverage_the_two_formatters_agree_away_from_the_boundary(engine):
    for lon in (74.699, 45.75210000000001, 12 + 27 / 60 + 40 / 3600, 29.99999, 359.9999999, 0.0, 360.0):
        table = engine["get_degree_string"](lon)
        d, m = engine["_wheel_dm"](lon)
        sign = engine["SIGN_ORDER"][int((lon % 360.0) // 30)][:3]
        assert f"{d:02d}° {sign} {m:02d}'" == table, (lon, table, (d, m))


def test_l5_02_sweep_the_wheel_equals_the_table_at_every_minute_boundary(engine):
    lons = [29 + 59.9999 / 60, 359 + 59.9999 / 60, 30 + 1 / 60, 360.0, -1e-9]
    for k in range(0, 360 * 60, 71):
        for eps in (0.0, 1e-9, -1e-9, 1e-7, -1e-7, 0.9999999999):
            lons.append((k + eps) / 60.0)
    lons += [i * 0.37 + 0.999999 / 60 for i in range(300)]
    assert len(lons) > 300
    for lon in lons:
        table = engine["get_degree_string"](lon)
        d, m = engine["_wheel_dm"](lon)
        assert (f"{d:02d}", f"{m:02d}") == (table[:2], table[-3:-1]), (lon, table, (d, m))


# --- L5-03: the edited record's name ---------------------------------------------

def _loaded_record(tmp_path, monkeypatch, page="chart"):
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = tmp_path / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    (d / "saved_charts.json").write_text(json.dumps({"Rec": PETOSKEY}))
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash(page)
    at.run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    return at


def test_l5_03_an_edited_record_is_named_modified_in_the_export_too(tmp_path, monkeypatch):
    at = _loaded_record(tmp_path, monkeypatch)
    assert _strip(at).startswith("Rec ·"), _strip(at)
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 10
    at.run()
    assert_no_exception(at, "edited record")
    strip_name = _strip(at).split(" · ")[0]
    assert strip_name == "Rec (modified)", strip_name
    export = at.session_state["_analysis_export"]
    md_title = at.session_state["_analysis_markdown"].splitlines()[0].replace("# Analysis: ", "")
    html_title = re.search(r"<title>Analysis: (.*?)</title>", at.session_state["_analysis_html"]).group(1)
    # Both halves, each on its own: the name in every export AND the status's flag.
    # The 'or' these lines had was met by the key "modified" that every status
    # carries, true or false, so the test held with the export's name put back to
    # the bare record name (re-pass L5R-05).
    modified_flagged = "modified" in json.dumps(export["status"]).lower()
    assert modified_flagged and export["status"]["modified"] is True, export["status"]
    assert export["chart"] == strip_name, (export["chart"], export["status"])
    assert md_title == strip_name, md_title
    assert html_title == strip_name, html_title


def test_l5_03_coverage_an_unedited_record_has_one_name_everywhere(tmp_path, monkeypatch):
    at = _loaded_record(tmp_path, monkeypatch)
    assert_no_exception(at, "loaded record")
    export = at.session_state["_analysis_export"]
    assert _strip(at).split(" · ")[0] == "Rec"
    assert export["chart"] == "Rec"
    assert at.session_state["_analysis_markdown"].splitlines()[0] == "# Analysis: Rec"
    assert "<title>Analysis: Rec</title>" in at.session_state["_analysis_html"]


# --- L5-04: the JSON's precision claim ------------------------------------------

def test_l5_04_the_json_carries_the_engine_longitude_it_claims_to(engine):
    at = make_app(page="chart").run(timeout=300)
    export = at.session_state["_analysis_export"]
    assert "the JSON does not" in export["precision"]
    rows = export["results"]["Chart"]["Planetary Positions"][0]["rows"]
    for row in rows:
        assert isinstance(row["Absolute"], float), (row["Planet"], row["Absolute"])


def test_l5_04_coverage_the_markdown_and_html_print_the_same_cells():
    """What held: the Markdown and the HTML exports print identical cell
    text for every table (one cell printer serves both), and both carry
    as many tables as the JSON."""
    at = make_app(page="chart").run(timeout=300)
    md = at.session_state["_analysis_markdown"]
    html = at.session_state["_analysis_html"]
    export = at.session_state["_analysis_export"]
    md_tables, current = [], None
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
            current = current if current is not None else []
            if not all(c == "---" for c in cells):
                current.append([c.replace("\\|", "|").replace("&lt;", "<").replace("&gt;", ">") for c in cells])
        elif current:
            md_tables.append(current)
            current = None
    if current:
        md_tables.append(current)
    import html as H
    html_tables = []
    for table in re.findall(r"<table>(.*?)</table>", html, re.S):
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            rows.append([H.unescape(c.replace("<br>", "\n")).strip() for c in re.findall(r"<t[hd]>(.*?)</t[hd]>", tr, re.S)])
        html_tables.append(rows)
    json_tables = 7 + sum(len(entries) for headings in export["results"].values() for entries in headings.values())
    assert len(md_tables) == len(html_tables) == json_tables
    squeeze = lambda s: re.sub(r"\s+", " ", s)
    for a, b in zip(md_tables, html_tables):
        assert len(a) == len(b)
        for ra, rb in zip(a, b):
            assert [squeeze(c) for c in ra] == [squeeze(c) for c in rb]


# --- L5-05: the supplement's attribution with the supplement off -------------------

def test_l5_05_course_text_depth_does_not_attribute_the_syzygy_partner_to_the_supplement():
    at = make_app(date="1240-08-22", page="victors")
    at.session_state["_reading_depth"] = "Course text"
    at.run(timeout=300)
    assert_no_exception(at, "victors, course text")
    syz = {r["Metric"]: str(r["Value"]) for r in _rows(_tables(at)["Prenatal Lunation (Syzygy)"])}
    assert syz["Position"].endswith("Vir 59'"), syz["Position"]
    assert "Great Introduction" not in syz["Triplicity table"], syz["Triplicity table"]
    assert "Partner: Mercury" not in syz["Triplicity Lords"], syz["Triplicity Lords"]


def test_l5_05_coverage_the_governor_reads_the_sect_lord_whatever_the_table():
    """What held: the governor and the almuten read the day/night lord
    only, so the table's partner changes nothing computed."""
    results = {}
    for depth in ("Course text", "Course text and supplement"):
        at = make_app(date="1240-08-22", page="victors")
        at.session_state["_reading_depth"] = depth
        at.run(timeout=300)
        syz = {r["Metric"]: str(r["Value"]) for r in _rows(_tables(at)["Prenatal Lunation (Syzygy)"])}
        results[depth] = (syz["Governor of the syzygy degree (Sahl, On Nativities 1.7, 3-7)"],
                          next(v for k, v in syz.items() if k.startswith("Almuten")))
    assert results["Course text"] == results["Course text and supplement"], results


# --- L5-06: Mercury's sect on two pages ------------------------------------------

def _mercury_sect_rows(date):
    at = make_app(date=date, page="dignities").run(timeout=300)
    sect = {r["Planet"]: r for r in _rows(_tables(at)["Sect"])}
    at2 = make_app(date=date, page="configurations")
    at2.session_state["_reading_depth"] = "Course text and supplement"
    at2.run(timeout=300)
    pairs = [r for h, df in _tables(at2).items() if h.startswith("Right-sidedness")
             for r in _rows(df) if "Mercury" in str(r["Pair"])]
    return at, sect, pairs


def test_l5_06_mercurys_sect_reads_the_same_on_dignities_and_configurations():
    at, sect, pairs = _mercury_sect_rows("1240-05-23")
    assert sect["Mercury"]["Planet's sect"] == "Diurnal" and sect["Mercury"]["Of the chart's sect"] == "Yes"
    assert "Diurnal" in _strip(at)
    saturn_mercury = next(r for r in pairs if r["Pair"] == "Saturn and Mercury")
    # Saturn is diurnal, Mercury diurnal by phase, the chart diurnal: one
    # sect, and in the sect of the chart.
    assert saturn_mercury["One sect"] == "yes", saturn_mercury
    assert saturn_mercury["In the sect of the chart (2.5, 1)"] == "yes", saturn_mercury


def test_l5_06_coverage_the_other_six_planets_sects_agree_between_the_two_tables():
    at, sect, _pairs = _mercury_sect_rows("1240-05-23")
    at2 = make_app(date="1240-05-23", page="configurations")
    at2.session_state["_reading_depth"] = "Course text and supplement"
    at2.run(timeout=300)
    fixed = {"Sun": "Diurnal", "Jupiter": "Diurnal", "Saturn": "Diurnal", "Moon": "Nocturnal", "Venus": "Nocturnal", "Mars": "Nocturnal"}
    for planet, expected in fixed.items():
        assert sect[planet]["Planet's sect"] == expected, (planet, sect[planet])
    for h, df in _tables(at2).items():
        if h.startswith("Right-sidedness"):
            for r in _rows(df):
                a, _, b = str(r["Pair"]).partition(" and ")
                if a in fixed and b in fixed:
                    assert r["One sect"] == ("yes" if fixed[a] == fixed[b] else "no"), r


# --- L5-07: an absence line over a bounded search ---------------------------------

def test_l5_07_an_empty_prevented_connections_names_the_horizon_of_its_search(engine):
    at = make_app(date="1240-01-08", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    assert_no_exception(at, "1240-01-08 configurations")
    assert not any(h.startswith("Prevented connections") for h in _tables(at)), "the chart has prevented connections after all"
    absence = [c.value for c in at.main.caption if "Not present in this chart" in c.value and "Prevented" in c.value]
    assert not absence, absence
    horizon = str(engine["FAVOR_SEARCH_DAYS"])
    said = [b for b in _markdown_bodies(at) if "Prevented" in b and horizon in b]
    assert said, "nothing beside the empty Prevented connections names the search's horizon"


def test_l5_07_coverage_forward_looking_conditions_names_its_horizon_when_empty():
    """What held: the one finding built with absent= says what it searched."""
    at = make_app(date="1240-01-08", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    bodies = _markdown_bodies(at)
    drawn = any(h.startswith("Forward-Looking Conditions") for h in _tables(at))
    said = any("200 days" in b and "later events were not evaluated" in b for b in bodies)
    # either the table is drawn (a row was found) or the absence sentence names the horizon
    assert drawn or said, bodies[:5]
    # and the horizon the sentence or the heading names is the engine's
    assert any("200 days" in b for b in bodies), "the 200-day horizon is named beside Forward-Looking Conditions"


# --- Attacks that held -------------------------------------------------------------


def test_held_an_unresolved_governor_reads_the_same_in_three_places():
    at = make_app(date="1240-05-20", page="victors").run(timeout=300)
    syz = {r["Metric"]: str(r["Value"]) for r in _rows(_tables(at)["Prenatal Lunation (Syzygy)"])}
    page = syz["Governor of the syzygy degree (Sahl, On Nativities 1.7, 3-7)"]
    assert page.startswith("unresolved between Moon and Saturn"), page
    export = at.session_state["_analysis_export"]
    rows = export["results"]["Lunation and victors"]["Prenatal Lunation (Syzygy)"][0]["rows"]
    exported = next(str(r["Value"]) for r in rows if r["Metric"].startswith("Governor of the syzygy"))
    assert exported == page
    at2 = make_app(date="1240-05-20", page="findings").run(timeout=300)
    assert any(b == page for b in _markdown_bodies(at2)), "the Findings page repeats the same judgment"


def test_held_the_target_survives_an_age_date_age_round_trip_on_the_widgets():
    at = make_app(page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "2026-09-15"
    at.run(timeout=300)
    at.main.radio(key="target_mode").set_value("Age").run(timeout=300)
    at.main.number_input(key="target_age").set_value(41).run(timeout=300)
    at.main.radio(key="target_mode").set_value("Date").run(timeout=300)
    assert at.main.text_input(key="target_date").value == "1281-05-23"
    at.main.radio(key="target_mode").set_value("Age").run(timeout=300)
    assert at.main.number_input(key="target_age").value == 41
    header = next(b for b in _markdown_bodies(at) if "-- age" in b)
    assert header.startswith("**1281-05-23** -- age **41** completed"), header
    target = at.session_state["_analysis_export"]["target"]
    assert {k: target[k] for k in ("mode", "date", "age")} == {"mode": "Age", "date": "1281-05-23", "age": 41}


def test_held_the_ut_across_the_reform_agrees_between_sidebar_calculation_and_export():
    at = make_app(date="1582-10-15", page="chart")
    at.session_state["time_input_key"] = time(0, 30)
    at.session_state["manual_lon_key"] = 75.0
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 5.0
    at.run(timeout=300)
    assert_no_exception(at, "reform")
    calc = {r["Quantity"]: r["Value"] for r in _rows(_tables(at)["Calculation"])}
    assert calc["Universal time"].startswith("1582-10-04 19:30:00 UT (Julian calendar"), calc["Universal time"]
    box = next(i.value for i in at.sidebar.info if "UT " in i.value)
    assert "UT 1582-10-04 19:30:00 · Julian calendar" in box, box
    export = at.session_state["_analysis_export"]["input"]
    assert export["calendar"] == "Gregorian calendar" and export["ut_calendar"].startswith("Julian calendar")


def test_held_an_unresolved_testimony_is_counted_apart_on_the_page_and_in_the_export():
    at = make_app(date="1240-01-01", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    strength = next(_rows(df) for h, df in _tables(at).items() if h == "Strength of the Planets")
    mercury = next(r for r in strength if r["Planet"] == "Mercury")
    assert str(mercury["Count"]) == "2" and float(mercury["Unresolved"]) == 1.0, mercury
    export = at.session_state["_analysis_export"]
    row = next(r for r in export["results"]["Configurations"]["Strength of the Planets"][0]["rows"] if r["Planet"] == "Mercury")
    assert row["Count"] == 2 and row["Unresolved Count"] == 1
    md = at.session_state["_analysis_markdown"]
    line = next(l for l in md.splitlines() if l.startswith("| Mercury |") and "Advancing (83)" in l)
    assert "Unresolved" in line


def test_held_mercury_on_the_sun_leaves_the_distribution_partner_open_in_every_place(monkeypatch):
    """The tie route for the distributions: Mercury moved onto the Sun
    makes two partners open the Ascendant's first period at one degree.
    The table, the Now line, the indicator, the governor's tally and the
    export all say so; none picks a planet."""
    at = make_app(page="timing")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 1
    import engine
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart["planetary_data"]["Mercury"]["longitude"] = chart["planetary_data"]["Sun"]["longitude"]
        return chart
    monkeypatch.setattr(engine, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    assert_no_exception(at, "tied partner")
    # The owner's ruling 52 (2026-10-06), after rulings 14, 19 and 33
    # (PN IV III.1, 50): the two met at one degree are partners together, so
    # every place names both and none says "Unresolved"; the assertions about
    # the tie follow.
    tables = _tables(at)
    now_row = next(r for h, df in tables.items() if h.startswith("The distribution from the Ascendant")
                   for r in _rows(df) if str(r.get("Now", "")).strip())
    assert str(now_row["Partner"]) == "Mercury and Sun", now_row
    indicators = next(_rows(df) for h, df in tables.items() if h.startswith("Indicators of the year"))
    three = next(r for r in indicators if str(r["#"]) == "3")
    assert str(three["Ruler"]) == "Mercury and Sun", three
    now_line = next(b for b in _markdown_bodies(at) if "**Now**" in b and "Midheaven" not in b and "Fourth" not in b)
    assert "partner **Mercury and Sun**" in now_line and "nresolved" not in now_line, now_line
    governor = _all_rows(at, "The governor (PN IV IX.9")
    partner = next(r for r in governor if str(r.get("Testimony", "")).startswith("The partner to them both"))
    assert "the Ascendant's are Mercury and Sun, together" in str(partner["Planet"]), partner
    assert str(partner["Planet"]).startswith("Mercury;") and str(partner["Counted"]) == "yes", partner
    export = at.session_state["_analysis_export"]
    exported = next(r for r in export["results"]["Prediction"]["Indicators of the year, in Abu Ma'shar's order (PN IV II.1, 5-24)"][0]["rows"]
                    if str(r["#"]) == "3")
    assert exported["Ruler"]["display"] == "Mercury and Sun", exported
    assert "Mercury by trine and Sun by trine" in exported["Active point"], exported


def _tied_partner_indicator_row(monkeypatch):
    at = make_app(page="timing")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 1
    import engine
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart["planetary_data"]["Mercury"]["longitude"] = chart["planetary_data"]["Sun"]["longitude"]
        return chart
    monkeypatch.setattr(engine, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    assert_no_exception(at, "tied partner")
    export = at.session_state["_analysis_export"]
    return next(r for r in export["results"]["Prediction"]["Indicators of the year, in Abu Ma'shar's order (PN IV II.1, 5-24)"][0]["rows"]
                if str(r["#"]) == "3")


def test_l5_12_an_unresolved_ruler_is_typed_in_the_export_like_its_active_point(monkeypatch):
    row = _tied_partner_indicator_row(monkeypatch)
    # The owner's ruling 52 (2026-10-06), after rulings 14, 19 and 33
    # (PN IV III.1, 50): the two partners are read together, so the Active
    # point is the settled sentence naming both, and the Ruler stays typed --
    # the pair, not a flattened sentence.
    assert isinstance(row["Active point"], str) and "together (PN IV III.1, 50)" in row["Active point"], row["Active point"]
    assert isinstance(row["Ruler"], dict) and row["Ruler"]["result_type"] == "PN4Together", row["Ruler"]
    assert row["Ruler"]["values"] == ["Mercury", "Sun"], row["Ruler"]


# --- L5-11: an alternative with an empty value prints a conditional with no consequence ---

def _saturn_model_cells(at):
    """Saturn's Model cell in the governor's candidate table: as the page
    draws it, as the export's JSON carries it (typed, with its display
    string), and the Markdown lines that hold it."""
    page = next(str(row["Model"]) for _h, node in table_nodes(at) if "Model" in node.value.columns
                for _i, row in node.value.iterrows() if str(row["Planet"]) == "Saturn")
    export = at.session_state["_analysis_export"]
    exported = next(r for tables in export["results"].values() for entries in tables.values()
                    for entry in entries for r in entry["rows"]
                    if isinstance(r, dict) and r.get("Planet") == "Saturn" and "Model" in r)
    model = exported["Model"]
    assert isinstance(model, dict) and model["result_type"] == "UnresolvedResult", model
    markdown = [line for line in at.session_state["_analysis_markdown"].splitlines()
                if line.startswith("| Saturn |") and "eastern preference" in line]
    return page, model, markdown


def test_l5_11_an_empty_alternative_prints_nothing():
    at = make_app(date="1240-05-20", page="victors")
    at.run()
    assert_no_exception(at, "victors page, 1240-05-20")
    page, model, markdown = _saturn_model_cells(at)
    # premise: Saturn's Model turns on the Moon's eastern preference, and one route gives him nothing
    alternatives = {a["name"]: a["value"] for a in model["alternatives"]}
    assert alternatives == {"if Moon eastern preference not met": "the pick", "if Moon eastern preference met": ""}, alternatives
    # the right behaviour: the empty alternative prints nothing, in every rendering, and the JSON keeps it
    assert markdown, "Saturn's row is not in the Markdown"
    for text in (page, model["display"], *markdown):
        assert "if Moon eastern preference not met: the pick" in text, text
        assert not re.search(r"met: *[);|]", text), text
        assert "if Moon eastern preference met" not in text, text


# --- The sweep tool over a small fixed input -----------------------------------------


