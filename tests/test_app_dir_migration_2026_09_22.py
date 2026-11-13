"""The rename to Zij: a chart saved under the old name is not
left behind. The first run under the new name moves the whole folder
across, once, and only when the new one does not exist yet.

The move is made where the data folder is resolved: at the import of the
data layer (user_data.py), which the engine takes whole. A launch is a fresh
import of both; here the harness's own reload stands for it (conftest's
sync_engine_to_environment: the data layer, then the engine), and each test
looks at the folder as the import left it, before anything else asks for
it. The last test is the positive control: the engine reloaded alone
resolves nothing again and moves nothing, so the tests above fail if the
harness stops reloading the data layer."""
import json
import os
from pathlib import Path

from conftest import sync_engine_to_environment


def _reload(monkeypatch, base):
    monkeypatch.setenv("XDG_DATA_HOME", str(base))
    import engine
    sync_engine_to_environment()
    return engine


def test_the_old_folder_is_moved_across_on_the_first_run(monkeypatch, tmp_path):
    legacy = tmp_path / "TraditionalAstrologyEngine"
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps(
        {"Sample": {"date_string": "1977-12-16", "time_string": "10:08:00", "location_query": "Escanaba"}}))
    (legacy / "preferences.json").write_text(json.dumps({"_connection_rule": "Sahl"}))
    module = _reload(monkeypatch, tmp_path)
    moved = Path(module.DATA_DIR)
    assert moved == tmp_path / "Zij"
    assert not legacy.exists(), "the old folder is moved, not copied, so the two cannot drift"
    assert json.loads((moved / "saved_charts.json").read_text())["Sample"]["location_query"] == "Escanaba"
    assert json.loads((moved / "preferences.json").read_text())["_connection_rule"] == "Sahl"
    assert Path(module._user_data_dir()) == moved


def test_an_existing_new_folder_is_never_overwritten(monkeypatch, tmp_path):
    legacy = tmp_path / "TraditionalAstrologyEngine"
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"old": {}}))
    current = tmp_path / "Zij"
    current.mkdir()
    (current / "saved_charts.json").write_text(json.dumps({"new": {}}))
    module = _reload(monkeypatch, tmp_path)
    assert Path(module.DATA_DIR) == current
    assert list(json.loads((current / "saved_charts.json").read_text())) == ["new"]
    assert legacy.exists(), "nothing is moved when there is already a folder under the new name"
    assert Path(module._user_data_dir()) == current and legacy.exists()


def test_a_fresh_machine_just_gets_the_new_folder(monkeypatch, tmp_path):
    module = _reload(monkeypatch, tmp_path)
    assert Path(module.DATA_DIR) == tmp_path / "Zij" and (tmp_path / "Zij").is_dir()
    assert not (tmp_path / "TraditionalAstrologyEngine").exists()


def test_the_engine_reloaded_alone_moves_nothing(monkeypatch, tmp_path):
    """The positive control of the three above: the engine reloaded without
    the data layer (Streamlit's watcher, in development: an accepted
    difference) re-runs its star import against the data layer
    already loaded. The folder it holds is still the one before, and the
    folder under the former name is not moved; so a harness that stopped
    reloading the data layer would fail the tests above."""
    import importlib
    import engine
    sync_engine_to_environment()
    before, own = Path(engine.DATA_DIR), engine.UnresolvedResult
    legacy = tmp_path / "TraditionalAstrologyEngine"
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"Sample": {}}))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    importlib.reload(engine)
    assert engine.UnresolvedResult is not own, "the reload did not run"
    assert Path(engine.DATA_DIR) == before != tmp_path / "Zij"
    assert legacy.exists() and not (tmp_path / "Zij").exists(), "a reload of the engine alone moved the folder"
