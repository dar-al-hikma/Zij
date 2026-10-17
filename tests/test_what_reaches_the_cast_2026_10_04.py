"""What reaches the cast from a saved record or from session state: lane G4
of the re-pass of 2026-10-04 (L6R-N3, L6-06 partly, L6-10 partly), the cases
beside the re-pass's own pins in ``test_repass_l6_2026_10_04.py``.

* A record lacking its date, its time, or under the manual standard its
  offset, is refused on load with a sentence; nothing is cast under its name,
  at a launch as on a selection, and no "Edited since it was saved." is said
  of it.
* A refused coordinate pair stays refused on every later run, a NaN
  longitude as a NaN latitude, until a box is changed.
* A reading's widget key holding a value outside its options is dropped as
  its store key is, and a valid reading is kept.
"""
import ast
import json
import os
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

LMT, MANUAL = "LMT (Local Mean Time)", "Manual UTC offset"
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
FIRST = {**FLORENCE_REC, "date_string": "1990-01-01", "time_string": "22:15:00",
         "time_standard": MANUAL, "utc_offset": 5.0}


def _store():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d / "saved_charts.json"


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


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


# --- L6R-N3: the fields the cast cannot do without ---------------------------

@pytest.mark.parametrize("record, lack", [
    ({k: v for k, v in FLORENCE_REC.items() if k != "date_string"}, "date"),
    ({k: v for k, v in FLORENCE_REC.items() if k != "time_string"}, "time"),
    ({**FLORENCE_REC, "time_standard": MANUAL}, "UTC offset for its manual time standard"),
    ({**FLORENCE_REC, "time_standard": MANUAL, "utc_offset": None}, "UTC offset for its manual time standard"),
])
def test_a_record_lacking_a_field_the_cast_needs_is_named(engine, record, lack):
    assert engine["chart_record_lack"](record) == lack


@pytest.mark.parametrize("record", [
    FLORENCE_REC,
    {**FLORENCE_REC, "utc_offset": None},
    {**FLORENCE_REC, "time_standard": MANUAL, "utc_offset": -3.5},
    {k: v for k, v in FLORENCE_REC.items() if k != "time_standard"},
])
def test_a_record_carrying_what_the_cast_needs_lacks_nothing(engine, record):
    assert engine["chart_record_lack"](record) is None


@pytest.mark.parametrize("name, record, said", [
    ("No time", {k: v for k, v in FLORENCE_REC.items() if k != "time_string"}, "it holds no time."),
    ("Null offset", {**FLORENCE_REC, "time_standard": MANUAL, "utc_offset": None},
     "it holds no UTC offset for its manual time standard."),
])
def test_a_selected_record_lacking_a_field_is_refused_with_its_sentence(scratch, name, record, said):
    _store().write_text(json.dumps({"First": FIRST, name: record}))
    at = make_app(date="1240-05-23", page="chart").run()
    at.sidebar.selectbox(key="chart_picker").select("First").run()
    at.sidebar.selectbox(key="chart_picker").select(name).run()
    assert_no_exception(at)
    texts = _sidebar_texts(at)
    assert f"'{name}' could not be loaded: {said}" in texts, texts
    assert "Edited since it was saved." not in texts, texts
    assert _strip(at).startswith("Unsaved chart · "), _strip(at).splitlines()[:1]


def test_a_record_loaded_after_a_refused_one_is_named_again(scratch):
    _store().write_text(json.dumps({"First": FIRST, "No date": {k: v for k, v in FLORENCE_REC.items()
                                                                if k != "date_string"}}))
    at = make_app(date="1240-05-23", page="chart").run()
    at.sidebar.selectbox(key="chart_picker").select("No date").run()
    assert _strip(at).startswith("Unsaved chart · "), "the premise: the record is refused"
    at.sidebar.selectbox(key="chart_picker").select("First").run()
    assert_no_exception(at)
    assert _strip(at).startswith("First · 1990-01-01 22:15:00 · UTC+05:00"), _strip(at).splitlines()[:1]
    assert not [v for v in _sidebar_texts(at) if "could not be loaded" in v]


def test_a_last_chart_lacking_its_time_opens_on_no_chart_with_its_sentence(scratch, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    _store().write_text(json.dumps({"No time": {k: v for k, v in FLORENCE_REC.items() if k != "time_string"}}))
    (_store().parent / "preferences.json").write_text(json.dumps({"last_chart": "No time"}))
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.run()
    assert_no_exception(at)
    assert "'No time' could not be loaded: it holds no time." in _sidebar_texts(at)
    assert at.sidebar.selectbox(key="chart_picker").value != "No time"
    assert _strip(at).startswith("Unsaved chart · 1240-05-23 14:30:00"), _strip(at).splitlines()[:1]


# --- L6-06: a refused pair stays refused ------------------------------------

@pytest.mark.parametrize("lat, lon", [(43.77, float("nan")), (float("nan"), float("nan"))])
def test_a_nan_coordinate_stays_refused_until_a_box_is_changed(lat, lon):
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    for run in range(3):
        at.run()
        assert_no_exception(at, f"run {run + 1}")
        assert not at.main.dataframe, f"run {run + 1} cast {_strip(at).splitlines()[:1]}"
    [n for n in at.sidebar.number_input if n.label == "Latitude"][0].set_value(45.0).run()
    [n for n in at.sidebar.number_input if n.label == "Longitude"][0].set_value(11.0).run()
    assert_no_exception(at)
    assert at.main.dataframe, "the boxes were changed and the chart is still refused"


# --- L6-10: a reading's keys outside its options ----------------------------

def _registry_default(engine, key):
    """The store key and the default of the READINGS_REGISTRY row that holds
    `key` (its widget key or its store key), as app.py declares them: the
    tuple literal read with ast, a default written as `NAME[i]` looked up in
    the engine, so that no value is copied here."""
    tree = ast.parse(APP_PATH.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "READINGS_REGISTRY"
                                                for t in node.targets):
            for row in node.value.elts:
                _label, widget_key, store_key, default, _page = row.elts
                if key not in (widget_key.value, store_key.value):
                    continue
                if isinstance(default, ast.Constant):
                    return store_key.value, default.value
                return store_key.value, engine[default.value.id][default.slice.value]
    raise LookupError(f"{key} is not in READINGS_REGISTRY")


@pytest.mark.parametrize("key, value", [("connection_rule", 5), ("_connection_rule", "Ptolemy")])
@pytest.mark.parametrize("page", ["chart", "timing"])
def test_a_reading_key_outside_its_options_falls_to_the_default(engine, page, key, value):
    store_key, default = _registry_default(engine, key)
    options = engine["_preference_option_tuples"]()[store_key]
    assert default in options and value not in options, (default, value, options)
    at = make_app(date="1240-05-23", page=page)
    at.session_state[key] = value
    at.run()
    assert_no_exception(at, f"{key}={value!r}")
    # The reading in force, as the run reads it (_reading) and the analysis
    # export records it: the declared default, not the seeded value and not
    # another option.
    in_force = {row["label"]: row["value"] for row in at.session_state["_analysis_export"]["readings"]}  # ruling 28: by the label
    label = "Connection test used in the shared tables"
    assert in_force[label] == default, f"{key}={value!r} left {store_key} at {in_force[label]!r}"


def test_a_reading_inside_its_options_is_kept():
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["_connection_rule"] = "Abu Ma'shar"
    at.session_state["_moon_rays_15"] = True
    at.run()
    assert_no_exception(at)
    assert (at.session_state["_connection_rule"], at.session_state["_moon_rays_15"]) == ("Abu Ma'shar", True)
