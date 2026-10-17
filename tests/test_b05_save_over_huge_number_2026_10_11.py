"""B-05 of the third outside pass (ruling 146): Save over a damaged record
asks to replace it, whatever number the record holds.

Save over a name already in use compared the stored record with the chart
in hand BEFORE asking whether the stored record could be loaded at all, and
the comparison converted each stored number with ``float()``, catching only
``TypeError`` and ``ValueError``. A stored integer past the float range (a
hand edit: JSON reads any length of digits as an int) raised
``OverflowError`` and the page showed a traceback in place of the question.

SC-17's rule is that a record the loader refuses "is not 'already saved as
it is': the reader is asked whether to replace it". Now:

- the Save path asks ``chart_record_fault`` (and ``chart_record_lack``)
  first, and never compares a record the loader refuses;
- ``_record_inputs_match`` reads each stored number through the engine's
  ``record_number``, so a value it cannot read as a number is a mismatch,
  never an exception.

Every case is cast under the manual time standard with the target date
fixed, so that the comparison reaches each of the four numeric fields (under
LMT the chart's offset is None and a stored offset is never converted; the
age is reached only when the target date agrees).
"""
import ast
import json
import os
import re
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app, ui_source

MANUAL = "Manual UTC offset"
TARGET_DATE = "2000-01-01"
# The record Save writes for the chart these tests open (1240-05-23 14:30,
# Florence by coordinates, at UTC+1, the target 2000-01-01), without its
# readings and stamp: a schema-1 record, which no readings can disagree with.
SAME = {"date_string": "1240-05-23", "time_string": "14:30:00", "time_standard": MANUAL, "utc_offset": 1.0,
        "location_query": "Manual [43.7792, 11.2463]", "lat": 43.7792, "lon": 11.2463,
        "target_mode": "Date", "target_date": TARGET_DATE, "target_age": 759}
FIELDS = ("lat", "lon", "utc_offset", "target_age")
HUGE = 10 ** 400                       # past the float range: float() raises OverflowError
# 10**20 (refused by the loader, a float to compare) and 91 (out of range as a
# latitude, a longitude or an age the loader takes, an offset it takes) asked
# to replace on the base; they still do.
VALUES = [pytest.param(HUGE, id="10e400"), pytest.param(10 ** 20, id="10e20"), pytest.param(91, id="91")]
QUESTION = "'Broken' exists. Replace it?"


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable XDG directory for each case; preferences stay off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def _store():
    return Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"


def _put_store(charts):
    """Write the store; the bytes written, which no press may change."""
    data = json.dumps(charts, indent=2).encode("ascii")
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_bytes(data)
    return data


def _broken(field, value):
    record = dict(SAME)
    record[field] = value
    return record


def _launch():
    at = make_app(page="chart", timeout=300)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 1.0
    at.session_state["_target_date"] = TARGET_DATE
    return at.run()


def _name_box(at):
    return [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0]


def _save_button(at):
    return [b for b in at.sidebar.button if "Save" in b.label][0]


def _labelled(at, label):
    hits = [b for b in at.sidebar.button if b.label == label]
    assert len(hits) == 1, f"expected one sidebar button '{label}', found {[b.label for b in at.sidebar.button]}"
    return hits[0]


def _has(at, label):
    return any(b.label == label for b in at.sidebar.button)


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _strip(at):
    for caption in at.main.caption:
        if " · " in caption.value:
            return caption.value.split(" · ")[0]
    return ""


def _refusals(at):
    return [e.value for kind in ("error", "warning", "info", "caption") for e in getattr(at.sidebar, kind)
            if "could not be loaded" in e.value]


def _save_over_broken(at):
    _name_box(at).set_value("Broken").run()
    _save_button(at).click().run()


def _the_chart_in_hand(record):
    """The fields of `record` the chart in hand sets, as SAME holds them."""
    return {field: record.get(field) for field in SAME}


# --- the press: the question, and nothing written -----------------------------

@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("field", FIELDS)
def test_save_over_a_damaged_record_asks_to_replace_and_writes_nothing(scratch, field, value):
    written = _put_store({"Broken": _broken(field, value)})
    at = _launch()
    assert_no_exception(at, "the launch")
    _save_over_broken(at)
    assert_no_exception(at, f"Save over a record whose {field} is {value if value != HUGE else '10**400'}")
    assert QUESTION in [w.value for w in at.sidebar.warning], (
        f"no replace question: warnings {[w.value for w in at.sidebar.warning]}")
    assert _has(at, "Replace") and _has(at, "Keep both")
    assert "'Broken' is already saved as it is." not in [i.value for i in at.sidebar.info]
    assert at.session_state["_replace_pending"] == "Broken"
    assert _store().read_bytes() == written, "the press alone wrote the store"


# --- Replace: the chart in hand is written, and loads ------------------------

@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("field", FIELDS)
def test_replace_writes_the_chart_in_hand_and_the_record_loads(scratch, field, value, engine):
    _put_store({"Broken": _broken(field, value)})
    at = _launch()
    _save_over_broken(at)
    _labelled(at, "Replace").click().run()
    assert_no_exception(at, "replace")
    stored = json.loads(_store().read_text())
    assert list(stored) == ["Broken"]
    assert _the_chart_in_hand(stored["Broken"]) == SAME, stored["Broken"]
    assert engine["chart_record_fault"](stored["Broken"]) is None
    assert _picker(at).value == "Broken"
    assert _strip(at) == "Broken"
    assert not _refusals(at), _refusals(at)
    assert not _has(at, "Replace")


