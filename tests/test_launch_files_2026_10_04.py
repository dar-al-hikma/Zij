"""The launch's files after lane G2 of the re-pass of 2026-10-04 (L6R-N4,
L6R-N6), pinned where its blind check found the suite silent.

* A data folder that could not be made at launch and is put right while the
  app is open is made the way the launch makes it: the folder kept under the
  app's former name is moved across first, once, so its saved charts are in
  the store the next launch reads. (The check's probe: the retry made an
  empty folder, after which the move could never run, and the old charts
  dropped out of the app with no sentence.)
* A delete in one window forgets the last chart only while the preferences
  file still names the record deleted: a last chart another window has
  opened since stands. A window that deletes its own last chart forgets it.

The preferences file is live here (the harness switches it off elsewhere),
against a tmp_path per test.
"""
import json
import os
import sys
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

PETOSKEY = {"date_string": "1982-11-19", "time_string": "11:44:00", "time_standard": "LMT (Local Mean Time)",
            "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533}
FLORENCE = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
            "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
FORMER_NAME = "TraditionalAstrologyEngine"     # the folder's name before the app was renamed


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    return tmp_path


def _launch(page="chart"):
    """A session that seeds nothing, after the engine's import a launch
    makes (its paths and its data folder are read at import)."""
    from streamlit.testing.v1 import AppTest
    module = sys.modules.get("engine")
    if module is not None:
        module._harness_environment = None
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash(page)
    return at


def _folder_sentences(at):
    return [e.value for e in list(at.sidebar.warning) + list(at.sidebar.error) if "cannot be kept" in e.value]


def _prefs_file():
    return Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "preferences.json"


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _delete(at, name):
    _picker(at).select(name).run()
    [b for b in at.sidebar.button if b.label == "\U0001F5D1"][0].click().run()
    at.sidebar.button(key="_delete_confirm").click().run()
    assert_no_exception(at, f"delete {name}")


def test_a_folder_put_right_while_open_is_made_as_the_launch_makes_it(prefs_on):
    """A file where the folder should be (the trigger that fails for any
    account), the folder under the former name holding a chart beside it;
    the file is removed while the app is open, the session runs again, and
    the next launch opens with that chart in the picker."""
    former = prefs_on / FORMER_NAME
    former.mkdir()
    (former / "saved_charts.json").write_text(json.dumps({"Old": PETOSKEY}))
    (prefs_on / "Zij").write_text("not a folder")

    at = _launch().run()
    assert_no_exception(at, "the launch")
    assert _folder_sentences(at), "the premise: the launch says the folder cannot be made"

    (prefs_on / "Zij").unlink()
    at.run()
    assert_no_exception(at, "the run after the folder is put right")
    assert not _folder_sentences(at), "the sentence stands after the folder was put right"
    moved = prefs_on / "Zij" / "saved_charts.json"
    assert moved.is_file() and "Old" in json.loads(moved.read_text()), (
        f"the folder under the former name was not moved across: Zij holds "
        f"{sorted(p.name for p in (prefs_on / 'Zij').iterdir())}")

    again = _launch().run()
    assert_no_exception(again, "the next launch")
    assert "Old" in _picker(again).options, f"the next launch's picker: {_picker(again).options}"


def test_a_delete_forgets_the_last_chart_only_while_the_file_names_it(prefs_on):
    (prefs_on / "Zij").mkdir()
    (prefs_on / "Zij" / "saved_charts.json").write_text(json.dumps({"X": PETOSKEY, "D": FLORENCE}))
    a = make_app(date="1983-11-19", page="chart").run()
    b = make_app(date="1990-01-01", page="chart").run()
    _picker(a).select("D").run()
    _picker(b).select("X").run()
    assert json.loads(_prefs_file().read_text()).get("last_chart") == "X", "the premise: B opened X last"

    _delete(a, "D")
    assert json.loads(_prefs_file().read_text()).get("last_chart") == "X", (
        "A's delete of D forgot the last chart B had opened since")

    _delete(b, "X")
    assert "last_chart" not in json.loads(_prefs_file().read_text()), (
        "B's delete of its own last chart did not forget it")
