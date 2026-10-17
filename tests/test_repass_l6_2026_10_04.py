"""Re-pass of the hostile pass of 2026-10-03, lane L6 (inputs, lifecycle, the
store, names, the shell), on the repaired engine.

The ``xfail(strict=True)`` tests assert the RIGHT behaviour and fail today:
each is a finding of the re-pass (a ``partly`` of the pass's own finding, or a
new defect beside a repair). The plain tests at the foot are inputs the
repairs' checks did not try and the engine survives, pinned so they stay
survived. The report is the corpus's
``process/hostile_pass_2026-10-03/repass/L6_REPASS.md``.

* N1 -- a store the app can neither read nor copy (a permissions failure) is
  announced ("could not be read, and no copy of the file could be made"),
  and then the next Save replaces it: every saved record is destroyed.
* N2 -- a store that becomes unreadable while a session is open (a hand
  edit) is copied aside by the re-read L6-02 added, and the Save writes a
  store holding the new record alone, saying only "Saved"; the session's
  records vanish from the picker and nothing names the copy.
* N3 -- a record lacking a field the cast needs (no time, no date, or a
  Manual standard with no offset) loads under its own name with the
  PREVIOUS chart's value for that field.
* N4 -- a data folder that cannot be made kills the launch with a raw
  traceback before any page.
* N5 -- a preferences.json beginning with a BOM is read as empty and written
  over at the same launch: home, last chart and readings lost.
* N6 -- two sessions on one preferences file: a reading moved in one window
  erases the home place and the last chart another window set.
* N7 -- a window holding a stale copy of a record that another window has
  replaced says "'X' is already saved as it is".
* N8 -- the strip and the sidebar's sentences hand the chart's name to
  Markdown: "Smith *draft* $x$" is printed in italics and math.
* L6-06 partly -- a NaN latitude is refused once, then cast at the South Pole.
* L6-10 partly -- a reading's store key holding a value outside its options
  (``_connection_rule = 5``) takes the page down with a KeyError.
"""
import json
import os
import subprocess
import sys
import textwrap
from datetime import time
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

LMT, ZONE, OLD_ZONE, MANUAL = ("LMT (Local Mean Time)", "Standard time (named zone)",
                               "Standard time (pytz)", "Manual UTC offset")
PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00", "time_standard": LMT,
            "utc_offset": None, "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533,
            "target_mode": "Date", "target_date": "2026-09-15", "target_age": 43}
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
NEW_YORK = (40.71427, -74.00597)


# --- helpers ----------------------------------------------------------------

def _data_dir():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store():
    return _data_dir() / "saved_charts.json"


def _prefs():
    return _data_dir() / "preferences.json"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _fresh(page="chart"):
    """A session that seeds nothing, as a real open is."""
    from streamlit.testing.v1 import AppTest
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash(page)
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


