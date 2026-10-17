"""Hostile pass of 2026-09-22 -- the falsification report's reproductions.

An adversarial sweep of the whole input surface before v1.4.0, run by an
agent with no build context against a clone served on its own port (8526),
with XDG_DATA_HOME pointed at a scratch copy of the owner's data. The prose
account is process/tae_docs/HOSTILE_PASS_2026-09-22.md; this file keeps the
reproductions in the suite (the model is tests/test_hostile_pass_2026_09_16.py).

The ``xfail(strict=True)`` tests assert the RIGHT behaviour and fail today,
so they mark open defects: when one is fixed the test xpasses and the strict
marker turns that into a failure that says "un-xfail me". The plain tests are
the coverage -- what the pass tried to break and could not, pinned so it
stays broken-proof.

Findings (severity by consequence: a misleading stored record is critical;
a lost shell or a wrong qualification is high; friction is medium):

* H1 -- a saved record whose target_age is a huge integer-valued number
  (3e9, 1e19, 1e300) passes chart_record_fault (non-negative, integral) and
  crashes the whole script on load with an OverflowError from swe.julday;
  as the last chart it is dead-on-open on every page, Reference included.
  The H3 class of the previous pass, reopened through the one field whose
  range check has no upper bound.
* M1 -- the city box hands its text to SQL LIKE unescaped, so "%" or "_"
  alone matches every city and casts a confident chart for Shanghai, the
  most populous match; "Flor%" casts Florianopolis.
* M2 -- switching "Enter coordinates directly" OFF after a record has been
  loaded (or after a pair was typed into the fields) casts the chart for
  the city text left in the box, the example's "Florence": the change of
  input method changes the place, the one thing F02 held it must not do.
* M3 -- a target date before the birth is accepted: the Prediction pages
  say "age 0 completed ... the target is in month 1 of 12" and the
  revolution table prints a negative "years elapsed"; a birth after today
  produces the same by itself.
* M4 -- across the Julian/Gregorian reform the sidebar's box and the
  Calculation table print the UT in the Gregorian calendar under a label
  that says "Julian calendar": 1582-10-04 23:00 Detroit reads "UT
  1582-10-15 04:32:00 · Julian calendar (before the reform of 1582-10-15)".
* M5 -- the panel a click on the wheel opens prints the engine's own keys as
  condition names: PlanetSect, ContraryDomain, UnderBeams, Exalt -- the
  same facts the Dignities page calls "Of the chart's sect", "Domain
  (hayz)", "Exaltation".
* L1 -- the answer key under every tick grid ends each testimonies cell with
  a dangling "; ".
* L2 -- the Markdown export prints Python's None, True and False in cells the
  page shows blank or as a checkbox, and unrounded floats where the page
  rounds, against its own precision paragraph.
* L3 -- Favor & Recompense's 200-day search for the recompense is unstated
  where it finds nothing: the column simply vanishes.
* L4 -- an unsaved chart is "Unsaved chart" in the strip and "Transits" in
  the wheel's hub and the export's title and file name.
* L5 -- the ephemeris refusal says the span "covers 3000 BC to 3000 AD" and
  refuses dates in the last months of 3000 AD.
* L6 -- a city text with surrounding spaces matches nothing, while a typed
  coordinate pair tolerates them.
* L7 -- "Net" names two different numbers for one planet: the VII.6 Net of
  the Configurations page's Planetary Condition (Jupiter 3 on the default
  chart) and the Dignities page's ranking-convenience Net (Jupiter 5).
* M6 -- the analysis export carries a fixed list of tables, not what the
  pages draw: Planetary Condition, Prevented connections, Handing Over,
  Non-reception, Transfer, Collection and Reflection of Light, Banished,
  the spear-bearing tables, Corruption of the Moon and the Fardar page's
  tables are absent, and nothing in either file says so.
"""
import json
import math
import os
import re
from collections import namedtuple
from datetime import time
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import (APP_PATH, CHARTS, PAGES, READING_DEPTHS, assert_no_exception, make_app,
                      sync_engine_to_environment)

PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00",
            "time_standard": "Standard time (pytz)", "utc_offset": None,
            "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533,
            "target_mode": "Date", "target_date": "2026-09-15", "target_age": 43}
PETOSKEY_STATE = {"manual_lat_key": 45.37334, "manual_lon_key": -84.95533,
                  "time_input_key": time(11, 44), "time_standard_key": "Standard time (pytz)"}

# What a page must never print: a Python repr, a NaN, an object address.
REPR_LEAK = re.compile(r"UnresolvedResult\(|YearsOutcome\(|object at 0x|<class |Traceback|\{'|\[\(|dict_")


def _data_dir():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fresh_launch(page="chart"):
    """An AppTest that seeds nothing -- a browser session, so the launch
    autoload and the preferences read run as they do for a real open."""
    from streamlit.testing.v1 import AppTest
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash(page)
    return at


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children:
        for child in (children.values() if isinstance(children, dict) else children):
            yield from _walk(child)


def _unescape(text):
    """A protobuf text-format string literal back to its text: the quote and
    newline escapes, and the octal bytes non-ASCII is written as."""
    text = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), text)
    try:
        text = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def _strings(root):
    """Every string a rendered tree carries: the text protos' fields and
    every dataframe cell, as (where, text) pairs."""
    for node in _walk(root):
        kind = getattr(node, "type", "")
        if kind in ("dataframe", "table"):
            df = node.value
            for col in df.columns:
                yield (f"column {col}", str(col))
                for value in df[col].tolist():
                    yield (f"cell {col}", str(value))
            continue
        proto = getattr(node, "proto", None)
        if proto is None:
            continue
        for m in re.finditer(r'(\w+): "((?:[^"\\]|\\.)*)"', str(proto)):
            if m.group(1) in ("id", "form_id", "key", "url_path"):
                continue
            yield (f"{kind}.{m.group(1)}", _unescape(m.group(2)))


def _tables_by_heading(root):
    """[(heading, DataFrame)] in render order, each dataframe under the
    subheader that precedes it."""
    heading, out = None, []
    for node in _walk(root):
        kind = getattr(node, "type", "")
        if kind in ("subheader", "header"):
            heading = node.proto.body
        elif kind in ("dataframe", "table"):
            out.append((heading, node.value))
    return out


def _strip(at):
    return next((c.value for c in at.main.caption if " · " in c.value), "")


def _petoskey(at):
    for key, value in PETOSKEY_STATE.items():
        at.session_state[key] = value
    return at


def _petoskey_before_standard_time(at):
    """Petoskey in 1582: the named zone has no rule that early (a birth
    there under Standard time is refused), so the calendar tests that cast
    it use a manual offset of -5:30, which is all they need."""
    _petoskey(at)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = -5.5
    return at


# --- H1: a saved target_age past a C long kills the shell -------------------

@pytest.mark.parametrize("age", [3e9, 1e19, 1e300])
def test_a_saved_target_age_past_the_ephemeris_keeps_the_shell_on_load(tmp_path, monkeypatch, age):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (_data_dir() / "saved_charts.json").write_text(
        json.dumps({"Rec": {**PETOSKEY, "target_mode": "Age", "target_age": age}}))
    at = make_app(page="timing").run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    assert_no_exception(at, f"loading a record whose target_age is {age!r}")
    assert len(at.main.header) == 1


