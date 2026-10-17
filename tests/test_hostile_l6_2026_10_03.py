"""Hostile pass of 2026-10-03, lane L6 -- inputs, lifecycle, state and the shell.

Reproductions for the lane's report (scratchpad REPORT.md; the coordinator
files it under process/tae_docs/). The ``xfail(strict=True)`` tests assert
the RIGHT behaviour and fail today, so they mark open defects; when one is
fixed it xpasses and the strict marker says "un-xfail me". The plain tests
are the attacks the app survived, pinned so they stay survived.

Findings (severity by consequence; the rubric of the preamble):

* L6-01 -- "Standard time (pytz)" on a birth before standard time casts the
  chart at the ZONE'S reference city's LMT rounded to the minute, labels it
  "(LMT)", and nothing on any page says the offset is not the birthplace's
  local mean time (Delhi 1850: +05:53 against +05:08:48, ten degrees of
  Ascendant).
* L6-02 -- two sessions on one store (two browser tabs) each write their own
  stale mapping over the file: the second save drops the first tab's record,
  and a save from a tab opened before a delete resurrects the deleted one.
* L6-03 -- a record field that is a JSON integer too large for a float
  raises OverflowError INSIDE chart_record_fault, so selecting the record is
  a raw traceback and as last_chart the app is dead on open.
* L6-04 -- a saved_charts.json that starts with a UTF-8 BOM is "unreadable":
  every record vanishes from the picker and the next save writes a fresh
  store.
* L6-05 -- the Save button reads chart_ok before the named-zone refusals
  and the ephemeris check run, so a chart the same run refuses to cast (a
  date past 3000-09-20, a DST-gap time, a Julian-only date under a zone) is
  written as a record and announced "Saved".
* L6-06 -- a latitude outside +-90 seeded into the field is refused once;
  Streamlit then writes the widget's minimum (-90) into the key and the next
  run casts and saves a South-Pole chart with no error (session-state reach
  only; the loader and the browser both block 95).
* L6-07 -- a store record named exactly "-- New Chart --" is listed twice,
  cannot be selected or deleted, and as last_chart is loaded into the fields
  while the picker and the strip say "new"/"Unsaved".
* L6-08 -- the Markdown export's title takes the chart name raw: a newline
  splits the heading and markup is written verbatim.
* L6-09 -- a directory where saved_charts.json should be opens with an empty
  picker and no message; a save then leaves saved_charts.json.tmp behind.
* L6-10 -- a widget key holding a type its widget never produces (a str
  time, a str offset, a None latitude, an int place text) takes the script
  down with a raw traceback (session-state reach only).
"""
import json
import os
import re
import shutil
from datetime import datetime, time, timezone
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00",
            "time_standard": "Standard time (pytz)", "utc_offset": None,
            "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533,
            "target_mode": "Date", "target_date": "2026-09-15", "target_age": 43}
LMT, ZONE, MANUAL = "LMT (Local Mean Time)", "Standard time (pytz)", "Manual UTC offset"
NEW_YORK = (40.71427, -74.00597)
RECOVERY_WORDS = ("No place is resolved", "No matches found", "Latitude must be", "ephemeris covers",
                  "does not exist in", "happens twice in", "no standard-time zone", "Timezone boundary")


# --- helpers ---------------------------------------------------------------

def _data_dir():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store():
    return _data_dir() / "saved_charts.json"


def _prefs():
    return _data_dir() / "preferences.json"


def _fresh(page="chart"):
    """A session that seeds nothing: the launch autoload and the preferences
    read run as they do for a real open."""
    from streamlit.testing.v1 import AppTest
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash(page)
    return at


def _set(at, **state):
    for key, value in state.items():
        at.session_state[key] = value
    return at


def _strip(at):
    for caption in at.main.caption:
        if " · " in caption.value:
            return caption.value
    return ""


def _sidebar_texts(at):
    out = []
    for kind in ("error", "warning", "info", "success", "caption", "markdown"):
        out += [e.value for e in getattr(at.sidebar, kind)]
    return out


def _calc(at):
    """The Chart page's Calculation table as {Quantity: Value}."""
    return {r.iloc[0]: r.iloc[1] for _, r in at.main.dataframe[0].value.iterrows()}


