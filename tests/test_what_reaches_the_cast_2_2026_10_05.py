"""What reaches the cast, the follow-ups' lane KC (K-11 to K-15 of
the re-pass's follow-ups of 2026-10-05): the cases beside their own pins in
``test_followups_2026_10_05.py``.

* A record carrying neither its coordinates nor a place query is refused on
  load with a sentence, at a launch as on a selection; a record with a query
  and no coordinates still loads (the legacy case the loader reads on purpose).
* A record whose date the parser cannot read is refused on load with a
  sentence (the owner's ruling 42 of 2026-10-06), at a launch as on a
  selection; a date the parser reads, a Julian leap day or a year before 1000
  among them, still loads.
* An integer too large for a float in a coordinate key is refused with the
  range sentence on every run, either sign, and the chart is cast once both
  boxes are changed.
* The strip names a record only while the boxes hold what was loaded from it
  as the store now holds it, and a refusal's sentence goes when the record it
  spoke of is replaced: a refused record with a wrong-typed field as a lacking
  one, a loaded record another window replaced with another nativity, and
  this window's own save afterwards named again.
"""
import json
import os
from datetime import time
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

LMT = "LMT (Local Mean Time)"
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
SYDNEY_REC = {**FLORENCE_REC, "location_query": "Sydney", "lat": -33.87, "lon": 151.21}
PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00", "time_standard": LMT,
            "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533}
NO_PLACE = {k: v for k, v in FLORENCE_REC.items() if k not in ("lat", "lon", "location_query")}
RANGE_SENTENCE = "Latitude must be between -90 and 90 and longitude between -180 and 180."


def _store():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d / "saved_charts.json"


def _strip(at):
    for caption in at.main.caption:
        if " · " in caption.value:
            return caption.value.splitlines()[0]
    return ""


def _sidebar_texts(at):
    out = []
    for kind in ("error", "warning", "info", "success", "caption", "markdown"):
        out += [e.value for e in getattr(at.sidebar, kind)]
    return out


def _pick(at, name):
    at.sidebar.selectbox(key="chart_picker").select(name).run()
    return at


