"""A saved chart under the empty name can be deleted.

Save refuses an empty name (and one of spaces only, which it strips to
empty), but the store keeps every name as it is written, so a store written
by hand or by another program can hold a record under "". The picker lists it
as "[... no name]" (with an ellipsis). The delete used to ask whether the
name picked, pending or confirmed was true rather than whether there was one,
so the bin asked nothing and the record could never be deleted. It is deleted
now as any other record is: the same question, under the same lock, by the
same write, which removes that record and leaves every other one, byte for
byte, as it stood.

A load of it is not asked for, and is as it was: picking it puts the example
nativity in the boxes, as "-- New Chart --" does.
"""
import json
import os
from pathlib import Path

import pytest

import user_data
from conftest import APP_PATH, assert_no_exception, sync_engine_to_environment

NEW_CHART = "-- New Chart --"
NO_NAME = "[… no name]"
ZWSP, ZWNJ = "\u200b", "\u200c"
RECORD = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
          "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
BIN_HELP = "Delete the selected saved chart"
MOVED_TAIL = " The saved charts have been reloaded and nothing was written; look at the list and try again."
BUSY = ("Another window of this app is holding the saved charts just now, "
        "so nothing was written. Try again in a moment.")


def _record(year):
    """A record of its own: each name's record differs by its date."""
    return dict(RECORD, date_string=f"{year}-01-01")


def _engine():
    sync_engine_to_environment()
    import engine
    return engine


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable data folder, asserted to be the one the app reads and
    writes before anything else is done; preferences stay off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("ALMUTEN_NO_PREFERENCES", "1")
    engine = _engine()
    assert Path(engine.DATA_DIR).resolve().is_relative_to(tmp_path.resolve()), engine.DATA_DIR
    assert Path(engine.SAVED_CHARTS_PATH).resolve().is_relative_to(tmp_path.resolve()), engine.SAVED_CHARTS_PATH
    assert _store_path().resolve().is_relative_to(tmp_path.resolve())
    return tmp_path


def _store_path():
    return Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"


def _put_store(charts):
    """Write the store as the app writes one; its text."""
    text = json.dumps(charts, indent=2)
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    _store_path().write_text(text, encoding="utf-8")
    return text


def _store_text():
    return _store_path().read_text(encoding="utf-8")


def _block(name, record):
    """A record's lines in the store's text, as the app writes them."""
    return json.dumps({name: record}, indent=2)[2:-2]


def _assert_left_as_they_stood(text, charts):
    """The store's text is exactly the app's text of `charts`, and each
    record's lines in it are the very lines it had."""
    assert text == json.dumps(charts, indent=2), text
    for name, record in charts.items():
        assert _block(name, record) in text, name


def _launch():
    """A session that seeds nothing, as a launch is."""
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    return at.run()


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _warnings(at):
    return [e.value for e in at.sidebar.warning]


def _bin(at):
    hits = [b for b in at.sidebar.button if b.help == BIN_HELP]
    assert len(hits) == 1, [(b.label, b.help) for b in at.sidebar.button]
    return hits[0]


def _ask_to_delete(at, name):
    """Pick `name` and press the bin; the question must stand."""
    _picker(at).select(name).run()
    assert_no_exception(at, "the pick")
    _bin(at).click().run()
    assert_no_exception(at, "the bin")
    question = f"Delete '{_picker(at).format_func(name)}'?"
    assert question in _warnings(at), (question, _warnings(at))
    return at


def _confirm(at):
    at.sidebar.button(key="_delete_confirm").click().run()
    assert_no_exception(at, "the delete")
    return at


# --- the list and the question -------------------------------------------

def test_the_unnamed_record_is_listed_under_its_label_and_its_question_names_it_so(scratch):
    _put_store({"": _record(1980), "Alice": _record(1981), "Bob": _record(1982)})
    at = _launch()
    assert_no_exception(at, "the launch")
    assert list(_picker(at).options) == [NEW_CHART, NO_NAME, "Alice", "Bob"]
    _ask_to_delete(at, "")
    assert f"Delete '{NO_NAME}'?" in _warnings(at), _warnings(at)


def test_the_unnamed_record_is_deleted_and_the_named_ones_stay_byte_for_byte(scratch):
    """The unnamed record stands between the named ones in the file, so a
    delete of the first or the last record instead is told apart."""
    charts = {"Alice": _record(1981), "": _record(1980), "Bob": _record(1982)}
    _put_store(charts)
    at = _confirm(_ask_to_delete(_launch(), ""))
    _assert_left_as_they_stood(_store_text(), {"Alice": charts["Alice"], "Bob": charts["Bob"]})
    assert list(_picker(at).options) == [NEW_CHART, "Alice", "Bob"]
    assert _picker(at).value == NEW_CHART
    assert f"Delete '{NO_NAME}'?" not in _warnings(at)


def test_a_named_record_beside_the_unnamed_one_is_deleted_alone(scratch):
    """The honest case: deleting a named record leaves the unnamed one."""
    charts = {"": _record(1980), "Alice": _record(1981), "Bob": _record(1982)}
    _put_store(charts)
    _confirm(_ask_to_delete(_launch(), "Alice"))
    _assert_left_as_they_stood(_store_text(), {"": charts[""], "Bob": charts["Bob"]})