def _save_as(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    return at


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _delete(at, name):
    _picker(at).select(name).run()
    [b for b in at.sidebar.button if b.label == "\U0001F5D1"][0].click().run()
    at.sidebar.button(key="_delete_confirm").click().run()
    return at


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

def test_n1_a_save_never_replaces_a_store_it_could_neither_read_nor_copy(scratch, monkeypatch):
    """The real trigger is a permissions failure (mode 000 on the file in a
    folder the account can write: ran at 428e05e, uid 1000). Simulated here by
    making the two reads the engine makes of that one path raise what mode 000
    raises, so the test does not depend on who runs it."""
    original = json.dumps({"X": PETOSKEY, "Y": {**PETOSKEY, "date_string": "1990-01-01"}}).encode()
    _store().write_bytes(original)
    target = _store()
    real_read_bytes, real_read_text = Path.read_bytes, Path.read_text

    def _denied(real):
        def read(self, *args, **kwargs):
            if self == target:
                raise PermissionError(13, "Permission denied", str(self))
            return real(self, *args, **kwargs)
        return read

    real_open = os.open

    def _denied_open(path, flags, *args, **kwargs):
        # SB-05 (ruling 157): the engine reads the store through os.open
        # (_read_regular_file), which a mode-000 file refuses the same way.
        if Path(path) == target:
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", _denied(real_read_bytes))
    monkeypatch.setattr(Path, "read_text", _denied(real_read_text))
    monkeypatch.setattr(os, "open", _denied_open)
    at = make_app(date="1240-05-23", page="chart").run()
    assert_no_exception(at)
    assert any("could not be read, and no copy" in v for v in _sidebar_texts(at)), "the premise: the launch says so"
    _save_as(at, "Z")
    assert_no_exception(at, "the save")
    monkeypatch.setattr(Path, "read_bytes", real_read_bytes)
    monkeypatch.setattr(Path, "read_text", real_read_text)
    monkeypatch.setattr(os, "open", real_open)
    kept = [p.read_bytes() for p in target.parent.iterdir() if p.is_file()]
    assert original in kept, (
        f"the Save replaced the store it could not read: it now holds {sorted(_read(target))}, "
        f"and no file in {sorted(p.name for p in target.parent.iterdir())} holds X and Y")


def test_n2_a_store_broken_under_an_open_session_is_not_silently_replaced(scratch):
    _store().write_text(json.dumps({"X": PETOSKEY, "Y": {**PETOSKEY, "date_string": "1990-01-01"}}))
    at = make_app(date="1240-05-23", page="chart").run()
    assert set(_picker(at).options) == {"-- New Chart --", "X", "Y"}, "the premise: the session holds X and Y"
    # A hand edit while the app is open leaves a trailing comma.
    _store().write_text(_store().read_text().rstrip().rstrip("}") + ",}")
    _save_as(at, "Z")
    assert_no_exception(at)
    written = set(_read(_store()))
    told = [v for v in _sidebar_texts(at) if "could not be read" in v]
    assert {"X", "Y"} <= written or told, (
        f"the store now holds {sorted(written)}, the picker {_picker(at).options}, and the sidebar says only "
        f"{[v for v in _sidebar_texts(at) if 'Saved' in v]}")


@pytest.mark.parametrize("name, record, inherited", [
    ("No time", {k: v for k, v in FLORENCE_REC.items() if k != "time_string"}, "22:15:00"),
    ("No date", {k: v for k, v in FLORENCE_REC.items() if k != "date_string"}, "1990-01-01"),
    ("Null offset", {**FLORENCE_REC, "time_standard": MANUAL, "utc_offset": None}, "UTC+05:00"),
    ("No offset", {**FLORENCE_REC, "time_standard": MANUAL}, "UTC+05:00"),
])
def test_n3_a_record_missing_a_field_is_not_cast_with_the_previous_charts_value(scratch, name, record, inherited):
    first = {**FLORENCE_REC, "date_string": "1990-01-01", "time_string": "22:15:00",
             "time_standard": MANUAL, "utc_offset": 5.0}
    _store().write_text(json.dumps({"First": first, name: record}))
    at = make_app(date="1240-05-23", page="chart").run()
    _picker(at).select("First").run()
    assert inherited in _strip(at), "the premise: the first chart shows the value"
    _picker(at).select(name).run()
    assert_no_exception(at)
    strip = _strip(at)
    assert not (strip.startswith(name) and inherited in strip), (
        f"the strip names the record and shows the previous chart's {inherited}: {strip.splitlines()[0]!r}")


def test_n4_a_data_folder_that_cannot_be_made_does_not_kill_the_launch(tmp_path):
    """The real trigger is a data folder the account cannot create (ran at
    428e05e: XDG_DATA_HOME with mode 555 -> PermissionError from
    _user_data_dir's mkdir). A FILE where the folder should be fails the same
    mkdir for any user. A fresh interpreter, so that app.py's import of the
    engine is the import that meets it."""
    (tmp_path / "Zij").write_text("not a folder")
    probe = textwrap.dedent(f"""
        import json
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file({str(APP_PATH)!r}, default_timeout=300).run()
        print(json.dumps({{"exceptions": [str(e.value).splitlines()[-1] if e.value else "" for e in at.exception],
                           "headers": [h.value for h in at.main.header]}}))
    """)
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path), "ALMUTEN_NO_PREFERENCES": "1"}
    done = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=600)
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["exceptions"] == [], f"the launch raised {result['exceptions']}; page headers {result['headers']}"


def test_n5_a_bom_prefixed_preferences_file_is_read_not_written_over(prefs_on):
    _store().write_text(json.dumps({"Mine": PETOSKEY}))
    held = {"last_chart": "Mine", "_reading_depth": "Course text and supplement", "_launches": 7,
            "home_place": {"label": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533}}
    _prefs().write_bytes("﻿".encode("utf-8") + json.dumps(held, indent=2).encode("utf-8"))
    at = _fresh("chart").run()
    assert_no_exception(at)
    after = _read(_prefs())
    assert after.get("home_place") == held["home_place"], f"the launch wrote over the file: {after}"
    assert _picker(at).value == "Mine", f"the launch opened on {_picker(at).value!r}"