def _save_as(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    return at


def _replace_if_asked(at):
    if any(b.key == "_replace_now" for b in at.sidebar.button):
        at.sidebar.button(key="_replace_now").click().run()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


# --- K-11: the place ---------------------------------------------------------

@pytest.mark.parametrize("record", [
    NO_PLACE,
    {**NO_PLACE, "lat": 40.0},
    {**NO_PLACE, "lon": 10.0, "location_query": None},
    {**NO_PLACE, "lat": None, "lon": None, "location_query": None},
], ids=["nothing", "latitude only", "longitude and a null query", "all three null"])
def test_a_record_with_neither_coordinates_nor_a_query_lacks_its_place(engine, record):
    assert engine["chart_record_lack"](record) == "place"


@pytest.mark.parametrize("record", [
    {**NO_PLACE, "location_query": "Florence"},
    {**NO_PLACE, "lat": 43.7792, "lon": 11.2463},
    FLORENCE_REC,
], ids=["a query only", "coordinates only", "both"])
def test_a_record_with_coordinates_or_a_query_does_not_lack_its_place(engine, record):
    assert engine["chart_record_lack"](record) is None


def test_a_selected_record_with_no_place_is_refused_and_the_boxes_keep_their_place(scratch):
    _store().write_text(json.dumps({"First": SYDNEY_REC, "No place": NO_PLACE}))
    at = make_app(page="chart").run()
    _pick(at, "First")
    assert _strip(at).startswith("First · ") and "Sydney" in _strip(at), "the premise: First is cast at Sydney"
    _pick(at, "No place")
    assert_no_exception(at)
    texts = _sidebar_texts(at)
    assert "'No place' could not be loaded: it holds no place." in texts, texts
    assert "Edited since it was saved." not in texts, texts
    assert _strip(at).startswith("Unsaved chart · "), _strip(at)


def test_a_record_with_a_query_and_no_coordinates_still_loads(scratch):
    _store().write_text(json.dumps({"First": SYDNEY_REC, "Legacy": {**NO_PLACE, "location_query": "Florence"}}))
    at = make_app(page="chart").run()
    _pick(at, "First")
    _pick(at, "Legacy")
    assert_no_exception(at)
    assert not [v for v in _sidebar_texts(at) if "could not be loaded" in v], _sidebar_texts(at)
    assert _strip(at).startswith("Legacy") and "Florence" in _strip(at), _strip(at)


def test_a_last_chart_with_no_place_opens_on_no_chart_with_its_sentence(scratch, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    _store().write_text(json.dumps({"No place": NO_PLACE}))
    (_store().parent / "preferences.json").write_text(json.dumps({"last_chart": "No place"}))
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.run()
    assert_no_exception(at)
    assert "'No place' could not be loaded: it holds no place." in _sidebar_texts(at)
    assert at.sidebar.selectbox(key="chart_picker").value != "No place"
    assert _strip(at).startswith("Unsaved chart · 1240-05-23 14:30:00"), _strip(at)


# --- K-12: a date the parser cannot read ---------------------------------------

UNREADABLE = ("date", "calendar date as YYYY-MM-DD")


@pytest.mark.parametrize("bad", ["", "   ", "garbage", "1990-02-30", "0000-01-01", "10000-01-01",
                                 "1900-02-29", "1240-05-23T14:30"])
def test_a_date_the_parser_cannot_read_is_a_fault(engine, bad):
    assert engine["chart_record_fault"]({**FLORENCE_REC, "date_string": bad}) == UNREADABLE


@pytest.mark.parametrize("good", ["1983-11-19", "1300-02-29", "0787-08-10", " 1983-11-19 "])
def test_a_date_the_parser_reads_is_not_a_fault(engine, good):
    assert engine["chart_record_fault"]({**FLORENCE_REC, "date_string": good}) is None


def test_a_selected_record_with_an_unreadable_date_is_refused_and_the_boxes_keep_their_date(scratch):
    _store().write_text(json.dumps({"First": {**FLORENCE_REC, "date_string": "1977-07-07"},
                                    "Bad date": {**FLORENCE_REC, "date_string": "1990-02-30"}}))
    at = make_app(page="chart").run()
    _pick(at, "First")
    _pick(at, "Bad date")
    assert_no_exception(at)
    texts = _sidebar_texts(at)
    assert "'Bad date' could not be loaded: its date is not a calendar date as YYYY-MM-DD." in texts, texts
    assert at.session_state["date_input_key"] == "1977-07-07"
    assert _strip(at).startswith("Unsaved chart · 1977-07-07"), _strip(at)


def test_a_last_chart_with_an_unreadable_date_opens_on_no_chart_with_its_sentence(scratch, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    _store().write_text(json.dumps({"Bad date": {**FLORENCE_REC, "date_string": "garbage"}}))
    (_store().parent / "preferences.json").write_text(json.dumps({"last_chart": "Bad date"}))
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.run()
    assert_no_exception(at)
    assert ("'Bad date' could not be loaded: its date is not a calendar date as YYYY-MM-DD."
            in _sidebar_texts(at)), _sidebar_texts(at)
    assert at.sidebar.selectbox(key="chart_picker").value != "Bad date"
    assert _strip(at).startswith("Unsaved chart · 1240-05-23 14:30:00"), _strip(at)


# --- K-13: a coordinate too large for a float ---------------------------------

@pytest.mark.parametrize("lat, lon", [(10 ** 400, 0.0), (0.0, -(10 ** 400)), (-(10 ** 400), 10 ** 400)],
                         ids=["latitude", "longitude", "both"])
def test_the_range_check_refuses_an_integer_too_large_for_a_float(engine, lat, lon):
    assert engine["coordinates_in_range"](lat, lon) is False


@pytest.mark.parametrize("key", ["manual_lat_key", "manual_lon_key"])
def test_a_negative_integer_too_large_for_a_float_stays_refused_until_both_boxes_change(key):
    at = make_app(date="1240-05-23", page="chart")
    at.session_state[key] = -(10 ** 400)
    for run in range(3):
        at.run()
        assert_no_exception(at, f"run {run + 1}")
        assert RANGE_SENTENCE in [e.value for e in at.sidebar.error], f"run {run + 1}: {_sidebar_texts(at)}"
        assert not at.main.dataframe, f"run {run + 1} cast {_strip(at)}"
    at.sidebar.number_input(key="manual_lat_key").set_value(45.0).run()
    at.sidebar.number_input(key="manual_lon_key").set_value(11.0).run()
    assert_no_exception(at)
    assert at.main.dataframe, "the boxes were changed and the chart is still refused"


# --- K-14, K-15: the record as the store now holds it -------------------------

def test_a_refusal_for_a_wrong_typed_field_goes_when_another_window_replaces_the_record(scratch):
    _store().write_text(json.dumps({"First": FLORENCE_REC, "Bad": {**FLORENCE_REC, "time_string": 1030},
                                    "Third": PETOSKEY}))
    a = make_app(page="chart").run()
    _pick(a, "First")
    _pick(a, "Bad")
    assert any(v.startswith("'Bad' could not be loaded: its time") for v in _sidebar_texts(a)), "the premise"
    b = make_app(page="chart").run()
    _pick(b, "Third")
    _save_as(b, "Bad")
    _replace_if_asked(b)
    assert json.loads(_store().read_text())["Bad"]["time_string"] == "11:44:00", "the premise: B replaced it"
    _save_as(a, "Bad")
    _replace_if_asked(a)
    a.run()
    assert_no_exception(a)
    assert not [v for v in _sidebar_texts(a) if "could not be loaded" in v], _sidebar_texts(a)
    assert "Edited since it was saved." not in _sidebar_texts(a)
    assert not _strip(a).startswith("Bad"), _strip(a)


def test_a_loaded_record_another_window_replaced_is_not_named_until_loaded_again(scratch):
    rec = {**FLORENCE_REC, "time_string": "08:00:00"}
    _store().write_text(json.dumps({"Rec": rec}))
    a = make_app(page="chart").run()
    _pick(a, "Rec")
    assert _strip(a).startswith("Rec · 1983-11-19 08:00:00"), "the premise: A loaded Rec"
    b = make_app(page="chart").run()
    _pick(b, "Rec")
    b.session_state["time_input_key"] = time(9, 0)
    b.run()
    _save_as(b, "Rec")
    _replace_if_asked(b)
    assert json.loads(_store().read_text())["Rec"]["time_string"] == "09:00:00", "the premise: B replaced it"
    _save_as(a, "Rec")
    assert any("'Rec' was replaced by another window" in v for v in _sidebar_texts(a)), _sidebar_texts(a)
    a.run()
    assert_no_exception(a)
    assert _strip(a).startswith("Unsaved chart · 1983-11-19 08:00:00"), _strip(a)
    assert "Edited since it was saved." not in _sidebar_texts(a)
    _pick(a, "-- New Chart --")
    _pick(a, "Rec")
    assert_no_exception(a)
    assert _strip(a).startswith("Rec · 1983-11-19 09:00:00"), _strip(a)


def test_this_windows_own_save_after_the_store_moved_is_named(scratch):
    rec = {**FLORENCE_REC, "time_string": "08:00:00"}
    _store().write_text(json.dumps({"Rec": rec}))
    a = make_app(page="chart").run()
    _pick(a, "Rec")
    _store().write_text(json.dumps({"Rec": {k: v for k, v in rec.items() if k != "time_string"}}))
    _save_as(a, "Rec")
    a.run()
    assert _strip(a).startswith("Unsaved chart · "), "the premise: the store's Rec holds no time"
    _save_as(a, "Kept")
    assert_no_exception(a)
    assert _strip(a).startswith("Kept · 1983-11-19 08:00:00"), _strip(a)
    assert json.loads(_store().read_text())["Kept"]["time_string"] == "08:00:00"
