"""The saved-charts store's write, across two and three sessions on one file.

Beside the re-pass's three findings on the write (L6R-N1, L6R-N2, L6R-N7 in
``test_repass_l6_2026_10_04.py``): whatever stands in the store's place when
a session writes, the write replaces no bytes the session could neither read
nor copy aside, and every refusal says what happened and where any copy went.
The unreadable file is simulated as N1's test simulates it (the reads of that
one path raise what mode 000 raises), so nothing here depends on the user
who runs it.
"""
import json
import os
from datetime import time
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app
from test_repass_l6_2026_10_04 import (PETOSKEY, _delete, _picker, _read, _save_as, _sidebar_texts, _store,
                                       scratch)

XY = {"X": PETOSKEY, "Y": {**PETOSKEY, "date_string": "1990-01-01"}}
REFUSED = "could not be read, and no copy of the file could be made, so nothing was written"


def _deny_reads(monkeypatch, target):
    """The reads the engine makes of `target` raise PermissionError: through
    Path, and through os.open, the way the engine reads the store since SB-05
    (ruling 157: _read_regular_file)."""
    real_bytes, real_text, real_open = Path.read_bytes, Path.read_text, os.open

    def denied(real):
        def read(self, *args, **kwargs):
            if self == target:
                raise PermissionError(13, "Permission denied", str(self))
            return real(self, *args, **kwargs)
        return read

    def denied_open(path, flags, *args, **kwargs):
        if Path(path) == target:
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", denied(real_bytes))
    monkeypatch.setattr(Path, "read_text", denied(real_text))
    monkeypatch.setattr(os, "open", denied_open)
    return lambda: (monkeypatch.setattr(Path, "read_bytes", real_bytes),
                    monkeypatch.setattr(Path, "read_text", real_text),
                    monkeypatch.setattr(os, "open", real_open))


def _copies():
    return sorted(_store().parent.glob("saved_charts.json.unreadable-*"))


def test_three_sessions_write_nothing_over_an_unreadable_store_and_merge_once_it_reads(scratch, monkeypatch):
    original = json.dumps(XY).encode("utf-8")
    _store().write_bytes(original)
    a = make_app(date="1983-11-19", page="chart").run()
    restore = _deny_reads(monkeypatch, _store())
    b = make_app(date="1990-01-01", page="chart").run()
    assert any("could not be read, and no copy" in v for v in _sidebar_texts(b)), "the premise: B's launch says so"
    for at, name in ((b, "From B"), (a, "From A")):
        _save_as(at, name)
        assert_no_exception(at, name)
        texts = _sidebar_texts(at)
        assert any(REFUSED in v for v in texts), (name, texts)
        assert [v for v in texts if f"Saved '{name}'" in v] == [], (name, texts)
    _delete(a, "X")
    assert any(REFUSED in v for v in _sidebar_texts(a)), "the delete is refused as the save is"
    assert set(_picker(a).options) == {"-- New Chart --", "X", "Y"}, "A keeps its own list"
    restore()
    assert _store().read_bytes() == original, "a refused write moved the store"
    assert _copies() == [], "nothing was copied: there were no bytes to copy"
    c = make_app(date="1995-01-01", page="chart").run()
    _save_as(c, "From C")
    _save_as(b, "From B")
    _save_as(a, "From A")
    assert set(_read(_store())) == {"X", "Y", "From A", "From B", "From C"}


def test_a_directory_in_the_stores_place_refuses_the_save_with_its_sentence(scratch):
    _store().mkdir(parents=True)
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, "Z")
    assert_no_exception(at)
    assert any(REFUSED in v for v in _sidebar_texts(at)), _sidebar_texts(at)
    assert _store().is_dir() and sorted(p.name for p in _store().parent.iterdir()) == ["saved_charts.json"]


def test_a_broken_store_whose_bytes_cannot_be_copied_is_not_written_over(scratch, monkeypatch):
    import engine as engine_module

    _store().write_text(json.dumps(XY))
    at = make_app(date="1240-05-23", page="chart").run()
    broken = json.dumps(XY).rstrip("}") + ",}"
    _store().write_text(broken)
    monkeypatch.setattr(engine_module, "_preserve_unreadable_store", lambda path, data=None: None)
    _save_as(at, "Z")
    assert_no_exception(at)
    assert any(REFUSED in v for v in _sidebar_texts(at)), _sidebar_texts(at)
    assert _store().read_text() == broken


def test_a_store_broken_under_two_sessions_keeps_both_and_names_the_copy(scratch):
    _store().write_text(json.dumps(XY))
    a = make_app(date="1983-11-19", page="chart").run()
    c = make_app(date="1990-01-01", page="chart").run()
    broken = _store().read_text().rstrip().rstrip("}") + ",}"
    _store().write_text(broken)
    _save_as(a, "Z")
    assert_no_exception(a)
    copies = _copies()
    assert len(copies) == 1 and copies[0].read_text() == broken, [p.name for p in copies]
    told = [v for v in _sidebar_texts(a) if "could not be read" in v]
    assert len(told) == 1 and "A copy of the file was kept beside the saved charts" in told[0], told
    assert set(_read(_store())) == {"X", "Y", "Z"}
    _save_as(c, "W")
    assert set(_read(_store())) == {"W", "X", "Y", "Z"}, "the stale window merges onto the kept store"
    # Broken again: a delete keeps the rest and names its own copy.
    _store().write_text(broken + " ")
    _delete(a, "X")
    assert_no_exception(a)
    assert set(_read(_store())) == {"Y", "Z"}
    assert len(_copies()) == 2
    assert any("A copy of the file was kept beside the saved charts" in v for v in _sidebar_texts(a)), _sidebar_texts(a)


def test_a_stale_unchanged_save_of_a_deleted_record_names_the_deletion_and_writes_nothing(scratch):
    _store().write_text(json.dumps(XY))
    a = make_app(page="chart").run()
    _picker(a).select("X").run()
    b = make_app(page="chart").run()
    _delete(b, "X")
    _save_as(a, "X")
    assert_no_exception(a)
    said = [v for v in _sidebar_texts(a) if "'X' was deleted by another window" in v]
    assert said and not any("already saved as it is" in v for v in _sidebar_texts(a)), _sidebar_texts(a)
    assert set(_read(_store())) == {"Y"}
    _save_as(a, "X")
    assert set(_read(_store())) == {"X", "Y"}


def test_three_windows_a_stale_delete_does_not_remove_a_replaced_record(scratch):
    _store().write_text(json.dumps({"X": PETOSKEY}))
    a = make_app(page="chart").run()
    _picker(a).select("X").run()
    b = make_app(page="chart").run()
    _picker(b).select("X").run()
    c = make_app(page="chart").run()
    _picker(c).select("X").run()
    b.session_state["time_input_key"] = time(9, 0)
    b.run()
    _save_as(b, "X")
    b.sidebar.button(key="_replace_now").click().run()
    _delete(c, "X")
    assert_no_exception(c)
    assert any("'X' was replaced by another window" in v for v in _sidebar_texts(c)), _sidebar_texts(c)
    assert _read(_store())["X"]["time_string"] == "09:00:00"
    _save_as(a, "X")
    assert any("'X' was replaced by another window" in v for v in _sidebar_texts(a)), _sidebar_texts(a)
    _save_as(a, "X")
    assert any("'X' exists. Replace it?" in v for v in _sidebar_texts(a)), _sidebar_texts(a)
    a.sidebar.button(key="_replace_now").click().run()
    assert _read(_store())["X"]["time_string"] == "11:44:00"