def test_a_delete_kept_at_its_question_deletes_nothing_and_can_be_asked_again(scratch):
    text = _put_store({"": _record(1980), "Alice": _record(1981)})
    at = _ask_to_delete(_launch(), "")
    at.sidebar.button(key="_delete_keep").click().run()
    assert_no_exception(at, "the keep")
    assert _store_text() == text
    assert f"Delete '{NO_NAME}'?" not in _warnings(at), _warnings(at)
    assert list(_picker(at).options) == [NEW_CHART, NO_NAME, "Alice"]
    _bin(at).click().run()
    assert f"Delete '{NO_NAME}'?" in _warnings(at), _warnings(at)
    assert _store_text() == text


# --- names a reader may take for no name ---------------------------------

@pytest.mark.parametrize("other", [ZWSP, ZWSP + ZWNJ, " ", "   "], ids=["zwsp", "zwsp-zwnj", "space", "spaces"])
def test_the_unnamed_record_and_a_name_that_draws_nothing_are_each_deleted_alone(scratch, other):
    """Beside a name of invisible marks only, or of spaces only (neither
    can be saved empty: Save keeps the marks and strips the spaces, so a
    space-only name is a hand edit's): each has a label of its own, and
    each delete removes its own record only."""
    charts = {"": _record(1980), other: _record(1981), "Alice": _record(1982)}
    _put_store(charts)
    at = _launch()
    labels = list(_picker(at).options)
    assert len(set(labels)) == len(labels) == 4 and labels[1] == NO_NAME, labels
    _confirm(_ask_to_delete(at, ""))
    _assert_left_as_they_stood(_store_text(), {other: charts[other], "Alice": charts["Alice"]})
    _put_store(charts)
    _confirm(_ask_to_delete(_launch(), other))
    _assert_left_as_they_stood(_store_text(), {"": charts[""], "Alice": charts["Alice"]})


def test_a_typed_no_name_label_is_not_the_unnamed_record(scratch):
    """A name typed as the label's own text is drawn apart from it, and
    deleting either leaves the other."""
    charts = {"": _record(1980), NO_NAME: _record(1981)}
    _put_store(charts)
    at = _launch()
    labels = list(_picker(at).options)
    assert labels[1] == NO_NAME and labels[2] != NO_NAME, labels
    _confirm(_ask_to_delete(at, NO_NAME))
    _assert_left_as_they_stood(_store_text(), {"": charts[""]})


# --- two unnamed records --------------------------------------------------

def test_a_store_naming_the_empty_name_twice_is_kept_aside_whole_and_nothing_is_deleted(scratch):
    """One store cannot hold two records under one name: bytes that repeat
    a name are not a store (the parser would keep the last and drop the
    first), so they are copied aside whole and listed as no records, and no
    delete can choose between the two. As before this change."""
    raw = '{\n  "": %s,\n  "": %s,\n  "Alice": %s\n}' % tuple(
        json.dumps(_record(year)) for year in (1980, 1981, 1982))
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    _store_path().write_text(raw, encoding="utf-8")
    at = _launch()
    assert_no_exception(at, "the launch")
    assert list(_picker(at).options) == [NEW_CHART]
    assert _store_text() == raw
    copies = [p for p in _store_path().parent.iterdir() if p.name != "saved_charts.json" and "saved_charts" in p.name
              and p.suffix != ".lock"]
    assert any(p.read_text(encoding="utf-8") == raw for p in copies), [p.name for p in copies]
    _bin(at).click().run()
    assert "_delete_confirm" not in [b.key for b in at.sidebar.button]
    assert _store_text() == raw


def test_two_windows_listing_the_unnamed_record_delete_it_once(scratch):
    """The other window's sentence names it by its label, and nothing more
    is deleted: the second delete finds it gone and writes nothing."""
    charts = {"": _record(1980), "Alice": _record(1981), "Bob": _record(1982)}
    _put_store(charts)
    first = _ask_to_delete(_launch(), "")
    _confirm(_ask_to_delete(_launch(), ""))
    named = {"Alice": charts["Alice"], "Bob": charts["Bob"]}
    _assert_left_as_they_stood(_store_text(), named)
    _confirm(first)
    assert f"'{NO_NAME}' was deleted by another window since this one read it.{MOVED_TAIL}" in _warnings(first), (
        _warnings(first))
    _assert_left_as_they_stood(_store_text(), named)
    assert list(_picker(first).options) == [NEW_CHART, "Alice", "Bob"]


def test_an_unnamed_record_written_again_since_the_list_is_not_deleted(scratch):
    """The record the window listed is the one it deletes: another record
    put under the empty name since (by hand, or by another program) is not
    the one asked about, so it stays, and the window says so."""
    charts = {"": _record(1980), "Alice": _record(1981)}
    _put_store(charts)
    at = _ask_to_delete(_launch(), "")
    since = dict(charts, **{"": _record(1999)})
    text = _put_store(since)
    _confirm(at)
    assert f"'{NO_NAME}' was replaced by another window since this one read it.{MOVED_TAIL}" in _warnings(at), (
        _warnings(at))
    assert _store_text() == text