@pytest.mark.parametrize("page", ["chart", "reference", "sources"])
def test_a_saved_target_age_past_the_ephemeris_does_not_kill_the_launch(tmp_path, monkeypatch, page):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    d = _data_dir()
    (d / "saved_charts.json").write_text(json.dumps({"Rec": {**PETOSKEY, "target_mode": "Age", "target_age": 3e9}}))
    (d / "preferences.json").write_text(json.dumps({"last_chart": "Rec"}))
    at = _fresh_launch(page).run()
    assert_no_exception(at, f"launch on {page} with a last_chart whose target_age is 3e9")
    assert len(at.main.header) == 1


def test_a_saved_target_age_merely_out_of_reach_is_kept_and_named(tmp_path, monkeypatch):
    """Coverage: an age that overflows nothing but lies past the ephemeris
    (5000 on a 1982 birth) loads, keeps the last target and says so."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (_data_dir() / "saved_charts.json").write_text(
        json.dumps({"Rec": {**PETOSKEY, "target_mode": "Age", "target_age": 5000}}))
    at = make_app(page="timing").run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    assert_no_exception(at, "loading a record whose target_age is 5000")
    assert any("beyond this app's ephemeris" in e.value for e in at.main.error)


# --- M1: SQL LIKE wildcards in the city box ---------------------------------

@pytest.mark.parametrize("query", ["%", "_", "Flor%"])
def test_a_like_wildcard_in_the_city_box_matches_nothing(tmp_path, monkeypatch, query):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = query
    at.run()
    assert_no_exception(at, f"place {query!r}")
    matches = [s for s in at.sidebar.selectbox if s.label.startswith("Select specific")]
    # The right behaviour: no match for a bare wildcard, and "Flor%" is not
    # a prefix of Florianopolis (the % is a character, not a wildcard).
    assert not matches or not any("Shanghai" in o or "Florian" in o for o in matches[0].options), (
        f"{query!r} resolved to {matches[0].options[:3]}")
    assert "Shanghai" not in _strip(at) and "Florian" not in _strip(at), _strip(at)


def test_a_hostile_city_text_is_parametrised_and_a_real_prefix_resolves(tmp_path, monkeypatch):
    """Coverage: the query is parametrised (an injection reads as text) and
    the prefix search itself works, case-insensitively."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for query, expected in (("'; DROP TABLE cities;--", None), ("florence", "Florence, 16 (IT)"), ("FLORENCE", "Florence, 16 (IT)")):
        at = make_app(page="chart")
        at.session_state["manual_coords_key"] = False
        at.session_state["location_input_key"] = query
        at.run()
        assert_no_exception(at, f"place {query!r}")
        matches = [s for s in at.sidebar.selectbox if s.label.startswith("Select specific")]
        if expected is None:
            assert not matches and any("No matches" in w.value for w in at.sidebar.warning)
        else:
            assert matches and matches[0].options[0] == expected


# --- M2: the coordinate toggle switched OFF changes the place ---------------

