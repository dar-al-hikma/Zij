"""B-04 of the third outside pass (ruling 146): text no page can carry is
refused on load, as the loader's contract says.

A lone surrogate -- ``"\\ud800"`` in the file, the ASCII escape default
``json.dumps`` writes -- parses as valid JSON into a ``str`` that no
Streamlit element can carry (``UnicodeEncodeError`` in the element's proto).
It passed every check, and:

- as a saved chart's NAME the sidebar's picker raised before any page, at
  every launch: the store is now refused as a store with any other unusable
  name is, copied aside with its notice;
- as a record's place (``location_query``), or a time standard this app
  does not offer (``time_standard``, which the sidebar's sentence names as
  stored), the page raised when the record was chosen, and the launch when
  it was the last chart: the record is now refused on load with its field
  named, by ``chart_record_fault``;
- as ``preferences.json``'s ``home_place.label`` the launch raised at the
  Home popover: the preference is now refused as any other unusable home
  place is.

Ordinary non-ASCII text, and a surrogate PAIR written as two escapes (one
character), load exactly as before.
"""
import json
import os
import sys
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, make_app, sync_engine_to_environment

LMT = "LMT (Local Mean Time)"
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
BAD = "Invalid " + chr(0xD800) + " text"
LOW = "Invalid " + chr(0xDC00) + " text"   # a lone LOW surrogate: refused as the high one is
FIRENZE = "Firenze — città"
TOKYO = "東京都"
MOON = "\U0001F319"                        # json.dumps writes it as two escapes, a surrogate pair


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


def _data_dir():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_store(charts):
    data = json.dumps(charts).encode("ascii")              # the ASCII escape, as default json.dumps writes
    (_data_dir() / "saved_charts.json").write_bytes(data)
    return data


def _write_prefs(prefs):
    (_data_dir() / "preferences.json").write_text(json.dumps(prefs))


def _launch(page="chart"):
    """A session that seeds nothing, after the engine's import a launch makes."""
    from streamlit.testing.v1 import AppTest
    module = sys.modules.get("engine")
    if module is not None:
        module._harness_environment = None
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash(page)
    return at


def _exceptions(at):
    return [str(e.value).splitlines()[-1] if e.value else "" for e in at.exception]


def _sidebar_texts(at):
    return [e.value for kind in ("error", "warning", "info", "caption") for e in getattr(at.sidebar, kind)]


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _refusals(at):
    return [t for t in _sidebar_texts(at) if "could not be loaded" in t]


# --- 1. a saved chart's name ---------------------------------------------------

def test_a_store_whose_name_holds_a_lone_surrogate_is_copied_aside_and_the_app_opens(scratch):
    data = _write_store({BAD: FLORENCE_REC, "Florence": FLORENCE_REC})
    assert b"\\ud800" in data, "the premise: the file holds the ASCII escape, valid JSON"
    at = make_app(page="chart").run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    assert any(t.startswith("Saved charts could not be read. A copy of the file was kept") for t in _sidebar_texts(at)), (
        f"the store was not refused with its notice: {_sidebar_texts(at)}")
    copies = [p for p in _data_dir().iterdir() if p.name.startswith("saved_charts.json.unreadable-")]
    assert len(copies) == 1, f"no single recovery copy: {sorted(p.name for p in _data_dir().iterdir())}"
    assert copies[0].read_bytes() == data, "the copy does not hold the original file's bytes"
    assert BAD not in _picker(at).options and "Florence" not in _picker(at).options


def test_the_loader_refuses_the_name_as_it_refuses_a_name_that_is_not_text(engine):
    with pytest.raises(ValueError):
        engine["_validate_chart_mapping"]({BAD: dict(FLORENCE_REC)})
    with pytest.raises(ValueError):
        engine["_parse_chart_mapping"](json.dumps({BAD: dict(FLORENCE_REC)}).encode())
    assert engine["_parse_chart_mapping"](json.dumps({FIRENZE: dict(FLORENCE_REC), MOON: dict(FLORENCE_REC)}).encode())


# --- 2. a record's text field --------------------------------------------------

@pytest.mark.parametrize("field, named", [("location_query", "its place is not"),
                                          ("time_standard", "its time standard is not")])
def test_a_record_whose_text_field_holds_a_lone_surrogate_is_refused_with_the_field_named(scratch, field, named):
    _write_store({"Bad": dict(FLORENCE_REC, **{field: BAD}), "Good": dict(FLORENCE_REC, location_query=FIRENZE)})
    at = make_app(page="chart").run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    assert {"Bad", "Good"} <= set(_picker(at).options), "the store itself was refused"
    _picker(at).select("Bad").run()
    assert not _exceptions(at), f"choosing the record raised {_exceptions(at)}"
    assert [t for t in _refusals(at) if t.startswith("'Bad' could not be loaded: " + named)], (
        f"the record was not refused with its field named: {_sidebar_texts(at)}")
    _picker(at).select("Good").run()
    assert not _exceptions(at) and not _refusals(at), f"the other record did not load: {_sidebar_texts(at)}"
    assert at.session_state["_record_loaded"]["name"] == "Good"


def test_a_last_chart_whose_time_standard_holds_a_lone_surrogate_does_not_stop_the_launch(prefs_on):
    _write_store({"Bad": dict(FLORENCE_REC, time_standard=BAD)})
    _write_prefs({"last_chart": "Bad"})
    at = _launch().run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    assert [t for t in _refusals(at) if "its time standard is not" in t], _sidebar_texts(at)