def _name_box(at):
    return [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0]


def _save_button(at):
    return [b for b in at.sidebar.button if "Save" in b.label][0]


def _save_as(at, name):
    _name_box(at).set_value(name).run()
    _save_button(at).click().run()
    return at


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _petoskey(at, date="1982-11-19"):
    return _set(at, manual_lat_key=PETOSKEY["lat"], manual_lon_key=PETOSKEY["lon"],
                time_input_key=time(11, 44), time_standard_key=ZONE, date_input_key=date)


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable XDG directory; preferences stay off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    """A disposable XDG directory with the preferences file live."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    return tmp_path


# =============================================================================
# The findings (strict xfail: the right behaviour, failing today)
# =============================================================================

def test_l6_01_zone_lmt_before_standard_time_is_qualified():
    """Delhi 1850 under a named zone: the zone's database then holds only the
    local mean time of its reference city (Kolkata's +05:53, rounded to the
    minute) where the birthplace's own local mean time is +05:08:48. The
    owner's ruling (D1) is that the chart is REFUSED, not cast, with a
    sentence that names the date and points to LMT."""
    at = _set(make_app(date="1850-05-23", page="chart"), time_standard_key=ZONE,
              manual_lat_key=28.6, manual_lon_key=77.2).run()
    assert_no_exception(at)
    errors = [e.value for e in at.sidebar.error]
    assert any("1850-05-23" in text and "LMT" in text for text in errors), errors
    # An announced offset is "UTC offset" followed by the offset itself
    # (+hh:mm); the refusal and the sidebar's notes name the option "Manual UTC
    # offset", which no offset follows.
    announced = [text for text in _sidebar_texts(at) if re.search(r"UTC offset [+-]\d\d:\d\d", text)]
    assert announced == [], "no offset is announced for a chart that is not cast"
    assert any("1850-05-23" in e.value and "LMT" in e.value for e in at.main.error), (
        "the page's recovery panel carries the same sentence")


def test_l6_02_two_sessions_do_not_lose_each_others_records(scratch):
    a = make_app(date="1983-11-19", page="chart").run()
    b = make_app(date="1990-01-01", page="chart").run()
    _save_as(a, "From A")
    assert set(json.loads(_store().read_text())) == {"From A"}
    _save_as(b, "From B")
    assert_no_exception(b)
    assert set(json.loads(_store().read_text())) >= {"From A", "From B"}, (
        f"B's save wrote {list(json.loads(_store().read_text()))}: A's record is gone")


def test_l6_03_pure_validator_refuses_a_huge_integer_without_raising(engine):
    """chart_record_fault is the gate that keeps a bad record from the widgets;
    it must answer with a fault, never raise. Today `_is_real_number` hands a
    Python int above ~1.8e308 to math.isfinite, which raises."""
    for field in ("lat", "lon", "utc_offset", "target_age"):
        for value in (10 ** 400, -(10 ** 400)):
            fault = engine["chart_record_fault"]({**PETOSKEY, field: value})
            assert fault is not None, f"{field}={value!r} must be a fault"


def test_l6_03_a_huge_integer_field_is_refused_not_raised(scratch):
    _store().write_text(json.dumps({"Huge": {**PETOSKEY, "lat": 10 ** 400}}))
    at = make_app(page="chart").run()
    _picker(at).select("Huge").run()
    assert_no_exception(at, "selecting a record with a huge latitude")
    assert any("could not be loaded" in v for v in _sidebar_texts(at))


def test_l6_04_a_bom_prefixed_store_still_loads(scratch):
    _store().write_bytes("﻿".encode("utf-8") + json.dumps({"Good": PETOSKEY}).encode("utf-8"))
    at = make_app(page="chart").run()
    assert_no_exception(at)
    assert "Good" in _picker(at).options, (
        f"picker {_picker(at).options}; sidebar {[v for v in _sidebar_texts(at) if 'could not be read' in v]}")


@pytest.mark.parametrize("label, state", [
    ("past the ephemeris", {"date_input_key": "3100-01-01"}),
    ("DST spring-forward gap", {"date_input_key": "2024-03-10", "time_input_key": time(2, 30), "time_standard_key": ZONE,
                                "manual_lat_key": NEW_YORK[0], "manual_lon_key": NEW_YORK[1]}),
    ("Julian-only date under a zone", {"date_input_key": "1300-02-29", "time_standard_key": ZONE}),
])
def test_l6_05_save_refuses_a_chart_the_run_refuses_to_cast(scratch, label, state):
    at = _set(make_app(date="1240-05-23", page="chart"), **state).run()
    assert_no_exception(at)
    assert not at.main.dataframe, f"the premise: {label} casts no chart"
    assert any(any(w in e.value for w in RECOVERY_WORDS) for e in at.main.error), "the premise: the recovery panel"
    _save_as(at, "Refused")
    assert_no_exception(at, "the save")
    written = json.loads(_store().read_text()) if _store().exists() else {}
    assert "Refused" not in written, f"{label}: a chart the run refused was saved as {written['Refused']!r}" if "Refused" in written else ""
    assert not any("Saved 'Refused'" in v for v in _sidebar_texts(at))


def test_l6_06_a_refused_latitude_stays_refused_on_the_next_run():
    at = _set(make_app(date="1240-05-23", page="chart"), manual_lat_key=95.0).run()
    assert_no_exception(at)
    assert not at.main.dataframe, "the premise: the first run refuses 95"
    at.run()
    assert_no_exception(at)
    assert not at.main.dataframe or "-90.00" not in _strip(at), (
        f"the second run cast {_strip(at).splitlines()[0]!r} with no error")


def test_l6_07_a_record_named_like_the_sentinel_is_not_loaded_as_a_new_chart(prefs_on):
    _store().write_text(json.dumps({"-- New Chart --": PETOSKEY, "Other": {**PETOSKEY, "date_string": "1990-01-01"}}))
    _prefs().write_text(json.dumps({"last_chart": "-- New Chart --"}))
    at = _fresh("chart").run()
    assert_no_exception(at)
    options = _picker(at).options
    assert len(options) == len(set(options)), f"the picker lists {options}"
    held = at.session_state["date_input_key"]
    assert not (_strip(at).startswith("Unsaved chart") and held == PETOSKEY["date_string"]), (
        f"the fields hold the record ({held}) while the strip says {_strip(at).splitlines()[0]!r}")


def test_l6_08_markdown_export_title_survives_a_hostile_name(scratch):
    name = "<script>alert(1)</script> line one\nline two"
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert_no_exception(at)
    assert _picker(at).value == name.strip()
    md = at.session_state["_analysis_markdown"]
    heading = md.splitlines()[0]
    assert heading.startswith("# "), md[:200]
    assert "<script>" not in heading and "line two" in heading, (
        f"heading {heading!r}: the name's newline split it and its markup is raw")


def test_l6_09_an_unreadable_store_is_announced_even_without_a_copy(scratch):
    _store().mkdir(parents=True)
    at = make_app(date="1240-05-23", page="chart").run()
    assert_no_exception(at)
    assert any("could not be read" in v for v in _sidebar_texts(at)), (
        f"no sentence in the sidebar: {[v[:60] for v in _sidebar_texts(at)]}")


@pytest.mark.parametrize("key, value", [
    ("time_input_key", "14:30:00"),
    ("utc_offset_key", "5"),
    ("manual_lat_key", None),
    ("location_input_key", 5),
])
def test_l6_10_a_wrong_type_in_a_widget_key_is_refused_not_raised(key, value):
    at = make_app(date="1240-05-23", page="chart")
    if key == "utc_offset_key":
        at.session_state["time_standard_key"] = MANUAL
    if key == "location_input_key":
        at.session_state["manual_coords_key"] = False
    at.session_state[key] = value
    at.run()
    assert_no_exception(at, f"{key}={value!r}")


def test_l6_10_a_nan_target_age_is_refused_not_raised():
    """The fifth wrong-typed key of L6-10: an age that is not a finite number."""
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["target_mode"] = "Age"
    at.session_state["_target_age"] = float("nan")
    at.run()
    assert_no_exception(at, "_target_age=nan")


# =============================================================================
# Attacks that held (plain tests, so they stay held)
# =============================================================================

@pytest.mark.parametrize("draft", ["not-a-date", "1240-13-01", "0000-01-01", "", "12400-05-23", "1240/05/23",
                                   "1240-02-30", "1900-02-29", "-1240-05-23", "1240-05-23T14:30"])
def test_an_unparseable_date_keeps_the_last_chart_and_the_shell(scratch, draft):
    at = _set(make_app(date="1240-05-23", page="chart"), date_input_key=draft).run()
    assert_no_exception(at)
    assert [h.value for h in at.main.header] == ["Chart"]
    assert _strip(at).startswith("Unsaved chart · 1240-05-23 14:30:00")
    assert any("Date must be YYYY-MM-DD" in e.value for e in at.sidebar.error)
    assert any("Results have not updated" in w.value for w in at.main.warning)
    _save_as(at, "Bad date")
    assert not _store().exists() or "Bad date" not in json.loads(_store().read_text())


@pytest.mark.parametrize("draft, shown", [
    ("1240-5-23", "1240-05-23"), (" 1240-05-23 ", "1240-05-23"), ("1240-05-23\n", "1240-05-23"),
    ("١٢٤٠-٠٥-٢٣", "1240-05-23"),   # Arabic-Indic digits: \d and int() both take them
    ("1300-02-29", "1300-02-29"), ("1600-02-29", "1600-02-29"), ("0001-01-01", "0001-01-01"),
    ("1-1-1", "0001-01-01"), ("1582-10-10", "1582-10-10"), ("3000-09-20", "3000-09-20"),
])
def test_a_tolerated_date_form_casts_the_date_it_means(draft, shown):
    at = _set(make_app(date="1240-05-23", page="chart"), date_input_key=draft).run()
    assert_no_exception(at)
    assert f" · {shown} 14:30:00 · " in _strip(at)
    assert not at.sidebar.error


@pytest.mark.parametrize("draft", ["9999-12-31", "3000-09-21", "3100-06-01"])
def test_a_date_past_the_ephemeris_keeps_the_shell_and_names_the_limit(draft):
    at = _set(make_app(date="1240-05-23", page="chart"), date_input_key=draft).run()
    assert_no_exception(at)
    assert [h.value for h in at.main.header] == ["Chart"]
    assert not at.main.dataframe
    assert any("3000-09-20" in e.value for e in at.main.error)
    for page in ("reference", "sources"):
        other = _set(make_app(date="1240-05-23", page=page), date_input_key=draft).run()
        assert_no_exception(other)
        assert other.main.dataframe, f"{page} lost its tables"


@pytest.mark.parametrize("clock, ut", [(time(23, 59, 59), "UT 1240-05-23 23:15:00"), (time(0, 0, 0), "UT 1240-05-22 23:15:01")])
def test_the_seconds_edges_cast_and_carry_the_date(clock, ut):
    at = _set(make_app(date="1240-05-23", page="chart"), time_input_key=clock).run()
    assert_no_exception(at)
    assert any(ut in v for v in _sidebar_texts(at))


@pytest.mark.parametrize("offset, label, ut", [
    (-14.0, "UTC-14:00", "UT 1240-05-24 04:30:00"), (14.0, "UTC+14:00", "UT 1240-05-23 00:30:00"),
    (13.75, "UTC+13:45", "UT 1240-05-23 00:45:00"), (0.1, "UTC+00:06", "UT 1240-05-23 14:24:00"),
    (5.5, "UTC+05:30", "UT 1240-05-23 09:00:00"), (-5.1, "UTC-05:06", "UT 1240-05-23 19:36:00"),
    (-0.0, "UTC+00:00", "UT 1240-05-23 14:30:00"),
])
def test_a_manual_offset_is_printed_the_same_in_the_box_the_strip_and_the_table(offset, label, ut):
    at = _set(make_app(date="1240-05-23", page="chart"), time_standard_key=MANUAL, utc_offset_key=offset).run()
    assert_no_exception(at)
    assert f" · {label} · " in _strip(at)
    assert any(label in v and ut in v for v in _sidebar_texts(at))
    assert _calc(at)["Time standard"] == label


def test_a_manual_offset_is_printed_the_same_in_the_box_the_strip_and_the_table_blank():
    """The (None, ...) row of the test above, split out: the blank box is the case
    that is refused (HP-09), so there is no label to print and no UTC+00:00 anywhere."""
    at = _set(make_app(date="1240-05-23", page="chart"), time_standard_key=MANUAL, utc_offset_key=None).run()
    assert_no_exception(at)
    texts = _sidebar_texts(at)
    assert any("The UTC offset box is blank." in v for v in texts) and all("UTC+00:00" not in v for v in texts), texts
    assert "UTC+00:00" not in _strip(at)
    assert not at.main.dataframe, "no chart is cast, so no Calculation table"


def test_an_out_of_range_offset_is_refused_by_the_loader_not_clamped(scratch):
    """H5 of 2026-09-16, re-tested: 99 and 14.25 both stay in the file, the box
    keeps 0.0, the sentence names the stored value, the strip reads modified."""
    _store().write_text(json.dumps({"Off99": {**PETOSKEY, "time_standard": MANUAL, "utc_offset": 99},
                                    "Off14q": {**PETOSKEY, "time_standard": MANUAL, "utc_offset": 14.25}}))
    at = make_app(page="chart").run()
    for name, stored in (("Off99", "99"), ("Off14q", "14.25")):
        _picker(at).select(name).run()
        assert_no_exception(at)
        assert at.session_state["utc_offset_key"] == 0.0
        assert any(f"UTC offset of {stored}" in v for v in _sidebar_texts(at))
        assert _strip(at).startswith(f"{name} (modified)")
    assert json.loads(_store().read_text())["Off99"]["utc_offset"] == 99


@pytest.mark.parametrize("text", ["", "   ", "\t", "zzzz-no-such-city", "New York, NY", "Flor%", "%", "_", "\\",
                                  "x" * 300, "45.3733,  -84.9553,", "91, 0", "0, 181", "nan, nan", "1e2, 0",
                                  "45,37, -84,95", "45.3733° N, 84.9553° W", "1240, 5", "Florence,", "Zurich"])
def test_a_place_text_that_resolves_to_nothing_casts_nothing_and_keeps_the_shell(text):
    """M1 and its L6 regression (a lone space cast Shanghai) re-tested."""
    at = _set(make_app(date="1240-05-23", page="chart"), manual_coords_key=False, location_input_key=text).run()
    assert_no_exception(at)
    assert [h.value for h in at.main.header] == ["Chart"]
    assert not at.main.dataframe
    assert "Shanghai" not in _strip(at) and _strip(at) == ""
    # A text longer than any place is refused before either lookup, with its
    # own sentence (the security release's lane SEC5, ruling 160).
    why = (("This entry is too long to be a city or a latitude, longitude pair, so it was not looked up.",)
           if len(text) > 200 else ("No place is resolved.", "No matches found in offline atlas."))
    assert any(e.value in why for e in at.main.error)


@pytest.mark.parametrize("text, place", [
    ("Florence", "Florence, 16 (IT) 43.78, 11.25"), ("florence", "Florence, 16 (IT) 43.78, 11.25"),
    ("'s-Hertogenbosch", "'s-Hertogenbosch, 06 (NL) 51.70, 5.30"), ("Zürich", "Zürich, ZH (CH) 47.37, 8.55"),
    ("Saint-Étienne", "Saint-Étienne, 84 (FR) 45.43, 4.39"), ("New York", "New York City, NY (US) 40.71, -74.01"),
    ("45.3733, -84.9553", "45.37, -84.96"), ("45.3733,-84.9553", "45.37, -84.96"), ("45.3733 -84.9553", "45.37, -84.96"),
    ("45.3733,\n-84.9553", "45.37, -84.96"), ("+45.3733, +11.2463", "45.37, 11.25"), ("-90, -180", "-90.00, -180.00"),
    ("90, 180", "90.00, 180.00"), ("12, 34", "12.00, 34.00"), ("1,5", "1.00, 5.00"), ("-0, -0", "0.00, 0.00"),
])
def test_a_place_text_that_resolves_casts_where_it_says(text, place):
    at = _set(make_app(date="1240-05-23", page="chart"), manual_coords_key=False, location_input_key=text).run()
    assert_no_exception(at)
    assert _strip(at).splitlines()[0].rstrip().endswith(place), _strip(at).splitlines()[0]


def test_the_coordinate_toggle_keeps_the_place_in_both_directions():
    """F02 and M2 re-tested: ON from a city text, OFF back to the box."""
    at = _set(make_app(date="1240-05-23", page="chart"), manual_coords_key=False, location_input_key="Petoskey").run()
    assert "45.37, -84.96" in _strip(at)
    toggle = [t for t in at.sidebar.toggle if t.label.startswith("Enter coordinates")][0]
    toggle.set_value(True).run()
    assert_no_exception(at)
    assert (at.session_state["manual_lat_key"], at.session_state["manual_lon_key"]) == (45.37334, -84.95533)
    assert "45.37, -84.96" in _strip(at)
    toggle = [t for t in at.sidebar.toggle if t.label.startswith("Enter coordinates")][0]
    toggle.set_value(False).run()
    assert_no_exception(at)
    assert at.session_state["location_input_key"] == "45.3733, -84.9553"
    assert "45.37, -84.96" in _strip(at)


@pytest.mark.parametrize("lat, lon", [(95.0, 0.0), (0.0, -200.0), (float("nan"), 0.0), (90.0000001, 0.0), (1e308, 0.0)])
def test_an_impossible_seeded_coordinate_is_refused_on_the_run_that_seeds_it(lat, lon):
    at = _set(make_app(date="1240-05-23", page="chart"), manual_lat_key=lat, manual_lon_key=lon).run()
    assert_no_exception(at)
    assert not at.main.dataframe
    assert any("Latitude must be between -90 and 90" in e.value for e in at.sidebar.error)


@pytest.mark.parametrize("date, clock, word", [("2024-03-10", time(2, 30), "does not exist in America/New_York"),
                                               ("2024-11-03", time(1, 30), "happens twice in America/New_York")])
def test_the_dst_gap_and_overlap_are_refused_with_the_shell(date, clock, word):
    for page in ("chart", "victors", "reference"):
        at = _set(make_app(date=date, page=page), time_standard_key=ZONE, time_input_key=clock,
                  manual_lat_key=NEW_YORK[0], manual_lon_key=NEW_YORK[1]).run()
        assert_no_exception(at, page)
        assert at.main.header
        if page == "reference":
            assert at.main.dataframe
        else:
            assert not at.main.dataframe
            assert any(word in e.value for e in at.main.error)


@pytest.mark.parametrize("lat", [66.5634, 80.0, 89.9, 90.0, -90.0])
@pytest.mark.parametrize("date", ["2000-06-21", "2000-12-21"])
def test_a_polar_chart_renders_the_pages_that_read_it_without_an_exception(lat, date):
    for page in ("chart", "timing", "days"):
        at = _set(make_app(date=date, page=page), manual_lat_key=lat, manual_lon_key=0.0, time_input_key=time(12, 0)).run()
        assert_no_exception(at, f"{page} at {lat}")
        assert at.main.header


@pytest.mark.parametrize("age, kept", [(1761, True), (9999, True), (1760, False), (0, False), (-1, False)])
def test_the_timing_age_is_bounded_by_the_ephemeris_and_kept_when_past_it(age, kept):
    at = _set(make_app(date="1240-05-23", page="timing"), _target_mode="Age", _target_age=age).run()
    assert_no_exception(at)
    box = [n for n in at.main.number_input if n.label.startswith("Age")][0]
    assert box.max == 1760
    if kept:
        assert any("beyond this app's ephemeris (3000-09-20)" in e.value for e in at.main.error)
        assert box.value == 786
    else:
        assert not at.main.error
        assert box.value == max(0, age)


@pytest.mark.parametrize("target", ["1200-01-01", "1240-05-22"])
def test_a_target_before_the_birth_is_refused_and_the_switch_to_age_clears_it(target):
    """M3 re-tested, with the mode switch the verification tried."""
    at = _set(make_app(date="1240-05-23", page="timing"), _target_mode="Date", _target_date=target).run()
    assert_no_exception(at)
    assert any("is before the birth (1240-05-23)" in e.value for e in at.main.error)
    at.main.radio(key="target_mode").set_value("Age").run()
    assert_no_exception(at)
    assert not at.main.error
    assert [n.value for n in at.main.number_input if n.label.startswith("Age")] == [786]


@pytest.mark.parametrize("target", ["not-a-date", "", "3000-09-21", "9999-12-31"])
def test_an_unusable_target_keeps_the_last_valid_target(target):
    at = _set(make_app(date="1240-05-23", page="timing"), _target_mode="Date", _target_date=target).run()
    assert_no_exception(at)
    today = datetime.now().date().isoformat()
    assert at.session_state["_target_date"] == today
    assert [t.value for t in at.main.text_input if t.label.startswith("Target")] == [today]


def test_the_reform_gap_prints_the_ut_in_its_own_calendar_on_every_page():
    """M4 and its verification re-tested at cb7390d."""
    at = _set(make_app(date="1582-10-15", page="chart"), time_input_key=time(0, 30), time_standard_key=MANUAL,
              utc_offset_key=5.0, manual_lon_key=75.0).run()
    assert _calc(at)["Universal time"].startswith("1582-10-04 19:30:00 UT (Julian calendar")
    at = make_app(date="1582-10-10", page="chart").run()
    assert _calc(at)["Universal time"].startswith("1582-10-20 13:45:01 UT (Gregorian calendar")
    at = _set(make_app(date="1582-10-10", page="timing"), _target_mode="Age", _target_age=0).run()
    said = [m.value for m in at.main.markdown if "revolution of the year fell on" in m.value]
    assert said and "**1582-10-20**" in said[0]


@pytest.mark.parametrize("standard, extra", [
    (LMT, {"_target_mode": "Date", "_target_date": "1300-01-01"}),
    (ZONE, {"date_input_key": "1982-11-19", "time_input_key": time(11, 44, 7), "_target_mode": "Age", "_target_age": 30}),
    (MANUAL, {"utc_offset_key": -5.75, "_target_mode": "Date", "_target_date": "1290-06-15"}),
    (MANUAL, {"utc_offset_key": 13.75, "_target_mode": "Age", "_target_age": 0}),
])
def test_a_record_round_trips_through_a_fresh_session(scratch, standard, extra):
    at = _set(make_app(date="1240-05-23", page="timing"), time_standard_key=standard, **extra).run()
    keys = ("date_input_key", "time_input_key", "time_standard_key", "utc_offset_key", "manual_lat_key",
            "manual_lon_key", "_target_mode", "_target_date", "_target_age")
    before = {k: at.session_state[k] for k in keys if k in at.session_state}
    strip_before = _strip(at).split(" · ", 1)[1]
    _save_as(at, "Round trip")
    assert_no_exception(at)
    fresh = _fresh("timing").run()
    _picker(fresh).select("Round trip").run()
    assert_no_exception(fresh)
    after = {k: fresh.session_state[k] for k in keys if k in fresh.session_state}
    assert after == before
    assert _strip(fresh).split(" · ", 1)[1] == strip_before
    assert _strip(fresh).startswith("Round trip ·")


def test_a_malformed_store_is_preserved_and_announced_and_never_rewritten_by_a_load(scratch):
    for content in ("", "[]", "null", '"string"', '{"A": null}', '{"A": []}'):
        for stale in _data_dir().glob("saved_charts.json*"):
            stale.unlink()
        _store().write_text(content)
        at = make_app(page="chart").run()
        assert_no_exception(at, content)
        assert _picker(at).options == ["-- New Chart --"]
        assert any("could not be read" in v for v in _sidebar_texts(at)), content
        assert _store().read_text() == content, "a load rewrote the store"
        copies = list(_data_dir().glob("saved_charts.json.unreadable-*"))
        assert len(copies) == 1 and copies[0].read_text() == content


@pytest.mark.parametrize("field, value, word", [
    ("utc_offset", float("nan"), "UTC offset"), ("lat", float("inf"), "latitude"), ("lat", "abc", "latitude"),
    ("time_string", 1144, "time of day"), ("date_string", 19821119, "date"), ("target_age", 3e9, "target age"),
    ("target_age", -1, "target age"), ("lon", 181, "longitude"),
])
def test_a_record_with_a_bad_field_is_refused_with_its_sentence_and_left_in_the_file(scratch, field, value, word):
    """H3 of 2026-09-16 and H1 of 2026-09-22 re-tested, NaN written as JSON's
    NaN literal included."""
    _store().write_text(json.dumps({"R": {**PETOSKEY, field: value}}))
    at = make_app(page="chart").run()
    _picker(at).select("R").run()
    assert_no_exception(at)
    assert any("'R' could not be loaded" in v and word in v for v in _sidebar_texts(at))
    assert _strip(at).startswith("Unsaved chart · 1240-05-23")
    assert "R" in json.loads(_store().read_text())


def test_a_refused_last_chart_opens_with_the_sentence_on_every_page(prefs_on):
    _store().write_text(json.dumps({"Bad": {**PETOSKEY, "lat": "abc"}}))
    _prefs().write_text(json.dumps({"last_chart": "Bad"}))
    for page in ("chart", "timing", "reference", "sources"):
        at = _fresh(page).run()
        assert_no_exception(at, page)
        assert at.main.header
        assert _picker(at).value == "-- New Chart --"
        assert any("'Bad' could not be loaded" in v for v in _sidebar_texts(at))


def test_a_preferences_file_of_the_wrong_shape_or_types_still_opens_the_app(prefs_on):
    for content in ('{"_launches": "many", "_moon_rays_15": "yes", "_reading_depth": 3, "_target_mode": ["Age"], '
                    '"last_chart": ["a"], "home_place": "x"}', "[1, 2]", "{{{", '{"home_place": {"label": "X", "lat": 95.0, "lon": 0.0}}'):
        _prefs().write_text(content)
        at = _fresh("chart").run()
        assert_no_exception(at, content)
        assert [h.value for h in at.main.header] == ["Chart"]
        here_now = [b for b in at.sidebar.button if "Here" in b.label][0]
        assert here_now.disabled


def test_here_and_now_at_the_fall_back_overlap_casts_the_right_instant_and_saves_nothing(prefs_on, monkeypatch):
    import engine
    _store().write_text(json.dumps({"Pet": PETOSKEY}))
    # _fresh() re-imports the engine when XDG_DATA_HOME has moved (conftest's
    # sync_engine_to_environment), which would wipe a clock frozen before it.
    at = _fresh("chart")
    monkeypatch.setattr(engine, "now_utc", lambda: datetime(2024, 11, 3, 5, 30, tzinfo=timezone.utc))
    at.run()
    _picker(at).select("Pet").run()
    at.session_state["home_place"] = {"label": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533}
    at.run()
    [b for b in at.sidebar.button if "Here" in b.label][0].click().run()
    assert_no_exception(at)
    assert at.session_state["time_standard_key"] == MANUAL and at.session_state["utc_offset_key"] == -4.0
    assert at.session_state["date_input_key"] == "2024-11-03" and at.session_state["time_input_key"] == time(1, 30)
    assert _strip(at).startswith("Pet (modified) · 2024-11-03 01:30:00 · UTC-04:00")
    assert json.loads(_store().read_text())["Pet"] == PETOSKEY


@pytest.mark.parametrize("name", ["-- New Chart --", "--new chart--", "-- NEW CHART --", "", "   "])
def test_a_reserved_or_empty_name_is_refused(scratch, name):
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert_no_exception(at)
    assert not _store().exists()
    assert any(v in ("That name is reserved; choose another.", "Enter a name before saving.") for v in _sidebar_texts(at))


def test_a_hostile_name_is_escaped_in_the_html_export_and_the_svg_hub(scratch):
    name = "]]></svg><script>alert(1)</script>&\"'<b>x</b>"
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert_no_exception(at)
    assert _picker(at).value == name
    from conftest import natal_wheel_envelope
    svg = natal_wheel_envelope(at.main)["svg"]
    assert "<script>" not in svg and "]]></svg>" not in svg and "&lt;script&gt;" in svg
    html = at.session_state["_analysis_html"]
    body = html[html.find("<body"):]
    assert "<script>alert" not in body and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert at.session_state["_analysis_export"]["chart"] == name
    assert json.loads(_store().read_text())[name]["date_string"] == "1240-05-23"