def test_n6_two_sessions_do_not_erase_each_others_preferences(prefs_on):
    a = make_app(date="1983-11-19", page="chart").run()
    b = make_app(date="1990-01-01", page="chart").run()
    a.sidebar.button(key="_set_home").click().run()
    _save_as(a, "A chart")
    before = _read(_prefs())
    assert before.get("home_place") and before.get("last_chart") == "A chart", f"the premise: {before}"
    [c for c in b.main.checkbox if c.label == "Dark wheel"][0].check().run()
    assert_no_exception(b)
    after = _read(_prefs())
    assert after.get("home_place") == before["home_place"] and after.get("last_chart") == "A chart", (
        f"window B's toggle wrote its own stale preferences over A's: {after}")


def test_n7_a_stale_window_does_not_call_a_replaced_record_already_saved(scratch):
    _store().write_text(json.dumps({"X": PETOSKEY}))
    a = make_app(page="chart").run()
    _picker(a).select("X").run()
    b = make_app(page="chart").run()
    _picker(b).select("X").run()
    b.session_state["time_input_key"] = time(9, 0)
    b.run()
    _save_as(b, "X")
    b.sidebar.button(key="_replace_now").click().run()
    assert _read(_store())["X"]["time_string"] == "09:00:00", "the premise: B replaced X"
    _save_as(a, "X")
    assert_no_exception(a)
    said = [v for v in _sidebar_texts(a) if "already saved as it is" in v]
    assert not said, f"A says {said} while the store's X is B's 09:00 chart and A's is 11:44"


def test_n8_the_strip_prints_a_typed_name_as_typed(scratch):
    name = "Smith *draft* $x$"
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert _picker(at).value == name, "the premise: the record is saved and picked"
    caption = [c for c in at.main.caption if " · " in c.value][0]
    assert type(caption.proto).__name__ == "Markdown" and not caption.proto.allow_html, "the premise"
    value = caption.value
    assert ("\\*draft\\*" in value and "\\$x\\$" in value) or f"`{name}`" in value, (
        f"the strip's Markdown is {value.splitlines()[0]!r}: the name renders as italics and math")


def test_l6_06_partly_a_nan_latitude_stays_refused_on_the_next_run():
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["manual_lat_key"] = float("nan")
    at.run()
    assert_no_exception(at)
    assert not at.main.dataframe, "the premise: the first run refuses NaN"
    at.run()
    assert_no_exception(at)
    assert not at.main.dataframe or "-90.00" not in _strip(at), (
        f"the second run cast {_strip(at).splitlines()[0]!r} with no error")


@pytest.mark.parametrize("page", ["chart", "timing"])
def test_l6_10_partly_a_reading_store_key_outside_its_options_is_refused_not_raised(page):
    at = make_app(date="1240-05-23", page=page)
    at.session_state["_connection_rule"] = 5
    at.run()
    assert_no_exception(at, "_connection_rule=5")


# =============================================================================
# Inputs beside the repairs that the repairs' checks did not try, and that held
# =============================================================================

@pytest.mark.parametrize("label, state", [
    ("past the ephemeris, manual offset", {"date_input_key": "3100-01-01", "time_standard_key": MANUAL,
                                           "utc_offset_key": 3.0}),
    ("the repeated hour", {"date_input_key": "2024-11-03", "time_input_key": time(1, 30), "time_standard_key": ZONE,
                           "manual_lat_key": NEW_YORK[0], "manual_lon_key": NEW_YORK[1]}),
    ("the skipped hour, the old label", {"date_input_key": "2024-03-10", "time_input_key": time(2, 30),
                                         "time_standard_key": OLD_ZONE,
                                         "manual_lat_key": NEW_YORK[0], "manual_lon_key": NEW_YORK[1]}),
    ("before the zone's first rule (D1)", {"date_input_key": "1850-05-23", "time_standard_key": ZONE,
                                           "manual_lat_key": 28.6, "manual_lon_key": 77.2}),
    ("a point at sea", {"date_input_key": "2000-01-01", "time_standard_key": ZONE,
                        "manual_lat_key": 0.0, "manual_lon_key": -30.0}),
    ("a blank offset", {"date_input_key": "2000-01-01", "time_standard_key": MANUAL, "utc_offset_key": None}),
    ("an offset past the box", {"date_input_key": "2000-01-01", "time_standard_key": MANUAL, "utc_offset_key": 14.25}),
])
def test_save_refuses_every_refused_chart_and_leaves_a_same_named_record_alone(scratch, label, state):
    _store().write_text(json.dumps({"Good": PETOSKEY}))
    at = make_app(date="1240-05-23", page="chart")
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert_no_exception(at)
    assert not at.main.dataframe, f"the premise: {label} casts no chart"
    for name in ("New one", "Good"):
        _save_as(at, name)
        assert_no_exception(at, f"{label}: save as {name}")
        texts = _sidebar_texts(at)
        assert any("cannot be cast as entered; nothing was saved" in v for v in texts), (label, name, texts)
        asked = [v for v in texts if "exists. Replace it?" in v]
        assert asked == [], (label, name, asked)
        assert _read(_store()) == {"Good": PETOSKEY}, f"{label}: the store moved"
    assert "_analysis_export" not in at.session_state, f"{label}: an export stands for a refused chart (S1-5)"


