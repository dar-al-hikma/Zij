"""B-06 of the third outside pass (ruling 146): a launch count no write can
carry is dropped on load.

``preferences.json`` holding ``{"_launches": 10**4300 - 1}`` is read by
``json.loads`` (4300 digits is the limit) and was kept by the loader; the
launch added one, and ``json.dumps`` refused the 4301-digit result
(``ValueError``, uncaught), so the app stopped before any page, on every
launch. Now the loader keeps a count only below 10**16, the bound a record's
number has, so the entry is dropped and the count starts again from its
default; and ``write_preferences`` refuses, as for an ``OSError``, a write
``json.dumps`` cannot make.
"""
import json
import os
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from conftest import APP_PATH, sync_engine_to_environment


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    """A disposable XDG directory with the preferences file live."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    return tmp_path


def _file():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d / "preferences.json"


def _launch():
    module = sys.modules.get("engine")
    if module is not None:
        module._harness_environment = None
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.session_state["manual_coords_key"] = True
    at.session_state["manual_lat_key"] = 43.7792
    at.session_state["manual_lon_key"] = 11.2463
    at.session_state["date_input_key"] = "1240-05-23"
    at.session_state["time_input_key"] = "14:30:00"
    return at.run()


def _count():
    return json.loads(_file().read_text()).get("_launches")


def _opens(at):
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Chart" in [h.value for h in at.header]


def _seed(n):
    _file().write_text('{"_launches": %d}' % n)


def test_a_count_at_the_digit_limit_cannot_stop_the_launch(prefs_on):
    _seed(10 ** 4300 - 1)
    _opens(_launch())
    assert _count() == 1                       # dropped, started again from its default
    _opens(_launch())                          # a second launch
    assert _count() == 2


def test_the_count_below_the_bound_increments(prefs_on):
    _seed(10 ** 16 - 1)
    at = _launch()
    _opens(at)
    assert at.session_state["_launches"] == 10 ** 16      # the launch in hand counts it
    # A later write in the same launch re-reads the file as a load does, and
    # a load no longer keeps 10**16: the file ends without a count, and the
    # next launch counts 1.
    assert _count() is None
    again = _launch()
    _opens(again)
    assert again.session_state["_launches"] == 1


def test_the_count_at_the_bound_is_dropped(prefs_on):
    _seed(10 ** 16)
    at = _launch()
    _opens(at)
    assert at.session_state["_launches"] == 1
    assert _count() == 1


def test_an_ordinary_count_increments(prefs_on):
    _seed(5)
    _opens(_launch())
    assert _count() == 6


def test_a_boolean_count_is_dropped(prefs_on):
    _file().write_text('{"_launches": true}')
    at = _launch()
    _opens(at)
    assert at.session_state["_launches"] == 1          # not True + 1
    assert _count() == 1


def test_the_validator_bound():
    import engine
    assert engine.preference_is_valid("_launches", 10 ** 16 - 1)
    assert not engine.preference_is_valid("_launches", 10 ** 16)
    assert not engine.preference_is_valid("_launches", 10 ** 4300 - 1)
    assert not engine.preference_is_valid("_launches", True)


def test_a_write_json_cannot_make_is_refused_and_leaves_the_file(prefs_on):
    import engine
    sync_engine_to_environment()
    _file().write_text('{"_launches": 5}')
    assert engine.write_preferences({"_launches": 10 ** 4300}) is False    # 4301 digits
    assert _file().read_bytes() == b'{"_launches": 5}'
