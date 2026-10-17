"""The rename to Zij (2026-09-22): a chart saved under the old name is not
left behind. The first run under the new name moves the whole folder
across, once, and only when the new one does not exist yet."""
import json
import os
from pathlib import Path


def _reload(monkeypatch, base):
    import importlib
    monkeypatch.setenv("XDG_DATA_HOME", str(base))
    import engine
    return importlib.reload(engine)


def test_the_old_folder_is_moved_across_on_the_first_run(monkeypatch, tmp_path):
    legacy = tmp_path / "TraditionalAstrologyEngine"
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps(
        {"Jason": {"date_string": "1982-11-19", "time_string": "11:44:00", "location_query": "Petoskey"}}))
    (legacy / "preferences.json").write_text(json.dumps({"_connection_rule": "Sahl"}))
    module = _reload(monkeypatch, tmp_path)
    moved = Path(module._user_data_dir())
    assert moved == tmp_path / "Zij"
    assert json.loads((moved / "saved_charts.json").read_text())["Jason"]["location_query"] == "Petoskey"
    assert json.loads((moved / "preferences.json").read_text())["_connection_rule"] == "Sahl"
    assert not legacy.exists(), "the old folder is moved, not copied, so the two cannot drift"


def test_an_existing_new_folder_is_never_overwritten(monkeypatch, tmp_path):
    legacy = tmp_path / "TraditionalAstrologyEngine"
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"old": {}}))
    current = tmp_path / "Zij"
    current.mkdir()
    (current / "saved_charts.json").write_text(json.dumps({"new": {}}))
    module = _reload(monkeypatch, tmp_path)
    assert Path(module._user_data_dir()) == current
    assert list(json.loads((current / "saved_charts.json").read_text())) == ["new"]
    assert legacy.exists(), "nothing is moved when there is already a folder under the new name"


def test_a_fresh_machine_just_gets_the_new_folder(monkeypatch, tmp_path):
    module = _reload(monkeypatch, tmp_path)
    assert Path(module._user_data_dir()) == tmp_path / "Zij"
    assert not (tmp_path / "TraditionalAstrologyEngine").exists()
