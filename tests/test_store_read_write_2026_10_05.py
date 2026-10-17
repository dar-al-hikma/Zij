"""The saved-charts store's read and write, beside the follow-ups' pins.

The pins (K-01, K-03 to K-08 in ``test_followups_2026_10_05.py``) hold the
store's own cases. These hold what the same changes reach beyond them: the
preferences file goes through the store's writer, so it keeps its mode and
its link too; a link to a link to a read-only file; a delete under a store
removed while the window was open; two windows when the folder comes back;
a store nested past the parser's depth named once, at launch, and not again
at the first save; the digest a session keeps after a write is of the bytes
written. And one guard on the repeated-name rule: a field repeated inside a
record is not a chart named twice, and the store still loads.
"""
import hashlib
import json
import os
import stat

from conftest import assert_no_exception, make_app, sync_engine_to_environment
from test_followups_2026_10_05 import DEEP_JSON, FORMER_NAME, _all_alerts, _launch, prefs_on
from test_repass_l6_2026_10_04 import (PETOSKEY, _delete, _picker, _read, _save_as, _sidebar_texts, _store,
                                       scratch)

XY = {"X": PETOSKEY, "Y": {**PETOSKEY, "date_string": "1990-01-01"}}
REMOVED = "The saved charts file had been removed since this window read it"


def _prefs_file():
    return _store().parent / "preferences.json"


def _copies():
    return sorted(_store().parent.glob("saved_charts.json.unreadable-*"))


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_a_delete_under_a_store_removed_while_open_keeps_the_rest_and_says_so(scratch):
    _store().write_text(json.dumps(XY))
    at = make_app(date="1983-11-19", page="chart").run()
    assert sorted(_picker(at).options) == ["-- New Chart --", "X", "Y"], "the premise: the session holds X and Y"
    _store().unlink()
    _delete(at, "X")
    assert_no_exception(at, "the delete")
    texts = _sidebar_texts(at)
    assert sorted(_read(_store())) == ["Y"], "the delete wrote this window's other record back"
    assert any(v.startswith(REMOVED) for v in texts), texts
    assert [v for v in texts if "by another window" in v] == [], texts


def test_the_preferences_keep_their_mode_and_their_link(prefs_on, tmp_path):
    synced = tmp_path / "synced"
    synced.mkdir()
    target = synced / "prefs.json"
    target.write_text(json.dumps({"_launches": 3}))
    target.chmod(0o440)
    _prefs_file().symlink_to(target)
    try:
        at = _launch().run()
        assert_no_exception(at, "the launch")
        assert _prefs_file().is_symlink(), "the link in the preferences' place became a regular file"
        assert json.loads(target.read_text()).get("_launches") == 4, "the launch's count did not reach the linked file"
        assert _mode(target) == 0o440, f"the preferences' mode is now {oct(_mode(target))}"
        assert [p.name for p in synced.iterdir()] == ["prefs.json"], "a temp file was left beside the preferences"
    finally:
        target.chmod(0o644)


def test_a_store_reached_through_two_links_keeps_both_and_its_mode(scratch, tmp_path):
    synced = tmp_path / "synced"
    synced.mkdir()
    target = synced / "charts.json"
    target.write_text(json.dumps(XY))
    target.chmod(0o444)
    hop = synced / "hop.json"
    hop.symlink_to(target)
    _store().symlink_to(hop)
    try:
        at = make_app(date="1983-11-19", page="chart").run()
        _save_as(at, "Z")
        assert_no_exception(at, "Save through two links")
        assert _store().is_symlink() and hop.is_symlink(), "a link on the way became a regular file"
        assert sorted(_read(target)) == ["X", "Y", "Z"], sorted(_read(target))
        assert _mode(target) == 0o444, f"the store's mode is now {oct(_mode(target))}"
        assert sorted(p.name for p in synced.iterdir()) == ["charts.json", "hop.json"], "a temp file was left"
        _save_as(at, "W")
        assert sorted(_read(target)) == ["W", "X", "Y", "Z"], "the second save did not reach the linked file"
    finally:
        target.chmod(0o644)


def test_two_windows_open_when_the_folder_comes_back_both_list_what_arrived(prefs_on):
    former = prefs_on / FORMER_NAME
    former.mkdir()
    (former / "saved_charts.json").write_text(json.dumps({"Old": PETOSKEY}))
    (prefs_on / "Zij").write_text("not a folder")
    a = _launch().run()
    b = _launch().run()
    assert any("cannot be kept" in t for t in _all_alerts(a)), "the premise: the folder cannot be made"
    (prefs_on / "Zij").unlink()
    b.run()
    assert_no_exception(b, "B's run after the folder is put right")
    assert "Old" in _picker(b).options, f"B's picker: {_picker(b).options}"
    a.run()
    assert_no_exception(a, "A's run after B moved the charts across")
    assert "Old" in _picker(a).options, f"A's picker: {_picker(a).options}"
    _save_as(b, "B1")
    _save_as(a, "A1")
    assert sorted(_read(prefs_on / "Zij" / "saved_charts.json")) == ["A1", "B1", "Old"]


def test_a_store_nested_past_the_parsers_depth_is_named_at_launch_and_not_again(scratch):
    _store().write_text(DEEP_JSON)
    at = make_app(date="1983-11-19", page="chart").run()
    assert_no_exception(at, "the launch")
    copies = _copies()
    assert len(copies) == 1 and copies[0].read_text() == DEEP_JSON, [p.name for p in copies]
    launch_copy = copies[0]
    said = [v for v in _sidebar_texts(at) if "A copy of the file was kept beside the saved charts" in v]
    assert len(said) == 1 and said[0].startswith("Saved charts could not be read."), said
    _save_as(at, "Z")
    assert_no_exception(at, "the first save")
    texts = _sidebar_texts(at)
    assert "Saved 'Z'." in texts, texts
    assert [v for v in texts if "could not be read" in v] == [], texts
    assert _copies() == [launch_copy], "a second copy of the same bytes"
    assert sorted(_read(_store())) == ["Z"]


def test_the_digest_kept_after_a_write_or_a_load_is_of_those_bytes(scratch):
    import engine
    sync_engine_to_environment()           # reloads in place: the store's path follows this test's folder
    assert engine.SAVED_CHARTS_PATH == _store(), "the premise: the engine writes this test's store"
    assert engine.write_saved_charts(XY) is True
    on_disk = hashlib.sha256(_store().read_bytes()).hexdigest()
    assert engine.saved_charts_digest(XY) == on_disk, "the digest a write leaves is not of the bytes it wrote"
    _store().write_bytes(b"\xef\xbb\xbf" + json.dumps(XY, indent=4).encode("utf-8"))
    assert engine.load_saved_charts() == XY
    assert engine.loaded_saved_charts_digest() == hashlib.sha256(_store().read_bytes()).hexdigest()


def test_a_field_repeated_inside_one_record_is_not_a_chart_named_twice(scratch):
    record = json.dumps(PETOSKEY)
    _store().write_text('{"X": ' + record[:-1] + ', "date_string": "1901-02-03"}, "Y": ' + record + "}")
    at = make_app(date="1983-11-19", page="chart").run()
    assert_no_exception(at, "the launch")
    assert sorted(_picker(at).options) == ["-- New Chart --", "X", "Y"], _picker(at).options
    assert _copies() == [], "a store with one record's field repeated was taken as malformed"