# --- Keep both: the damaged record stands, the chart saved beside it ----------

@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("field", FIELDS)
def test_keep_both_keeps_the_damaged_record_and_saves_under_the_next_free_name(scratch, field, value):
    _put_store({"Broken": _broken(field, value)})
    at = _launch()
    _save_over_broken(at)
    _labelled(at, "Keep both").click().run()
    assert_no_exception(at, "keep both")
    stored = json.loads(_store().read_text())
    assert sorted(stored) == ["Broken", "Broken (2)"]
    assert stored["Broken"] == _broken(field, value), "the damaged record was altered"
    assert _the_chart_in_hand(stored["Broken (2)"]) == SAME, stored["Broken (2)"]
    assert _picker(at).value == "Broken (2)"
    assert _strip(at) == "Broken (2)"


# --- a usable record of the same chart is still already saved ----------------

def test_a_usable_identical_record_is_still_already_saved_as_it_is(scratch, engine):
    assert engine["chart_record_fault"](SAME) is None, "the premise: the record loads"
    written = _put_store({"Broken": dict(SAME)})
    at = _launch()
    _save_over_broken(at)
    assert_no_exception(at, "Save over the same chart")
    assert any(i.value == "'Broken' is already saved as it is." for i in at.sidebar.info), (
        [i.value for i in at.sidebar.info])
    assert not _has(at, "Replace") and not _has(at, "Keep both")
    assert QUESTION not in [w.value for w in at.sidebar.warning]
    assert _store().read_bytes() == written


def test_a_refused_record_the_comparison_calls_the_same_chart_still_asks(scratch, engine):
    """An age of 759.00001 is the chart in hand to four places, and the
    loader refuses it (an age is a whole number): it is not "already saved
    as it is" (SC-17), so the question is asked, as on the base."""
    record = _broken("target_age", 759.00001)
    assert engine["chart_record_fault"](record) is not None, "the premise: the loader refuses it"
    written = _put_store({"Broken": record})
    at = _launch()
    _save_over_broken(at)
    assert_no_exception(at, "Save over a refused record of the same chart")
    assert QUESTION in [w.value for w in at.sidebar.warning]
    assert "'Broken' is already saved as it is." not in [i.value for i in at.sidebar.info]
    assert _store().read_bytes() == written


# --- the comparison itself never raises on a stored value -------------------

def _app_function(name, **names):
    """One module-level function of app.py, lifted by its source and run with
    `names` as its globals."""
    source = ui_source()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = dict(names)
    exec(ast.get_source_segment(source, node), namespace)
    return namespace[name]


@pytest.fixture
def inputs_match(engine):
    """_record_inputs_match with the engine's readers and a zone that is the
    same on both sides (the zone is compared last, after every field)."""
    return _app_function("_record_inputs_match", _RECORD_NOT_INPUT=("readings", "saved_with"),
                         time_standard_current=engine["time_standard_current"],
                         record_number=engine["record_number"],
                         _manual_place_label=lambda lat, lon: f"Manual [{lat}, {lon}]",
                         _cast_zone=lambda record: None)


@pytest.mark.parametrize("field", FIELDS)
def test_the_comparison_reads_a_number_past_the_float_range_as_a_mismatch(inputs_match, field):
    """Each numeric field the comparison reaches, not only the first: the
    same stored record with the field put right matches, so the field is
    reached and compared."""
    assert inputs_match(dict(SAME), dict(SAME)) is True
    for value in (HUGE, -HUGE, str(HUGE)):
        assert inputs_match(_broken(field, value), dict(SAME)) is False, (field, type(value).__name__)


def test_the_comparison_still_reads_a_number_as_the_number_it_means(inputs_match):
    """As before: a latitude written as text, a whole number read back as an
    int, and an offset or age within four places are the same chart; a
    coordinate below the fourth place is not (ruling 145, B-01)."""
    assert inputs_match(dict(SAME, lat="43.7792", lon=" 11.2463 "), dict(SAME)) is True
    assert inputs_match(dict(SAME, utc_offset=1, target_age=759.0), dict(SAME)) is True
    assert inputs_match(dict(SAME, utc_offset=1.00001), dict(SAME)) is True
    assert inputs_match(dict(SAME, lat=43.77921), dict(SAME)) is False
    assert inputs_match(dict(SAME, target_age="seven"), dict(SAME)) is False
    assert inputs_match(dict(SAME, utc_offset=None), dict(SAME)) is False


# --- the order on the Save path ---------------------------------------------

def test_the_save_path_asks_whether_the_record_loads_before_comparing_it():
    """Structural: whether the record loads is asked before it is compared,
    so no comparison ever sees a record the loader refuses. With the
    comparison guarded as well, the order shows in no page, and only this
    pin holds it."""
    source = ui_source()
    start = source.index('_existing = st.session_state["saved_charts"].get(trimmed_name)')
    branch = source[start:source.index('st.session_state["_replace_pending"] = trimmed_name', start)]
    fault = branch.index("chart_record_fault(_existing) is None")
    lack = branch.index("chart_record_lack(_existing) is None")
    match = branch.index("_records_match(_existing, input_record)")
    assert fault < match and lack < match, "the Save path compares a record before asking whether it loads"
    assert len(re.findall(r"_records_match\(", branch)) == 1