def test_a_question_about_an_unnamed_record_that_has_left_the_list_is_dropped(scratch):
    """Another window deletes the unnamed record while this one asks about
    it; this window's next save reads the store again, and the list it
    keeps no longer holds the record. The question goes with it, on the
    save's own run: one left standing over a list without its record, even
    for one run, would offer a Delete that does nothing."""
    charts = {"": _record(1980), "Alice": _record(1981)}
    _put_store(charts)
    at = _ask_to_delete(_launch(), "")
    engine = _engine()
    with engine.saved_charts_lock():
        stands = engine.saved_charts_as_they_stand()
        assert stands.state == "readable"
        assert engine.write_saved_charts({"Alice": charts["Alice"]})
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value("Carol").run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    assert_no_exception(at, "the save")
    assert not [w for w in _warnings(at) if w.startswith("Delete '")], _warnings(at)
    assert "_delete_confirm" not in [b.key for b in at.sidebar.button]
    at.run()
    assert_no_exception(at, "the run after the save")
    assert set(json.loads(_store_text())) == {"Alice", "Carol"}, _store_text()
    assert list(_picker(at).options) == [NEW_CHART, "Alice", "Carol"], list(_picker(at).options)
    assert not [w for w in _warnings(at) if w.startswith("Delete '")], _warnings(at)
    assert "_delete_confirm" not in [b.key for b in at.sidebar.button]


# --- the lock -------------------------------------------------------------

def test_another_windows_save_between_the_list_and_the_delete_is_kept(scratch):
    charts = {"": _record(1980), "Alice": _record(1981), "Bob": _record(1982)}
    _put_store(charts)
    at = _ask_to_delete(_launch(), "")
    engine = _engine()
    with engine.saved_charts_lock():
        stands = engine.saved_charts_as_they_stand()
        assert stands.state == "readable"
        assert engine.write_saved_charts(dict(stands.charts, Carol=_record(1983)))
    _confirm(at)
    assert not [w for w in _warnings(at) if "another window" in w], _warnings(at)
    _assert_left_as_they_stood(_store_text(), {"Alice": charts["Alice"], "Bob": charts["Bob"],
                                               "Carol": _record(1983)})


def test_the_delete_of_the_unnamed_record_waits_for_the_lock_and_writes_nothing_without_it(scratch, monkeypatch):
    text = _put_store({"": _record(1980), "Alice": _record(1981)})
    at = _ask_to_delete(_launch(), "")
    engine = _engine()
    monkeypatch.setattr(user_data, "LOCK_WAIT_SECONDS", 0.5)
    with engine.saved_charts_lock():
        at.sidebar.button(key="_delete_confirm").click().run()
        assert _store_text() == text, "the store was written while another held its lock"
    assert_no_exception(at, "the delete")
    assert BUSY in [e.value for e in at.sidebar.error], [e.value for e in at.sidebar.error]
    assert _store_text() == text
    assert NO_NAME in list(_picker(at).options)


def test_a_store_made_malformed_before_the_unnamed_record_is_deleted_is_copied_first(scratch):
    """Bytes that are no longer a store when Delete is pressed are copied
    aside whole before anything is written over them, and the sidebar says
    so; the delete of the unnamed record is no exception."""
    charts = {"": _record(1980), "Alice": _record(1981)}
    _put_store(charts)
    at = _ask_to_delete(_launch(), "")
    broken = '{\n  "": {"date_string": "1980-01-01",\n'
    _store_path().write_text(broken, encoding="utf-8")
    _confirm(at)
    copies = [p for p in _store_path().parent.iterdir() if p.name != "saved_charts.json" and "saved_charts" in p.name
              and p.suffix != ".lock"]
    assert [p.name for p in copies if p.read_text(encoding="utf-8") == broken], [p.name for p in copies]
    said = [e.value for kind in ("warning", "info", "error", "success") for e in getattr(at.sidebar, kind)]
    assert [s for s in said if "A copy of the file was kept beside the saved charts" in s], said
    _assert_left_as_they_stood(_store_text(), {"Alice": charts["Alice"]})


# --- the store ------------------------------------------------------------

def test_the_store_reads_and_writes_the_empty_name_as_it_is(scratch):
    """The store keeps a name as written: an empty one is read as empty and
    written back as empty (nothing in the store strips or drops it), so the
    page's delete is the only place it was ever lost."""
    engine = _engine()
    charts = {"": _record(1980), ZWSP: _record(1981), "Alice": _record(1982)}
    text = _put_store(charts)
    assert engine.load_saved_charts() == charts
    stands = engine.saved_charts_as_they_stand()
    assert stands.state == "readable" and stands.charts == charts
    remaining = dict(stands.charts)
    remaining.pop("")
    with engine.saved_charts_lock():
        assert engine.write_saved_charts(remaining)
    _assert_left_as_they_stood(_store_text(), {ZWSP: charts[ZWSP], "Alice": charts["Alice"]})
    assert text != _store_text()
