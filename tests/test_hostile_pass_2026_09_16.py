"""An adversarial review's reproductions.

An adversarial sweep of the input surface, run by an agent with no build
context against a worktree server on its own port, with XDG_DATA_HOME
pointed at a scratch copy of the owner's data. This file keeps the
reproductions in the suite (the model is tests/test_input_state_2026_09_16.py).

The ``xfail(strict=True)`` tests assert the RIGHT behaviour and fail today,
so they mark open defects: when one is fixed the test xpasses and the strict
marker turns that into a failure that says "un-xfail me". The plain tests are
the coverage -- things the pass tried to break and could not, pinned so they
stay broken-proof.

Findings (severity by consequence: lost shell / wrong qualification = high;
misleading stored record = critical; friction = medium):

* A valid birth date outside the ephemeris (year > ~3001) raises an
  uncaught swisseph error at module level, before st.navigation().run(), so
  no page and no recovery panel render and the nav bar goes inert. The
  shell guarantee does not cover a valid-but-uncomputable input.
* The Timing target reaches the same limit: a large Age (no upper
  bound on the widget) or a far target date crashes identically.
* A saved record with a type-wrong field (time_string/date_string/lat/
  utc_offset/target_age) crashes the whole script on load, and at launch if
  it is the last_chart. The store validator checks the shape, never the
  field types the engine consumes.
* A preferences file with a non-int _launches or a non-str last_chart
  crashes the app on open.
* A saved utc_offset outside +-14 is silently pulled to the WRONG bound
  (-14) by the widget's seeded clamp, the class fixed for lat/lon but not
  for the offset; the chart casts at UTC-14:00 with no warning and a re-save
  rewrites the record to -14.
* Verdict (Configurations) and Lean (Dignities) read the same Net and
  disagree at |Net| == 1 ("Good"/"Bad" vs "Indeterminate"), a follow-on to
  the reading of a zero net.

One finding (a finite 200-day search folded into the unbounded absence
line) was resolved while the review was under way; the guard
test below documents that it holds.
"""
import json
import os
from datetime import time
from pathlib import Path

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

FLORENCE = (43.7792, 11.2463)
ESCANABA = {"date_string": "1977-12-16", "time_string": "10:08:00",
            "time_standard": "Standard time (pytz)", "utc_offset": None,
            "location_query": "Escanaba, MI (US)", "lat": 45.74525, "lon": -87.06458,
            "target_mode": "Date", "target_date": "2026-09-15", "target_age": 48}


def _saved_path():
    p = Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fresh_launch(page="chart"):
    """An AppTest that seeds nothing -- a browser session, so the launch
    autoload and the preferences read run as they do for a real open."""
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=90)
    at._page_hash = calc_hash(page)
    return at


# --- a valid birth date the ephemeris cannot reach kills the shell -----------

def test_a_birth_year_past_the_ephemeris_keeps_the_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="3100-06-01", page="chart").run()
    assert_no_exception(at, "birth year 3100")
    assert len(at.main.header) == 1


def test_reference_survives_a_birth_year_past_the_ephemeris(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="3100-06-01", page="reference").run()
    assert_no_exception(at, "Reference at birth year 3100")
    assert len(at.main.dataframe) == 7


# --- the Timing target reaches the same limit --------------------------------

def test_a_large_timing_age_keeps_the_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1240-05-23", page="timing")
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 2000
    at.run()
    assert_no_exception(at, "timing age 2000 on the 1240 chart")


def test_a_far_timing_date_keeps_the_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1977-12-16", page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "3500-01-01"
    at.run()
    assert_no_exception(at, "timing target 3500-01-01")


# --- a corrupt saved record crashes on load, and at launch -------------------

@pytest.mark.parametrize("field,value", [
    ("time_string", 1008),
    ("date_string", 19771216),
    ("lat", "45.3"),
    ("utc_offset", "abc"),
    ("target_age", "abc"),
])
def test_a_type_wrong_saved_field_keeps_the_shell(tmp_path, monkeypatch, field, value):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    entry = {**ESCANABA, field: value}
    if field == "utc_offset":
        entry["time_standard"] = "Manual UTC offset"
    if field == "target_age":
        entry["target_mode"] = "Age"
    if field == "lat":
        entry["lon"] = "-84.9"
    _saved_path().write_text(json.dumps({"Rec": entry}))
    at = make_app(page="chart").run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    assert_no_exception(at, f"loading a record whose {field} is {value!r}")