@pytest.mark.parametrize("lat, lon", [(-95.0, 11.25), (1e308, 11.25), (43.77, 200.0), (43.77, -200.0),
                                      (43.77, float("inf"))])
def test_an_impossible_seeded_coordinate_stays_refused_for_three_runs(lat, lon):
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    for run in range(3):
        at.run()
        assert_no_exception(at, f"run {run + 1}")
        assert not at.main.dataframe, f"run {run + 1} cast {_strip(at).splitlines()[:1]}"


@pytest.mark.parametrize("key, value", [
    ("date_input_key", 12400523), ("date_input_key", None), ("time_standard_key", 5), ("time_standard_key", None),
    ("manual_coords_key", "yes"), ("_target_mode", 5), ("_target_age", "5"), ("utc_offset_key", True),
    ("manual_lat_key", True), ("_reading_depth", "bogus"),
])
def test_a_wrong_typed_key_beside_l6_10s_five_does_not_raise(key, value):
    at = make_app(date="1240-05-23", page="chart")
    at.session_state[key] = value
    at.run()
    assert_no_exception(at, f"{key}={value!r}")


@pytest.mark.parametrize("field", ["lon", "utc_offset", "target_age"])
def test_a_huge_integer_in_any_number_field_of_the_last_chart_opens_with_its_sentence(prefs_on, field):
    _store().write_text(json.dumps({"Huge": {**PETOSKEY, field: -(10 ** 400)}, "Good": PETOSKEY}))
    _prefs().write_text(json.dumps({"last_chart": "Huge", "_launches": 10 ** 400}))
    at = _fresh("timing").run()
    assert_no_exception(at)
    assert any("'Huge' could not be loaded" in v for v in _sidebar_texts(at))
    assert _strip(at).startswith("Unsaved chart")


def test_a_record_under_the_old_standard_label_keeps_it_until_an_edit_is_saved(prefs_on):
    old = {**PETOSKEY, "time_standard": OLD_ZONE}
    _store().write_text(json.dumps({"Old": old}))
    _prefs().write_text(json.dumps({"last_chart": "Old"}))
    at = _fresh("chart").run()
    assert_no_exception(at)
    assert at.session_state["time_standard_key"] == ZONE
    assert _strip(at).startswith("Old · ") and "(modified)" not in _strip(at)
    _save_as(at, "Old")
    assert any("already saved as it is" in v for v in _sidebar_texts(at))
    assert _read(_store())["Old"]["time_standard"] == OLD_ZONE, "an unchanged save wrote into the record"
    at.session_state["time_input_key"] = time(11, 45)
    at.run()
    _save_as(at, "Old")
    at.sidebar.button(key="_replace_now").click().run()
    assert _read(_store())["Old"]["time_standard"] == ZONE
    assert _read(_store())["Old"]["time_string"] == "11:45:00"


def test_two_sessions_merge_their_saves_and_a_stale_save_does_not_resurrect_a_deleted_record(scratch):
    a = make_app(date="1983-11-19", page="chart").run()
    b = make_app(date="1990-01-01", page="chart").run()
    _save_as(a, "From A")
    _save_as(b, "From B")
    c = make_app(date="1995-01-01", page="chart").run()
    _delete(b, "From B")
    assert set(_read(_store())) == {"From A"}
    _save_as(c, "From C")
    assert set(_read(_store())) == {"From A", "From C"}
