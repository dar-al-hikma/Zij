"""The sentence for a data folder this account cannot open, in the three
states it can be read in (the blind check of the KB lane, finding 2).

The folder sentence said "..., cannot be opened (Permission denied), so the
saved charts in it are not listed." in every state. That is false when the
folder is shut after this window has read the saved charts: the picker
beside the sentence lists them and opens them. It also speaks of saved
charts in a folder that holds none. Each test shuts the folder with a real
``chmod`` and asserts its premise (that this account cannot enter it), so
under a root account the premise fails rather than the test passing.
"""
import json
import os
import sys
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, assert_no_exception, sync_engine_to_environment

RECORD = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
          "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """The data folder under a disposable XDG directory, preferences live;
    opened again after the test whatever happens in it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    path = tmp_path / "Zij"
    path.mkdir()
    yield path
    path.chmod(0o755)


def _launch():
    """A session that seeds nothing, after the engine's import a launch makes."""
    from streamlit.testing.v1 import AppTest
    module = sys.modules.get("engine")
    if module is not None:
        module._harness_environment = None
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    return at


def _shut(path):
    path.chmod(0o000)
    assert not os.access(path, os.X_OK), "the premise: this account cannot enter the folder"


def _folder_sentences(at):
    """Every alert on the page that speaks of the data folder."""
    out = []
    for where in (at.sidebar, at.main):
        for kind in ("error", "warning"):
            out += [e.value for e in getattr(where, kind) if "their folder" in e.value]
    return out


def _listed(at):
    return [o for o in at.sidebar.selectbox(key="chart_picker").options if o != "-- New Chart --"]


def _press_save(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()


def test_a_folder_shut_after_the_charts_were_read_is_not_said_to_hide_the_charts_listed(folder):
    (folder / "saved_charts.json").write_text(json.dumps({"X": RECORD}))
    at = _launch().run()
    assert_no_exception(at, "the launch")
    assert _listed(at) == ["X"], f"the premise: the launch lists X, not {_listed(at)}"
    _shut(folder)
    at.run()
    assert_no_exception(at, "the run after the folder was shut")
    said = _folder_sentences(at)
    assert said, "the premise: the folder is said"
    assert _listed(at) == ["X"], f"the premise: the picker still lists X, not {_listed(at)}"
    _press_save(at, "S")
    assert_no_exception(at, "Save")
    said = _folder_sentences(at)
    assert len(said) >= 2, f"the premise: Save refused with the folder sentence: {said}"
    wrong = [s for s in said if "not listed" in s or "cannot be read" in s]
    assert not wrong, f"the picker lists X, and the page says the saved charts are not: {wrong}"


def test_a_folder_shut_at_launch_with_charts_in_it_says_why_none_is_listed(folder):
    (folder / "saved_charts.json").write_text(json.dumps({"X": RECORD}))
    _shut(folder)
    at = _launch().run()
    assert_no_exception(at, "the launch")
    assert _listed(at) == [], f"the premise: nothing can be listed, yet the picker lists {_listed(at)}"
    said = _folder_sentences(at)
    assert said, "the folder is not said"
    assert all("saved charts in it are not listed" in s for s in said), (
        f"the picker is empty and the page does not say why: {said}")


def test_a_folder_shut_at_launch_with_nothing_in_it_is_not_said_to_hold_charts(folder):
    _shut(folder)
    at = _launch().run()
    assert_no_exception(at, "the launch")
    said = _folder_sentences(at)
    assert said, "the folder is not said"
    presumed = [s for s in said if "the saved charts in it" in s]
    assert not presumed, f"the folder holds no saved chart, and the page speaks of the ones in it: {presumed}"
