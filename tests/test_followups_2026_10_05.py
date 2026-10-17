"""The re-pass's follow-ups (2026-10-05): what the lanes' builders and blind
checkers of the re-pass of 2026-10-04 found and left ("noted, not changed",
"outside the lane", "for a later lane"), each reproduced on ``main`` and pinned
here where nothing the owner has not ruled stands in the way.

Every test is ``xfail(strict=True)``: it asserts the RIGHT behaviour and fails
today at that assertion. The plan that groups them into lanes, and the items
held for the owner or dropped, is the corpus's
``process/hostile_pass_2026-10-03/repass/FOLLOWUPS_PLAN.md``; each reason
begins with its K-number there.

The tests that import or run a file under ``tools/`` stand apart, in a
development-only file of their own beside this one.
"""
import json
import math
import os
import re
import stat
import sys
from datetime import time
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import (APP_PATH, EXECUTABLE_DIR, assert_no_exception, make_app, sync_engine_to_environment,
                      table_nodes)
from corpus_paths import CORPUS_DIR
from skip_guard import needs_corpus

LMT, ZONE, MANUAL = "LMT (Local Mean Time)", "Standard time (named zone)", "Manual UTC offset"
SUPPLEMENT = "Course text and supplement"
PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00", "time_standard": LMT,
            "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533}
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
SYDNEY_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
              "location_query": "Sydney", "lat": -33.87, "lon": 151.21}
FORMER_NAME = "TraditionalAstrologyEngine"
DEEP_JSON = "[" * 200_000 + "]" * 200_000

_corpus = needs_corpus()