def test_chart_record_fault_names_the_field(engine):
    assert engine["chart_record_fault"](dict(FLORENCE_REC, location_query=BAD))[0] == "place"
    assert engine["chart_record_fault"](dict(FLORENCE_REC, time_standard=BAD))[0] == "time standard"
    assert engine["chart_record_fault"](dict(FLORENCE_REC, location_query=FIRENZE + " " + TOKYO + MOON)) is None


# --- 3. the home place's label -------------------------------------------------

def test_a_home_place_label_holding_a_lone_surrogate_is_refused_and_the_launch_goes_on(prefs_on, engine):
    _write_prefs({"home_place": {"label": BAD, "lat": 43.7792, "lon": 11.2463}})
    at = _launch().run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    texts = _sidebar_texts(at)
    assert "Resolve a place under Birthplace, then set it as home." in texts, (
        "the home place was not refused as an unusable one is (the popover offers to set one)")
    assert [t for t in texts if t.startswith("Home: ")] == []
    assert not engine["home_place_is_valid"]({"label": BAD, "lat": 43.7792, "lon": 11.2463})


# --- 4. ordinary non-ASCII text loads as before --------------------------------

def test_ordinary_non_ascii_names_and_places_load_as_before(prefs_on):
    _write_store({FIRENZE: dict(FLORENCE_REC, location_query=FIRENZE),
                  TOKYO: dict(FLORENCE_REC, location_query=TOKYO + " " + MOON)})
    _write_prefs({"home_place": {"label": FIRENZE, "lat": 43.7792, "lon": 11.2463}})
    at = _launch().run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    assert {FIRENZE, TOKYO} <= set(_picker(at).options)
    assert any(t.startswith("Home: ") and FIRENZE in t for t in _sidebar_texts(at)), _sidebar_texts(at)
    for name in (FIRENZE, TOKYO):
        _picker(at).select(name).run()
        assert not _exceptions(at) and not _refusals(at), f"{name!r} did not load: {_sidebar_texts(at)}"
        assert at.session_state["_record_loaded"]["name"] == name
    assert not [p for p in _data_dir().iterdir() if ".unreadable-" in p.name], "a well-formed store was copied aside"


# --- polish round (the blind check's M6, M7) -------------------------------------

@pytest.mark.parametrize("place", ["store name", "record place", "home label"])
def test_a_lone_low_surrogate_is_refused_in_each_place(prefs_on, engine, place):
    """M6: a check that looked only for HIGH surrogates (U+D800-DBFF) would
    let "\\udc00" through, and the page would raise on it just the same."""
    assert b"\\udc00" in json.dumps(LOW).encode("ascii"), "the premise: the file holds the escape"
    if place == "store name":
        data = _write_store({LOW: FLORENCE_REC, "Florence": FLORENCE_REC})
        with pytest.raises(ValueError):
            engine["_validate_chart_mapping"]({LOW: dict(FLORENCE_REC)})
    elif place == "record place":
        _write_store({"Bad": dict(FLORENCE_REC, location_query=LOW), "Good": FLORENCE_REC})
        _write_prefs({"last_chart": "Bad"})
        assert engine["chart_record_fault"](dict(FLORENCE_REC, location_query=LOW))[0] == "place"
    else:
        _write_prefs({"home_place": {"label": LOW, "lat": 43.7792, "lon": 11.2463}})
        assert not engine["home_place_is_valid"]({"label": LOW, "lat": 43.7792, "lon": 11.2463})
    at = _launch().run()
    assert not _exceptions(at), f"the launch raised {_exceptions(at)}"
    texts = _sidebar_texts(at)
    if place == "store name":
        assert any(t.startswith("Saved charts could not be read. A copy of the file was kept") for t in texts), texts
        copies = [p for p in _data_dir().iterdir() if p.name.startswith("saved_charts.json.unreadable-")]
        assert [c.read_bytes() for c in copies] == [data], "the copy does not hold the original file's bytes"
    elif place == "record place":
        assert [t for t in texts if t.startswith("'Bad' could not be loaded: its place is not")], texts
    else:
        assert "Resolve a place under Birthplace, then set it as home." in texts, texts


@pytest.mark.parametrize("bad", [BAD, LOW], ids=["high", "low"])
@pytest.mark.parametrize("before", [b'{"Florence": {"date_string": "1983-11-19"}}', None], ids=["store", "no store"])
def test_the_writer_refuses_a_name_holding_a_lone_surrogate_and_writes_nothing(scratch, bad, before):
    """M7: the writer refuses what the reader refuses. A writer that let such
    a name through would write a store the next launch copies aside."""
    import importlib
    importlib.import_module("engine")
    sync_engine_to_environment()                   # the paths are read at import: this test's folder
    engine = vars(sys.modules["engine"])
    path = _data_dir() / "saved_charts.json"
    if before is not None:
        path.write_bytes(before)
    assert Path(engine["SAVED_CHARTS_PATH"]) == path, "the premise: the engine writes into this test's folder"
    assert engine["write_saved_charts"]({bad: dict(FLORENCE_REC), "Florence": dict(FLORENCE_REC)}) is False
    if before is None:
        assert not path.exists(), "a store was written"
    else:
        assert path.read_bytes() == before, "the store's bytes changed"
    assert sorted(p.name for p in _data_dir().iterdir()) == ([] if before is None else ["saved_charts.json"])
    assert engine["write_saved_charts"]({FIRENZE: dict(FLORENCE_REC)}) is True, "the premise: the writer writes"