def test_switching_the_coordinate_fields_off_keeps_the_loaded_place(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (_data_dir() / "saved_charts.json").write_text(json.dumps({"Rec": PETOSKEY}))
    at = _fresh_launch("chart").run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    assert "45.37, -84.96" in _strip(at), _strip(at)
    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert_no_exception(at, "switching the fields off after a load")
    # A change of input method is not a change of place (F02's own rule for
    # the other direction): the chart is still cast at Petoskey, or nothing
    # is cast until the reader types a place -- never Florence unasked.
    assert "Florence" not in _strip(at), _strip(at)


def test_switching_the_coordinate_fields_off_keeps_a_typed_pair(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart")
    at.session_state["manual_lat_key"] = 10.0
    at.session_state["manual_lon_key"] = 10.0
    at.run()
    assert "10.00, 10.00" in _strip(at), _strip(at)
    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert_no_exception(at, "switching the fields off after typing a pair")
    assert "Florence" not in _strip(at), _strip(at)


def test_switching_the_coordinate_fields_on_starts_them_at_the_resolved_city(tmp_path, monkeypatch):
    """Coverage: the ON direction (F02, re-fixed 2026-09-18) holds -- the
    fields start at the place the box resolved."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "Berlin"
    at.run()
    assert "Berlin" in _strip(at), _strip(at)
    at.sidebar.toggle(key="manual_coords_key").set_value(True).run()
    assert round(at.session_state["manual_lat_key"], 2) == 52.52, at.session_state["manual_lat_key"]


# --- M3: a target before the birth --------------------------------------------

def _revolution_row(at, item):
    table = next(d.value for d in at.main.dataframe if "Item" in d.value.columns)
    return str(table[table["Item"] == item].iloc[0]["Value"])


@pytest.mark.parametrize("birth,target", [("1240-05-23", "1200-01-01"), ("2990-05-23", "2026-09-22")])
def test_a_target_before_the_birth_is_refused_or_named(tmp_path, monkeypatch, birth, target):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=birth, page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = target
    at.run()
    assert_no_exception(at, f"target {target} on a {birth} birth")
    said = " ".join(w.value for w in list(at.main.warning) + list(at.main.error))
    assert "before the birth" in said or "precedes the birth" in said, said
    # The refused target is kept out as an out-of-reach one is (F17's
    # pattern): the last valid target -- never one before the birth -- is
    # analysed and named, so no page counts a negative age or year.
    said_target = next((m.value for m in at.main.markdown if "completed" in m.value), "")
    assert "age **-" not in said_target and f"before the birth ({birth})" in said, said
    assert not _revolution_row(at, "Count of the year").lstrip().startswith("-") and " -" not in _revolution_row(at, "Count of the year")
    assert not _revolution_row(at, "Count of the year").lstrip().startswith("-") and " -" not in _revolution_row(at, "Count of the year")


def test_targets_at_and_after_the_birth_count_their_years(tmp_path, monkeypatch):
    """Coverage: the birthday itself opens year 0, the day before the first
    birthday is still year 0's twelfth month, age 150 is the 150th birthday."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1240-05-23", page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1241-05-22"
    at.run()
    assert_no_exception(at, "target the day before the first birthday")
    said = next(m.value for m in at.main.markdown if "completed" in m.value)
    assert "age **0** completed" in said and "month **12** of 12" in said, said
    at = make_app(date="1240-05-23", page="timing")
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 150
    at.run()
    assert_no_exception(at, "age 150")
    said = next(m.value for m in at.main.markdown if "completed" in m.value)
    assert "**1390-05-23** -- age **150** completed" in said, said
    box = next(n for n in at.main.number_input if n.label.startswith("Age"))
    assert box.proto.min == 0 and box.proto.max == 1760


# --- M4: the calendar label across the reform -------------------------------

def test_the_ut_across_the_reform_is_not_labelled_julian(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _petoskey_before_standard_time(make_app(date="1582-10-04", page="chart"))
    at.session_state["time_input_key"] = time(23, 0)
    at.run()
    assert_no_exception(at, "1582-10-04 23:00 Detroit")
    box = " ".join(i.value for i in at.sidebar.info)
    calc = {r.iloc[0]: r.iloc[1] for _, r in at.main.dataframe[0].value.iterrows()}
    # The JD is right (2299160.6889, the evening of the last Julian day).
    assert calc["Julian Day"].startswith("2299160.68"), calc
    # The label beside the UT names the UT's own calendar, and the digits
    # round-trip: the birth is Julian (the box's caption says so) while its
    # UT, past the reform's JD, is the Gregorian 1582-10-15 and is labelled
    # so -- never a Gregorian date under a "Julian calendar" note.
    assert "UT 1582-10-15" in box and "UT 1582-10-15 04:30:00 · Gregorian calendar" in box, box
    assert calc["Universal time"].startswith("1582-10-15 04:30:00 UT (Gregorian calendar; the birth date is Julian calendar)"), calc["Universal time"]
    back = _petoskey(make_app(date="1582-10-15", page="chart"))
    back.session_state["time_input_key"] = time(4, 30)
    back.session_state["time_standard_key"] = "Manual UTC offset"
    back.session_state["utc_offset_key"] = 0.0
    back.run()
    calc_back = {r.iloc[0]: r.iloc[1] for _, r in back.main.dataframe[0].value.iterrows()}
    assert calc_back["Julian Day"][:10] == calc["Julian Day"][:10], (calc_back["Julian Day"], calc["Julian Day"])


def test_a_gregorian_birth_in_the_reforms_first_days_prints_a_julian_ut_and_agrees_across_pages(tmp_path, monkeypatch):
    """The verification's mirror case: 1582-10-15 00:30 at +5 has its UT
    before the reform's JD, so it is written in the Julian calendar
    (1582-10-04 19:30) and labelled so, not as the proleptic 1582-10-14;
    and the Revolutions page writes the same instant by the same rule."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1582-10-15", page="chart")
    at.session_state["time_input_key"] = time(0, 30)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 5.0
    at.session_state["manual_lon_key"] = 75.0
    at.run()
    assert_no_exception(at, "1582-10-15 00:30 at +5")
    calc = {r.iloc[0]: r.iloc[1] for _, r in at.main.dataframe[0].value.iterrows()}
    assert calc["Universal time"].startswith("1582-10-04 19:30:00 UT (Julian calendar; the birth date is Gregorian calendar)"), calc["Universal time"]
    box = " ".join(i.value for i in at.sidebar.info)
    assert "UT 1582-10-04 19:30:00 · Julian calendar" in box, box
    timing = make_app(date="1582-10-10", page="timing")
    timing.session_state["_target_mode"] = "Age"
    timing.session_state["_target_age"] = 0
    timing.run()
    assert_no_exception(timing, "1582-10-10 at age 0")
    chart = make_app(date="1582-10-10", page="chart").run()
    ut_value = {r.iloc[0]: r.iloc[1] for _, r in chart.main.dataframe[0].value.iterrows()}["Universal time"]
    moment = _revolution_row(timing, "Moment of the revolution")[:10]
    # The digits 1582-10-10 are Julian by the box's rule, a moment past the
    # reform's JD: every page writes it Gregorian, 1582-10-20, and the
    # Chart page says the two calendars differ.
    assert ut_value[:10] == moment == "1582-10-20", (ut_value, moment)
    assert "Gregorian calendar; the birth date is Julian calendar" in ut_value, ut_value


def test_the_reform_gap_is_one_day_wide_in_julian_days(tmp_path, monkeypatch):
    """Coverage: 1582-10-04 (Julian) and 1582-10-15 (Gregorian) are one day
    apart, and the digits 1582-10-10, a day that never was, are read as
    Julian -- consistently with the date box's own help."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    jd = {}
    for date in ("1582-10-04", "1582-10-15", "1582-10-10"):
        at = _petoskey_before_standard_time(make_app(date=date, page="chart")).run()
        assert_no_exception(at, date)
        calc = {r.iloc[0]: r.iloc[1] for _, r in at.main.dataframe[0].value.iterrows()}
        jd[date] = float(calc["Julian Day"])
    assert round(jd["1582-10-15"] - jd["1582-10-04"], 4) == 1.0, jd
    assert round(jd["1582-10-10"] - jd["1582-10-04"], 4) == 6.0, jd


# --- M5: the wheel panel prints engine keys as condition names --------------

_IDENTIFIER = re.compile(r"^[A-Z][a-z]+[A-Z]")      # PlanetSect, ContraryDomain, UnderBeams
_ABBREVIATIONS = {"Exalt"}


def _panel_labels(engine, date_text="1982-11-19"):
    from datetime import datetime, timedelta
    lat, lon = 45.37334, -84.95533
    local = datetime(1982, 11, 19, 11, 44)
    chart = engine["calculate_traditional_chart"](local + timedelta(hours=5), lat, lon)
    p_data, sect = chart["planetary_data"], chart["sect"]
    essential = engine["evaluate_essential_dignities"](p_data, sect)
    accidental = engine["evaluate_accidental_dignities"](
        p_data, chart["houses"], sect, chart["julian_day"],
        armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    labels = []
    for planet in p_data:
        summary = engine["point_summary"](planet, chart, essential, accidental, [], [], [], [])
        labels += [row["Condition"] for row in summary["accidental"]]
        labels += [row["Dignity"] for row in summary["essential"]]
    return labels


def test_the_wheel_panel_names_conditions_in_the_pages_words(engine):
    labels = _panel_labels(engine)
    assert labels, "the 1982 chart has conditions to list"
    bad = sorted({l for l in labels if _IDENTIFIER.match(str(l)) or l in _ABBREVIATIONS})
    assert not bad, f"machine identifiers on the page: {bad}"


def test_the_wheel_panel_restates_positions_the_chart_page_prints(engine):
    """Coverage: the panel's position rows are the Chart page's own numbers."""
    from datetime import datetime, timedelta
    lat, lon = 45.37334, -84.95533
    chart = engine["calculate_traditional_chart"](datetime(1982, 11, 19, 16, 44), lat, lon)
    summary = engine["point_summary"]("Saturn", chart, {}, {}, [], [], [], [])
    rows = {r["Reading"]: r["Value"] for r in summary["position"]}
    assert rows["Position"] == engine["get_degree_string"](chart["planetary_data"]["Saturn"]["longitude"])
    assert rows["Whole-sign place"] == str(engine["get_wsh_house"](chart["planetary_data"]["Saturn"]["longitude"], chart["ascendant"]))


# --- L1: the answer key's trailing separator --------------------------------

def test_answer_key_cells_do_not_end_with_a_dangling_separator(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="configurations").run()
    cells = []
    for heading, df in _tables_by_heading(at.main):
        for col in ("Strength Testimonies", "Weakness Testimonies"):
            if col in df.columns:
                cells += [str(v) for v in df[col].tolist()]
    assert cells, "the two answer keys render"
    dangling = [c for c in cells if c.rstrip().endswith(";")]
    assert not dangling, dangling[:3]


# --- L2: the Markdown export's cells ----------------------------------------

def test_the_markdown_export_prints_no_python_scalars(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart").run(timeout=300)
    md = at.session_state["_analysis_markdown"]
    cells = [c.strip() for line in md.splitlines() if line.startswith("|") for c in line.split("|")[1:-1]]
    assert "None" not in cells, "a None printed as a cell"
    assert "True" not in cells and "False" not in cells, "a bool printed as a cell"


def test_the_markdown_and_json_exports_carry_no_repr_and_agree_on_the_moment(tmp_path, monkeypatch):
    """Coverage: neither export leaks a repr; both name the same moment the
    strip and the Calculation table name."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart").run(timeout=300)
    md = at.session_state["_analysis_markdown"]
    js = at.session_state["_analysis_export"]
    assert not REPR_LEAK.search(md), REPR_LEAK.search(md).group(0)
    assert not REPR_LEAK.search(json.dumps(js, ensure_ascii=False))
    assert "result_type" not in md and '"facts"' not in md
    calc = {r.iloc[0]: r.iloc[1] for _, r in at.main.dataframe[0].value.iterrows()}
    assert js["input"]["date"] == "1240-05-23" and js["input"]["time"] == "14:30:00"
    assert calc["Julian Day"] == f"{js['input']['julian_day_ut']:.4f}"
    assert js["input"]["date"] in _strip(at) and js["input"]["time"] in _strip(at)


# --- L3: the recompense search's horizon ------------------------------------

def test_favor_without_recompense_names_the_horizon_of_the_search(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1240-01-22", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run()
    section, texts = False, []
    for node in _walk(at.main):
        kind = getattr(node, "type", "")
        if kind == "subheader":
            section = node.proto.body.startswith("Favor")
            if section:
                texts.append(node.proto.help)
        elif section and kind in ("caption", "markdown"):
            texts.append(node.proto.body)
        elif section and kind in ("dataframe", "table"):
            df = node.value
            assert "Favored By" in df.columns and len(df) == 1, df
            assert "Recompense (days)" in df.columns, "the searched-for column is gone with its search"
    assert any("200" in t for t in texts), texts


# --- L4: the unsaved chart's two names --------------------------------------

def test_an_unsaved_chart_has_one_name(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart").run(timeout=300)
    assert _strip(at).startswith("Unsaved chart")
    export = at.session_state["_analysis_export"]
    assert export["chart"] == "Unsaved chart", export["chart"]


# --- L5: the ephemeris sentence and its own last months ---------------------

def test_the_ephemeris_refusal_does_not_contradict_its_own_span(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="3000-10-01", page="chart").run()
    assert_no_exception(at, "3000-10-01")
    refusals = [e.value for e in at.sidebar.error if "ephemeris" in e.value]
    if refusals:
        assert not any("to 3000 AD" in r for r in refusals), refusals
    else:
        assert len(at.main.dataframe) > 0


def test_the_ephemeris_edges_hold_the_shell(tmp_path, monkeypatch):
    """Coverage: 0001-01-01 casts; 3000-06-01 casts; 9999-12-31 and 3100 are
    refused with the shell and the sentence."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for date, cast in (("0001-01-01", True), ("3000-06-01", True), ("9999-12-31", False), ("3100-06-01", False)):
        at = make_app(date=date, page="chart").run()
        assert_no_exception(at, date)
        assert len(at.main.header) == 1
        assert (len(at.main.dataframe) > 0) == cast, date
        if not cast:
            assert any("ephemeris" in e.value for e in at.sidebar.error), date


# --- L6: whitespace round a city text ---------------------------------------

def test_a_city_text_with_surrounding_spaces_resolves(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "  Florence  "
    at.run()
    assert "Florence" in _strip(at), _strip(at)


def test_a_typed_pair_tolerates_spaces_tabs_and_a_plus_sign(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for text in ("45.3733 , -84.9553", "45.3733,\t-84.9553", "+45.3733, -84.9553", "45.3733 -84.9553"):
        at = make_app(page="chart")
        at.session_state["manual_coords_key"] = False
        at.session_state["location_input_key"] = text
        at.run()
        assert "45.37, -84.96" in _strip(at), (text, _strip(at))


# --- Coverage: no repr on any page, at either depth, behind every detail ----

@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_no_page_prints_a_repr_at_either_depth_behind_any_detail_selector(tmp_path, monkeypatch, page, depth):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _petoskey(make_app(date="1982-11-19", page=page))
    at.session_state["_reading_depth"] = depth
    at.session_state["_domain_rule"] = "Masha'allah"       # the reading that makes Mercury's cells typed
    at.run(timeout=300)
    assert_no_exception(at, f"{page} at {depth}")

    def check(tag):
        for where, text in _strings(at.main):
            assert not REPR_LEAK.search(text), (tag, where, text[:200])
        for where, text in _strings(at.sidebar):
            assert not REPR_LEAK.search(text), (tag, where, text[:200])

    check("base")
    for box in at.main.selectbox:
        if (box.key or "").endswith("_detail"):
            for option in box.options:
                box.select(option).run(timeout=300)
                assert_no_exception(at, f"{page}: detail {box.key}={option}")
                check(f"{box.key}={option}")


# --- Coverage: the export is the pages' own tables ---------------------------

# Every result page, with the export section its tables go to. The Findings
# page has none: its tables are all in LEFT_OUT below.
EXPORT_SECTION = {"chart": "Chart", "dignities": "Dignities and places", "findings": None,
                  "configurations": "Configurations", "lots": "Lots", "victors": "Lunation and victors",
                  "timing": "Prediction", "releaser": "Prediction", "days": "Prediction", "fardar": "Prediction"}


def _norm(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(round(value, 6))
    if isinstance(value, dict) and "display" in value:
        return str(value["display"])
    if isinstance(value, (list, tuple)):
        return "; ".join(_norm(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    text = str(value)
    try:
        number = float(text)
    except ValueError:
        return text
    if not math.isfinite(number):
        return text
    return str(int(number)) if number.is_integer() else repr(round(number, 6))


def _page_tables(monkeypatch, tmp_path):
    """Every result page's dataframes with their headings, at the supplement
    depth, and the export the last run left behind (the same on every page)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    tables, export = {}, None
    for page in sorted(EXPORT_SECTION):
        at = make_app(page=page)
        at.session_state["_reading_depth"] = "Course text and supplement"
        at.run(timeout=300)
        assert_no_exception(at, page)
        tables[page] = _tables_by_heading(at.main)
        export = at.session_state["_analysis_export"]
    return tables, export


_NUMBER_PRINTED = re.compile(r"-?\d+\.(\d+)(°?)")
_NOTHING_PRINTED = "–"


def _as_the_page_prints(df, column):
    """Where the page prints a column as text and the JSON carries the
    engine's own value (the hostile pass of 2026-10-03: "where a page or a
    report rounds, the JSON does not"), the export's value printed the
    page's way; any other value as it stands. Two shapes:

    * a column whose every cell is a number printed as text to one fixed
      number of places, all with a degree sign or all without (the
      Planetary Positions' Absolute, L5-04; Indicator 15's Distance,
      L7-06): the export's float, at those places;
    * a column the page never leaves empty, in which it prints an en dash
      (Indicator 15's Motion, Applicant and Receiver for a pair in
      aversion, L7-06): the export's None, as that dash."""
    cells = list(df[column])
    printed = [isinstance(v, str) and _NUMBER_PRINTED.fullmatch(v) for v in cells]
    shapes = {(len(m.group(1)), m.group(2)) for m in printed if m}
    if cells and all(printed) and len(shapes) == 1:
        places, sign = shapes.pop()
        return lambda value: f"{value:.{places}f}{sign}" if isinstance(value, float) else value
    if any(isinstance(v, str) and v == _NOTHING_PRINTED for v in cells) and not any(_norm(v) == "" for v in cells):
        return lambda value: _NOTHING_PRINTED if value is None else value
    return lambda value: value


def _same_rows(df, entry):
    columns = [str(c) for c in df.columns]
    if not set(columns) <= set(entry["columns"]):
        return False
    printers = [_as_the_page_prints(df, c) for c in df.columns]
    export_rows = sorted(tuple(_norm(printer(r.get(c, ""))) for c, printer in zip(columns, printers))
                         for r in entry["rows"])
    page_rows = sorted(tuple(_norm(v) for v in row) for row in df.itertuples(index=False))
    return export_rows == page_rows


def _is_tick_grid_or_answer_key(df):
    columns = [str(c) for c in df.columns]
    return ("Strength Testimonies" in columns or "Weakness Testimonies" in columns
            or (len(df) and "\u2713" in "".join(str(v) for v in df.iloc[0].tolist())))


def test_every_table_the_export_carries_is_on_its_page_with_the_same_cells(tmp_path, monkeypatch):
    """Coverage: the export's tables are the pages' own rows, cell for cell
    (the tick grids compared through their answer keys are the L1 exception;
    the Ascendant triplicity lords table is exported behind its own toggle,
    as its help says)."""
    tables, export = _page_tables(monkeypatch, tmp_path)
    everything = [df for page in tables for _heading, df in tables[page]]
    unmatched = []
    for section, headings in export["results"].items():
        for heading, entries in headings.items():
            for entry in entries:
                if heading.startswith("Ascendant triplicity lords") or heading in ("Strength of the Planets", "Weakness of the Planets"):
                    continue
                if not any(_same_rows(df, entry) for df in everything):
                    unmatched.append((section, heading, entry["columns"][:5], len(entry["rows"])))
    assert not unmatched, unmatched


# The tables the export leaves on their pages, in ONE list. The coverage
# test below excludes exactly these and nothing else, so a new table a page
# draws and the export does not carry fails it; and
# test_the_scope_note_names_exactly_what_is_left_out requires EXPORT_SCOPE_NOTE
# to name every entry and its page, so a note that stops naming one fails too.
#
# Each entry: the page; prefixes of the subheader above the table, of the
# bold or italic line that introduces it, and of its columns (None: any);
# the words the note names it by, in a sentence that also names the page;
# and a witness, the (chart, depth) at which the coverage test must find it
# drawn (EVERY: at every one), so that an entry no chart draws any more
# fails as well. The chosen-point days have no witness here: the selector
# test below draws them.
LeftOut = namedtuple("LeftOut", "page heading label columns named witness")
_SAHL, _BOTH = READING_DEPTHS
EVERY = "every chart and depth"
# A chart where Venus is in aversion to all six others, so that Wildness is
# drawn; no harness chart draws it.
WILDNESS_CHART = "1240-10-02"
# A chart where a 1.23, 12 flag stands on a house-master that is NOT the
# lord of the Ascendant, so that 1.23, 13's table is drawn: Libra rising,
# Venus its lord, Saturn the house-master (an infortune). On every harness
# chart that flags the house-master, the lord of the Ascendant is the
# house-master itself, and 13 draws nothing.
REDIRECTION_CHART = "1240-05-10"
LEFT_OUT = (
    # The Findings page: all of it.
    LeftOut("findings", "The fetus's stay (Sahl)", None, ("Item", "Value", "Text"),
            "The fetus's stay", ("1240-05-23", _SAHL)),
    LeftOut("findings", "The Moon on the third day (Sahl)", None, ("Item", "Value", "Text"),
            "The Moon on the third day", ("1240-05-23", _SAHL)),
    LeftOut("findings", "Sahl: indications of fortune and livelihood", None, ("Class", "Ground"),
            "indications of fortune and livelihood", ("1240-05-23", _SAHL)),
    LeftOut("findings", "Places harming the eyesight", None, ("Point", "Position", "Place"),
            "Places harming the eyesight", ("1240-05-25", _BOTH)),
    LeftOut("findings", "Mars in his own domicile, by sect (Abu Bakr)", None, ("Mars", "Sign"),
            "Mars in his own domicile", ("1240-05-23", _BOTH)),
    LeftOut("findings", "The Moon's phase, Valens's eleven", None, ("Moon", "Angle from Sun"),
            "Valens's eleven", ("1240-05-23", _BOTH)),
    LeftOut("findings", "Mercury's phase against the sect", None, ("Mercury", "Phase"),
            "Mercury's phase against the sect", ("1240-05-23", _BOTH)),
    LeftOut("findings", "Mercury's company and sect", None, ("Companion", "Relationship"),
            "Mercury's company and sect", ("1240-05-23", _BOTH)),
    LeftOut("findings", "Affliction and fortification after Rhetorius", None, ("Planet", "Condition", "By"),
            "Affliction and fortification", ("1240-05-23", _BOTH)),
    LeftOut("findings", "Morin's rules for aspects into good and bad houses", None, ("Planet", "Aspect", "To"),
            "Morin's rules", ("1240-05-23", _BOTH)),
    # The moment's intermediate quantities: not all of the table is carried
    # (test_the_calculation_table_is_carried_as_the_note_says holds which).
    LeftOut("chart", "Calculation", None, ("Quantity", "Value"),
            "Calculation table", EVERY),
    # Readings on other pages, drawn when a chart has them.
    LeftOut("chart", "Special Degrees & Conditions", None, ("Planet", "Position", "Condition"),
            "Special Degrees & Conditions", ("1240-05-25", _SAHL)),
    LeftOut("chart", "Degrees of nobility and rank", None, ("Point", "Position", "Degree"),
            "Degrees of nobility and rank", ("1240-05-25", _SAHL)),
    # 1240-05-26's Venus (between Mars's and Saturn's rays) is dissolved by
    # the Sun's ray between them since lane F6 of 2026-10-03 (Ch. 3, 121);
    # 1240-10-05 encloses the Sun and the Moon between the infortunes.
    LeftOut("configurations", "Enclosure", None, ("Planet", "Enclosed By"),
            "Enclosure", ("1240-10-05", _SAHL)),
    LeftOut("configurations", "Returning", None, ("Manner", "Planet", "Returned By"),
            "Returning", ("1240-05-25", _SAHL)),
    LeftOut("configurations", "Wildness", None, ("Planet", "Bound Lord (residual connection)"),
            "Wildness", (WILDNESS_CHART, _SAHL)),
    LeftOut("configurations", "Favor & Recompense", None, ("Planet", "Condition", "Favored By"),
            "Favor & Recompense", ("1240-05-25", _SAHL)),
    LeftOut("configurations", "Book V degrees", None, ("Point", "Position", "Table"),
            "Book V degrees", ("1240-09-18", _BOTH)),
    LeftOut("releaser", "The house-master directed", "*1.23, 13: the lord of the Ascendant", ("Target", "Degree"),
            "directs the lord of the Ascendant in the house-master's stead", (REDIRECTION_CHART, _SAHL)),
    LeftOut("releaser", "The house-master directed", "*1.23, 14: the degree of the Ascendant", ("Target", "Degree"),
            "then the degree of the Ascendant", ("1240-05-26", _SAHL)),
    # The Days and months page: a further point chosen in its selector.
    LeftOut("days", None, "**Small days from the revolution's", ("From day", "To day"),
            "a further point chosen there", None),
    LeftOut("days", None, "**Mighty days from the natal", ("From day", "To day"),
            "mighty days from the natal point profected", None),
    # Lookups keyed to this chart. The sign categories sit in an expander
    # after the page's last subheader, so they are known by their columns.
    LeftOut("chart", None, None, ("Point", "Sign", "Four-footed (Intro)"),
            "Sahl's sign categories for this chart's points", ("1240-05-23", _SAHL)),
    LeftOut("fardar", "The triplicity lords of the twelve houses, al-Andarzaghar", None, ("House", "Sign", "First lord"),
            "al-Andarzaghar's triplicity lords of the twelve houses", ("1240-05-23", _BOTH)),
    # The one reference material that reads the same for every chart.
    LeftOut("fardar", "Directing: which ascensions", "**III.1, 12", ("Point directed", "Measured in"),
            "Directing: which ascensions", ("1240-05-23", _SAHL)),
    LeftOut("fardar", "Directing: which ascensions", "**III.1, 6", ("Directed in the", "A degree is"),
            "Directing: which ascensions", ("1240-05-23", _SAHL)),
    LeftOut("fardar", "Directing: which ascensions", "**III.1, 13", ("Arc", "Is"),
            "Directing: which ascensions", ("1240-05-23", _SAHL)),
)
# The page names as the navigation shows them.
PAGE_TITLE = {"chart": "Chart", "findings": "Findings", "configurations": "Configurations",
              "releaser": "The releaser", "days": "Days and months", "fardar": "Fardar and ages"}


def _note_names(entry, scope):
    """The scope note names this entry in a sentence that also names its
    page ("the Chart page", "The releaser page", "the Chart page's")."""
    page = PAGE_TITLE[entry.page] + " page"
    return any(entry.named in sentence and page in sentence
               for sentence in re.split(r"(?<=\.)\s+", scope))


def _drawn_tables(root):
    """[(heading, label, DataFrame)] in render order: the subheader above
    each table, and the bold or italic line since that subheader which
    introduces it (the house-master's redirection, the chosen-point days and
    the Directing tables are told apart only by theirs)."""
    out, state = [], {"heading": None, "label": None}
    for node in _walk(root):
        kind = getattr(node, "type", "")
        if kind in ("subheader", "header"):
            state["heading"], state["label"] = node.proto.body, None
        elif kind == "markdown" and node.value.lstrip().startswith("*"):
            state["label"] = node.value.strip()
        elif kind in ("dataframe", "table"):
            out.append((state["heading"], state["label"], node.value))
    return out


def _left_out_entry(page, heading, label, df, scope):
    """The LEFT_OUT entry this table is, if the run's own scope note names
    it: an exclusion the note does not state excuses nothing."""
    columns = tuple(str(c) for c in df.columns)
    for entry in LEFT_OUT:
        if (entry.page == page and _note_names(entry, scope)
                and (entry.heading is None or (heading or "").startswith(entry.heading))
                and (entry.label is None or (label or "").startswith(entry.label))
                and columns[:len(entry.columns)] == entry.columns):
            return entry
    return None


def _against_the_export(page, at):
    """(missing, left_out, carried, entries): the tables this page draws
    that the export does not carry and that are not LEFT_OUT entries named
    by the export's own scope note; the LEFT_OUT entries it draws, each with
    its table; those of them the export DOES carry, which makes the note
    false, with no allowance (where the lord of the Ascendant is the
    house-master, 1.23, 13 draws no table to repeat the house-master's
    carried one); and the export's tables."""
    export = at.session_state["_analysis_export"]
    entries = [entry for section in export["results"].values() for tables_ in section.values() for entry in tables_]
    drawn = _drawn_tables(at.main)
    missing, left_out, carried = [], [], []
    for heading, label, df in drawn:
        if len(df.columns) < 2 or _is_tick_grid_or_answer_key(df):
            continue
        entry = _left_out_entry(page, heading, label, df, export["scope"])
        if entry is not None:
            left_out.append((entry, df))
            if any(_same_rows(df, e) for e in entries):
                carried.append((page, entry.named, len(df)))
            continue
        if not any(_same_rows(df, e) for e in entries):
            missing.append((page, heading, (label or "")[:60], [str(c) for c in df.columns][:4], len(df)))
    return missing, left_out, carried, entries


@pytest.mark.parametrize("page", sorted(EXPORT_SECTION))
@pytest.mark.parametrize("depth", READING_DEPTHS)
@pytest.mark.parametrize("date", sorted(CHARTS) + [WILDNESS_CHART, REDIRECTION_CHART])
def test_every_reading_a_page_draws_is_in_the_export(tmp_path, monkeypatch, date, depth, page):
    """M6, taken 2026-09-22 and since widened: on every harness chart
    (and one that draws Wildness, and one that draws 1.23, 13's redirection
    to a lord of the Ascendant other than the house-master), at both depths,
    every table a result page draws is in the export cell for cell, or is an
    entry of LEFT_OUT, which the scope note names with its page and the
    export does not carry. Each LEFT_OUT entry is drawn at its witness."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=date, page=page)
    at.session_state["_reading_depth"] = depth
    at.run(timeout=300)
    assert_no_exception(at, f"{page} {date} {depth}")
    missing, left_out, carried, _entries = _against_the_export(page, at)
    assert not missing, missing
    assert not carried, carried
    drawn = {entry for entry, _df in left_out}
    unwitnessed = [entry for entry in LEFT_OUT
                   if entry.page == page and entry.witness in ((date, depth), EVERY) and entry not in drawn]
    assert not unwitnessed, unwitnessed


@pytest.mark.parametrize("point", ["Saturn", "house 2 ("])
@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_a_point_chosen_on_the_days_page_draws_the_two_declared_tables_and_the_export_lacks_them(
        tmp_path, monkeypatch, depth, point):
    """The Days and months selector directs a further point: its small days
    and its mighty days are the two LEFT_OUT entries of that page, drawn
    and not carried; everything else the page draws still is. (House 1 is
    not tried: its cusp is the revolution's Ascendant, so its tables are
    the carried ones.)"""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="days")
    at.session_state["_reading_depth"] = depth
    at.run(timeout=300)
    box = next(s for s in at.main.selectbox if s.key == "pn4_day_point")
    box.select(next(o for o in box.options if o.startswith(point))).run(timeout=300)
    assert_no_exception(at, f"days {point} {depth}")
    missing, left_out, carried, entries = _against_the_export("days", at)
    assert not missing, missing
    assert not carried, carried
    assert sorted(entry.label for entry, _df in left_out) == sorted(
        entry.label for entry in LEFT_OUT if entry.page == "days"), left_out
    for entry, df in left_out:
        assert not any(_same_rows(df, e) for e in entries), entry.label


@pytest.mark.parametrize("date", sorted(CHARTS) + [WILDNESS_CHART])
def test_the_calculation_table_is_carried_as_the_note_says(tmp_path, monkeypatch, date):
    """The note's sentence on the Chart page's Calculation table, row by
    row: the local time, time standard and Julian day are the export's
    moment and place; the MC and Ascendant are its Calculated Points rows
    (the MC there as the Midheaven);
    the universal time, the two sidereal times, the RAMC and the obliquity
    are nowhere in the JSON or the Markdown."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=date, page="chart").run(timeout=300)
    assert_no_exception(at, f"chart {date}")
    calc = next(df for heading, _label, df in _drawn_tables(at.main) if heading == "Calculation")
    rows = dict(zip(calc["Quantity"], calc["Value"]))
    export = at.session_state["_analysis_export"]
    moment = export["input"]
    assert rows["Local time"] == f"{moment['date']} {moment['time']}"
    assert rows["Time standard"] == moment["timezone"]
    assert rows["Julian Day"] == f"{moment['julian_day_ut']:.4f}"
    points = {r["Point"]: r["Position"] for e in export["results"]["Chart"]["Calculated Points"] for r in e["rows"]}
    assert points["Midheaven"] == rows["MC"] and points["Ascendant"] == rows["Ascendant"], (points, rows)
    written = json.dumps(export, ensure_ascii=False) + at.session_state["_analysis_markdown"]
    for quantity in ("Universal time", "Greenwich sidereal time at birth", "Local sidereal time", "RAMC",
                     "Obliquity of the ecliptic"):
        value = rows[quantity].split(" UT")[0].rstrip('"')
        assert value not in written, (quantity, value)
    assert set(rows) == {"Local time", "Time standard", "Universal time", "Julian Day",
                         "Greenwich sidereal time at birth", "Local sidereal time", "RAMC",
                         "Obliquity of the ecliptic", "MC", "Ascendant"}, set(rows)


# --- Coverage: the same fact in two places -----------------------------------

def test_positions_places_lots_and_nets_agree_across_every_page(tmp_path, monkeypatch):
    """Every (planet, Position), (planet, WS place), (Lot, Position) and
    (planet, Net) pair printed by any table of any page is the same pair on
    every other page that prints it; the strip is one caption on every page."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    facts, strips = {}, set()
    for page in PAGES:
        at = make_app(page=page)
        at.session_state["_reading_depth"] = "Course text and supplement"
        at.run(timeout=300)
        assert_no_exception(at, page)
        strips.add(_strip(at))
        for heading, df in _tables_by_heading(at.main):
            if heading and "image of the revolution" in heading:
                continue            # root and revolution positions side by side, by design
            for _, row in df.iterrows():
                r = {str(k): v for k, v in row.items()}
                planet = r.get("Planet")
                if isinstance(planet, str) and isinstance(r.get("Position"), str):
                    facts.setdefault(("position", planet), set()).add(r["Position"])
                if isinstance(planet, str) and "WS place" in r:
                    facts.setdefault(("WS place", planet), set()).add(str(r["WS place"]))
                if isinstance(planet, str) and "Net" in r:
                    facts.setdefault(("net", planet, heading), set()).add(str(r["Net"]))
                lot = r.get("Lot") or r.get("Lot Name")
                if isinstance(lot, str) and isinstance(r.get("Position"), str):
                    facts.setdefault(("lot", lot), set()).add(r["Position"])
    assert len(strips) == 1, strips
    disagreeing = {k: v for k, v in facts.items() if len(v) > 1}
    assert not disagreeing, disagreeing
    assert len([k for k in facts if k[0] == "position"]) >= 7 and len([k for k in facts if k[0] == "lot"]) >= 30


def test_a_column_named_net_holds_one_number_per_planet_across_the_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    nets = {}
    for page in ("configurations", "dignities"):
        at = make_app(page=page).run(timeout=300)
        for heading, df in _tables_by_heading(at.main):
            if "Planet" in df.columns and "Net" in df.columns:
                for _, row in df.iterrows():
                    nets.setdefault(row["Planet"], {})[(page, heading)] = str(row["Net"])
    assert nets, "both pages print a Net"
    disagreeing = {planet: seen for planet, seen in nets.items() if len(set(seen.values())) > 1}
    assert not disagreeing, disagreeing


def test_sect_day_lord_hour_lord_and_lunation_agree_between_strip_and_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="victors").run(timeout=300)
    strip = _strip(at)
    m = re.search(r"\*\*(Diurnal|Nocturnal) · (\w+) lunation · Day lord (\w+) · Hour lord (\w+)", strip)
    assert m, strip
    sect, lunation, day_lord, hour_lord = m.groups()
    syzygy = {r.iloc[0]: r.iloc[1] for _, r in at.main.dataframe[0].value.iterrows()}
    assert syzygy["Event Type"].startswith(lunation), syzygy["Event Type"]
    matrix = next(d.value for d in at.main.dataframe if "Row" in d.value.columns)
    day_row = matrix[matrix["Row"].str.startswith("Lord of the Day")].iloc[0]
    hour_row = matrix[matrix["Row"].str.startswith("Lord of the Hour")].iloc[0]
    assert str(day_row[day_lord]).strip() == "7" and str(hour_row[hour_lord]).strip() == "6"
    timing = make_app(page="timing").run(timeout=300)
    revolution = {r["Item"]: str(r["Value"]) for _, r in next(d.value for d in timing.main.dataframe if "Item" in d.value.columns).iterrows()}
    orb = next(d.value for d in timing.main.dataframe if "Indicator" in d.value.columns and any("lord of the orb" in str(v) for v in d.value["Indicator"]))
    assert f"natal hour lord ({hour_lord})" in " ".join(map(str, orb["Active point"].tolist()))
    assert revolution["Sect of the revolution"] in ("Diurnal", "Nocturnal")


# --- Coverage: the shell under every invalid input, on every page -----------

INVALID = {
    "unresolved place": {"manual_coords_key": False, "location_input_key": "zzzz-no-such-city"},
    "latitude 91": {"manual_lat_key": 91.0},
    "DST gap": {"date_input_key": "2025-03-09", "time_input_key": time(2, 30), "time_standard_key": "Standard time (pytz)",
                "manual_lat_key": 40.71427, "manual_lon_key": -74.00597},
    "ephemeris 3100": {"date_input_key": "3100-06-01"},
    "blank place": {"manual_coords_key": False, "location_input_key": ""},
}


@pytest.mark.parametrize("name", sorted(INVALID))
@pytest.mark.parametrize("page", ["chart", "timing", "days", "reference", "sources"])
def test_the_shell_holds_and_names_the_invalid_input_on_every_page(tmp_path, monkeypatch, name, page):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page=page)
    for key, value in INVALID[name].items():
        at.session_state[key] = value
    at.run(timeout=300)
    assert_no_exception(at, f"{name} on {page}")
    assert len(at.main.header) == 1
    if page == "reference":
        assert len(at.main.dataframe) == 7
    elif page == "sources":
        assert len(at.main.dataframe) >= 1
    else:
        assert len(at.main.dataframe) == 0
        assert at.main.error, "the recovery panel names the input"
        assert not at.sidebar.download_button or all(b.proto.disabled for b in at.sidebar.download_button)


# --- Coverage: polar and equatorial latitudes on the prediction pages --------

@pytest.mark.parametrize("lat,lon,date", [(90.0, 0.0, "2000-06-21"), (-90.0, 0.0, "2000-06-21"), (89.0, 180.0, "2000-12-21"), (0.0, 0.0, "2000-03-20")])
@pytest.mark.parametrize("page", ["timing", "releaser", "days", "fardar"])
def test_prediction_pages_render_or_refuse_at_the_poles(tmp_path, monkeypatch, lat, lon, date, page):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=date, page=page)
    at.session_state["time_input_key"] = time(12, 0)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.run(timeout=300)
    assert_no_exception(at, f"{page} at {lat},{lon}")
    assert len(at.main.header) == 1
    strip = _strip(at)
    if abs(lat) >= 89.0:
        assert "equal-hour approximation" in strip, strip
        if page in ("timing", "releaser"):
            assert any("Refused at this latitude" in w.value for w in at.main.warning)
    else:
        assert "equal-hour" not in strip


# --- Coverage: page controls persist -------------------------------------------

@pytest.mark.parametrize("page,kind,key,alternative", [
    ("chart", "checkbox", "moon_rays_15", True),
    ("configurations", "radio", "connection_rule", "Abu Ma'shar"),
    ("timing", "selectbox", "timing_wheel_view", "Month"),
    ("days", "radio", "pn4_monthly_turn", "PN IV IX.1, 26-34"),
])
def test_a_page_control_moved_once_is_in_the_store_the_file_and_a_fresh_session(tmp_path, monkeypatch, page, kind, key, alternative):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    at = make_app(page=page).run(timeout=300)
    widget = next(w for w in getattr(at.main, kind) if w.key == key)
    widget.set_value(alternative).run(timeout=300)
    assert_no_exception(at, f"{key} -> {alternative!r}")
    assert at.session_state["_" + key] == alternative
    prefs = json.loads((_data_dir() / "preferences.json").read_text())
    assert prefs["_" + key] == alternative
    fresh = _fresh_launch(page).run()
    assert next(w for w in getattr(fresh.main, kind) if w.key == key).value == alternative


# --- Coverage: provenance pinned where it was read against the corpus --------

def test_quotations_checked_against_the_corpus_stand_as_read(tmp_path, monkeypatch):
    """The sentences this pass read to chapter and sentence in the corpus
    (On Nativities 8.2, 17 and 2.11, 1-2; The Introduction Ch. 3, 4-5 and 64;
    PN IV VI.1, 4 and IX.7, 29-31, 42), pinned as the pages print them."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    lots = _petoskey(make_app(date="1982-11-19", page="lots")).run(timeout=300)
    killer = next(df.value for df in lots.main.dataframe if "Lot" in df.value.columns and any("killer" in str(v) for v in df.value["Lot"]))
    row = killer[killer["Lot"].str.contains("killer")].iloc[0]
    assert row["Formula"].startswith("Ascendant + (Moon - Saturn")
    detail = next(s for s in lots.main.selectbox if "provenance" in (s.key or ""))
    detail.select(next(o for o in detail.options if "killer" in o)).run(timeout=300)
    printed = " ".join(t for _, t in _strings(lots.main))
    assert "**Source.** Sahl, On Nativities Ch. 8.2, 17" in printed
    assert "from the lord of the Ascendant to the Moon by day (and by night the reverse), and is cast out from the Ascendant" in printed

    text = " ".join(t for _, t in _strings(make_app(page="configurations").run(timeout=300).main))
    assert "The banished planet is the planet which none of the planets connects to" in text
    chart = " ".join(t for _, t in _strings(make_app(page="chart").run(timeout=300).main))
    assert "advancing or retreating in Sahl's sense (The Introduction Ch. 3, 4-5): stake or succedent versus falling" in chart
    timing = " ".join(t for _, t in _strings(make_app(page="timing").run(timeout=300).main))
    assert "the lord of the hour in which the native was born" in timing
    days = " ".join(t for _, t in _strings(make_app(page="days").run(timeout=300).main))
    assert "59' 08\" a day" in days and "sign after sign" in days
    fardar = " ".join(t for _, t in _strings(make_app(page="fardar").run(timeout=300).main))
    assert "If you found both of the two lords of the triplicity of the luminary to be strong, they indicate high rank from the beginning of his life to its end" in fardar


def test_the_scope_note_names_exactly_what_is_left_out(tmp_path, monkeypatch):
    """M6, taken 2026-09-22: the note is in the JSON envelope, at the head of
    the Markdown and on the Sources page, and it names every entry of
    LEFT_OUT -- the list the coverage tests hold the pages to -- by a short
    phrase each, in a sentence that also names its page. It calls the chart-keyed lookups lookups,
    and says the Directing tables read the same for every chart. A note that
    named a carried reading would be false."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="sources").run(timeout=300)
    export = at.session_state["_analysis_export"]
    scope = export["scope"]
    assert "this chart's readings" in scope
    unnamed = [(entry.page, entry.named) for entry in LEFT_OUT if not _note_names(entry, scope)]
    assert not unnamed, unnamed
    assert "lookups keyed to this chart" in scope
    assert "read the same for every chart" in scope.partition("Directing: which ascensions")[2]
    # The readings it used to disclaim are carried now, so it must not name them.
    for reading in ("Planetary Condition", "Handing Over", "Corruption of the Moon",
                    "Forward-Looking Conditions", "Rays cast by ascensions"):
        assert reading not in scope, reading
    md = at.session_state["_analysis_markdown"]
    assert md.index(export["scope"]) < md.index("## Results")
    assert any(export["scope"] in m.value for m in at.main.markdown), "the Sources page states the scope"


def test_a_blank_city_text_is_an_empty_box(tmp_path, monkeypatch):
    """The verification's reopening of M1 through L6: whitespace only is
    "No place is resolved", never the bare pattern that matches every city."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for query in (" ", "   ", "\t", "\n", "\u00a0"):
        at = make_app(page="chart")
        at.session_state["manual_coords_key"] = False
        at.session_state["location_input_key"] = query
        at.run()
        assert_no_exception(at, f"place {query!r}")
        assert "Shanghai" not in _strip(at), (query, _strip(at))
        assert not [s for s in at.sidebar.selectbox if s.label.startswith("Select specific")], query


def test_a_typed_draft_name_is_one_name_on_the_strip_and_the_export(tmp_path, monkeypatch):
    """L4's typed-but-unsaved case: "Draft" typed into the name box names
    the strip, the hub and the export alike until it is saved."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart").run(timeout=300)
    next(t for t in at.sidebar.text_input if t.label.startswith("Chart name")).set_value("Draft").run()
    # A typed name is a form value until it is saved: the chart stays
    # "Unsaved chart" on the strip and in the export alike (the download's
    # file name may use the typed word; the chart's name does not).
    assert _strip(at).startswith("Unsaved chart"), _strip(at)
    assert at.session_state["_analysis_export"]["chart"] == "Unsaved chart"