def XF(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


# --- helpers ----------------------------------------------------------------

def _data_dir():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store():
    return _data_dir() / "saved_charts.json"


def _prefs():
    return _data_dir() / "preferences.json"


def _launch(page="chart"):
    """A session that seeds nothing, after the engine's import a launch makes
    (its paths and its data folder are read at import)."""
    from streamlit.testing.v1 import AppTest
    module = sys.modules.get("engine")
    if module is not None:
        module._harness_environment = None
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


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _save_as(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    return at


def _exceptions(at):
    return [str(e.value).splitlines()[-1] if e.value else "" for e in at.exception]


def _render(page, date="1240-05-23", depth="Course text", **state):
    at = make_app(date=date, page=page)
    at.session_state["_reading_depth"] = depth
    for key, value in state.items():
        at.session_state[key] = value
    at.run(timeout=300)
    assert_no_exception(at, page)
    return at


def _markdown_bodies(at):
    out = []
    for node in at.main:
        if getattr(node, "type", "") in ("markdown", "caption"):
            out.append(str(getattr(node, "value", "") or ""))
    return out


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
# K-01 .. K-07: the store's read and write
# =============================================================================

def test_k01_a_store_nested_past_the_parsers_depth_does_not_kill_the_launch(scratch):
    _store().write_text(DEEP_JSON)
    at = _launch().run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    said = [t for t in _sidebar_texts(at) if "could not be read" in t]
    assert said, "the launch opened without saying the saved charts could not be read"


def test_k02_a_preferences_file_nested_past_the_parsers_depth_does_not_kill_the_launch(prefs_on):
    _prefs().write_text(DEEP_JSON)
    at = _launch().run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    assert _prefs().read_text() == DEEP_JSON or any(
        p.name.startswith("preferences.json.unreadable-") for p in _data_dir().iterdir()), (
        "the unreadable preferences were written over with no copy kept")


OTHER = {"date_string": "1990-01-01", "time_string": "08:00:00", "time_standard": LMT,
         "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}


@pytest.mark.parametrize("moment", ["after this window's write", "after this window's load"])
def test_k03_a_write_landing_after_this_windows_own_is_not_taken_as_its_own(scratch, monkeypatch, moment):
    import engine
    _store().write_text(json.dumps({"X": FLORENCE_REC}))
    landed = []

    def other_window_writes():
        if not landed:
            held = json.loads(_store().read_text())
            held["OTHER"] = OTHER
            _store().write_text(json.dumps(held, indent=2))
            landed.append(True)

    if moment == "after this window's load":
        at = make_app(page="chart")            # make_app may reload the engine: patch after it
        real_load = engine.load_saved_charts

        def load_then_other():
            charts = real_load()
            other_window_writes()
            return charts
        monkeypatch.setattr(engine, "load_saved_charts", load_then_other)
        at.run()
        monkeypatch.setattr(engine, "load_saved_charts", real_load)
        assert landed and "OTHER" not in _picker(at).options, "the premise: the other write landed after the load"
    else:
        at = make_app(page="chart").run()
        real_write = engine.write_saved_charts

        def write_then_other(charts):
            ok = real_write(charts)
            other_window_writes()
            return ok
        monkeypatch.setattr(engine, "write_saved_charts", write_then_other)
        _save_as(at, "Z")
        monkeypatch.setattr(engine, "write_saved_charts", real_write)
        assert landed and "OTHER" in json.loads(_store().read_text()), "the premise: the other write landed"
    _save_as(at, "W")
    assert_no_exception(at, "the next Save")
    held = json.loads(_store().read_text())
    assert "OTHER" in held, (
        f"another window's record was written over: the store holds {sorted(held)}; the sidebar says "
        f"{[t for t in _sidebar_texts(at) if 'Saved' in t or 'window' in t]}")


def test_k04_a_store_naming_a_chart_twice_does_not_lose_a_record_silently(scratch):
    first, second = dict(FLORENCE_REC, date_string="1901-02-03"), dict(FLORENCE_REC, date_string="1999-12-31")
    _store().write_text('{"X": ' + json.dumps(first) + ', "X": ' + json.dumps(second) + "}")
    at = make_app(page="chart").run()
    assert_no_exception(at, "the launch")
    _save_as(at, "Z")
    assert_no_exception(at, "Save")
    kept = [p.name for p in _data_dir().iterdir() if "1901-02-03" in p.read_text(errors="replace")]
    assert kept, (f"the first 'X' (1901-02-03) is in no file after the Save: {sorted(p.name for p in _data_dir().iterdir())}; "
                  f"the sidebar said {[t for t in _sidebar_texts(at) if 'Saved' in t or 'read' in t]}")


@pytest.mark.parametrize("act", ["save a new chart", "re-save a loaded chart"])
def test_k05_a_store_removed_under_an_open_session_is_named_as_removed(scratch, act):
    _store().write_text(json.dumps({"X": FLORENCE_REC, "Y": PETOSKEY}))
    at = make_app(page="chart").run()
    if act == "re-save a loaded chart":
        _picker(at).select("X").run()
    _store().unlink()
    _save_as(at, "Z" if act == "save a new chart" else "X")
    assert_no_exception(at, act)
    texts = _sidebar_texts(at)
    record_sentences = [t for t in texts if "by another window" in t]
    kept = {"X", "Y"} <= set(_picker(at).options)
    named = [t for t in texts if "saved charts" in t.lower() and "by another window" not in t]
    assert not record_sentences and (kept or named), (
        f"picker {_picker(at).options}; the sidebar says {texts}")


def test_k06_a_read_only_store_keeps_its_mode(scratch):
    _store().write_text(json.dumps({"X": FLORENCE_REC}))
    os.chmod(_store(), 0o444)
    try:
        at = make_app(page="chart").run()
        _save_as(at, "Z")
        assert_no_exception(at, "Save over a read-only store")
        mode = stat.S_IMODE(os.stat(_store()).st_mode)
        assert mode == 0o444, f"the store's mode is now {oct(mode)}"
    finally:
        os.chmod(_store(), 0o644)


def test_k07_a_store_kept_as_a_link_is_written_through_the_link(scratch, tmp_path):
    elsewhere = tmp_path / "synced" / "charts.json"
    elsewhere.parent.mkdir()
    elsewhere.write_text(json.dumps({"X": FLORENCE_REC}))
    _store().symlink_to(elsewhere)
    at = make_app(page="chart").run()
    _save_as(at, "Z")
    assert_no_exception(at, "Save through a link")
    assert _store().is_symlink(), "the link in the store's place became a regular file"
    assert "Z" in json.loads(elsewhere.read_text()), "the file the link points to does not hold the save"


# =============================================================================
# K-08 .. K-10: the launch's files and the preferences
# =============================================================================

def _all_alerts(at):
    out = []
    for where in (at.sidebar, at.main):
        for kind in ("error", "warning"):
            out += [e.value for e in getattr(where, kind)]
    return out


def test_k08_saved_charts_moved_in_while_open_reach_this_sessions_picker(prefs_on):
    former = prefs_on / FORMER_NAME
    former.mkdir()
    (former / "saved_charts.json").write_text(json.dumps({"Old": PETOSKEY}))
    (prefs_on / "Zij").write_text("not a folder")
    at = _launch().run()
    assert_no_exception(at, "the launch")
    assert any("cannot be kept" in t for t in _all_alerts(at)), "the premise: the launch says the folder cannot be made"
    (prefs_on / "Zij").unlink()
    at.run()
    assert_no_exception(at, "the run after the folder is put right")
    assert (prefs_on / "Zij" / "saved_charts.json").is_file(), "the premise: the folder was moved across"
    assert "Old" in _picker(at).options, f"this session's picker after the move: {_picker(at).options}"


def _folder_said(at):
    """The data folder's own sentence among the alerts (app.py's
    _data_folder_refusal), not any error or warning (lane TL, TL-25)."""
    return any(a.startswith("Saved charts and preferences cannot be kept: their folder, ") for a in _all_alerts(at))


@pytest.mark.parametrize("mode", [0o555, 0o000], ids=["unwritable 555", "unenterable 000"])
def test_k09_a_data_folder_this_account_cannot_use_is_said(prefs_on, mode):
    folder = _data_dir()
    (folder / "saved_charts.json").write_text(json.dumps({"X": FLORENCE_REC}))
    (folder / "preferences.json").write_text(json.dumps({"_launches": 3}))
    folder.chmod(mode)
    try:
        assert not os.access(folder, os.W_OK), "the premise: this account cannot write in the folder"
        at = _launch().run()
        assert_no_exception(at, f"the launch, folder {oct(mode)}")
        if mode == 0o555:
            at.sidebar.button(key="_set_home").click().run()
            assert_no_exception(at, "Set as home")
            kept = "home_place" in json.loads((folder / "preferences.json").read_text())
            assert kept or _folder_said(at), (
                "Set as home kept no home and did not say the folder cannot be used: the session shows "
                f"{[c.value for c in at.sidebar.caption if c.value.startswith('Home')]}")
        else:
            assert "X" in _picker(at).options or _folder_said(at), (
                f"the folder holds a saved chart; the picker is {_picker(at).options} and the folder is not named")
    finally:
        folder.chmod(0o755)


def test_k10_a_windows_own_choice_reaches_the_file_again_after_another_windows(prefs_on):
    _store().write_text(json.dumps({"X": FLORENCE_REC, "Y": PETOSKEY}))
    a = make_app(page="chart").run()
    b = make_app(page="chart").run()
    _picker(a).select("X").run()
    _picker(b).select("Y").run()
    assert json.loads(_prefs().read_text()).get("last_chart") == "Y", "the premise: B opened Y last"
    _picker(a).select("-- New Chart --").run()
    _picker(a).select("X").run()
    assert_no_exception(a, "A re-opens X")
    last = json.loads(_prefs().read_text()).get("last_chart")
    assert last == "X", f"A opened X last, and the file names {last!r}"


# =============================================================================
# K-11 .. K-15: what reaches the cast from a record or from session state
# =============================================================================

def test_k11_a_record_with_no_place_is_not_cast_at_the_previous_charts_place(scratch):
    no_place = {k: v for k, v in FLORENCE_REC.items() if k not in ("lat", "lon", "location_query")}
    _store().write_text(json.dumps({"First": SYDNEY_REC, "No place": no_place}))
    at = make_app(page="chart").run()
    _picker(at).select("First").run()
    assert "Sydney" in _strip(at), "the premise: the first chart is cast at Sydney"
    _picker(at).select("No place").run()
    assert_no_exception(at, "No place")
    strip = _strip(at)
    assert not (strip.startswith("No place") and "Sydney" in strip), (
        f"the strip names the record and casts it at the previous chart's place: {strip.splitlines()[0]!r}")


@pytest.mark.parametrize("bad", ["", "garbage", "1990-02-30"], ids=["empty", "garbage", "1990-02-30"])
def test_k12_a_record_with_an_unreadable_date_is_refused_not_cast_at_the_previous_date(scratch, bad):
    first = dict(FLORENCE_REC, date_string="1977-07-07")
    _store().write_text(json.dumps({"First": first, "Bad date": dict(FLORENCE_REC, date_string=bad)}))
    at = make_app(page="chart").run()
    _picker(at).select("First").run()
    assert "1977-07-07" in _strip(at), "the premise: the first chart shows its date"
    _picker(at).select("Bad date").run()
    assert_no_exception(at, f"date_string {bad!r}")
    strip = _strip(at)
    assert not (strip.startswith("Bad date") and "1977-07-07" in strip), (
        f"the strip names the record and shows the previous chart's date: {strip.splitlines()[0]!r}")


@pytest.mark.parametrize("key", ["manual_lat_key", "manual_lon_key"])
def test_k13_a_coordinate_too_large_for_a_float_is_refused_not_raised(key):
    at = make_app(page="chart")
    at.session_state[key] = 10 ** 400
    at.run(timeout=300)
    assert not _exceptions(at), f"{key} = 10**400 raised {_exceptions(at)}"


def test_k14_a_record_made_unloadable_under_an_open_window_is_not_named_as_loaded(scratch):
    rec = dict(FLORENCE_REC, time_string="08:00:00")
    _store().write_text(json.dumps({"Rec": rec}))
    at = make_app(page="chart").run()
    _picker(at).select("Rec").run()
    assert _strip(at).startswith("Rec") and "08:00:00" in _strip(at), "the premise: Rec is loaded"
    _store().write_text(json.dumps({"Rec": {k: v for k, v in rec.items() if k != "time_string"}}))
    _save_as(at, "Rec")
    assert_no_exception(at, "the save that re-reads the store")
    assert any("by another window" in t for t in _sidebar_texts(at)), "the premise: the window re-read the store"
    at.run()
    strip = _strip(at)
    assert not (strip.startswith("Rec ·") and "(modified)" not in strip.splitlines()[0]), (
        f"the store's Rec holds no time, and the strip still calls the boxes Rec: {strip.splitlines()[0]!r}")


def test_k15_a_refusal_is_not_said_of_a_record_another_window_has_since_replaced(scratch):
    first = dict(FLORENCE_REC, date_string="1990-01-01", time_string="22:15:00")
    third = dict(PETOSKEY)
    lacking = {k: v for k, v in FLORENCE_REC.items() if k != "time_string"}
    _store().write_text(json.dumps({"First": first, "No time": lacking, "Third": third}))
    a = make_app(page="chart").run()
    _picker(a).select("First").run()
    _picker(a).select("No time").run()
    assert any("holds no time" in t for t in _sidebar_texts(a)), "the premise: A's loader refused No time"
    b = make_app(page="chart").run()
    _picker(b).select("Third").run()
    _save_as(b, "No time")
    b.sidebar.button(key="_replace_now").click().run()
    assert json.loads(_store().read_text())["No time"].get("time_string") == "11:44:00", "the premise: B replaced it"
    _save_as(a, "No time")
    if any(b_.key == "_replace_now" for b_ in a.sidebar.button):
        a.sidebar.button(key="_replace_now").click().run()
    assert_no_exception(a, "A's save under the replaced name")
    a.run()
    stale = [t for t in _sidebar_texts(a) if "holds no time" in t]
    strip = _strip(a).splitlines()[0]
    assert not stale and not strip.startswith("No time"), (
        f"A still says {stale} and its strip reads {strip!r}, while the store's 'No time' is B's whole record")


# =============================================================================
# K-16: the seam (a longitude a hair under 0 Aries) in the readers G8 left
# =============================================================================

def _same(a, b):
    """a and b equal, floats within 1e-9 (the seam's -1e-16 against 0.0)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) < 1e-9
    return a == b


def _florence_chart(engine):
    import swisseph as swe
    return engine["calculate_traditional_chart_jd"](swe.julday(1240, 5, 23, 13.75, swe.JUL_CAL), 43.7792, 11.2463)


def _moon_at(engine, chart, lon):
    import copy
    data = copy.deepcopy(chart["planetary_data"])
    data["Moon"]["longitude"] = lon
    return data


def _asc_at(chart, lon):
    import copy
    out = copy.deepcopy(chart)
    out["ascendant"] = lon
    return out


def _seam_pairwise(engine, chart, lon):
    return engine["_pairwise_configurations"](_moon_at(engine, chart, lon))


def _seam_special_degrees(engine, chart, lon):
    return engine["evaluate_special_degrees"](_moon_at(engine, chart, lon))


def _seam_turning_rows(engine, chart, lon):
    return engine["pn4_turning_rows"](_asc_at(chart, lon), 30)


def _seam_lot_house_endpoint(engine, chart, lon):
    return engine["_lot_house_endpoint"](1, lon, None, engine["LOT_HOUSE_CUSP_OPTIONS"][0])


def _seam_bounds_ring(engine, chart, lon):
    import math as _m
    svg = "".join(engine["_bounds_ring_svg"](lambda a: a, lambda r, a: (r * _m.cos(a), r * _m.sin(a)),
                                              lambda r0, r1, a0, a1: f"{r0} {r1} {a0} {a1}", 1, 2, highlight=lon))
    return svg.count(engine["_PALETTE_LIGHT"]["bound_tint"])


def _seam_profection_arc(engine, chart, lon):
    svg = engine["generate_multiwheel_svg"]([{"label": "Root", "chart": chart, "when": "x"}], "t",
                                            profection_from=lon, shade_sign=0)
    return 'class="profection"' in svg


def _seam_data_lon(engine, chart, lon):
    import copy
    from datetime import datetime
    moved = copy.deepcopy(chart)
    moved["planetary_data"]["Moon"]["longitude"] = lon
    hybrid = engine["generate_hybrid_svg"](moved, "t", "Florence", 43.7792, 11.2463, datetime(1240, 5, 23, 14, 30), "LMT")
    multi = engine["generate_multiwheel_svg"]([{"label": "Root", "chart": moved, "when": "x"}], "t")
    return sorted(set(re.findall(r'data-lon="(3[56]\d\.\d+|0\.0+)"', hybrid + multi)))


# The eighteen readers G8's survey named (G8_BUILD, "Seen, not in the lane"), added before any was fixed
# (FOLLOWUPS_PLAN, KD). Where the default chart cannot show a reader's seam (no trio in Aries for blocking),
# the planets around it are placed so that it can. Four readers' answers cannot move at the seam by value
# (each says so above it); there the parameter is a no-exception check, and the reading of the seam itself is
# pinned by a spy in test_kd_the_seam_2026_10_06.py.

def _placed(engine, chart, lon, **others):
    data = _moon_at(engine, chart, lon)
    for name, value in others.items():
        data[name]["longitude"] = value
    return data


def _moved_inputs(engine, chart, lon):
    """The Moon at `lon`, and what the Configurations page computes from her before its readers run."""
    data, sect = _moon_at(engine, chart, lon), chart["sect"]
    essential = engine["evaluate_essential_dignities"](data, sect)
    accidental = engine["evaluate_accidental_dignities"](data, chart["houses"], sect, chart["julian_day"],
                                                         armc=chart["armc"], obliquity=chart["obliquity"],
                                                         geo_lat=chart["geo_lat"])
    return data, sect, essential, accidental, engine["_simulate_forward"](data, chart["julian_day"])


def _seam_blocking(engine, chart, lon):
    # Sahl's Fig. 13 in Aries: the Moon first, Mercury between, Saturn last and heaviest.
    return engine["evaluate_blocking"](_placed(engine, chart, lon, Mercury=4.0, Saturn=8.0))


def _seam_cutting_the_light(engine, chart, lon):
    data, _sect, _ess, _acc, sim = _moved_inputs(engine, chart, lon)
    return engine["evaluate_cutting_the_light"](data, sim)


def _seam_find_recompense_day(engine, chart, lon):
    # The forward simulation is the ephemeris's own (never an entered longitude), so its series is set here.
    # Saturn's fall is Aries: at 0 Aries every sampled day opens the search, and the Moon's payback is found
    # (day 67.0); a seam read as Pisces opens none and finds nothing.
    import copy
    sim = copy.deepcopy(engine["_simulate_forward"](chart["planetary_data"], chart["julian_day"]))
    sim["series"]["Saturn"]["lon"] = [lon] * len(sim["series"]["Saturn"]["lon"])
    found = engine["_find_recompense_day"](sim, "Saturn", "Moon")
    assert found is not None
    return found


def _seam_favor_and_recompense(engine, chart, lon):
    # A no-exception check, not a test by value: no input moves this answer at the seam. Its own sign test
    # is the well (Aries degree 1 in no Aries list; Pisces degree 31 in none); its fall is the caller's.
    # Its reading of the seam is pinned by a spy instead: test_kd_the_seam_2026_10_06.py::
    # test_a_reader_reads_the_seam_through_on_circle.
    data, sect, essential, _acc, sim = _moved_inputs(engine, chart, lon)
    return engine["evaluate_favor_and_recompense"](data, essential, sect, sim)


def _seam_book_v_degrees(engine, chart, lon):
    # A no-exception check, not a test by value: no input moves this answer at the seam. At 0.0 it reads
    # Aries degree 1, which no Aries list holds; read as Pisces it would read degree 31, which no list holds.
    # Its reading of the seam is pinned by a spy instead: test_kd_the_seam_2026_10_06.py::
    # test_a_reader_reads_the_seam_through_on_circle.
    return (engine["evaluate_book_v_degrees"](_moon_at(engine, chart, lon), chart["ascendant"],
                                              chart["lot_of_fortune"], chart["sect"]),
            engine["evaluate_book_v_degrees"](chart["planetary_data"], lon, lon, chart["sect"]))


def _seam_nobility_degrees(engine, chart, lon):
    # A no-exception check, not a test by value: no input moves this answer at the seam. At 0.0 it reads
    # Aries degree 1, which no Aries list holds; read as Pisces it would read degree 31, which no list holds.
    # Its reading of the seam is pinned by a spy instead: test_kd_the_seam_2026_10_06.py::
    # test_a_reader_reads_the_seam_through_on_circle.
    return (engine["evaluate_nobility_degrees"](_moon_at(engine, chart, lon), chart["ascendant"], chart["sect"]),
            engine["evaluate_nobility_degrees"](chart["planetary_data"], lon, chart["sect"]))


def _seam_abu_mashar_enclosed(engine, chart, lon):
    data = _moon_at(engine, chart, lon)
    rows = engine["_pairwise_configurations"](data)
    return [engine["_abu_mashar_enclosed"]("Moon", kind, data, rows)
            for kind in (engine["FORTUNES"], engine["INFORTUNES"])]


def _seam_abu_mashar_condition(engine, chart, lon):
    data, sect, essential, accidental, sim = _moved_inputs(engine, chart, lon)
    return engine["evaluate_abu_mashar_condition"](data, chart["houses"], sect, essential, accidental,
                                                   chart["julian_day"], chart["ascendant"], sim)


def _seam_mashaallah_condition(engine, chart, lon):
    return ([engine["mashaallah_condition"](house, "Moon", _moon_at(engine, chart, lon), chart["ascendant"])
             for house in range(1, 13)],
            [engine["mashaallah_condition"](house, "Venus", chart["planetary_data"], lon) for house in range(1, 13)])


def _seam_pn4_looks_at_sign(engine, chart, lon):
    return [engine["_pn4_looks_at_sign"](_moon_at(engine, chart, lon), sign) for sign in engine["SIGN_ORDER"]]


def _seam_pn4_twelfth_part(engine, chart, lon):
    return engine["pn4_twelfth_part"](lon)


def _seam_revolution(chart, lon, who="Moon", asc=None):
    import copy
    out = copy.deepcopy(chart)
    out["planetary_data"][who]["longitude"] = lon
    if asc is not None:
        out["ascendant"] = asc
    return out


def _seam_pn4_i7_ascendant(engine, chart, lon):
    # The revolution's Ascendant at the seam; then its lord's (Venus, of the Libra Ascendant) body there.
    return (engine["pn4_i7_ascendant"](chart, _seam_revolution(chart, lon, asc=lon)),
            engine["pn4_i7_ascendant"](chart, _seam_revolution(chart, lon, who="Venus")))


def _seam_pn4_i7_planets(engine, chart, lon):
    return engine["pn4_i7_planets"](chart, _seam_revolution(chart, lon))


def _seam_pn4_profect(engine, chart, lon):
    return [engine["pn4_profect"](lon, steps, forward) for steps in (0, 1, 5) for forward in (True, False)]


def _seam_pn4_monthly_turn_forward(engine, chart, lon):
    # A no-exception check, not a test by value: no input moves this answer at the seam. Aries, convertible,
    # turns backward; Pisces read at its 30th degree (past 15) turns backward too.
    # Its reading of the seam is pinned by a spy instead: test_kd_the_seam_2026_10_06.py::
    # test_a_reader_reads_the_seam_through_on_circle.
    return [engine["pn4_monthly_turn_forward"](lon, rule) for rule in engine["PN4_MONTHLY_TURN_OPTIONS"]]


def _seam_sign_has_four_feet(engine, chart, lon):
    return engine["sign_has_four_feet"](lon)


def _seam_time_lords(engine, chart, lon):
    from datetime import date
    return engine["calculate_time_lords"](lon, date(1240, 5, 30), date(1245, 6, 1))


SEAM_READERS = {
    "_pairwise_configurations": _seam_pairwise,
    "evaluate_special_degrees": _seam_special_degrees,
    "pn4_turning_rows": _seam_turning_rows,
    "_lot_house_endpoint": _seam_lot_house_endpoint,
    "_bounds_ring_svg": _seam_bounds_ring,
    "generate_multiwheel_svg profection": _seam_profection_arc,
    "data-lon": _seam_data_lon,
    "evaluate_blocking": _seam_blocking,
    "evaluate_cutting_the_light": _seam_cutting_the_light,
    "_find_recompense_day": _seam_find_recompense_day,
    "evaluate_favor_and_recompense": _seam_favor_and_recompense,
    "evaluate_book_v_degrees": _seam_book_v_degrees,
    "evaluate_nobility_degrees": _seam_nobility_degrees,
    "_abu_mashar_enclosed": _seam_abu_mashar_enclosed,
    "evaluate_abu_mashar_condition": _seam_abu_mashar_condition,
    "mashaallah_condition": _seam_mashaallah_condition,
    "_pn4_looks_at_sign": _seam_pn4_looks_at_sign,
    "pn4_twelfth_part": _seam_pn4_twelfth_part,
    "pn4_i7_ascendant": _seam_pn4_i7_ascendant,
    "pn4_i7_planets": _seam_pn4_i7_planets,
    "pn4_profect": _seam_pn4_profect,
    "pn4_monthly_turn_forward": _seam_pn4_monthly_turn_forward,
    "sign_has_four_feet": _seam_sign_has_four_feet,
    "calculate_time_lords": _seam_time_lords,
}


@pytest.mark.parametrize("reader", list(SEAM_READERS))
def test_k16_every_reader_takes_the_seam_as_0_aries(engine, reader):
    chart = _florence_chart(engine)
    at_zero = SEAM_READERS[reader](engine, chart, 0.0)
    at_seam = SEAM_READERS[reader](engine, chart, -1e-16)
    assert _same(at_zero, at_seam), f"{reader}: at 0.0 {str(at_zero)[:160]!r}; at -1e-16 {str(at_seam)[:160]!r}"


# =============================================================================
# K-17: a column of numbers with nothing in a cell draws "None"
# =============================================================================

def _null_cells_drawn_as_none(at):
    """(heading, column, rows) for every grid holding a missing value with no
    placeholder: Streamlit draws a missing value as "None" unless the
    dataframe names a placeholder (st.dataframe's own documentation)."""
    out = []
    for heading, node in table_nodes(at):
        df = node.value
        holes = {str(c): int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()}
        if not holes:
            continue
        proto = getattr(node, "proto", None)
        placeholder = proto.placeholder if proto is not None and proto.HasField("placeholder") else None
        if placeholder is None or placeholder == "None":
            out.append((heading, holes))
    return out


@pytest.mark.parametrize("case", ["configurations 1240-04-01", "dignities, Mercury on the Sun"])
def test_k17_no_grid_draws_none_where_nothing_is_open(monkeypatch, case):
    if case.startswith("configurations"):
        at = _render("configurations", date="1240-04-01")
    else:
        at = make_app(page="dignities")
        import engine
        original = engine.calculate_traditional_chart_jd

        def mercury_on_the_sun(*args, **kwargs):
            chart = original(*args, **kwargs)
            chart["planetary_data"]["Mercury"]["longitude"] = chart["planetary_data"]["Sun"]["longitude"]
            return chart
        monkeypatch.setattr(engine, "calculate_traditional_chart_jd", mercury_on_the_sun)
        at.run(timeout=300)
        assert_no_exception(at, case)
    drawn = _null_cells_drawn_as_none(at)
    assert not drawn, drawn


# =============================================================================
# K-18 .. K-24: the Prediction pages' words and numbers
# =============================================================================

def _age_zero_timing():
    """The default chart (1240-05-23 14:30 LMT = 13:45 UT) at Age 0: noon UT on
    the birth date falls before the birth, so the bundle's clamp applies."""
    at = _render("timing", _target_mode="Age", _target_age=0)
    header = next((b for b in _markdown_bodies(at) if "years elapsed from the birth hour" in b), "")
    assert "read at the birth's own moment" in header, f"the premise: the clamp applies: {header[:200]!r}"
    return at, header


def test_k18_the_target_help_does_not_contradict_the_header_under_the_clamp():
    at, _header = _age_zero_timing()
    radio = [r for r in at.main.radio if r.label == "Target by"]
    assert radio, "the premise: the Target by control is drawn"
    help_text = radio[0].help or ""
    assert ("noon UT" not in help_text or "birth's own moment" in help_text
            or "before the birth" in help_text), help_text


def test_k19_a_date_column_wholly_after_the_reform_does_not_name_the_julian_calendar():
    at = _render("releaser", date="1950-06-01", _target_mode="Date", _target_date="1990-06-01")
    told = []
    for heading, node in table_nodes(at):
        df = node.value
        if "Date" in df.columns and len(df):
            dates = [str(d)[:10] for d in df["Date"].tolist()]
            if all(d > "1582-10-14" for d in dates) and "Julian" in str(getattr(node, "proto", "")):
                told.append(heading)
    assert not told, told


def test_k20_the_days_page_sentence_is_true_where_the_clamp_reaches_the_next_day():
    at = _render("days", date="1950-06-01", time_input_key=time(23, 30), time_standard_key=MANUAL,
                 utc_offset_key=-13.0, manual_coords_key=True, manual_lat_key=40.0, manual_lon_key=-170.0,
                 _target_mode="Date", _target_date="1950-06-02")
    bodies = _markdown_bodies(at)
    header = next((b for b in bodies if "years elapsed from the birth hour" in b), "")
    assert "read at the birth's own moment" in header and "1950-06-02" in header, f"the premise: {header[:200]!r}"
    day = next((b for b in bodies if b.startswith("**The day.**")), "")
    assert day, "the premise: the Days page's day paragraph is drawn"
    assert "falls before the birth" in day or "noon UT" not in day, day


def test_k21_the_small_days_now_row_opens_at_or_before_the_printed_day():
    at = _render("days", _target_mode="Date", _target_date="1270-04-09")
    line = next((b for b in _markdown_bodies(at) if b.startswith("**Ascendant of the revolution**")), "")
    m = re.search(r"\(day ([\d.]+) of the year\)", line)
    assert m, f"the premise: the Now line prints the day: {line[:160]!r}"
    small = [n.value for h, n in table_nodes(at) if "From day" in n.value.columns and h.startswith("The small days")]
    assert small, "the premise: the small days' table is drawn"
    now = [row for row in small[0].to_dict("records") if row.get("Now") == "yes"]
    assert now, "the premise: a Now row"
    assert float(now[0]["From day"]) <= float(m.group(1)), (m.group(1), now[0]["From day"])


def test_k22_the_first_years_revolution_is_not_called_the_0th_return():
    _at, header = _age_zero_timing()
    assert "**0th**" not in header, header[:400]


def test_k23_the_node_years_are_named_as_the_quotation_counts_them():
    text = (EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8")
    assert "when the native enters year" in text, "the premise: the quotation is on the page"
    assert "In years 70-75 of each fardar cycle" not in text


def test_k24_one_unavailable_testimony_is_said_in_the_singular(engine):
    import swisseph as swe
    chart = engine["calculate_traditional_chart_jd"](swe.julday(1240, 5, 23, 13.75, swe.JUL_CAL), 43.7792, 11.2463)
    from datetime import date
    bundle = engine["pn4_timing_bundle"](chart, 43.7792, 11.2463, engine["CivilDate"].of(date(1240, 5, 23)),
                                         engine["parse_iso_date"]("1248-05-23"), engine["PN4_MONTHLY_TURN_OPTIONS"][0], None)
    texts = [str(row.get("text", "")) for row in bundle["governor"] if isinstance(row, dict)]
    said = [t for t in texts if "unavailable" in t]
    assert said, f"the premise: the summary counts the unavailable: {texts}"
    plural = [t for t in said if "1 are unavailable" in t]
    assert not plural, plural


# =============================================================================
# K-26 .. K-28: the Releaser page and the Lots exports
# =============================================================================

def test_k26_the_mercury_line_stands_under_abu_alis_heading():
    at = _render("releaser", depth=SUPPLEMENT, _target_mode="Age", _target_age=30)
    nodes = list(at.main)
    headings = [i for i, n in enumerate(nodes)
                if getattr(n, "type", None) == "subheader" and "(Abu 'Ali)" in n.value]
    lines = [i for i, n in enumerate(nodes)
             if getattr(n, "type", None) == "markdown" and "+20" in str(n.value) and "Mercury" in str(n.value)]
    assert headings and lines, "the premise: both are drawn"
    assert lines[0] > headings[0], f"the Mercury line is element {lines[0]}, Abu 'Ali's heading element {headings[0]}"


def _export_columns(at, page, heading):
    return [list(e["columns"]) for e in at.session_state["_analysis_export"]["results"][page].get(heading, [])]


@pytest.mark.parametrize("heading", ["Topical Lots (Sahl, On Nativities)", "Provenance and standing per Lot"])
def test_k27_the_lots_exports_carry_the_pages_columns(heading):
    at = _render("lots", depth=SUPPLEMENT)
    exported = _export_columns(at, "Lots", heading)
    assert exported, f"the premise: the export files {heading!r}"
    if heading.startswith("Topical"):
        drawn = [list(map(str, n.value.columns)) for h, n in table_nodes(at) if h == heading]
    else:      # an st.table under an expander, which table_nodes does not head
        drawn = [list(map(str, t.value.columns)) for t in at.main.table
                 if {"Topic", "Lot", "Standing", "Source"} <= set(map(str, t.value.columns))]
    assert drawn, f"the premise: the page draws {heading!r}"
    extra = sorted(set(exported[0]) - set(drawn[0]))
    assert not extra, (heading, "drawn", drawn[0], "exported besides", extra)


def test_k28_each_arm_of_an_open_releaser_shows_its_direction():
    at = _render("releaser", date="1900-04-27", time_input_key=time(8, 0), time_standard_key=MANUAL,
                 utc_offset_key=0.0, _target_mode="Date", _target_date="1960-06-01")
    bodies = _markdown_bodies(at)
    assert any("testimony #3 on each arm" in b or "on each arm" in b for b in bodies), (
        "the premise: the page says the governor reads #3 on each arm")
    directed = [h for h, n in table_nodes(at) if "Distributor" in n.value.columns]
    assert len(directed) >= 2, f"distribution tables drawn: {directed}"


# =============================================================================
# K-29 .. K-31: the sidebar's boxes and the Markdown export
# =============================================================================

def test_k29_a_place_label_of_spaces_draws_no_rule(scratch):
    _store().write_text(json.dumps({"Blank place": dict(FLORENCE_REC, location_query="   ")}))
    at = make_app(page="chart").run()
    _picker(at).select("Blank place").run()
    assert_no_exception(at, "a place of spaces")
    boxes = [m.value for m in at.sidebar.success if "43.7792, 11.2463" in m.value]
    assert boxes, "the premise: the place box is drawn"
    first = boxes[0].splitlines()[0]
    assert not re.fullmatch(r"\s*(?:[*_-]\s*){3,}", first), f"the place box opens {first!r}: a thematic break"


def test_k30_the_manual_offset_box_shows_the_offset_it_casts():
    at = make_app(page="chart")
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 5.125
    at.run(timeout=300)
    assert_no_exception(at, "offset 5.125")
    box = at.sidebar.number_input(key="utc_offset_key")
    assert box.value == 5.125, f"the premise: the box holds {box.value}"
    shown = box.proto.format % box.value
    assert float(shown) == 5.125, f"the box shows {shown!r} for 5.125"


@pytest.mark.parametrize("part", ["title", "place", "file name"])
def test_k31_the_markdown_export_prints_names_as_typed(scratch, monkeypatch, part):
    import streamlit
    names = []
    real = streamlit.download_button

    def capturing(*args, **kwargs):
        names.append(kwargs.get("file_name"))
        return real(*args, **kwargs)
    place = "Smith **bold** [x](https://example.org) $m$"
    chart = {"title": "Smith $x$ :sun:", "place": "Placed", "file name": "N" * 500}[part]
    _store().write_text(json.dumps({chart: dict(FLORENCE_REC, location_query=place)}))
    at = make_app(page="chart").run()
    monkeypatch.setattr(streamlit, "download_button", capturing)
    _picker(at).select(chart).run()
    assert_no_exception(at, part)
    report = at.session_state["_analysis_markdown"]
    if part == "title":
        title = report.splitlines()[0]
        assert "$x$" not in title and ":sun:" not in title, title
    elif part == "place":
        rows = [line for line in report.splitlines() if line.startswith("| Place")]
        assert rows, "the premise: the report has a Place row"
        assert "**bold**" not in rows[0] and "](https://" not in rows[0] and "$m$" not in rows[0], rows[0]
    else:
        long = [n for n in names if n and len(n.encode("utf-8")) > 255]
        assert names, "the premise: the download buttons were drawn"
        assert not long, [len(n) for n in long]


# =============================================================================
# K-32, K-33: the join across quarters
# =============================================================================

def test_k32_the_join_note_says_whose_claim_the_exactness_is():
    text = (EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8")
    start = text.index("Al-Qabisi's join across quarters")
    note = re.sub(r'"\s*\n\s*"', "", text[start:start + 700])
    sentence = note.split("It is not used", 1)[-1].split("Converse", 1)[0]
    assert "in every" in sentence, f"the premise: {sentence!r}"
    assert re.search(r"this app\S*[^.]*in every", sentence) and "gives that arc" not in sentence, sentence


def test_k33_the_join_comment_reads_as_the_page_does():
    text = (EXECUTABLE_DIR / "engine.py").read_text(encoding="utf-8")
    assert "IV.12c" in text, "the premise: the comment is there"
    assert "direct to the angle between" not in text