def test_a_corrupt_last_chart_does_not_kill_the_launch(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    d = Path(tmp_path) / "Zij"
    d.mkdir(parents=True)
    (d / "saved_charts.json").write_text(json.dumps({"Rec": {**ESCANABA, "time_string": 1008}}))
    (d / "preferences.json").write_text(json.dumps({"last_chart": "Rec"}))
    at = _fresh_launch("chart").run()
    assert_no_exception(at, "launch with a corrupt last_chart")


# --- corrupt preferences crash the launch ------------------------------------

@pytest.mark.parametrize("prefs", [
    {"_launches": "many"},
    {"last_chart": ["a"]},
])
def test_corrupt_preferences_do_not_kill_the_launch(tmp_path, monkeypatch, prefs):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    d = Path(tmp_path) / "Zij"
    d.mkdir(parents=True)
    (d / "saved_charts.json").write_text(json.dumps({"Rec": ESCANABA}))
    (d / "preferences.json").write_text(json.dumps(prefs))
    at = _fresh_launch("chart").run()
    assert_no_exception(at, f"launch with preferences {prefs}")


# --- an out-of-range saved offset is pulled to the wrong bound ---------------

def test_an_out_of_range_saved_offset_is_refused_not_silently_clamped(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    entry = {**ESCANABA, "time_standard": "Manual UTC offset", "utc_offset": 99}
    _saved_path().write_text(json.dumps({"Rec": entry}))
    at = make_app(page="chart").run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    assert_no_exception(at, "loading a record with utc_offset 99")
    strip = next((c.value for c in at.main.caption if " · " in c.value), "")
    # It must not silently read as -14:00; either a range refusal or nothing,
    # never a confident wrong chart.
    assert "UTC-14:00" not in strip, strip


# --- Verdict and Lean read one Net and disagree at |Net| == 1 ----------------

def test_verdict_and_lean_agree_on_the_same_net(tmp_path, monkeypatch):
    """Both stand in the JSON alone."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    date = "1975-03-26"     # an invented chart whose table stands on the band's edge, on both sides
    results = make_app(date=date, page="chart").run().session_state["_analysis_export"]["results"]
    verdicts = results["Configurations"]["Planetary Condition"][0]["rows"]
    leans = {row["Planet"]: row["Lean"] for row in results["Dignities and places"]["Topical Planets in Houses"][0]["rows"]}
    nets = [int(row["Net"]) for row in verdicts]
    assert 1 in nets and -1 in nets, nets
    for row in verdicts:
        planet, net, verdict = row["Planet"], row["Net"], row["Verdict"]
        lean = leans[planet]
        indeterminate_here = (verdict == "Indeterminate")
        indeterminate_there = (lean == "Indeterminate")
        assert indeterminate_here == indeterminate_there, (
            f"{planet}: Net {net}, Verdict {verdict!r} vs Lean {lean!r}")


# --- a finite search reads as an unbounded absence ---------------------------

def test_a_finite_search_is_not_folded_into_the_unbounded_absence_line(tmp_path, monkeypatch):
    """RESOLVED during the review ("the forward search's horizon said
    where its zero rows are"). Forward-Looking Conditions, a finite 200-day
    search, is no longer folded into the generic "Not present in this chart"
    line beside truly unbounded absences; it renders in place with its own
    heading. Kept as a regression guard."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1977-12-16", page="configurations").run()
    absence = " ".join(c.value for c in at.main.caption if c.value.startswith("Not present"))
    assert "Forward-Looking Conditions" not in absence, absence


# --- Coverage: what the pass tried and could not break -----------------------

@pytest.mark.parametrize("bad", ["not-a-date", "1240-13-01", "", "1900-02-29",
                                 "10000-01-01", "0000-01-01", "1240-05-23T14:30"])
def test_garbage_dates_hold_the_shell_and_save_nothing(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=bad, page="chart").run()
    assert_no_exception(at, f"date {bad!r}")
    assert len(at.main.header) == 1
    assert any("Results have not updated" in w.value for w in at.main.warning)


# "nan, nan" is now Nan, in Thailand's Nan province (a typed region after a
# comma); "nan, -nan" is the not-a-number pair no place matches.
@pytest.mark.parametrize("query", ["91, 0", "0, 181", "nan, -nan", "'; DROP TABLE cities;--"])
def test_out_of_range_or_hostile_place_gives_one_error_no_crash(tmp_path, monkeypatch, query):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = query
    at.run()
    assert_no_exception(at, f"place {query!r}")
    assert len(at.main.header) == 1
    assert len(at.main.dataframe) == 0


@pytest.mark.parametrize("lat,lon", [(90.0, 20.0), (-90.0, 20.0), (66.6, 20.0), (89.0, 20.0)])
def test_polar_latitudes_cast_without_crashing(tmp_path, monkeypatch, lat, lon):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="2000-06-21", page="chart")
    at.session_state["time_input_key"] = time(12, 0)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.run()
    assert_no_exception(at, f"polar lat {lat}")
    assert len(at.main.header) == 1


@pytest.mark.parametrize("date,t", [("2025-03-09", time(2, 30)), ("2025-11-02", time(1, 30))])
def test_dst_gap_and_overlap_show_the_recovery_panel(tmp_path, monkeypatch, date, t):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=date, page="chart")
    at.session_state["time_standard_key"] = "Standard time (pytz)"
    at.session_state["time_input_key"] = t
    at.session_state["manual_lat_key"] = 40.71427
    at.session_state["manual_lon_key"] = -74.00597
    at.run()
    assert_no_exception(at, f"DST {date} {t}")
    assert len(at.main.header) == 1
    assert len(at.main.dataframe) == 0


def test_a_manual_offset_and_age_target_round_trip_through_a_fresh_session(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1977-12-16", page="timing")
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = -5.5
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 30
    at.run()
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value("RT").run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    entry = json.loads(_saved_path().read_text())["RT"]
    assert entry["utc_offset"] == -5.5 and entry["time_standard"] == "Manual UTC offset"
    assert entry["target_mode"] == "Age" and entry["target_age"] == 30

    fresh = make_app(page="chart").run()
    fresh.sidebar.selectbox(key="chart_picker").select("RT").run()
    assert_no_exception(fresh, "round trip")
    assert fresh.session_state["utc_offset_key"] == -5.5
    assert fresh.session_state["_target_age"] == 30
